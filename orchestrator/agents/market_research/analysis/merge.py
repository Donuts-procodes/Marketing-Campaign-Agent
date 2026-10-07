"""
Cross-run report merging: combines a fresh SWOTReportDelta with a prior run's findings.

When a user runs an update, the pipeline searches only for recent changes. This module
merges the new findings on top of the old baseline so the final report is complete:

  - Competitors found in the new run: use new data (it is fresher).
  - Competitors in the old run but NOT re-found: retain their data, mark with prior_run_at.
  - Weaknesses / evidence: union of old + new, deduped.
  - Pricing: new value wins when present; fall back to old.
  - SWOT / positioning_gap: always use the new run's analysis when available.
  - Source URLs: union of old + new.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from orchestrator.core.config import get_settings
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta

logger = logging.getLogger(__name__)

_MAX_WEAKNESSES = 20
_MAX_EVIDENCE = 20
_MAX_SOURCES = 30


def _brand_key(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def _merge_competitor(old: CompetitorProfile, new: CompetitorProfile) -> CompetitorProfile:
    """Merges an old profile into a new one in-place and returns the enriched profile."""
    # Pricing: new wins when present, otherwise keep old
    if not new.pricing_model and old.pricing_model:
        new.pricing_model = old.pricing_model

    # Core claims: union, new first
    existing = set(new.core_claims)
    for claim in old.core_claims:
        if claim not in existing:
            new.core_claims.append(claim)

    # Weaknesses: union, deduped, capped
    existing_w = set(new.weaknesses_mined)
    for w in old.weaknesses_mined:
        if w not in existing_w and len(new.weaknesses_mined) < _MAX_WEAKNESSES:
            new.weaknesses_mined.append(w)
            existing_w.add(w)

    # Factual evidence: union, capped
    existing_e = set(new.factual_evidence)
    for e in old.factual_evidence:
        if e not in existing_e and len(new.factual_evidence) < _MAX_EVIDENCE:
            new.factual_evidence.append(e)
            existing_e.add(e)

    # Ad hooks: union
    existing_h = set(new.ad_hooks)
    for h in old.ad_hooks:
        if h not in existing_h:
            new.ad_hooks.append(h)

    # Sources: union, capped
    existing_s = set(new.sources)
    for s in old.sources:
        if s not in existing_s and len(new.sources) < _MAX_SOURCES:
            new.sources.append(s)
            existing_s.add(s)

    # Dynamic attributes: old fills gaps in new
    for k, v in old.dynamic_attributes.items():
        if k not in new.dynamic_attributes or new.dynamic_attributes[k] is None:
            new.dynamic_attributes[k] = v

    # Keep the more recent as_of date
    if old.as_of and (not new.as_of or old.as_of > new.as_of):
        pass  # new.as_of is newer or equal — keep it
    elif old.as_of and not new.as_of:
        new.as_of = old.as_of

    return new


def merge_reports(
    new_report: SWOTReportDelta,
    prior_report: SWOTReportDelta,
    prior_run_at: str | None = None,
) -> SWOTReportDelta:
    """
    Merges prior_report into new_report and returns the enriched report.

    new_report is mutated in-place — call after synthesis + grounding so the
    new analysis is already locked in before old data fills the gaps.
    """
    new_keys: dict[str, int] = {
        _brand_key(c.brand_name): i for i, c in enumerate(new_report.competitors)
    }

    carried_over = 0
    enriched = 0

    for old_comp in prior_report.competitors:
        key = _brand_key(old_comp.brand_name)
        if key in new_keys:
            # Competitor was re-found in the new run — enrich with old data
            idx = new_keys[key]
            new_report.competitors[idx] = _merge_competitor(old_comp, new_report.competitors[idx])
            enriched += 1
        else:
            # Competitor was NOT re-found (not mentioned in recent data) — carry forward
            # Mark the as_of so the UI can show "last seen: <date>"
            carried = old_comp.model_copy(deep=True)
            if prior_run_at and not carried.as_of:
                try:
                    dt = datetime.fromisoformat(prior_run_at.replace("Z", "+00:00"))
                    carried.as_of = dt.date().isoformat()
                except ValueError:
                    pass
            new_report.competitors.append(carried)
            carried_over += 1

    # Source URLs: union
    old_urls = set(prior_report.source_urls or [])
    new_urls = set(new_report.source_urls or [])
    new_report.source_urls = list(new_urls | old_urls)

    # Carried-forward competitors are appended after the shortlist cap was already applied, so
    # without this an update run grows the board every time the same product is re-run. Freshly
    # researched competitors keep their places and the stale ones fill whatever remains, newest
    # first, so re-running never pushes current findings off the report.
    cap = get_settings().research_max_competitors
    if cap and cap > 0 and len(new_report.competitors) > cap:
        fresh = [c for c in new_report.competitors if not c.as_of]
        carried = [c for c in new_report.competitors if c.as_of]
        carried.sort(key=lambda c: c.as_of or "", reverse=True)
        dropped = len(new_report.competitors) - cap
        new_report.competitors = (fresh + carried)[:cap]
        logger.info("Report merge: trimmed %d competitor(s) beyond the cap of %d", dropped, cap)

    logger.info(
        "Report merge: %d new competitors, %d enriched from prior run, %d carried forward",
        len(new_keys),
        enriched,
        carried_over,
    )

    return new_report
