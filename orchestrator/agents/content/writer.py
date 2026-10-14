"""
Content writer: turns an approved strategy into channel assets.

Each channel in the approved plan gets the assets its role needs (an email sequence, a couple of
posts, a champion and a challenger ad, a search ad), written from the plan's message tests, the
audience's pains and preferred message, and the rival gaps the strategy leans on. Nothing is
written without a model, and no claim goes in that the merchant's brief or the research does not
support: proof the brief lacks becomes a placeholder like [add delivery time] for the merchant
to fill, not an invented promise.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.core.clock import today as clock_today
from orchestrator.schemas.content import ContentAsset, ContentPack
from orchestrator.schemas.research import SWOTReportDelta
from orchestrator.schemas.strategy import CampaignStrategyBrief

logger = logging.getLogger(__name__)

# Plan channel text -> channel key. First match wins, so ads come before their organic platform.
_CHANNEL_RULES: list[tuple[str, str]] = [
    (r"google|search ads?|\bsem\b|\bppc\b", "google_ads"),
    (r"meta ads?|facebook ads?|instagram ads?|retarget", "meta_ads"),
    (r"e-?mail|newsletter|klaviyo|mailchimp", "email"),
    (r"linkedin", "linkedin"),
    (r"instagram|reels", "instagram"),
    (r"facebook", "facebook"),
    (r"whatsapp", "whatsapp"),
    (r"\bx\b|twitter", "x"),
]

# What each channel gets: (kind, how many, guidance)
_PLAYBOOK: dict[str, tuple[str, int, str]] = {
    "email": ("email", 3, "A short sequence: introduce, prove, last call. Subject ≤ 60 chars, preview ≤ 90, body ≤ 180 words, one CTA."),
    "linkedin": ("post", 2, "Professional tone, a hook in the first line, ≤ 150 words, one CTA."),
    "instagram": ("post", 2, "Caption ≤ 120 words, hook first, 3-6 relevant hashtags, and a creative_brief for the image or reel."),
    "facebook": ("post", 2, "Caption ≤ 100 words, conversational, one CTA, plus a creative_brief."),
    "meta_ads": ("ad", 2, "One ad per message test (champion, challenger): primary text ≤ 125 chars as body, a headline ≤ 40 chars in headlines[0], a CTA, and a creative_brief."),
    "google_ads": ("search_ad", 1, "Responsive search ad: 8-15 headlines of ≤ 30 characters and 2-4 descriptions of ≤ 90 characters."),
    "whatsapp": ("message", 2, "Broadcast message ≤ 60 words, personal, one link CTA."),
    "x": ("post", 2, "≤ 260 characters, one CTA."),
}

PROMPT = """\
You write campaign content for one channel from an approved strategy. Write in the merchant's \
voice for their market and currency.

