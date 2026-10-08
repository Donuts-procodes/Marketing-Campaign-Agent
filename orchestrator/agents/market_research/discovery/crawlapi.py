"""
Crawl API client for deep search and ad-library pages. Fetches live pages, rendered in a
headless browser, and returns them as markdown. Two providers are supported:

  - Firecrawl  POST https://api.firecrawl.dev/v2/scrape         (FIRECRAWL_API_KEY; preferred)
  - Crawlbase  GET  https://api.crawlbase.com/?token=..&url=..  (CRAWLAPI_TOKEN / CRAWLAPI_JS_TOKEN)

Every fetch either returns a real page body or raises CrawlAPIError; nothing is filled in.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from orchestrator.core.config import get_settings

logger = logging.getLogger(__name__)

FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v2/scrape"
CRAWLBASE_ENDPOINT = "https://api.crawlbase.com/"

# Target-site statuses that still carry a real page body.
_OK_STATUSES = {200, 201, 203, 204}

# Firecrawl plans are rate limited per minute: cap concurrency process-wide and retry on 429.
_FIRECRAWL_RETRIES = 3
# Keyed by (loop id, limit) so a settings change takes effect without a restart.
_firecrawl_semaphores: dict[tuple[int, int], asyncio.Semaphore] = {}


def _firecrawl_semaphore() -> asyncio.Semaphore:
    limit = max(get_settings().firecrawl_max_concurrent, 1)
    key = (id(asyncio.get_running_loop()), limit)
    sem = _firecrawl_semaphores.get(key)
    if sem is None:
        _firecrawl_semaphores.clear()
        sem = _firecrawl_semaphores[key] = asyncio.Semaphore(limit)
    return sem


def _retry_after_seconds(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("retry-after", "")
    try:
        return min(float(header), 60.0)
    except (ValueError, OverflowError):
        return min(10.0 * (attempt + 1), 60.0)



class CrawlAPIError(Exception):
    """Raised when no crawl provider is configured or a fetch does not return a real page."""


class CrawlAPIClient:
    """Async crawl client. `fetch` returns {"url", "status", "body"} or raises CrawlAPIError."""

    def __init__(
        self,
        token: str | None = None,
        js_token: str | None = None,
        timeout: float | None = None,
        firecrawl_api_key: str | None = None,
    ) -> None:
        settings = get_settings()
        self.firecrawl_api_key = (
            firecrawl_api_key if firecrawl_api_key is not None else settings.firecrawl_api_key
        )
        self.token = token if token is not None else settings.crawlapi_token
        self.js_token = js_token if js_token is not None else settings.crawlapi_js_token
        self.timeout = timeout or settings.crawlapi_timeout_seconds

    @property
    def provider(self) -> str | None:
        if self.firecrawl_api_key:
            return "firecrawl"
        if self.token or self.js_token:
            return "crawlbase"
        return None

    @property
    def configured(self) -> bool:
        return self.provider is not None

    @property
    def can_render_js(self) -> bool:
        # Firecrawl always renders in a browser; Crawlbase needs its JavaScript token.
        return bool(self.firecrawl_api_key or self.js_token)

    async def fetch(
        self,
        url: str,
        *,
        javascript: bool = False,
        output_format: str = "md",
        page_wait_ms: int | None = None,
        ajax_wait: bool = False,
        scroll: bool = False,
        country: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """`provider` forces "firecrawl" or "crawlbase"; by default Firecrawl is used when configured."""
        use_firecrawl = provider == "firecrawl" or (provider is None and bool(self.firecrawl_api_key))
        if use_firecrawl:
            if not self.firecrawl_api_key:
                raise CrawlAPIError("FIRECRAWL_API_KEY not configured")
            return await self._fetch_firecrawl(
                url, full_page=javascript, page_wait_ms=page_wait_ms, scroll=scroll, country=country
            )
        return await self._fetch_crawlbase(
            url,
            javascript=javascript,
            output_format=output_format,
            page_wait_ms=page_wait_ms,
            ajax_wait=ajax_wait,
            scroll=scroll,
            country=country,
        )

    async def _fetch_firecrawl(
        self,
        url: str,
        *,
        full_page: bool,
        page_wait_ms: int | None,
        scroll: bool,
        country: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "url": url,
            "formats": ["markdown"],
            # Ad-library pages need the whole page, not just the "main content" block.
            "onlyMainContent": not full_page,
            "timeout": int(self.timeout * 1000),
        }
        if page_wait_ms:
            payload["waitFor"] = page_wait_ms
        if scroll:
            payload["actions"] = [
                {"type": "scroll", "direction": "down"},
                {"type": "wait", "milliseconds": 1500},
                {"type": "scroll", "direction": "down"},
            ]
        if country:
            payload["location"] = {"country": country}

        response: httpx.Response | None = None
        for attempt in range(max(_FIRECRAWL_RETRIES, 0) + 1):
            # The slot is released before backing off: sleeping while holding it stalled every
            # other queued page for the whole 10/20/30s backoff.
            async with _firecrawl_semaphore(), httpx.AsyncClient(timeout=self.timeout + 15) as client:
                response = await client.post(
                    FIRECRAWL_ENDPOINT,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.firecrawl_api_key}"},
                )
            if response.status_code != 429 or attempt == _FIRECRAWL_RETRIES:
                break
            wait = _retry_after_seconds(response, attempt)
            logger.info("Firecrawl rate limited; retrying %s in %.0fs", url, wait)
            await asyncio.sleep(wait)

        if response is None:  # defensive: the retry loop always runs at least once
            raise CrawlAPIError(f"Firecrawl made no request for {url}")

        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code != 200 or not data.get("success"):
            reason = data.get("error") or data.get("message") or f"HTTP {response.status_code}"
            raise CrawlAPIError(f"Firecrawl failed for {url}: {reason}")

        page = data.get("data") or {}
        metadata = page.get("metadata") or {}
        original_status = int(metadata.get("statusCode") or 200)
        if original_status not in _OK_STATUSES:
            raise CrawlAPIError(f"Target returned HTTP {original_status} for {url}")
        body = page.get("markdown") or ""
        if not body.strip():
            raise CrawlAPIError(f"Empty page body for {url}")
        return {
            "url": metadata.get("sourceURL") or metadata.get("url") or url,
            "status": original_status,
            "body": body,
        }

    async def _fetch_crawlbase(
        self,
        url: str,
        *,
        javascript: bool,
        output_format: str,
        page_wait_ms: int | None,
        ajax_wait: bool,
        scroll: bool,
        country: str | None,
    ) -> dict[str, Any]:
        token = self.js_token if javascript else (self.token or self.js_token)
        if not token:
            raise CrawlAPIError(
                "Crawl API JavaScript token not configured" if javascript else "Crawl API not configured"
            )

        params: dict[str, Any] = {"token": token, "url": url, "format": output_format}
        if country:
            params["country"] = country
        if javascript:
            if page_wait_ms:
                params["page_wait"] = page_wait_ms
            if ajax_wait:
                params["ajax_wait"] = "true"
            if scroll:
                params["scroll"] = "true"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(CRAWLBASE_ENDPOINT, params=params)

        cb_status = _int_header(response.headers.get("cb_status") or response.headers.get("pc_status"))
        original_status = _int_header(response.headers.get("original_status"))
        if response.status_code != 200 or (cb_status and cb_status != 200):
            raise CrawlAPIError(f"Crawlbase status {cb_status or response.status_code} for {url}")
        if original_status and original_status not in _OK_STATUSES:
            raise CrawlAPIError(f"Target returned HTTP {original_status} for {url}")

        body = response.text
        if not body.strip():
            raise CrawlAPIError(f"Empty page body for {url}")
        return {"url": response.headers.get("url") or url, "status": original_status or 200, "body": body}


def _int_header(value: str | None) -> int:
    try:
        return int(value) if value else 0
    except ValueError:
        return 0
