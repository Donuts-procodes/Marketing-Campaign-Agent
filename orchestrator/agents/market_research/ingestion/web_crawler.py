"""
Crawl API client for deep search and ad-library pages. Fetches live pages, rendered in a
headless browser, and returns them as markdown. Supported providers:

  - Scrape.do  GET  https://api.scrape.do/?token=..&url=..&output=markdown (SCRAPEDO_API_KEY; preferred)
  - Firecrawl  POST https://api.firecrawl.dev/v2/scrape                   (FIRECRAWL_API_KEY; legacy)
  - Crawlbase  GET  https://api.crawlbase.com/?token=..&url=..            (CRAWLAPI_TOKEN / CRAWLAPI_JS_TOKEN)

Every fetch either returns a real page body or raises CrawlAPIError; nothing is filled in.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from orchestrator.core.config import get_settings
from orchestrator.agents.market_research.ingestion.provider_health import is_account_error

logger = logging.getLogger(__name__)

SCRAPEDO_ENDPOINT = "https://api.scrape.do/"
FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v2/scrape"
CRAWLBASE_ENDPOINT = "https://api.crawlbase.com/"
BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"

# Target-site statuses that still carry a real page body.
_OK_STATUSES = {200, 201, 203, 204}

# Retries on 429 rate limit
_SCRAPEDO_RETRIES = 3
_FIRECRAWL_RETRIES = 3
_BRIGHTDATA_RETRIES = 3
_scrapedo_semaphores: dict[tuple[int, int], asyncio.Semaphore] = {}
_firecrawl_semaphores: dict[tuple[int, int], asyncio.Semaphore] = {}
_brightdata_semaphores: dict[tuple[int, int], asyncio.Semaphore] = {}


def _brightdata_semaphore() -> asyncio.Semaphore:
    limit = max(get_settings().crawl_max_concurrent, 1)
    key = (id(asyncio.get_running_loop()), limit)
    sem = _brightdata_semaphores.get(key)
    if sem is None:
        _brightdata_semaphores.clear()
        sem = _brightdata_semaphores[key] = asyncio.Semaphore(limit)
    return sem


def _scrapedo_semaphore() -> asyncio.Semaphore:
    limit = max(get_settings().crawl_max_concurrent, 1)
    key = (id(asyncio.get_running_loop()), limit)
    sem = _scrapedo_semaphores.get(key)
    if sem is None:
        _scrapedo_semaphores.clear()
        sem = _scrapedo_semaphores[key] = asyncio.Semaphore(limit)
    return sem


def _firecrawl_semaphore() -> asyncio.Semaphore:
    limit = max(get_settings().firecrawl_max_concurrent, 1)
    key = (id(asyncio.get_running_loop()), limit)
    sem = _firecrawl_semaphores.get(key)
    if sem is None:
        _firecrawl_semaphores.clear()
        sem = _firecrawl_semaphores[key] = asyncio.Semaphore(limit)
    return sem


_shared_clients: dict[int, httpx.AsyncClient] = {}


def _client() -> httpx.AsyncClient:
    """One pooled keep-alive client per event loop, so batches reuse TLS connections."""
    key = id(asyncio.get_running_loop())
    client = _shared_clients.get(key)
    if client is None or client.is_closed:
        _shared_clients.clear()
        client = _shared_clients[key] = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=40),
        )
    return client


def _retry_after_seconds(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("retry-after", "")
    try:
        return min(float(header), 60.0)
    except (ValueError, OverflowError):
        return min(10.0 * (attempt + 1), 60.0)



class CrawlAPIError(Exception):
    """Raised when no crawl provider is configured or a fetch does not return a real page."""


class CrawlAccountError(CrawlAPIError):
    """The provider rejected the account (quota, zone, key), not the page."""


class CrawlAPIClient:
    """Async crawl client. `fetch` returns {"url", "status", "body"} or raises CrawlAPIError."""

    def __init__(
        self,
        token: str | None = None,
        js_token: str | None = None,
        timeout: float | None = None,
        firecrawl_api_key: str | None = None,
        scrapedo_api_key: str | None = None,
        brightdata_api_key: str | None = None,
        brightdata_zone: str | None = None,
    ) -> None:
        settings = get_settings()
        self.timeout = timeout or settings.crawlapi_timeout_seconds
        self.brightdata_zone = (
            brightdata_zone
            if brightdata_zone is not None
            else getattr(settings, "brightdata_zone", "web_unlocker")
        )

        explicit_keys = any(
            k is not None
            for k in (brightdata_api_key, scrapedo_api_key, firecrawl_api_key, token, js_token)
        )
        if explicit_keys:
            self.brightdata_api_key = brightdata_api_key or ""
            self.scrapedo_api_key = scrapedo_api_key or ""
            self.firecrawl_api_key = firecrawl_api_key or ""
            self.token = token or ""
            self.js_token = js_token or ""
        else:
            self.brightdata_api_key = getattr(settings, "brightdata_api_key", "")
            self.scrapedo_api_key = getattr(settings, "scrapedo_api_key", "")
            self.firecrawl_api_key = settings.firecrawl_api_key
            self.token = settings.crawlapi_token
            self.js_token = settings.crawlapi_js_token

    @property
    def provider(self) -> str | None:
        if self.brightdata_api_key:
            return "brightdata"
        if self.scrapedo_api_key:
            return "scrapedo"
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
        return bool(
            self.brightdata_api_key
            or self.scrapedo_api_key
            or self.firecrawl_api_key
            or self.js_token
        )

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
        """`provider` forces "brightdata", "scrapedo", "firecrawl" or "crawlbase"; otherwise the
        configured providers are tried in that order, skipping any switched off for account errors."""
        from orchestrator.agents.market_research.ingestion.provider_health import is_down, mark_down

        keys = {"brightdata": self.brightdata_api_key, "scrapedo": self.scrapedo_api_key,
                "firecrawl": self.firecrawl_api_key, "crawlbase": self.token or self.js_token}
        if provider:
            if not keys.get(provider):
                raise CrawlAPIError(f"{provider} not configured")
            chain = [provider]
        else:
            chain = [p for p in ("brightdata", "scrapedo", "firecrawl", "crawlbase") if keys[p] and not is_down(p)]
            if not chain:
                raise CrawlAPIError("No working crawl provider (all switched off for account errors)")

        last: CrawlAPIError | None = None
        for name in chain:
            try:
                if name == "brightdata":
                    return await self._fetch_brightdata(url, javascript=javascript, country=country)
                if name == "scrapedo":
                    return await self._fetch_scrapedo(url, javascript=javascript, country=country)
                if name == "firecrawl":
                    return await self._fetch_firecrawl(
                        url, full_page=javascript, page_wait_ms=page_wait_ms, scroll=scroll, country=country
                    )
                return await self._fetch_crawlbase(
                    url, javascript=javascript, output_format=output_format, page_wait_ms=page_wait_ms,
                    ajax_wait=ajax_wait, scroll=scroll, country=country,
                )
            except CrawlAccountError as exc:
                mark_down(name, str(exc)[:200])  # every later page skips this account
                last = exc
            except CrawlAPIError as exc:
                last = exc
            if name != chain[-1]:
                logger.warning("%s failed for %s (%s); trying the next provider", name, url, last)
        raise last or CrawlAPIError(f"Crawl failed for {url}")

    async def _fetch_brightdata(
        self,
        url: str,
        *,
        javascript: bool = True,
        country: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.brightdata_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "zone": self.brightdata_zone or "web_unlocker",
            "url": url,
            "format": "raw",
        }
        if country:
            payload["country"] = country.lower()

        response: httpx.Response | None = None
        for attempt in range(max(_BRIGHTDATA_RETRIES, 0) + 1):
            async with _brightdata_semaphore():
                client = _client()
                response = await client.post(
                    BRIGHTDATA_ENDPOINT,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout + 15,
                )
            if response.status_code != 429 or attempt == _BRIGHTDATA_RETRIES:
                break
            wait = _retry_after_seconds(response, attempt)
            logger.info("Bright Data rate limited; retrying %s in %.0fs", url, wait)
            await asyncio.sleep(wait)

        if response is None:
            raise CrawlAPIError(f"Bright Data made no request for {url}")

        if response.status_code != 200:
            err = CrawlAccountError if is_account_error(response.status_code, response.text) else CrawlAPIError
            raise err(f"Bright Data failed for {url} (HTTP {response.status_code}): {response.text[:200]}")

        target_status = _int_header(
            response.headers.get("x-response-code")
            or response.headers.get("x-status-code")
            or response.headers.get("orig-status")
        ) or 200

        if target_status not in _OK_STATUSES and target_status != 200:
            raise CrawlAPIError(f"Target returned HTTP {target_status} for {url}")

        body = response.text or ""
        if not body.strip():
            raise CrawlAPIError(f"Empty page body for {url}")

        resolved_url = response.headers.get("x-response-url") or url
        return {
            "url": resolved_url,
            "status": target_status,
            "body": body,
        }

    async def _fetch_scrapedo(
        self,
        url: str,
        *,
        javascript: bool = True,
        country: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "token": self.scrapedo_api_key,
            "url": url,
            "output": "markdown",
        }
        if javascript:
            params["render"] = "true"
        if country:
            params["geoCode"] = country.lower()

        response: httpx.Response | None = None
        for attempt in range(max(_SCRAPEDO_RETRIES, 0) + 1):
            async with _scrapedo_semaphore():
                client = _client()
                response = await client.get(SCRAPEDO_ENDPOINT, params=params, timeout=self.timeout + 15)
            if response.status_code != 429 or attempt == _SCRAPEDO_RETRIES:
                break
            wait = _retry_after_seconds(response, attempt)
            logger.info("Scrape.do rate limited; retrying %s in %.0fs", url, wait)
            await asyncio.sleep(wait)

        if response is None:
            raise CrawlAPIError(f"Scrape.do made no request for {url}")

        if response.status_code != 200:
            err = CrawlAccountError if is_account_error(response.status_code, response.text) else CrawlAPIError
            raise err(f"Scrape.do failed for {url} (HTTP {response.status_code}): {response.text[:200]}")

        target_status = _int_header(
            response.headers.get("scrape.do-initial-status-code")
            or response.headers.get("sc-status")
            or response.headers.get("original-status")
        ) or 200

        if target_status not in _OK_STATUSES and target_status != 200:
            raise CrawlAPIError(f"Target returned HTTP {target_status} for {url}")

        body = response.text or ""
        if not body.strip():
            raise CrawlAPIError(f"Empty page body for {url}")

        resolved_url = response.headers.get("scrape.do-resolved-url") or url
        return {
            "url": resolved_url,
            "status": target_status,
            "body": body,
        }

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
            async with _firecrawl_semaphore():
                client = _client()
                response = await client.post(
                    FIRECRAWL_ENDPOINT,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.firecrawl_api_key}"},
                    timeout=self.timeout + 15,
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
            err = CrawlAccountError if is_account_error(response.status_code, str(reason)) else CrawlAPIError
            raise err(f"Firecrawl failed for {url}: {reason}")

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

        response = await _client().get(CRAWLBASE_ENDPOINT, params=params, timeout=self.timeout)

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