Rules:
- Lead with the strategy's positioning and the assigned message tests; each asset should test \
one message.
- Speak to the persona's real pains (from customer reviews of rivals) and the preferred message.
- Claims must come from the merchant brief. If a strong claim needs proof the brief lacks \
(delivery time, warranty, discount), write a placeholder in square brackets, e.g. [add warranty \
period], instead of inventing it.
- Never name competitors negatively. No fake urgency, no invented prices or discounts.
- Follow the channel guidance exactly, including character limits.
"""


class _Draft(BaseModel):
    name: str = ""
    persona_id: str | None = None
    phase: str | None = None
    subject: str | None = None
    preview_text: str | None = None
    body: str = ""
    headlines: list[str] = Field(default_factory=list)
    descriptions: list[str] = Field(default_factory=list)
    cta: str | None = None
    creative_brief: str | None = None
    hashtags: list[str] = Field(default_factory=list)


class _Drafts(BaseModel):
    assets: list[_Draft] = Field(default_factory=list)


def channel_key(text: str) -> str | None:
    low = (text or "").lower()
    return next((key for pattern, key in _CHANNEL_RULES if re.search(pattern, low)), None)


def plan_channels(brief: CampaignStrategyBrief) -> list[tuple[str, list[str]]]:
    """(channel key, plan channel names it covers), in plan order, from the plan or the channel matrix."""
    names: list[str] = []
    if brief.plan and brief.plan.channels:
        names = [c.channel for c in brief.plan.channels]
    elif brief.channel_matrix:
        names = [getattr(c, "channel", "") or getattr(c, "channel_name", "") for c in brief.channel_matrix]
    names += list(brief.suggested_channels or [])
    out: dict[str, list[str]] = {}
    for n in names:
        if key := channel_key(n):
            out.setdefault(key, []).append(n)
    return list(out.items())


def _context(brief: CampaignStrategyBrief, report: SWOTReportDelta | None, merchant_context: dict[str, Any]) -> dict[str, Any]:
    plan = brief.plan
    audience = report.audience if report else None
    keys = ("product_name", "category", "primary_value_prop", "price", "currency", "target_geography",
            "products", "goal", "sales_channel")
    return {
        "merchant_brief": {k: merchant_context.get(k) for k in keys if merchant_context.get(k)},
        "positioning": (brief.messaging.positioning if brief.messaging and brief.messaging.positioning
                        else brief.primary_positioning_pillar),
        "core_message": brief.messaging.core_message if brief.messaging else "",
        "pillars": [p.model_dump() for p in brief.messaging.pillars] if brief.messaging else [],
        "core_goal": brief.core_goal,
        "message_tests": [t.model_dump(include={"test_id", "persona_id", "angle", "hook", "cta", "role"})
                          for t in (plan.message_tests if plan else [])][:6],
        "personas": [p.model_dump(include={"persona_id", "name", "pains", "motivations", "buying_triggers"})
                     for p in brief.personas_used][:3],
        "phases": [p.model_dump(include={"name", "days", "objective"}) for p in (plan.phases if plan else [])],
        "preferred_message": audience.preferred_message if audience else "",
        "customer_pains": [p.text for p in audience.pains][:5] if audience else [],
        "rival_gaps": [p.text for p in report.market_overview.positioning_opportunities][:4]
        if report and report.market_overview else [],
        "currency": brief.currency,
    }


def _clip(values: list[str], limit: int, count: int) -> list[str]:
    out = []
    for v in values:
        v = v.strip()
        if v and len(v) <= limit and v not in out:
            out.append(v)
    return out[:count]


def _to_asset(d: _Draft, key: str, kind: str, n: int) -> ContentAsset:
    headlines, descriptions = d.headlines, d.descriptions
    if kind == "search_ad":
        headlines, descriptions = _clip(headlines, 30, 15), _clip(descriptions, 90, 4)
    return ContentAsset(
        asset_id=f"{key}-{uuid.uuid4().hex[:8]}",
        channel=key,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        name=d.name.strip() or f"{key.replace('_', ' ').title()} {n}",
        persona_id=d.persona_id,
        phase=d.phase,
        subject=d.subject,
        preview_text=d.preview_text,
        body=d.body.strip(),
        headlines=headlines,
        descriptions=descriptions,
        cta=d.cta,
        creative_brief=d.creative_brief,
        hashtags=[h if h.startswith("#") else f"#{h}" for h in d.hashtags][:8],
    )


async def _write_channel(llm: Any, key: str, plan_names: list[str], ctx: dict[str, Any],
                         instruction: str | None = None, previous: ContentAsset | None = None) -> list[_Draft]:
    kind, count, guidance = _PLAYBOOK[key]
    if previous is not None:
        count = 1
    task = {
        "channel": key,
        "plan_lines": plan_names,
        "write": f"{count} {kind}(s)",
        "guidance": guidance,
        "strategy": ctx,
    }
    if previous is not None:
        task["rewrite_this"] = previous.model_dump(exclude={"status", "external_id", "error", "scheduled_for"})
        task["change_request"] = instruction or "Write a stronger alternative."
    result = await llm.with_structured_output(_Drafts).ainvoke([
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": json.dumps(task, ensure_ascii=False, default=str)},
    ])
    if not isinstance(result, _Drafts):
        result = _Drafts.model_validate(result)
    return result.assets[:count]


async def write_content(
    brief: CampaignStrategyBrief,
    report: SWOTReportDelta | None,
    merchant_context: dict[str, Any],
    llm: Any,
) -> ContentPack:
    pack = ContentPack(generated_at=clock_today().isoformat())
    if llm is None:
        pack.notes.append("Content needs a language model; none is configured.")
        return pack
    channels = [(k, names) for k, names in plan_channels(brief) if k in _PLAYBOOK]
    if not channels:
        pack.notes.append("The approved strategy names no channel we can write for.")
        return pack
    ctx = _context(brief, report, merchant_context)
    results = await asyncio.gather(
        *(_write_channel(llm, key, names, ctx) for key, names in channels), return_exceptions=True
    )
    for (key, _), drafts in zip(channels, results):
        if isinstance(drafts, BaseException):
            logger.warning("Content for %s failed: %s", key, drafts)
            pack.notes.append(f"Could not write {key.replace('_', ' ')} content ({type(drafts).__name__}).")
            continue
        kind = _PLAYBOOK[key][0]
        pack.assets += [_to_asset(d, key, kind, i + 1) for i, d in enumerate(drafts)]
    return pack


async def rewrite_asset(
    asset: ContentAsset,
    brief: CampaignStrategyBrief,
    report: SWOTReportDelta | None,
    merchant_context: dict[str, Any],
    llm: Any,
    instruction: str | None = None,
) -> ContentAsset:
    drafts = await _write_channel(llm, asset.channel, [], _context(brief, report, merchant_context),
                                  instruction=instruction, previous=asset)
    if not drafts:
        raise ValueError("The model returned no rewrite.")
    new = _to_asset(drafts[0], asset.channel, asset.kind, 1)
    return new.model_copy(update={"asset_id": asset.asset_id, "revision": asset.revision + 1,
                                  "name": new.name or asset.name})
