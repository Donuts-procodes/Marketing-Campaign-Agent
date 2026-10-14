"""
Google Trends client: weekly search interest and rising related searches for a keyword in a country.

Uses the public endpoints the Trends site itself calls (explore -> widget tokens -> multiline /
relatedsearches). No key is needed, but Google rate-limits: every failure raises TrendsError and
callers report the signal as unavailable instead of filling it in.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE = "https://trends.google.com"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


class TrendsError(Exception):
    pass


def _json(body: str) -> Any:
    # Responses start with an anti-JSON-hijacking prefix like ")]}'," before the payload.
    start = min((i for i in (body.find("{"), body.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise TrendsError("Unexpected Google Trends response")
    return json.loads(body[start:])


async def fetch_trends(keyword: str, geo: str = "", timeframe: str = "today 12-m", timeout: float = 20.0) -> dict[str, Any]:
    """
    {"points": [(iso_date, interest 0-100), ...], "rising": [(query, growth label)], "top": [query, ...]}.
    `geo` is an ISO country code ("IN"); empty means worldwide.
    """
    req = {"comparisonItem": [{"keyword": keyword, "geo": geo, "time": timeframe}], "category": 0, "property": ""}
    async with httpx.AsyncClient(headers=_HEADERS, timeout=timeout, follow_redirects=True) as client:
        try:
            await client.get(f"{BASE}/trends/explore", params={"geo": geo or "US", "q": keyword})  # sets NID cookie
            r = await client.get(f"{BASE}/trends/api/explore",
                                 params={"hl": "en-US", "tz": "0", "req": json.dumps(req)})
            if r.status_code != 200:
                raise TrendsError(f"explore HTTP {r.status_code}")
            widgets = {w.get("id"): w for w in _json(r.text).get("widgets", [])}
            out: dict[str, Any] = {"points": [], "rising": [], "top": []}

            ts = widgets.get("TIMESERIES")
            if ts:
                r = await client.get(f"{BASE}/trends/api/widgetdata/multiline", params={
                    "hl": "en-US", "tz": "0", "req": json.dumps(ts["request"]), "token": ts["token"]})
                if r.status_code != 200:
                    raise TrendsError(f"multiline HTTP {r.status_code}")
                for row in _json(r.text).get("default", {}).get("timelineData", []):
                    if row.get("hasData", [True])[0] is False:
                        continue
                    from datetime import datetime, timezone

                    day = datetime.fromtimestamp(int(row["time"]), tz=timezone.utc).date().isoformat()
                    out["points"].append((day, int(row["value"][0])))

            rq = widgets.get("RELATED_QUERIES")
            if rq:
                r = await client.get(f"{BASE}/trends/api/widgetdata/relatedsearches", params={
                    "hl": "en-US", "tz": "0", "req": json.dumps(rq["request"]), "token": rq["token"]})
                if r.status_code == 200:
                    lists = _json(r.text).get("default", {}).get("rankedList", [])
                    if lists:
                        out["top"] = [k.get("query") for k in lists[0].get("rankedKeyword", [])][:10]
                    if len(lists) > 1:
                        out["rising"] = [(k.get("query"), k.get("formattedValue", "")) for k in lists[1].get("rankedKeyword", [])][:10]
            return out
        except TrendsError:
            raise
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise TrendsError(f"{type(exc).__name__}: {exc}") from exc
