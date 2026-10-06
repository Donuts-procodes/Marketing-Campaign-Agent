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

from orchestrator.agents.market_research.discovery.crawlapi import CrawlAPIClient
from orchestrator.agents.market_research.discovery.search import TavilySearchResult
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


async def _crawlapi_pages(
    urls: list[str], crawl_client: Any, max_concurrent: int
) -> tuple[list[ExtractedPage], list[str]]:
    """Fetches URLs via CrawlAPI; returns (pages, urls that failed)."""
    semaphore = asyncio.Semaphore(max_concurrent)
    provider = getattr(crawl_client, "provider", None)
    label = provider if isinstance(provider, str) else "crawlapi"

    async def _fetch_one(url: str) -> ExtractedPage | None:
        async with semaphore:
            try:
                response = await crawl_client.fetch(url, output_format="md")
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
    max_concurrent: int = 5,
) -> list[ExtractedPage]:
    """
    Deep-scrapes target URLs into markdown: CrawlAPI first, then Tavily Extract for any URL
    CrawlAPI could not fetch (or for all URLs when CrawlAPI is not configured).
    """
    unique_urls = list(dict.fromkeys(u for u in urls if u))
    if not unique_urls:
        return []

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
    return balanced
