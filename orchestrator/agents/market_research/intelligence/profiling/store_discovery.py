"""
Store discovery: which online stores matter for this category in this country.

A fixed marketplace list only covers the countries someone wrote down, and even there misses the
category specialists. So for the merchant's market this step searches for the country's popular
shopping sites for the category, and a model picks the stores out of those results. A store is
kept only when its host appears in a result URL or snippet: the model chooses among stores the
search actually returned and cannot add one from memory.

The known seed list (listing_intel.MARKETPLACES / CATEGORY_STORES) is merged in, so a failed or
thin discovery never leaves a known market with fewer stores than before. With no target country,
global marketplaces are used. Results are cached per (country, category) for the process.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.agents.market_research.ingestion.search_client import (
    SearchQuery,
    TavilySearchResult,
    market_for,
)
from orchestrator.agents.market_research.ingestion.source_types import host_of

logger = logging.getLogger(__name__)

SearchFn = Callable[[list[SearchQuery]], Awaitable[list[TavilySearchResult]]]

VECTOR = "store_discovery"
MAX_DISCOVERED = 6

#: Used when the merchant names no country (or "global").
GLOBAL_STORES: list[tuple[str, str]] = [
    ("amazon.com", "marketplace"), ("ebay.com", "marketplace"), ("walmart.com", "marketplace"),
    ("aliexpress.com", "marketplace"), ("etsy.com", "marketplace"),
]

#: ISO code -> local currency, for markets the seed list does not cover.
CURRENCY_BY_ISO = {
    "IN": "INR", "US": "USD", "GB": "GBP", "AE": "AED", "AU": "AUD", "CA": "CAD", "DE": "EUR", "FR": "EUR",
    "ES": "EUR", "IT": "EUR", "NL": "EUR", "SG": "SGD", "JP": "JPY", "BR": "BRL", "ZA": "ZAR", "NZ": "NZD",
}

# Hosts that show up in "best shopping sites" articles but are not stores.
_NOT_STORES = re.compile(
    r"(facebook|instagram|youtube|twitter|x\.com|linkedin|reddit|quora|wikipedia|statista|similarweb|"
    r"medium|blogspot|wordpress|forbes|businessinsider|techcrunch|economictimes|news|google\.|bing\.|"
    r"pinterest|tiktok|trustpilot|semrush|ahrefs)",
    re.I,
)

PROMPT = """\
From the search results, list the online stores where shoppers in {country} buy {category}: \
the big marketplaces first, then stores that specialise in this category, then quick-commerce \
apps if the category sells there. Use only stores named in the results. For each give its \
website host exactly as it appears (e.g. "noon.com", "bol.com") and type: marketplace, d2c, \
quick_commerce or social_shop. At most {limit}. Skip news sites, blogs and directories.
"""


class _Store(BaseModel):
    host: str
    type: str = "marketplace"


class _Stores(BaseModel):
    stores: list[_Store] = Field(default_factory=list)


_cache: dict[tuple[str, str], list[tuple[str, str]]] = {}


def discovery_queries(country: str, category: str) -> list[SearchQuery]:
    return [
        SearchQuery(vector=VECTOR, query=f"best online shopping sites in {country} for {category}", search_depth="basic"),
        SearchQuery(vector=VECTOR, query=f"most popular e-commerce marketplaces {country}", search_depth="basic"),
        SearchQuery(vector=VECTOR, query=f"where to buy {category} online {country}", search_depth="basic"),
    ]


def _norm_host(raw: str) -> str:
    raw = raw.strip().lower()
    host = host_of(raw) if "://" in raw else raw.split("/")[0]
    return host.removeprefix("www.")


def ground_stores(found: _Stores, results: list[TavilySearchResult]) -> list[tuple[str, str]]:
    """Keeps stores whose host appears in a result URL or snippet; drops non-stores."""
    seen_text = " ".join(f"{r.url} {r.title} {r.snippet}" for r in results).lower()
    out: dict[str, str] = {}
    for s in found.stores:
        host = _norm_host(s.host)
        if not host or "." not in host or _NOT_STORES.search(host):
            continue
        brand = host.split(".")[0]
        # The host itself, or its brand name as a word, must be in what the search returned.
        if host not in seen_text and not re.search(rf"\b{re.escape(brand)}\b", seen_text):
            continue
        kind = s.type if s.type in ("marketplace", "d2c", "quick_commerce", "social_shop") else "marketplace"
        out.setdefault(host, kind)
    return list(out.items())[:MAX_DISCOVERED]


async def discover_stores(
    merchant_context: dict[str, Any], search_fn: SearchFn, llm: Any
) -> tuple[list[tuple[str, str]], str]:
    """(stores, note). Empty list when there is no country, no model or nothing grounded."""
    market = market_for(merchant_context)
    if market is None or llm is None:
        return [], ""
    iso, country, _ = market
    category = str(merchant_context.get("category") or merchant_context.get("product_name") or "products").strip()
    key = (iso, category.lower())
    if key in _cache:
        return _cache[key], f"cached for {country}"
    try:
        results = [r for r in await search_fn(discovery_queries(country, category)) if r.url]
    except Exception as exc:
        logger.warning("Store discovery search failed: %s", exc)
        return [], f"search failed ({type(exc).__name__})"
    if not results:
        return [], "search returned nothing"
    try:
        found = await llm.with_structured_output(_Stores).ainvoke([
            {"role": "system", "content": PROMPT.format(country=country, category=category, limit=MAX_DISCOVERED)},
            {"role": "user", "content": json.dumps(
                [{"title": r.title, "url": r.url, "snippet": r.snippet[:400]} for r in results[:20]],
                ensure_ascii=False)},
        ])
        if not isinstance(found, _Stores):
            found = _Stores.model_validate(found)
    except Exception as exc:
        logger.warning("Store discovery model call failed: %s", exc)
        return [], f"model failed ({type(exc).__name__})"
    stores = ground_stores(found, results)
    if stores:
        _cache[key] = stores
    return stores, f"{len(stores)} found for {country}"


def merge_stores(*lists: list[tuple[str, str]], cap: int) -> list[tuple[str, str]]:
    out: dict[str, str] = {}
    for stores in lists:
        for host, kind in stores:
            out.setdefault(host, kind)
    return list(out.items())[:cap]
