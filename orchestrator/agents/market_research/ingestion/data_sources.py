"""
Structured data sources: prices, price history and search volume as data, not scraped pages.

  - SerpApi Google Shopping: one query returns offers from every store in a country (store,
    price, old price, rating, reviews, image, link). Fills stores that block scrapers.
  - Keepa: Amazon price history (90-day average / low / high) and sales rank for an ASIN.
  - DataForSEO: Google Ads monthly search volume, CPC and competition for keywords.

Each is optional and used only when its key is set; every call either returns real data or
raises DataSourceError, and callers record the source as unavailable rather than guessing.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from orchestrator.core.config import get_settings

logger = logging.getLogger(__name__)


class DataSourceError(Exception):
    pass


# ── SerpApi: Google Shopping ────────────────────────────────────────────────────

async def google_shopping(query: str, country_iso: str | None, timeout: float = 30.0) -> list[dict[str, Any]]:
    """Offers for `query` in a country: [{title, store, price, old_price, rating, reviews, link, image}]."""
    key = get_settings().serpapi_api_key
    if not key:
        raise DataSourceError("SERPAPI_API_KEY not set")
    params = {"engine": "google_shopping", "q": query, "hl": "en", "api_key": key}
    if country_iso:
        params["gl"] = country_iso.lower()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get("https://serpapi.com/search.json", params=params)
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataSourceError(f"SerpApi: {type(exc).__name__}") from exc
    if r.status_code != 200 or data.get("error"):
        raise DataSourceError(f"SerpApi: {data.get('error') or r.status_code}")
    out = []
    for row in data.get("shopping_results") or []:
        price = row.get("extracted_price")
        if not isinstance(price, (int, float)) or price <= 0:
            continue
        old = row.get("extracted_old_price")
        out.append({
            "title": row.get("title") or "",
            "store": row.get("source") or "",
            "price": float(price),
            "old_price": float(old) if isinstance(old, (int, float)) and old > price else None,
            "rating": row.get("rating"),
            "reviews": row.get("reviews"),
            "link": row.get("product_link") or row.get("link") or "",
            "image": row.get("thumbnail"),
            "price_text": row.get("price") or "",
        })
    return out


# ── Keepa: Amazon price history and sales rank ──────────────────────────────────

# Keepa domain ids per Amazon host.
KEEPA_DOMAIN = {"amazon.com": 1, "amazon.co.uk": 2, "amazon.de": 3, "amazon.fr": 4, "amazon.co.jp": 5,
                "amazon.ca": 6, "amazon.it": 8, "amazon.es": 9, "amazon.in": 10, "amazon.com.mx": 11,
                "amazon.com.br": 12}
_ASIN = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")


def asin_of(url: str) -> str | None:
    m = _ASIN.search(url or "")
    return m.group(1) if m else None


def _keepa_price(v: Any) -> float | None:
    # Keepa stores prices as integers in the smallest unit; -1 means "no offer".
    return round(v / 100, 2) if isinstance(v, int) and v > 0 else None


async def keepa_history(asins: list[str], amazon_host: str, timeout: float = 30.0) -> dict[str, dict[str, Any]]:
    """{asin: {current, avg_90d, min_90d, max_90d, sales_rank, sales_rank_drops_30d}} for up to 20 ASINs."""
    key = get_settings().keepa_api_key
    if not key:
        raise DataSourceError("KEEPA_API_KEY not set")
    domain = KEEPA_DOMAIN.get(amazon_host.removeprefix("www."))
    if domain is None or not asins:
        return {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get("https://api.keepa.com/product", params={
                "key": key, "domain": domain, "asin": ",".join(asins[:20]), "stats": 90})
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataSourceError(f"Keepa: {type(exc).__name__}") from exc
    if r.status_code != 200 or data.get("error"):
        raise DataSourceError(f"Keepa: {(data.get('error') or {}).get('message') or r.status_code}")
    out: dict[str, dict[str, Any]] = {}
    for p in data.get("products") or []:
        st = p.get("stats") or {}

        def pick(series: Any, idx: int) -> Any:
            # Index 0 = Amazon's own offer, 1 = new third-party offers; prefer Amazon's.
            if not isinstance(series, list):
                return None
            for i in (0, 1) if idx == 0 else (idx,):
                v = series[i] if i < len(series) else None
                v = v[1] if isinstance(v, list) and len(v) == 2 else v
                if isinstance(v, int) and v > 0:
                    return v
            return None

        rank = (st.get("current") or [None] * 4)[3] if isinstance(st.get("current"), list) and len(st["current"]) > 3 else None
        out[p.get("asin")] = {
            "current": _keepa_price(pick(st.get("current"), 0)),
            "avg_90d": _keepa_price(pick(st.get("avg90"), 0)),
            "min_90d": _keepa_price(pick(st.get("min"), 0)),
            "max_90d": _keepa_price(pick(st.get("max"), 0)),
            "sales_rank": rank if isinstance(rank, int) and rank > 0 else None,
            "sales_rank_drops_30d": st.get("salesRankDrops30") if isinstance(st.get("salesRankDrops30"), int) else None,
        }
    return out


# ── DataForSEO: Google Ads search volume ────────────────────────────────────────

async def search_volume(keywords: list[str], location_name: str | None, timeout: float = 60.0) -> list[dict[str, Any]]:
    """[{keyword, search_volume, cpc, competition, monthly: [(YYYY-MM, volume)]}] from Google Ads data."""
    s = get_settings()
    if not (s.dataforseo_login and s.dataforseo_password):
        raise DataSourceError("DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not set")
    task: dict[str, Any] = {"keywords": keywords[:20], "language_code": "en"}
    if location_name:
        task["location_name"] = location_name
    try:
        async with httpx.AsyncClient(timeout=timeout, auth=(s.dataforseo_login, s.dataforseo_password)) as client:
            r = await client.post("https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live", json=[task])
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataSourceError(f"DataForSEO: {type(exc).__name__}") from exc
    tasks = data.get("tasks") or []
    if r.status_code != 200 or not tasks or tasks[0].get("status_code") != 20000:
        msg = tasks[0].get("status_message") if tasks else data.get("status_message")
        raise DataSourceError(f"DataForSEO: {msg or r.status_code}")
    out = []
    for row in tasks[0].get("result") or []:
        monthly = sorted(
            (f"{m['year']}-{m['month']:02d}", m.get("search_volume") or 0)
            for m in row.get("monthly_searches") or [] if m.get("year") and m.get("month")
        )
        out.append({
            "keyword": row.get("keyword"),
            "search_volume": row.get("search_volume"),
            "cpc": row.get("cpc"),
            "competition": row.get("competition"),
            "monthly": monthly,
        })
    return out
