"""
Messaging: positioning statement, core message and messaging pillars.

The plan says where to spend and what to test; this says what to say. It is written from the
opening the research found (wedge scan, unclaimed market positions, rival complaints), the
primary persona's pains and the merchant's own value proposition. Each pillar names the proof it
needs; when the merchant's brief does not hold that proof the pillar is marked `needs_proof` so
the content step writes a placeholder instead of a promise.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.schemas.strategy import MessagingPillar, MessagingStrategy

logger = logging.getLogger(__name__)

PROMPT = """\
Write the messaging for this campaign:
- positioning: one sentence — for [primary persona], [product] is the [category] that [key \
difference], unlike [the alternative they use now].
- core_message: the one line every asset carries (under 15 words, buyer's language).
- pillars: exactly 3. Each has a title (2-5 words), a one-sentence message, the proof that backs \
it, and needs_proof=true when the merchant brief does not already contain that proof.

Ground everything in the inputs: the opening comes from the research, the pains from real \
customer reviews, the difference from the merchant's own value proposition. Never invent \
numbers, guarantees or awards.
"""


class _Messaging(BaseModel):
    positioning: str = ""
    core_message: str = ""
    pillars: list[MessagingPillar] = Field(default_factory=list)


def _inputs(merchant_context: dict[str, Any], swot_report: Any, personas: list[Any]) -> dict[str, Any]:
    market = getattr(swot_report, "market_overview", None)
    audience = getattr(swot_report, "audience", None)
    wedge = getattr(swot_report, "wedge_scan", None)
    gap = getattr(swot_report, "positioning_gap", None)
    primary = next((p for p in personas if getattr(p, "role", None) == "primary"), personas[0] if personas else None)
    counter = [
        c.review_context.counter_positioning_angle
        for c in getattr(swot_report, "competitors", None) or []
        if c.review_context and c.review_context.counter_positioning_angle
    ][:3]
    keys = ("product_name", "category", "primary_value_prop", "price", "currency", "goal", "products")
    return {
        "merchant_brief": {k: merchant_context.get(k) for k in keys if merchant_context.get(k)},
        "primary_persona": primary.model_dump(include={"name", "description", "pains", "motivations", "objections"})
        if primary else None,
        "opening": wedge.wedge if wedge and wedge.wedge else None,
        "unclaimed_position": gap.model_dump() if gap else None,
        "market_opportunities": [p.text for p in market.positioning_opportunities][:4] if market else [],
        "customer_pains": [p.text for p in audience.pains][:5] if audience else [],
        "preferred_message": audience.preferred_message if audience else "",
        "counter_angles_from_reviews": counter,
    }


async def write_messaging(
    merchant_context: dict[str, Any], swot_report: Any, personas: list[Any], llm: Any
) -> MessagingStrategy | None:
    if llm is None:
        return None
    try:
        result = await llm.with_structured_output(_Messaging).ainvoke([
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(_inputs(merchant_context, swot_report, personas),
                                                   ensure_ascii=False, default=str)},
        ])
        if not isinstance(result, _Messaging):
            result = _Messaging.model_validate(result)
    except Exception as exc:
        logger.warning("Messaging step failed: %s", exc)
        return None
    if not result.core_message.strip():
        return None
    return MessagingStrategy(
        positioning=result.positioning.strip(),
        core_message=result.core_message.strip(),
        pillars=[p for p in result.pillars if p.title.strip()][:3],
    )
