"""
Recency validation: extracts publication dates from evidence and scores how current it is.

Accuracy grounding (grounding.py) proves a claim came from a fetched page; it says nothing
about *when* that page was written. A 2019 pricing table grounds perfectly and is still
wrong. This module supplies the missing time dimension.

Dates that cannot be found are not treated as stale — absence of metadata is not evidence of
age. Only verifiably old evidence is penalized, so the score never punishes a site for
omitting a date.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

from orchestrator.core.clock import today as _clock_today

logger = logging.getLogger(__name__)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_ALT = "|".join(_MONTHS)

# Earliest plausible publication year for live competitive intel; guards against matching
# version numbers, prices or phone fragments as dates.
_MIN_YEAR = 2000

_DATE_PATTERNS = (
    # 2024-05-13 / 2024/05/13
    re.compile(r"\b(?P<y>\d{4})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})\b"),
    # 13 May 2024 / 13 May, 2024
    re.compile(rf"\b(?P<d>\d{{1,2}})\s+(?P<mon>{_MONTH_ALT})[a-z]*\.?,?\s+(?P<y>\d{{4}})\b", re.I),
    # May 13, 2024 / May 2024
    re.compile(rf"\b(?P<mon>{_MONTH_ALT})[a-z]*\.?\s+(?:(?P<d>\d{{1,2}}),?\s+)?(?P<y>\d{{4}})\b", re.I),
)

# Explicit publication markers carry far more signal than a date loose in body text.
_PUBLICATION_MARKER = re.compile(
    r"(?:published|updated|last\s+modified|posted|reviewed|effective|as\s+of)\b[^\n]{0,40}",
    re.I,
)


def _build_date(year: int, month: int, day: int) -> date | None:
    # Allow next year so a post dated just over the UTC boundary is not discarded.
    if not (_MIN_YEAR <= year <= _clock_today().year + 1):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def extract_dates(text: str, *, limit: int = 4000) -> list[date]:
    """Pulls plausible calendar dates out of free text, newest-first, deduplicated."""
    if not text:
        return []
    window = text[:limit]
    found: set[date] = set()

    for pattern in _DATE_PATTERNS:
        for m in pattern.finditer(window):
            groups = m.groupdict()
            year = int(groups["y"])
            if "mon" in groups and groups.get("mon"):
                month = _MONTHS[groups["mon"][:3].lower()]
            else:
                month = int(groups["m"])
            day = int(groups["d"]) if groups.get("d") else 1
            if month > 12:
                continue
            parsed = _build_date(year, month, day)
            if parsed:
                found.add(parsed)

    return sorted(found, reverse=True)


def extract_publication_date(text: str) -> date | None:
    """
    Best-effort publication date for a page: prefers a date next to an explicit
    'Published/Updated/As of' marker, else falls back to the newest plausible date found.
    """
    if not text:
        return None

    for marker in _PUBLICATION_MARKER.finditer(text[:4000]):
        dates = extract_dates(marker.group(0), limit=200)
        if dates:
            return dates[0]

    all_dates = extract_dates(text)
    return all_dates[0] if all_dates else None


def parse_iso_date(value: str | None) -> date | None:
    """Parses a provider-supplied date string (e.g. Tavily's published_date)."""
    if not value:
        return None
    raw = value.strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    dates = extract_dates(raw, limit=100)
    return dates[0] if dates else None


def score_recency(
    evidence_dates: list[date],
    *,
    has_evidence: bool,
    max_age_days: int,
    today: date | None = None,
) -> tuple[float, list[str]]:
    """
    Scores how current the dated evidence is.

      - No evidence gathered at all              -> 0.0 (nothing to assess)
      - Evidence exists but carries no dates     -> 1.0, silently (unverifiable, not stale)
      - Otherwise -> share of dated evidence newer than `max_age_days`

    Returns (score, diagnostics).
    """
    diagnostics: list[str] = []

    if not has_evidence:
        diagnostics.append("R_recency: no sources available to date-check")
        return 0.0, diagnostics

    if not evidence_dates:
        # Missing publication metadata is common and is not proof of staleness.
        return 1.0, diagnostics

    reference = today or _clock_today()
    fresh = [d for d in evidence_dates if (reference - d).days <= max_age_days]
    score = len(fresh) / len(evidence_dates)

    if score < 1.0:
        oldest = min(evidence_dates)
        diagnostics.append(
            f"R_recency: {len(fresh)}/{len(evidence_dates)} dated sources are within "
            f"{max_age_days} days (oldest: {oldest.isoformat()})"
        )

    return round(score, 4), diagnostics


def latest_iso(dates: list[date]) -> str | None:
    """ISO string for the newest date, or None when the list is empty."""
    return max(dates).isoformat() if dates else None


def audit_report_freshness(report, corpus: list[str], *, max_age_days: int) -> list[str]:
    """
    Fills `as_of` where grounding left it empty and summarizes how current the report is.

    Grounding dates a profile only from snippets naming the brand. A rival often appears by
    product name instead ("MX Master 3S" rather than "Logitech"), and an explicit "Updated
    <date>" marker beats a stray date in body text, so this second pass matches both names and
    prefers marker dates. A profile with no datable evidence stays null: undated is not stale.
    """
    reference = _clock_today()
    filled: list[str] = []
    stale: list[str] = []
    undated: list[str] = []

    for comp in report.competitors:
        if not comp.as_of:
            names = [n.lower() for n in (comp.brand_name, comp.product_name) if n and len(n) > 2]
            dates = [
                d for text in corpus
                if text and any(n in text.lower() for n in names)
                for d in [extract_publication_date(text)] if d
            ]
            if dates:
                comp.as_of = latest_iso(dates)
                filled.append(comp.brand_name)
        if not comp.as_of:
            undated.append(comp.brand_name)
            continue
        try:
            age = (reference - date.fromisoformat(comp.as_of)).days
        except ValueError:
            continue
        if age > max_age_days:
            stale.append(f"{comp.brand_name} ({comp.as_of})")

    diagnostics = [
        f"[FRESHNESS_AUDIT] {len(report.competitors) - len(undated)}/{len(report.competitors)} "
        f"competitors dated; {len(filled)} newly dated by product-name/marker match."
    ]
    if stale:
        diagnostics.append(
            f"[FRESHNESS_AUDIT] Evidence older than {max_age_days} days: {', '.join(stale)} — "
            "pricing and claims may have moved."
        )
    if undated:
        diagnostics.append(f"[FRESHNESS_AUDIT] No dated evidence for: {', '.join(undated)}.")
    return diagnostics
