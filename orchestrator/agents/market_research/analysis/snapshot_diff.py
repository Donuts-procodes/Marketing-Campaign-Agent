"""
Snapshot diff: records what moved between scans for the fields `merge.py` does not track.

`merge._merge_competitor` already records pricing_model, core_claims added/dropped, rating and
founded moves inline, because it must see the old and new values before it unions them. That
leaves review volume, live ad creative and parsed price unrecorded, and those are exactly the
signals a merchant watches between scans: a review count jumping means a sales push, new ad
hooks mean a new campaign, a price normalized to a different monthly figure means a real move
even when the text was reworded.

Runs after the merge, so the new profile already holds unions; only additions are therefore
detectable for list fields, which is the half that matters (a new campaign, not a paused one).
"""

from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.schemas.research import CompetitorChange, CompetitorProfile, SWOTReportDelta

#: Matches merge._MAX_CHANGES so the two writers share one cap.
_MAX_CHANGES = 30
_MAX_LIST_ENTRIES = 3


def _brand_key(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def _already_recorded(comp: CompetitorProfile, field: str, observed_at: str) -> bool:
    return any(ch.field == field and ch.observed_at == observed_at for ch in comp.change_history)


def diff_competitor(new: CompetitorProfile, old: CompetitorProfile, observed_at: str) -> int:
    """Appends change entries to `new` and returns how many were written."""
    written = 0

    def record(field: str, previous: str | None, current: str | None) -> None:
        nonlocal written
        new.change_history.append(
            CompetitorChange(observed_at=observed_at, field=field, previous=previous, current=current)
        )
        written += 1

    if (
        new.review_count is not None
        and old.review_count is not None
        and new.review_count != old.review_count
        and not _already_recorded(new, "review_count", observed_at)
    ):
        record("review_count", str(old.review_count), str(new.review_count))

    old_hooks = set(old.ad_hooks)
    added_hooks = [h for h in new.ad_hooks if h and h not in old_hooks]
    if not _already_recorded(new, "ad_hooks.added", observed_at):
        for hook in added_hooks[:_MAX_LIST_ENTRIES]:
            record("ad_hooks.added", None, hook)

    # Parsed price catches a real move hidden behind reworded text, and is the only way to see
    # that "$49/mo" -> "$588/yr" is no change at all. Only recorded when merge did not already
    # log a pricing_model change this run, so one move is never reported twice.
    old_m = old.pricing_parsed.monthly_equivalent if old.pricing_parsed else None
    new_m = new.pricing_parsed.monthly_equivalent if new.pricing_parsed else None
    if (
        old_m is not None
        and new_m is not None
        and abs(old_m - new_m) >= 0.01
        and not _already_recorded(new, "pricing_model", observed_at)
        and not _already_recorded(new, "monthly_price", observed_at)
    ):
        record("monthly_price", f"{old_m:g}", f"{new_m:g}")

    if len(new.change_history) > _MAX_CHANGES:
        new.change_history = new.change_history[-_MAX_CHANGES:]
    return written


def diff_report(
    new_report: SWOTReportDelta,
    prior_report: SWOTReportDelta | None,
    observed_at: str | None = None,
) -> tuple[int, list[str]]:
    """Diffs every competitor present in both reports. Returns (changes written, diagnostics)."""
    if prior_report is None or not prior_report.competitors:
        return 0, []
    observed_at = observed_at or datetime.now(timezone.utc).date().isoformat()
    old_by_key = {_brand_key(c.brand_name): c for c in prior_report.competitors}

    total = 0
    moved: list[str] = []
    for comp in new_report.competitors:
        old = old_by_key.get(_brand_key(comp.brand_name))
        if old is None or old is comp:
            continue
        n = diff_competitor(comp, old, observed_at)
        if n:
            total += n
            moved.append(f"{comp.brand_name} ({n})")

    diagnostics = [f"[CHANGE_DETECT] {total} additional change(s) recorded since the last scan."]
    if moved:
        diagnostics.append(f"[CHANGE_DETECT] Moved: {', '.join(moved)}.")
    return total, diagnostics
