"""
Merchant corrections to a finished report.

A pure function so the chat assistant can dry-run an edit on a copy before offering it as a
confirmation card, and the edit endpoint applies exactly the same rules for real.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.schemas.api import ReportEdit
from orchestrator.schemas.research import CompetitorChange, SWOTReportDelta


class ReportEditError(ValueError):
    """An edit names a competitor or item the report does not contain."""


FIELD_WORDS = {
    "core_claims": "claim",
    "weaknesses_mined": "complaint",
    "strengths_mined": "praise",
    "ad_hooks": "ad",
    "factual_evidence": "evidence quote",
    "milestones": "milestone",
}


def _norm(name: str) -> str:
    return " ".join((name or "").lower().split())


def apply_report_edits(report: SWOTReportDelta, edits: list[ReportEdit]) -> tuple[SWOTReportDelta, list[str]]:
    """
    Applies `edits` to `report` in place and returns it with a description of each change.
    Raises ReportEditError on the first edit that does not fit; callers pass a copy so a
    failing batch leaves the real report untouched.

    A corrected price is recorded in the competitor's change history with source "merchant",
    so the report never presents it as something the research found.
    """
    applied: list[str] = []
    today = datetime.now(timezone.utc).date().isoformat()

    for edit in edits:
        comp = next((c for c in report.competitors if _norm(c.brand_name) == _norm(edit.competitor)), None)
        if comp is None:
            names = ", ".join(c.brand_name for c in report.competitors)
            raise ReportEditError(f"No competitor named '{edit.competitor}' in this report. It has: {names}.")

        if edit.op == "remove_competitor":
            report.competitors = [c for c in report.competitors if c is not comp]
            applied.append(f"Removed {comp.brand_name} from the report")
        elif edit.op == "set_price":
            value = (edit.value or "").strip() or None
            comp.change_history.append(
                CompetitorChange(
                    observed_at=today, field="pricing_model", previous=comp.pricing_model, current=value, source="merchant"
                )
            )
            comp.pricing_model = value
            applied.append(f"Set {comp.brand_name}'s price to {value}" if value else f"Cleared {comp.brand_name}'s price")
        elif edit.op == "set_rating":
            value = (edit.value or "").strip() or None
            comp.change_history.append(
                CompetitorChange(
                    observed_at=today, field="rating", previous=comp.rating, current=value, source="merchant"
                )
            )
            comp.rating = value
            applied.append(f"Set {comp.brand_name}'s rating to {value}" if value else f"Cleared {comp.brand_name}'s rating")
        else:  # remove_item
            if not edit.field or not edit.value:
                raise ReportEditError("Removing an item needs the field and the item's text.")
            items: list[str] = getattr(comp, edit.field)
            wanted = " ".join(edit.value.split()).lower()
            exact = [i for i, v in enumerate(items) if " ".join(v.split()).lower() == wanted]
            hits = exact or [i for i, v in enumerate(items) if wanted in v.lower()]
            if len(hits) != 1:
                listing = "; ".join(f'"{v[:80]}"' for v in items) or "none"
                problem = "matches several items" if hits else "is not in"
                raise ReportEditError(
                    f"'{edit.value[:80]}' {problem} {comp.brand_name}'s {FIELD_WORDS[edit.field]} list "
                    f"({edit.field}). Current items: {listing}"
                )
            removed = items[hits[0]]
            setattr(comp, edit.field, [v for i, v in enumerate(items) if i != hits[0]])
            applied.append(f"Removed {comp.brand_name}'s {FIELD_WORDS[edit.field]}: \"{removed[:90]}\"")

    return report, applied
