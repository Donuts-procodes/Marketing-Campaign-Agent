"""
LLM-powered dashboard relevance filter.

Post-synthesis step: scores each competitor by relevance to the merchant and curates
which data points are most useful for the dashboard view. The full dataset remains
available; this layer decides what to highlight by default.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.agents.market_research.intelligence.validation.grounding import is_supported_by
from orchestrator.schemas.research import (
    CompetitorProfile,
    CompetitorRelevance,
    DashboardInsights,
    SWOTReportDelta,
)

logger = logging.getLogger(__name__)

# How many heuristic-ranked candidates the category judge sees. Past ~20 the tail is
# directories and one-mention noise; the prompt cost grows and the picks do not change.
_CATEGORY_JUDGE_POOL = 20
# Below this a candidate is not in the merchant's category and never makes the shortlist.
_CATEGORY_FIT_FLOOR = 0.4


class _CategoryFit(BaseModel):
    competitor_relevance: list[CompetitorRelevance] = Field(default_factory=list)


CATEGORY_FIT_PROMPT = """\
You are vetting a competitor shortlist for one merchant. For EVERY candidate, by its 0-based \
index, give a score 0.0-1.0 for how directly it competes with the merchant, and one short reason.

- 1.0: sells the same kind of product/service to the same kind of customer
- 0.7: same category, somewhat different segment, scale or offering
- 0.4: adjacent category; a buyer would rarely compare the two
- <0.4: not a competitor at all: a directory or listing site (Clutch, G2, Yelp), a blog or \
publisher, a job board, a placeholder site, a vendor that sells TO this industry, or a \
different category entirely

Judge only from what is given. Do not invent facts about a candidate."""


async def rank_by_category_fit(
    candidates: list[CompetitorProfile],
    merchant_context: dict[str, Any],
    llm: Any,
) -> list[CompetitorProfile]:
    """
    Re-orders candidates by how squarely they sit in the merchant's category. The heuristic
    ranking counts mentions and evidence, so a directory site or a frequently-mentioned firm
    in a neighbouring category could take a shortlist slot. Candidates the judge scores below
    the floor drop behind every in-category one. On any failure the input order is returned.
    """
    pool = candidates[:_CATEGORY_JUDGE_POOL]
    if llm is None or len(pool) < 2:
        return candidates

    listing = [
        {
            "index": i,
            "name": c.product_name,
            "brand": c.brand_name,
            "website": (c.sources or [""])[0],
            "about": (c.core_claims or c.factual_evidence or [""])[0][:200],
        }
        for i, c in enumerate(pool)
    ]
    merchant = {
        k: merchant_context.get(k)
        for k in ("product_name", "category", "description", "target_geography", "business_model")
        if merchant_context.get(k)
    }
    try:
        result = await llm.with_structured_output(_CategoryFit).ainvoke([
            {"role": "system", "content": CATEGORY_FIT_PROMPT},
            {
                "role": "user",
                "content": f"## Merchant\n{json.dumps(merchant, indent=2)}\n\n"
                f"## Candidates\n{json.dumps(listing, indent=2)}",
            },
        ])
    except Exception as exc:
        logger.warning("Category-fit judge failed, keeping heuristic order: %s", exc)
        return candidates

    scores: dict[int, float] = {}
    for item in getattr(result, "competitor_relevance", []) or []:
        if 0 <= item.index < len(pool):
            scores[item.index] = item.score
            pool[item.index].relevance_score = item.score
            if item.reason:
                pool[item.index].relevance_reason = item.reason
    if not scores:
        return candidates

    ranked = sorted(range(len(pool)), key=lambda i: (-scores.get(i, _CATEGORY_FIT_FLOOR), i))
    fits = [pool[i] for i in ranked if scores.get(i, _CATEGORY_FIT_FLOOR) >= _CATEGORY_FIT_FLOOR]
    misfits = {pool[i].product_name for i in ranked if scores.get(i, _CATEGORY_FIT_FLOOR) < _CATEGORY_FIT_FLOOR}
    tail = [c for c in candidates[_CATEGORY_JUDGE_POOL:] if c.product_name not in misfits]
    if fits:
        return fits + tail
    return pool[:1] + tail

RELEVANCE_SYSTEM_PROMPT = """\
You are a strategic intelligence analyst curating a dashboard for a specific merchant.

Given the merchant's context and a completed competitive intelligence report, your job is to:

