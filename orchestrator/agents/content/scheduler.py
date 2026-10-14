"""
Scheduler: gives every asset a planned date and time from the approved strategy.

Assets are placed inside their strategy phase ("Days 1-14" style ranges from the plan, else the
campaign split into equal thirds), spread evenly within it per channel, starting from the
merchant's start date (tomorrow when none is set). Times are each channel's usual engagement
window, marked as a suggestion. A planned time is not a booking: an asset is only "scheduled"
once its channel is connected and the platform accepted it.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from orchestrator.core.clock import today as clock_today
from orchestrator.schemas.content import ContentPack
from orchestrator.schemas.strategy import CampaignStrategyBrief

# Usual engagement windows; shown to the merchant as suggestions they can change.
SUGGESTED_TIME = {
    "email": time(10, 0), "linkedin": time(9, 0), "instagram": time(19, 0), "facebook": time(19, 0),
    "x": time(12, 0), "whatsapp": time(18, 0), "meta_ads": time(0, 0), "google_ads": time(0, 0),
}
_RANGE = re.compile(r"(\d+)\s*[-–to]+\s*(\d+)")


def _phases(brief: CampaignStrategyBrief, days: int) -> list[tuple[str, int, int]]:
    """(name, first day, last day), 1-based, from the plan; equal thirds when the plan gives none."""
    out = []
    for p in (brief.plan.phases if brief.plan else []):
        if m := _RANGE.search(p.days or ""):
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= b:
                out.append((p.name, a, min(b, days)))
    if out:
        return out
    third = max(1, days // 3)
    return [("Phase 1", 1, third), ("Phase 2", third + 1, 2 * third), ("Phase 3", 2 * third + 1, days)]


def start_date(merchant_context: dict[str, Any]) -> date:
    raw = str(merchant_context.get("start_date") or "")
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return clock_today() + timedelta(days=1)


def plan_schedule(pack: ContentPack, brief: CampaignStrategyBrief, merchant_context: dict[str, Any]) -> int:
    """Sets scheduled_for on draft/approved assets that have none; returns how many were planned."""
    days = max(3, int(brief.campaign_days or 30))
    first = start_date(merchant_context)
    phases = _phases(brief, days)
    planned = 0
    for channel in pack.channels():
        assets = [a for a in pack.assets if a.channel == channel and not a.scheduled_for
                  and a.status in ("draft", "approved")]
        for i, a in enumerate(assets):
            # The asset's own phase when it names one; else spread the channel's assets across phases.
            phase = next((p for p in phases if a.phase and p[0].lower() in a.phase.lower()), None)
            if phase is None:
                phase = phases[min(len(phases) - 1, i * len(phases) // max(1, len(assets)))]
            _, a_day, b_day = phase
            same = [x for x in assets if x is not a and x.phase == a.phase] if a.phase else []
            slot = (b_day - a_day) * (i % (len(same) + 1)) // (len(same) + 1) if same else 0
            day = first + timedelta(days=a_day - 1 + slot)
            a.scheduled_for = datetime.combine(day, SUGGESTED_TIME.get(channel, time(10, 0))).isoformat()
            planned += 1
    return planned
