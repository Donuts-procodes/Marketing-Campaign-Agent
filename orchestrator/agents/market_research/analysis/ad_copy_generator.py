"""
Ad copy generation: ready-to-run ad concepts baked into every report.

The chat assistant can draft ad copy on request, but only for merchants who think to ask.
This step writes a handful of concepts from the finished research, each tied to the rival
weakness it exploits, so the report ends in something the merchant can launch. Each angle must
name a weakness that is actually in the research; angles that cite none are dropped.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.schemas.research import AdAngle, SWOTReportDelta

logger = logging.getLogger(__name__)

_MAX_ANGLES = 5

AD_COPY_PROMPT = """\
You write direct-response ad concepts for a merchant, using competitive research.

Write 3-5 ad angles. Each one:
- hook: a headline under 10 words, in the merchant's voice
- body: 1-2 sentences that make the claim concrete
- target_rival: the competitor whose unhappy buyers this pulls in
- format_hint: where it runs best (Google Search, Meta feed, LinkedIn, YouTube pre-roll)
- based_on_weakness: the EXACT rival complaint or gap from the research it exploits

Rules:
- Every angle must exploit a weakness listed in the input. Copy it verbatim into
  based_on_weakness.
- Do not name a competitor inside the hook or body (comparative-ad rules vary by platform).
- Only claim merchant benefits that appear in the merchant's own context.
- No filler, no "N/A".
"""


class _AdCopyResponse(BaseModel):
    angles: list[AdAngle] = Field(default_factory=list)


def _weakness_pool(report: SWOTReportDelta) -> dict[str, str]:
    """Every weakness the research supports, mapped to the rival it belongs to."""
    pool: dict[str, str] = {}
    for c in report.competitors:
        rc = c.review_context
        if rc:
            for a in rc.top_complaint_drivers:
                pool.setdefault(a.topic, c.brand_name)
            for need in rc.unmet_customer_needs:
                pool.setdefault(need, c.brand_name)
        for w in c.weaknesses_mined[:4]:
            pool.setdefault(w, c.brand_name)
    return pool


def _grounded(angle: AdAngle, pool: dict[str, str]) -> bool:
    cited = angle.based_on_weakness.strip().lower()
    if not cited or not angle.hook.strip():
        return False
    return any(cited in w.lower() or w.lower() in cited for w in pool)


def fallback_angles(report: SWOTReportDelta) -> list[AdAngle]:
    """Template angles from the top complaint themes; used when no LLM is available."""
    angles: list[AdAngle] = []
    for c in sorted(report.competitors, key=lambda c: c.relevance_score, reverse=True):
        rc = c.review_context
        if not rc or not rc.top_complaint_drivers:
            continue
        aspect = rc.top_complaint_drivers[0]
        if not aspect.merchant_opportunity:
            continue
        angles.append(AdAngle(
            hook=f"Tired of {aspect.topic.lower()}?",
            body=aspect.merchant_opportunity,
            target_rival=c.brand_name,
            format_hint="Google Search",
            based_on_weakness=aspect.topic,
        ))
        if len(angles) >= 2:
            break
    return angles


async def generate_ad_angles(
    report: SWOTReportDelta,
    merchant_context: dict[str, Any],
    llm: Any,
) -> tuple[SWOTReportDelta, list[str]]:
    pool = _weakness_pool(report)
    if not pool:
        return report, ["[AD_COPY] No rival weaknesses in the research to build angles on."]

    angles: list[AdAngle] = []
    source = "template"
    if llm is not None:
        merchant_keys = ("product_name", "category", "primary_value_prop", "price_usd", "target_geography", "goal")
        payload = {
            "merchant": {k: merchant_context.get(k) for k in merchant_keys if merchant_context.get(k)},
            "rival_weaknesses": [{"weakness": w, "rival": r} for w, r in list(pool.items())[:20]],
            "market_gap": report.positioning_gap.model_dump() if report.positioning_gap else None,
        }
        try:
            result = await llm.with_structured_output(_AdCopyResponse).ainvoke([
                {"role": "system", "content": AD_COPY_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ])
            if not isinstance(result, _AdCopyResponse):
                result = _AdCopyResponse.model_validate(result)
            angles = [a for a in result.angles if _grounded(a, pool)][:_MAX_ANGLES]
            source = "LLM"
        except Exception as exc:
            logger.warning("Ad copy LLM call failed: %s", exc)

    if not angles:
        angles = fallback_angles(report)
        source = "template"

    report.suggested_ad_angles = angles
    return report, [f"[AD_COPY] {len(angles)} grounded ad angle(s) generated ({source})."]