1. SCORE EACH COMPETITOR via competitor_relevance — one entry for EVERY competitor, using its \
0-based index, a score from 0.0 to 1.0, and a one-sentence reason the merchant would find useful:
   - 1.0 = direct head-to-head rival in the same market segment, price tier, and geography
   - 0.7+ = strong competitor the merchant needs to track
   - 0.4–0.6 = tangentially relevant, different segment or scale
   - <0.4 = noise — enterprise incumbents the merchant does not compete with, or unrelated products
   Scale matters: a firm orders of magnitude larger than the merchant is not a head-to-head rival, \
   however famous it is.

2. SELECT PRIMARY COMPETITORS: indices (0-based) of the 2-4 most relevant competitors to highlight \
by default. Every index MUST be a real index from the list you were given.

3. PRODUCE AN EXECUTIVE SUMMARY: 2-3 sentences written directly to the merchant explaining \
their competitive landscape — who matters, where they're vulnerable, and the merchant's best angle.

4. HIGHLIGHT WEAKNESSES: Pick the 3-5 most exploitable competitor weaknesses that the merchant \
can realistically act on (not generic complaints, but actionable friction points). SELECT these \
from the weaknesses_mined you were given and keep their wording — these came from real user \
complaints, and a rewritten one is dropped by an automated check.

5. HIGHLIGHT OPPORTUNITIES: 2-3 immediate market opportunities the merchant should act on, \
based on gaps you see in competitor coverage.

6. PRIORITY ATTRIBUTES: Which 3-5 dynamic taxonomy attributes matter most for this merchant's \
differentiation story. Only pick attributes where the merchant can credibly outperform.

7. RECOMMENDED ACTIONS: 3-5 concrete, specific next steps the merchant should take this week \
(e.g. "Launch a comparison landing page targeting [competitor]'s pricing complaints" not \
"improve marketing").

