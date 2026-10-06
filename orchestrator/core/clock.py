"""
Single source of live wall-clock time.

Every calendar decision in the pipeline — the year appended to a search query, whether
evidence counts as stale, the date handed to the models — reads from here, so they can
never disagree with each other.

UTC, deliberately: containers run in whatever timezone the host happens to have, and
`date.today()` would then shift the year boundary and the staleness cutoff with it.
Crawl providers stamp their dates in UTC, so comparing against UTC is also the honest
comparison.

Tests that need a fixed clock should pass an explicit `today=` argument to the function
under test rather than patching module globals.
"""

from __future__ import annotations

from datetime import date, datetime, timezone


def utc_now() -> datetime:
    """Current instant, timezone-aware UTC."""
    return datetime.now(timezone.utc)


def today() -> date:
    """Current UTC calendar date."""
    return utc_now().date()


def current_year() -> int:
    """Current UTC year, for recency hints in search queries."""
    return today().year


def today_iso() -> str:
    """Current UTC date as YYYY-MM-DD, for prompts and stamps."""
    return today().isoformat()
