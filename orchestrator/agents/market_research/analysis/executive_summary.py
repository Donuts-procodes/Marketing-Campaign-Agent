"""
Executive summary, written last.

The relevance filter drafts `dashboard_insights.executive_summary` in Phase 7, before the
display validator repairs pricing, before prices are parsed and before review context exists.
So the summary often said a price was unknown that the next step found, and could never name
why buyers leave a rival. This step rewrites it from the finished data. The relevance filter's
draft is kept whenever this step cannot do better.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.schemas.research import CompetitorProfile, DashboardInsights, SWOTReportDelta

logger = logging.getLogger(__name__)

EXEC_SUMMARY_PROMPT = """\
Write the executive summary a merchant reads first on their competitive dashboard.

Exactly 2-3 sentences, plain and specific. Cover, in this order where the data supports it:
1. The price landscape: who is cheapest and most expensive, with the actual figures.
2. The biggest threat and the one-line reason it matters.
3. The single best opening for the merchant: a rival weakness or market gap to act on now.

Rules:
- Use only the data given. Name competitors and numbers; never invent either.
- No openers like "Overall", "In summary" or "The competitive landscape is".
- No filler such as "N/A" or "unknown". If a point has no data, skip that point.
"""


class _SummaryResponse(BaseModel):
    summary: str = Field(default="")


def _rival_brief(c: CompetitorProfile) -> dict[str, Any]:
    rc = c.review_context
    out = {
        "name": c.brand_name,
        "price": c.pricing_model,
        "monthly_price": c.pricing_parsed.monthly_equivalent if c.pricing_parsed else None,
        "relevance": round(c.relevance_score, 2),
        "why_it_matters": c.relevance_reason or None,
        "top_complaint": (
            rc.top_complaint_drivers[0].topic
            if rc and rc.top_complaint_drivers
            else (c.weaknesses_mined[0] if c.weaknesses_mined else None)
        ),
        "counter_angle": rc.counter_positioning_angle if rc else None,
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def fallback_summary(report: SWOTReportDelta) -> str:
    """Deterministic summary from the finished data; used when no LLM is available."""
    comps = sorted(report.competitors, key=lambda c: c.relevance_score, reverse=True)
    if not comps:
        return ""
    sentences: list[str] = []

    priced = [c for c in comps if c.pricing_parsed and c.pricing_parsed.monthly_equivalent]
    if len(priced) >= 2:
        lo = min(priced, key=lambda c: c.pricing_parsed.monthly_equivalent)
        hi = max(priced, key=lambda c: c.pricing_parsed.monthly_equivalent)
        if lo is not hi:
            sentences.append(
                f"Monthly pricing runs from {lo.pricing_model} ({lo.brand_name}) "
                f"to {hi.pricing_model} ({hi.brand_name})."
            )

    top = comps[0]
    reason = f": {top.relevance_reason.rstrip('.')}" if top.relevance_reason else ""
    sentences.append(f"{top.brand_name} is the closest rival{reason}.")

    rc = top.review_context
    if rc and rc.top_complaint_drivers:
        sentences.append(f"Its customers most often complain about {rc.top_complaint_drivers[0].topic.lower()}.")
    elif report.positioning_gap:
        sentences.append(f"No rival covers the {report.positioning_gap.quadrant} position.")
    return " ".join(sentences)


async def write_executive_summary(
    report: SWOTReportDelta,
    merchant_context: dict[str, Any],
    llm: Any,
) -> tuple[SWOTReportDelta, list[str]]:
    if not report.competitors:
        return report, []

    summary = ""
    source = "rule-based"
    if llm is not None:
        merchant_keys = ("product_name", "category", "primary_value_prop", "price_usd", "target_geography")
        top = sorted(report.competitors, key=lambda c: c.relevance_score, reverse=True)[:5]
        payload = {
            "merchant": {k: merchant_context.get(k) for k in merchant_keys if merchant_context.get(k)},
            "rivals": [_rival_brief(c) for c in top],
            "market_gap": report.positioning_gap.model_dump() if report.positioning_gap else None,
            "swot_opportunities": report.swot.opportunities[:4],
            "swot_threats": report.swot.threats[:4],
        }
        try:
            result = await llm.with_structured_output(_SummaryResponse).ainvoke([
                {"role": "system", "content": EXEC_SUMMARY_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ])
            if not isinstance(result, _SummaryResponse):
                result = _SummaryResponse.model_validate(result)
            summary = result.summary.strip()
            source = "LLM"
        except Exception as exc:
            logger.warning("Executive summary LLM call failed: %s", exc)

    if not summary:
        # Prefer the relevance filter's draft over the template: it was written by a model
        # that saw the merchant's context, the template only restates the data.
        existing = report.dashboard_insights.executive_summary if report.dashboard_insights else ""
        if existing:
            return report, ["[EXEC_SUMMARY] Kept the relevance filter's summary."]
        summary = fallback_summary(report)

    if not summary:
        return report, ["[EXEC_SUMMARY] Not enough data for a summary."]
    if report.dashboard_insights is None:
        report.dashboard_insights = DashboardInsights()
    report.dashboard_insights.executive_summary = summary
    return report, [f"[EXEC_SUMMARY] Summary written from final data ({source})."]
