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

from orchestrator.agents.market_research.intelligence.validation.scoring import PLACEHOLDER_PRICING
from orchestrator.core.config import get_settings
from orchestrator.schemas.research import (
    CompetitorChange,
    CompetitorProfile,
    SWOTReportDelta,
)

logger = logging.getLogger(__name__)

_MAX_WEAKNESSES = 20
_MAX_EVIDENCE = 20
_MAX_SOURCES = 30
#: Change entries kept per competitor. Oldest are dropped first so the series stays readable
#: and the stored report cannot grow without bound across repeated scans.
_MAX_CHANGES = 30


def _brand_key(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def _merge_competitor(
    old: CompetitorProfile,
    new: CompetitorProfile,
    observed_at: str = "",
) -> CompetitorProfile:
    """Merges an old profile into a new one in-place and returns the enriched profile."""
    # The prior run's own change log carries forward: it is the only record of what this
    # competitor did before today, and nothing else in the pipeline reproduces it.
    new.change_history = list(old.change_history) + list(new.change_history)

    def _record(field: str, previous: str | None, current: str | None) -> None:
        new.change_history.append(
            CompetitorChange(
                observed_at=observed_at or datetime.now(timezone.utc).date().isoformat(),
                field=field,
                previous=previous,
                current=current,
            )
        )

    # Pricing: new wins when present, otherwise keep old. A move between two real prices is
    # the single most actionable thing a repeat scan produces, so it is recorded rather than
    # silently overwritten. The "detected" placeholder is not a price and never counts as one.
    real = lambda v: bool(v) and v != PLACEHOLDER_PRICING  # noqa: E731
    if real(new.pricing_model) and real(old.pricing_model) and new.pricing_model != old.pricing_model:
        _record("pricing_model", old.pricing_model, new.pricing_model)
    elif real(new.pricing_model) and not real(old.pricing_model):
        _record("pricing_model", old.pricing_model, new.pricing_model)
    if not new.pricing_model and old.pricing_model:
        new.pricing_model = old.pricing_model

    # Claims the competitor has started or stopped making: a repositioning shows up here
    # before it shows up anywhere else.
    added_claims = [c for c in new.core_claims if c and c not in old.core_claims]
    dropped_claims = [c for c in old.core_claims if c and c not in new.core_claims]
    for claim in added_claims[:3]:
        _record("core_claims.added", None, claim)
    for claim in dropped_claims[:3]:
        _record("core_claims.dropped", claim, None)

    if new.founded and old.founded and new.founded != old.founded:
        _record("founded", old.founded, new.founded)

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

    # Strengths: union, deduped, capped — same treatment as weaknesses, so a rival's praise
    # survives a re-scan exactly as its complaints do.
    existing_st = set(new.strengths_mined)
    for st in old.strengths_mined:
        if st not in existing_st and len(new.strengths_mined) < _MAX_WEAKNESSES:
            new.strengths_mined.append(st)
            existing_st.add(st)

    # Social proof: the newer scan wins, and a rating that moved is recorded. A competitor's
    # score sliding is a market signal in its own right.
    if new.rating and old.rating and new.rating != old.rating:
        _record("rating", old.rating, new.rating)
    if not new.rating and old.rating:
        new.rating = old.rating
    if new.review_count is None and old.review_count is not None:
        new.review_count = old.review_count

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

    # Background facts do not change between scans, so an earlier run's finding fills a gap
    # rather than being re-derived.
    if not new.founded and old.founded:
        new.founded = old.founded
    existing_m = set(new.milestones)
    for m in old.milestones:
        if m and m not in existing_m:
            new.milestones.append(m)
            existing_m.add(m)

    if len(new.change_history) > _MAX_CHANGES:
        new.change_history = new.change_history[-_MAX_CHANGES:]

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
    # Changes are stamped with today's date: this run is what observed them.
    observed_at = datetime.now(timezone.utc).date().isoformat()

    for old_comp in prior_report.competitors:
        key = _brand_key(old_comp.brand_name)
        if key in new_keys:
            # Competitor was re-found in the new run — enrich with old data
            idx = new_keys[key]
            new_report.competitors[idx] = _merge_competitor(
                old_comp, new_report.competitors[idx], observed_at=observed_at
            )
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