IMPORTANT: Be ruthlessly practical. A merchant using this dashboard wants to know "what do I \
do with this?" not "here is a summary of what we found." Every item should be actionable.
"""


async def curate_dashboard_insights(
    report: SWOTReportDelta,
    merchant_context: dict[str, Any],
    llm: Any,
) -> DashboardInsights:
    """
    Calls the LLM to score competitor relevance and curate the merchant dashboard.
    Returns a DashboardInsights that the frontend uses to filter the default view.
    """
    structured_llm = llm.with_structured_output(DashboardInsights, method="function_calling")

    competitor_summaries = []
    for i, comp in enumerate(report.competitors):
        competitor_summaries.append({
            "index": i,
            "brand_name": comp.brand_name,
            "product_name": comp.product_name,
            "pricing_model": comp.pricing_model,
            "core_claims": comp.core_claims[:3],
            "weaknesses_mined": comp.weaknesses_mined[:3],
            "ad_hooks": comp.ad_hooks[:2] if comp.ad_hooks else [],
        })

    taxonomy_context = ""
    if report.dynamic_taxonomy:
        taxonomy_context = (
            f"Dynamic Attributes: {', '.join(report.dynamic_taxonomy.critical_jtbd_drivers[:8])}\n"
        )

    swot_context = ""
    if report.swot:
        swot_context = (
            f"SWOT Strengths: {'; '.join(report.swot.strengths[:3])}\n"
            f"SWOT Opportunities: {'; '.join(report.swot.opportunities[:3])}\n"
        )

    positioning_context = ""
    if report.positioning_gap:
        positioning_context = (
            f"Positioning Gap: {report.positioning_gap.quadrant} — "
            f"{report.positioning_gap.hook_angle}\n"
        )

    user_message = (
        f"## Merchant Context\n"
        f"{json.dumps(merchant_context, indent=2)}\n\n"
        f"## Competitors ({len(report.competitors)} discovered)\n"
        f"{json.dumps(competitor_summaries, indent=2)}\n\n"
        f"{taxonomy_context}"
        f"{swot_context}"
        f"{positioning_context}\n"
        f"Score each competitor's relevance and produce the DashboardInsights."
    )

    result = await structured_llm.ainvoke([
        {"role": "system", "content": RELEVANCE_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ])

    if isinstance(result, DashboardInsights):
        return result
    return DashboardInsights.model_validate(result)


#: Ceiling for a competitor the model did not mark primary, so a secondary rival can never
#: outrank a primary one however it was scored.
_SECONDARY_CEILING = 0.6
_SECONDARY_FLOOR = 0.3


def apply_relevance_scores(
    report: SWOTReportDelta,
    insights: DashboardInsights,
    grounding_texts: list[str] | None = None,
    prune_irrelevant: bool = False,
) -> SWOTReportDelta:
    """
    Applies the model's relevance judgement to each competitor profile and reorders the
    dashboard so the rivals that matter come first.

    Per-competitor scores from the model are used when given; otherwise a rank-based decay
    fills in. Scores are clamped to the schema's [0, 1] bound and primaries always outrank
    secondaries. Indices the model invented are ignored rather than silently emptying the
    primary set.

    When `prune_irrelevant` is True (default), competitors judged < 0.4 (unrelated products
    or different categories, e.g. leather jackets for a footwear merchant) are pruned from
    the final report unless explicitly named by the merchant.
    """
    total = len(report.competitors)
    if total == 0:
        report.dashboard_insights = insights
        return report

    # Drop hallucinated/out-of-range indices instead of letting them erase the primary set.
    valid_primary = [i for i in dict.fromkeys(insights.primary_competitor_indices) if 0 <= i < total]
    dropped_indices = len(set(insights.primary_competitor_indices)) - len(valid_primary)
    if dropped_indices:
        logger.warning(
            "Relevance filter returned %d out-of-range competitor index/indices (have %d); ignoring them",
            dropped_indices,
            total,
        )

    scored_by_index = {
        r.index: r for r in insights.competitor_relevance if 0 <= r.index < total
    }

    # No usable primaries: fall back to the model's own top scores, else the existing order.
    if not valid_primary:
        if scored_by_index:
            ranked = sorted(scored_by_index.values(), key=lambda r: r.score, reverse=True)
            valid_primary = [r.index for r in ranked[: min(3, total)]]
        else:
            valid_primary = list(range(min(3, total)))

    primary_set = set(valid_primary)

    for i, comp in enumerate(report.competitors):
        judged = scored_by_index.get(i)
        if judged is not None:
            comp.relevance_reason = judged.reason
        if i in primary_set:
            # A primary rival keeps the model's score but never ranks below a secondary one.
            comp.relevance_score = (
                max(judged.score, _SECONDARY_CEILING) if judged else 1.0
            )
        elif judged is not None:
            comp.relevance_score = min(judged.score, _SECONDARY_CEILING)
        else:
            # Rank-based decay within the secondary group — never negative, never above the
            # ceiling, and independent of where the primaries happened to land.
            rank = sum(1 for j in range(i) if j not in primary_set)
            comp.relevance_score = max(_SECONDARY_FLOOR, _SECONDARY_CEILING - rank * 0.1)

    if grounding_texts:
        insights.highlight_weaknesses = _keep_grounded_weaknesses(
            insights.highlight_weaknesses, grounding_texts
        )

    report.dashboard_insights = insights

    primary = [c for i, c in enumerate(report.competitors) if i in primary_set]
    secondary = [c for i, c in enumerate(report.competitors) if i not in primary_set]
    primary.sort(key=lambda c: c.relevance_score, reverse=True)
    secondary.sort(key=lambda c: c.relevance_score, reverse=True)

    if prune_irrelevant:
        # Strictly evict competitors scored below the category floor (<0.4, classified as noise or
        # different categories entirely), unless explicitly named by the merchant.
        def _is_relevant(c: CompetitorProfile) -> bool:
            if getattr(c, "named_by_merchant", False):
                return True
            if c.relevance_score is None:
                return True
            return c.relevance_score >= _CATEGORY_FIT_FLOOR

        kept = [c for c in primary + secondary if _is_relevant(c)]
        if kept:
            primary = [c for c in primary if c in kept]
            secondary = [c for c in secondary if c in kept]
        else:
            primary = (primary + secondary)[:1]
            secondary = []

    report.competitors = primary + secondary

    # Indices refer to positions, so they must be restated after the reorder.
    report.dashboard_insights.primary_competitor_indices = list(range(len(primary)))

    return report


def _keep_grounded_weaknesses(highlights: list[str], grounding_texts: list[str]) -> list[str]:
    """
    Keeps only highlighted weaknesses that restate something a source actually said.

    The curation step is asked to pick the most exploitable weaknesses, and a model asked to
    pick will sometimes rewrite. Everything else in the report passes the factual gate before
    display; this keeps the dashboard's headline panel to the same standard.
    """
    kept = [w for w in highlights if is_supported_by(w, grounding_texts)]
    dropped = len(highlights) - len(kept)
    if dropped:
        logger.warning(
            "[FACTUAL_GUARD] Dropped %d highlighted weakness(es) not supported by mined complaints",
            dropped,
        )
    return kept
