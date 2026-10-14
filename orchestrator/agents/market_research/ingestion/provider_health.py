"""
Scraping-provider health: which crawl accounts work right now, and what to fix when one doesn't.

Two parts:
  - account errors seen during a run (wrong Bright Data zone, bad key, Scrape.do quota used up)
    switch that provider off for the process, so every later page goes straight to the next
    working provider instead of failing the same way first;
  - `check_providers()` reads each account's status from its free account endpoint (no page is
    fetched, no credit spent) and says in plain words what is wrong.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from orchestrator.core.config import get_settings

logger = logging.getLogger(__name__)

# provider -> (reason, when). Account problems (quota, zone, key) do not fix themselves mid-run.
_down: dict[str, tuple[str, float]] = {}
DOWN_FOR_SECONDS = 6 * 3600


class ProviderAccountError(Exception):
    """The provider rejected the account, not the page: retrying other pages will fail the same way."""


def is_account_error(status: int, body: str) -> bool:
    low = (body or "").lower()
    return status in (401, 402, 403) or ("zone" in low and "not found" in low) or "limit exceeded" in low


def mark_down(provider: str, reason: str) -> None:
    if provider not in _down:
        logger.warning("Crawl provider %s switched off: %s", provider, reason)
    _down[provider] = (reason, time.monotonic())


def is_down(provider: str) -> bool:
    hit = _down.get(provider)
    if hit and time.monotonic() - hit[1] > DOWN_FOR_SECONDS:
        _down.pop(provider, None)
        return False
    return hit is not None


def down_reasons() -> dict[str, str]:
    return {p: r for p, (r, _) in _down.items() if is_down(p)}


async def check_providers(timeout: float = 10.0) -> list[dict[str, Any]]:
    """[{provider, configured, ok, detail}] from each account's free status endpoint."""
    s = get_settings()
    out: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        if s.brightdata_api_key:
            entry = {"provider": "brightdata", "configured": True, "ok": False, "detail": ""}
            try:
                r = await client.get("https://api.brightdata.com/zone/get_active_zones",
                                     headers={"Authorization": f"Bearer {s.brightdata_api_key}"})
                if r.status_code != 200:
                    entry["detail"] = f"API key rejected (HTTP {r.status_code}). Check BRIGHTDATA_API_KEY."
                else:
                    zones = [z.get("name") for z in r.json() if isinstance(z, dict)]
                    if s.brightdata_zone in zones:
                        entry.update(ok=True, detail=f"Zone '{s.brightdata_zone}' is active.")
                    else:
                        unlockers = [z for z in zones if z and "unlock" in z.lower()]
                        entry["detail"] = (
                            f"Zone '{s.brightdata_zone}' does not exist. Active zones: {', '.join(zones) or 'none'}. "
                            + (f"Set BRIGHTDATA_ZONE={unlockers[0]}." if unlockers
                               else "Create a Web Unlocker zone in the Bright Data dashboard and set BRIGHTDATA_ZONE to its name.")
                        )
            except (httpx.HTTPError, ValueError) as exc:
                entry["detail"] = f"Could not reach Bright Data ({type(exc).__name__})."
            out.append(entry)
        if s.scrapedo_api_key:
            entry = {"provider": "scrapedo", "configured": True, "ok": False, "detail": ""}
            try:
                r = await client.get("https://api.scrape.do/info", params={"token": s.scrapedo_api_key})
                data = r.json() if r.status_code == 200 else {}
                left = data.get("RemainingMonthlyRequest")
                if r.status_code != 200:
                    entry["detail"] = f"Token rejected (HTTP {r.status_code}). Check SCRAPEDO_API_KEY."
                elif not data.get("IsActive", True) or (left is not None and int(left) <= 0):
                    entry["detail"] = "Monthly request limit used up. Upgrade the plan or wait for the next period."
                else:
                    entry.update(ok=True, detail=f"{left} requests left this month." if left is not None else "Active.")
            except (httpx.HTTPError, ValueError) as exc:
                entry["detail"] = f"Could not reach Scrape.do ({type(exc).__name__})."
            out.append(entry)
        if s.firecrawl_api_key:
            entry = {"provider": "firecrawl", "configured": True, "ok": False, "detail": ""}
            try:
                r = await client.get("https://api.firecrawl.dev/v1/team/credit-usage",
                                     headers={"Authorization": f"Bearer {s.firecrawl_api_key}"})
                credits = (r.json().get("data") or {}).get("remaining_credits") if r.status_code == 200 else None
                if r.status_code != 200:
                    entry["detail"] = f"Key rejected (HTTP {r.status_code}). Check FIRECRAWL_API_KEY."
                elif credits is not None and credits <= 0:
                    entry["detail"] = "No credits left."
                else:
                    entry.update(ok=True, detail=f"{credits} credits left." if credits is not None else "Active.")
            except (httpx.HTTPError, ValueError) as exc:
                entry["detail"] = f"Could not reach Firecrawl ({type(exc).__name__})."
            out.append(entry)
        for name, key in (("tavily", s.tavily_api_key), ("serpapi", getattr(s, "serpapi_api_key", "")),
                          ("keepa", getattr(s, "keepa_api_key", "")), ("dataforseo", getattr(s, "dataforseo_login", ""))):
            out.append({"provider": name, "configured": bool(key), "ok": bool(key),
                        "detail": "Key set." if key else "Not configured."})
    for e in out:
        if e["provider"] in down_reasons():
            e.update(ok=False, detail=f"{e['detail']} Switched off this run: {down_reasons()[e['provider']]}")
    return out
