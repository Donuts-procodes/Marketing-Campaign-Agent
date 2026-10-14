"""
Deep search: live page extraction via CrawlAPI, with Tavily Extract as the fallback.

Every page returned here was fetched from the live web; nothing is synthesized. A URL that
neither provider can fetch is dropped rather than filled in.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urlparse
from typing import Any

from orchestrator.agents.market_research.ingestion.web_crawler import CrawlAPIClient
from orchestrator.agents.market_research.ingestion.search_client import current_search_market, TavilySearchResult
from orchestrator.agents.market_research.ingestion.url_guard import filter_crawl_urls
from orchestrator.core.config import get_settings

logger = logging.getLogger(__name__)

# Tavily Extract accepts at most 20 URLs per call.
_TAVILY_EXTRACT_BATCH = 20
# Pages shorter than this are usually bot walls or empty shells, not content.
_MIN_PAGE_WORDS = 30


@dataclass
class ExtractedPage:
    """Clean markdown content scraped from a single URL."""

    url: str
    markdown: str
    token_estimate: int = 0
    provider: str = "crawlapi"


def _default_tavily_client() -> Any:
    try:
        from tavily import AsyncTavilyClient

        return AsyncTavilyClient(api_key=get_settings().tavily_api_key)
    except ImportError:
        logger.error("tavily-python not installed — Tavily Extract fallback unavailable")
        return None


# Stores that render price and stock with JavaScript: fetched through a headless browser.
_JS_COMMERCE = (
    "amazon.", "flipkart.com", "myntra.com", "ajio.com", "tatacliq.com", "nykaa.com", "nykaafashion.com",
    "meesho.com", "snapdeal.com", "jiomart.com", "blinkit.com", "zeptonow.com", "swiggy.com", "bigbasket.com",
    "croma.com", "reliancedigital.in", "firstcry.com", "purplle.com", "walmart.com", "target.com", "bestbuy.com",
    "ebay.", "etsy.com", "asos.com", "noon.com", "namshi.com", "shopee.", "lazada.", "mercadolibre.",
)


def needs_rendering(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(h in host for h in _JS_COMMERCE)


async def _crawlapi_pages(
    urls: list[str], crawl_client: Any, max_concurrent: int
) -> tuple[list[ExtractedPage], list[str]]:
    """Fetches URLs via CrawlAPI; returns (pages, urls that failed)."""
    semaphore = asyncio.Semaphore(max_concurrent)
    provider = getattr(crawl_client, "provider", None)
    label = provider if isinstance(provider, str) else "crawlapi"
    # The client's own timeout is sized for JS-rendered ad libraries; one dead competitor page
    # waiting that long held a whole round's crawl for ~90s.
    page_timeout = get_settings().crawl_page_timeout_seconds

    market = current_search_market()
    country = market[0].lower() if market else None

    async def _fetch_one(url: str) -> ExtractedPage | None:
        js = needs_rendering(url)
        options: dict[str, Any] = {"output_format": "md"}
        if js:
            options["javascript"] = True
        if country:
            # Marketplaces show a bot wall, another region's store or no price to foreign IPs.
            options["country"] = country
        async with semaphore:
            try:
                try:
                    call = crawl_client.fetch(url, **options)
                except TypeError:
                    call = crawl_client.fetch(url, output_format="md")  # a client without those options
                # A rendered page takes a browser run, so it gets longer than a plain fetch.
                response = await asyncio.wait_for(call, timeout=page_timeout * (2.5 if js else 1))
            except Exception as exc:
                logger.warning("CrawlAPI fetch failed for %s: %s", url, exc)
                return None
        md = response.get("body", "") if isinstance(response, dict) else ""
        if len(md.split()) < _MIN_PAGE_WORDS:
            return None
        return ExtractedPage(url=url, markdown=md, token_estimate=len(md.split()), provider=label)

    results = await asyncio.gather(*[_fetch_one(u) for u in urls])
    pages = [p for p in results if p is not None]
    fetched = {p.url for p in pages}
    return pages, [u for u in urls if u not in fetched]


async def _tavily_extract_pages(urls: list[str], tavily_client: Any) -> list[ExtractedPage]:
    """Fetches URLs via Tavily Extract (advanced depth) in batches of 20."""
    pages: list[ExtractedPage] = []
    for start in range(0, len(urls), _TAVILY_EXTRACT_BATCH):
        batch = urls[start : start + _TAVILY_EXTRACT_BATCH]
        try:
            response = await tavily_client.extract(urls=batch, extract_depth="advanced", format="markdown")
        except Exception as exc:
            logger.warning("Tavily Extract failed for %d URL(s): %s", len(batch), exc)
            continue
        for item in response.get("results", []) if isinstance(response, dict) else []:
            md = item.get("raw_content") or ""
            if len(md.split()) < _MIN_PAGE_WORDS:
                continue
            pages.append(
                ExtractedPage(
                    url=item.get("url", ""),
                    markdown=md,
                    token_estimate=len(md.split()),
                    provider="tavily_extract",
                )
            )
    return pages


async def extract_pages(
    urls: list[str],
    crawl_client: Any = None,
    tavily_client: Any = None,
    max_concurrent: int | None = None,
) -> list[ExtractedPage]:
    """
    Deep-scrapes target URLs into markdown: CrawlAPI first, then Tavily Extract for any URL
    CrawlAPI could not fetch (or for all URLs when CrawlAPI is not configured).
    """
    unique_urls = list(dict.fromkeys(u for u in urls if u))
    if not unique_urls:
        return []

    if max_concurrent is None:
        max_concurrent = get_settings().crawl_max_concurrent
    max_concurrent = max(max_concurrent, 1)

    if crawl_client is None:
        crawl_client = CrawlAPIClient()

    pages: list[ExtractedPage] = []
    remaining = unique_urls
    if getattr(crawl_client, "configured", True):
        pages, remaining = await _crawlapi_pages(unique_urls, crawl_client, max_concurrent)
    else:
        logger.info("CrawlAPI token not configured — deep search uses Tavily Extract only")

    if remaining:
        if tavily_client is None:
            tavily_client = _default_tavily_client()
        if tavily_client is not None:
            pages.extend(await _tavily_extract_pages(remaining, tavily_client))

    return pages


# Paths worth guessing when search never surfaced a competitor's commercial pages.
# Pricing and products lead so P_pricing and core claims get populated across both SaaS and physical e-commerce.
_GUESSED_PATHS = ("/pricing", "/plans", "/products", "/shop", "/product", "/features")

# Path segments that mark a page as commercially informative rather than incidental.
_COMMERCIAL_SEGMENTS = (
    "", "pricing", "plans", "price", "products", "shop", "product", "features", "solutions", "compare", "services",
)


# Hosts that list or host many businesses: never a competitor's own domain, so guessing
# /pricing on them only buys a 404.
_NOT_OWN_DOMAIN = (
    "clutch.co", "goodfirms.co", "designrush.com", "upwork.com", "g2.com", "capterra.com",
    "trustpilot.com", "yelp.com", "reddit.com", "quora.com", "linkedin.com", "crunchbase.com",
    "glassdoor.com", "indeed.com", "facebook.com", "instagram.com", "youtube.com", "x.com",
    "twitter.com", "medium.com", "site123.me", "wixsite.com", "wordpress.com", "blogspot.com",
    "github.io", "jobicy.com", "justdial.com", "indiamart.com", "sulekha.com",
)
# Guesses cost a full crawl each; most 404. Two is enough to catch /pricing and /plans.
_MAX_GUESSES = 2


def _canonical(url: str) -> str:
    """Drops query and fragment: ?ref=, ?source=, utm_ variants are the same page."""
    p = urlparse(url)
    return f"{p.scheme or 'https'}://{p.netloc}{p.path or '/'}"


def _is_own_domain(host: str) -> bool:
    return bool(host) and not any(host == d or host.endswith("." + d) for d in _NOT_OWN_DOMAIN)


def extract_competitor_target_urls(
    competitors: list[Any],
    search_results: list[TavilySearchResult],
    pages_per_competitor: int = 4,
    max_urls: int = 24,
    guess_missing_paths: bool = True,
) -> list[str]:
    """
    Picks crawl targets per competitor rather than per URL.

    Selecting by URL score alone spread the page budget across every host that appeared in
    search -- listicles, forums and directories included -- so each real competitor got about
    one page, and that page was rarely the one carrying their pricing. Budgeting per
    competitor instead fetches several pages from each shortlisted rival's own domain, which
    is where pricing, plans and feature claims actually live.

    When search surfaced fewer than `pages_per_competitor` pages on a competitor's domain, the
    remainder is topped up with guessed commercial paths. A guess that 404s costs one fetch and
    is dropped by the crawler's minimum-word filter; the alternative is leaving the budget unspent.
    """
    by_host: dict[str, list[str]] = {}
    for r in search_results:
        if not r.url:
            continue
        host = (urlparse(r.url).hostname or "").removeprefix("www.").lower()
        if host:
            by_host.setdefault(host, []).append(_canonical(r.url))

    def _commercial_rank(url: str) -> int:
        path = (urlparse(url).path or "/").lower().strip("/")
        return _COMMERCIAL_SEGMENTS.index(path) if path in _COMMERCIAL_SEGMENTS else 99

    targets: list[str] = []
    seen: set[str] = set()

    for comp in competitors:
        sources = [_canonical(s) for s in getattr(comp, "sources", []) or []]
        host = next(
            (h for h in ((urlparse(s).hostname or "").removeprefix("www.").lower() for s in sources)
             if _is_own_domain(h)),
            "",
        )
        if not host:
            continue

        # Everything search already found on this competitor's own domain, commercial first.
        candidates = list(dict.fromkeys(sources + by_host.get(host, [])))
        candidates = [u for u in candidates if (urlparse(u).hostname or "").removeprefix("www.").lower() == host]
        candidates.sort(key=_commercial_rank)

        if guess_missing_paths and len(candidates) < pages_per_competitor:
            scheme = urlparse(candidates[0]).scheme if candidates else "https"
            root = f"{scheme or 'https'}://{host}"
            have = {(urlparse(u).path or "/").lower().rstrip("/") for u in candidates}
            guesses = 0
            for path in _GUESSED_PATHS:
                if len(candidates) >= pages_per_competitor or guesses >= _MAX_GUESSES:
                    break
                if path not in have:
                    candidates.append(root + path)
                    guesses += 1

        for url in candidates[:pages_per_competitor]:
            if url not in seen:
                seen.add(url)
                targets.append(url)

    pairs = [(u, "alternative_discovery") for u in targets]
    return [u for u, _ in filter_crawl_urls(pairs)][:max_urls]


def extract_target_urls(
    search_results: list[TavilySearchResult],
    max_urls: int = 10,
    priority_order: tuple[str, ...] = (
        "pricing_scrape",
        "alternative_discovery",
        "gripe_mining",
        "messaging_claims",
    ),
) -> list[str]:
    """
    Selects top URLs from search results for deep scraping.
    """

    scored: list[tuple[float, str]] = []
    seen: set[str] = set()

    for vector in priority_order:
        vector_results = [r for r in search_results if r.vector == vector]
        for r in sorted(vector_results, key=lambda x: x.score, reverse=True):
            if r.url not in seen:
                seen.add(r.url)
                priority_bonus = (len(priority_order) - priority_order.index(vector)) * 0.1
                # Boost commercial pages (pricing, plans, features, root)
                parsed = urlparse(r.url)
                path_lower = (parsed.path or "/").lower().strip("/")
                if path_lower in ("", "pricing", "plans", "price", "features", "product", "solutions", "compare"):
                    priority_bonus += 0.35
                scored.append((r.score + priority_bonus, r.url))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Spread the budget across sites before going deep on any one of them. Ranking purely by
    # score let a single high-scoring domain take most of the slots, so other competitors got
    # one page each -- rarely the page carrying their pricing. Round-robin by host gives every
    # competitor a first page before any gets a second, while keeping score order within a host.
    by_host: dict[str, list[str]] = {}
    for _, url in scored:
        host = (urlparse(url).hostname or url).removeprefix("www.")
        by_host.setdefault(host, []).append(url)

    balanced: list[str] = []
    while len(balanced) < max_urls and by_host:
        for host in list(by_host):
            if len(balanced) >= max_urls:
                break
            balanced.append(by_host[host].pop(0))
            if not by_host[host]:
                del by_host[host]

    # Build (url, vector) pairs so the guard can apply domain-to-vector checks,
    # then return only the URLs that pass HTTPS enforcement + path/relevance checks.
    url_to_vector = {r.url: r.vector for r in search_results}
    pairs = [(u, url_to_vector.get(u, "")) for u in balanced]
    return [u for u, _ in filter_crawl_urls(pairs)]
