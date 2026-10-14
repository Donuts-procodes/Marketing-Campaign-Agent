"""
AI web-search price lookup: the last resort when a rival's listing pages are blocked or render
their price with JavaScript and the search excerpts carry no price either.

A web-search model (OpenAI Responses API, `web_search` tool) is asked for the rival's current
price on the merchant's market for one product type. Nothing it says is taken on trust:
- every listing must name a URL the model actually cited (a `url_citation` annotation),
- the price must appear in the answer text next to the currency,
- the listing is labelled `source="ai_search"` so the dashboard shows it as cited, not page-read.
A listing that fails any check is dropped; an empty answer stays empty.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from orchestrator.agents.market_research.ingestion.source_types import host_of
from orchestrator.core.clock import today as clock_today
from orchestrator.schemas.research import ChannelListing, CompetitorProfile

logger = logging.getLogger(__name__)

PROMPT = """\
Find the current selling price of {brand}'s {what} in {market}{sites}.
Search the web. Report only prices you saw on a product or listing page, for products of this \
brand. Give up to 3 listings, cheapest to dearest.

Answer with JSON only, no prose:
{{"listings": [{{"product": "<name as listed>", "selling_price": <number>, "mrp": <number or null>, \
"currency": "<ISO code>", "url": "<the page you read it on>"}}]}}
Return {{"listings": []}} when you found no price. Never estimate."""


def _json_block(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def _cited_urls(response: Any) -> set[str]:
    urls: set[str] = set()
    for item in getattr(response, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            for ann in getattr(part, "annotations", None) or []:
                if getattr(ann, "type", "") == "url_citation" and getattr(ann, "url", None):
                    urls.add(ann.url.split("?utm_")[0])
    return urls


def _price_in_text(value: float, text: str) -> bool:
    plain = f"{value:.0f}"
    return any(v in text for v in (plain, f"{value:,.0f}", f"{value:,.2f}", f"{value:.2f}"))


def parse_listings(
    response: Any, comp: CompetitorProfile, currency: str | None, site_types: dict[str, str]
) -> list[ChannelListing]:
    """The answer's listings that pass the citation, price-in-text and brand checks."""
    text = getattr(response, "output_text", "") or ""
    cited = _cited_urls(response)
    cited_hosts = {host_of(u) for u in cited}
    out: list[ChannelListing] = []
    for row in (_json_block(text).get("listings") or [])[:3]:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        price = row.get("selling_price")
        if not url or not isinstance(price, (int, float)) or price <= 0:
            continue
        host = host_of(url)
        # The URL must be one the search actually returned, not one the model wrote from memory.
        if url.split("?utm_")[0] not in cited and host not in cited_hosts:
            continue
        if not _price_in_text(float(price), text):
            continue
        row_currency = str(row.get("currency") or currency or "").upper()[:3] or None
        if currency and row_currency and row_currency != currency:
            continue  # a USD price on a ₹ market is a different store
        mrp = row.get("mrp") if isinstance(row.get("mrp"), (int, float)) and row["mrp"] > price else None
        site = next((h for h in site_types if host == h or host.endswith("." + h)), host)
        out.append(ChannelListing(
            competitor=comp.brand_name,
            product=str(row.get("product") or comp.product_name or "")[:120],
            site=site,
            site_type=site_types.get(site, "d2c"),  # type: ignore[arg-type]
            url=url,
            currency=row_currency,
            mrp=float(mrp) if mrp else None,
            selling_price=float(price),
            discount_pct=round((1 - price / mrp) * 100, 1) if mrp else None,
            observed_at=clock_today().isoformat(),
            evidence=f"AI web search, cited {url}",
            source="ai_search",
        ))
    return out


def make_ai_price_search(api_key: str, model: str, market: str | None, site_types: dict[str, str]):
    """An `AISearchFn` for collect_channel_listings, bound to one OpenAI key and model."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)

    async def search(
        comp: CompetitorProfile, product: dict[str, Any] | None, currency: str | None, hosts: list[str]
    ) -> list[ChannelListing]:
        what = str((product or {}).get("category") or (product or {}).get("name") or comp.product_name or "products")
        sites = f" (for example on {', '.join(hosts[:4])} or the brand's own store)" if hosts else ""
        prompt = PROMPT.format(brand=comp.brand_name, what=what, market=market or "their main market", sites=sites)
        response = await client.responses.create(model=model, tools=[{"type": "web_search"}], input=prompt)
        listings = parse_listings(response, comp, currency, site_types)
        logger.info("AI price search %s / %s: %d cited listing(s)", comp.brand_name, what, len(listings))
        return listings

    return search
