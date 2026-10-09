"""
Review context synthesis.

`strengths_mined` and `weaknesses_mined` are verbatim quotes: they say what a customer said,
not why that keeps being said, who said it, or what the merchant should do about it. This step
reads the review evidence a second time and synthesizes the context behind it -- recurring
themes, the mechanism driving each one, the buyer segments affected, and the counter-positioning
angle each theme opens up.

Runs after the display filter-validator, so it sees the final, cleaned display set and spends
tokens only on competitors that will actually be shown.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.schemas.research import (
    CompetitorProfile,
    CompetitorReviewContext,
    ReviewAspect,
    SWOTReportDelta,
)

logger = logging.getLogger(__name__)

# Domains and words that mark a passage as customer voice rather than vendor copy. A competitor's
# own landing page never explains why its buyers churn, so feeding it in just dilutes the prompt.
REVIEW_MARKERS = (
    "reddit.com",
    "trustpilot",
    "g2.com",
    "capterra",
    "amazon.com",
    "/reviews",
    "review",
    "reviewer",
    "stars",
    "star rating",
    "verified purchase",
    "customer said",
    "complaint",
    "complained",
    "refund",
    "returned it",
    "support ticket",
    "warranty",
    "would not recommend",
    "disappointed",
    "frustrat",
    "love it",
    "works great",
    "bought",
    "i use",
    "we use",
    "forum",
    "thread",
    "comment",
)

# Passage budget per LLM call. Review pages are long, so a tighter per-passage cap buys more
# distinct voices for the same context spend.
_MAX_PASSAGES = 24
_PASSAGE_CHARS = 2000

REVIEW_CONTEXT_PROMPT = """\
You are a product feedback and review intelligence analyst. You are given one competitor, the customer quotes already
mined for it, and raw review/forum passages about it. Synthesize the CONTEXT behind those
reviews for a merchant who competes with this rival. Focus strictly on product flaws, strengths, and counter-angles.

Produce, grounded strictly in the evidence given:
1. overall_sentiment_consensus - what reviewers collectively conclude about the product: why they buy it and why
   they leave. Two or three sentences, specific, no hedging.
2. top_complaint_drivers - the recurring complaint THEMES, most damaging first. For each:
   - topic: a short theme label
   - sentiment: "negative"
   - summary: the consensus finding
   - root_cause: the underlying mechanism - a product defect, a design limit, a billing or warranty policy, a
     support bottleneck. NOT a restatement of the complaint. If the evidence does not reveal a
     mechanism, leave root_cause empty rather than guessing one.
   - sample_quotes: verbatim excerpts from the evidence
   - merchant_opportunity: one concrete counter-positioning move for the merchant
3. top_praise_drivers - the same structure for what customers genuinely love (sentiment
   "positive"). These are the rival's product moats; the merchant needs to know what NOT to attack.
4. unmet_customer_needs - what product features or capabilities reviewers asked for and did not get.
5. counter_positioning_angle - the single strongest message for winning this rival's
   dissatisfied buyers, in the merchant's voice.

HARD RULES:
- Every claim must trace to the evidence given. Do not invent quotes, numbers or personas.
- Never emit filler like "N/A", "unknown", "not available" or "varies". Omit the field or
  return an empty list instead - blank renders correctly, filler is shown to the user verbatim.
- At most 4 complaint drivers and 3 praise drivers. Depth over breadth.
- If there is too little review evidence to say anything real, return empty lists.
"""


class _ReviewContextResponse(BaseModel):
    """What the LLM returns for one competitor (brand name is known from the caller)."""

    overall_sentiment_consensus: str = Field(default="")
    buyer_personas: list[str] = Field(default_factory=list)
    top_praise_drivers: list[ReviewAspect] = Field(default_factory=list)
    top_complaint_drivers: list[ReviewAspect] = Field(default_factory=list)
    unmet_customer_needs: list[str] = Field(default_factory=list)
    counter_positioning_angle: str = Field(default="")


def _names(c: CompetitorProfile) -> list[str]:
    return [n.lower() for n in (c.brand_name, c.product_name) if n and len(n) > 2]


def collect_review_passages(
    c: CompetitorProfile,
    corpus: list[str],
    limit: int = _MAX_PASSAGES,
) -> list[str]:
    """
    Passages that both name this competitor and read like customer voice.

    Two tiers: review-site and complaint-flavoured passages first, then any remaining passage
    naming the competitor, so a rival with thin review coverage still gets some context rather
    than none.
    """
    names = _names(c)
    if not names:
        return []

    primary: list[str] = []
    secondary: list[str] = []
    for text in corpus:
        if not text:
            continue
        lowered = text.lower()
        if not any(n in lowered for n in names):
            continue
        bucket = primary if any(m in lowered for m in REVIEW_MARKERS) else secondary
        bucket.append(text[:_PASSAGE_CHARS])
        if len(primary) >= limit:
            break

    return (primary + secondary)[:limit]


def _clean_aspects(aspects: list[ReviewAspect], cap: int) -> list[ReviewAspect]:
    """Drop aspects with no substance and placeholder text inside the ones that remain."""
    from orchestrator.agents.market_research.analysis.display_filter_validator import is_placeholder

    out: list[ReviewAspect] = []
    for a in aspects:
        if is_placeholder(a.topic):
            continue
        if is_placeholder(a.summary) and not a.sample_quotes:
            continue
        if is_placeholder(a.root_cause):
            a.root_cause = ""
        if is_placeholder(a.merchant_opportunity):
            a.merchant_opportunity = ""
        if is_placeholder(a.summary):
            a.summary = ""
        a.affected_personas = [p for p in a.affected_personas if not is_placeholder(p)]
        a.sample_quotes = [q for q in a.sample_quotes if not is_placeholder(q)]
        out.append(a)
    return out[:cap]


def _fallback_context(c: CompetitorProfile) -> CompetitorReviewContext | None:
    """
    Deterministic context from the quotes already mined, used when no LLM is available.

    No root causes or personas are invented: the fallback only reorganizes what is already
    verbatim in the profile, so the UI has a populated tab and nothing is fabricated.
    """
    praise, complaints = c.strengths_mined[:3], c.weaknesses_mined[:4]
    if not praise and not complaints:
        return None

    def aspect(quote: str, sentiment: str) -> ReviewAspect:
        # The quote itself is the only grounded content available without an LLM.
        return ReviewAspect(
            topic=" ".join(quote.split()[:6]).rstrip(".,;:") or "Customer feedback",
            sentiment=sentiment,
            summary=quote,
            sample_quotes=[quote],
        )

    consensus_bits = []
    if praise:
        consensus_bits.append(f"{len(c.strengths_mined)} praise point(s) mined")
    if complaints:
        consensus_bits.append(f"{len(c.weaknesses_mined)} complaint(s) mined")

    return CompetitorReviewContext(
        brand_name=c.brand_name,
        product_name=c.product_name,
        overall_sentiment_consensus=(
            "Verbatim review quotes only — " + ", ".join(consensus_bits) + "; "
            "no synthesis available for this run."
        ),
        top_praise_drivers=[aspect(q, "positive") for q in praise],
        top_complaint_drivers=[aspect(q, "negative") for q in complaints],
    )


async def _analyze_one(
    c: CompetitorProfile,
    passages: list[str],
    merchant_context: dict[str, Any],
    llm: Any,
) -> CompetitorReviewContext | None:
    merchant_keys = ("product_name", "category", "primary_value_prop", "price_usd", "target_geography")
    payload = {
        "merchant": {k: merchant_context.get(k) for k in merchant_keys if merchant_context.get(k)},
        "competitor": {
            "brand_name": c.brand_name,
            "product_name": c.product_name,
            "pricing_model": c.pricing_model,
            "rating_out_of_5": c.rating,
            "review_count": c.review_count,
            "already_mined_praise": c.strengths_mined[:10],
            "already_mined_complaints": c.weaknesses_mined[:12],
        },
        "review_evidence": passages,
    }
    response = await llm.with_structured_output(_ReviewContextResponse).ainvoke([
        {"role": "system", "content": REVIEW_CONTEXT_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ])
    if not isinstance(response, _ReviewContextResponse):
        response = _ReviewContextResponse.model_validate(response)

    from orchestrator.agents.market_research.analysis.display_filter_validator import is_placeholder

    complaints = _clean_aspects(response.top_complaint_drivers, 4)
    praise = _clean_aspects(response.top_praise_drivers, 3)
    personas = [p for p in response.buyer_personas if not is_placeholder(p)][:6]
    needs = [n for n in response.unmet_customer_needs if not is_placeholder(n)][:6]
    consensus = "" if is_placeholder(response.overall_sentiment_consensus) else response.overall_sentiment_consensus
    angle = "" if is_placeholder(response.counter_positioning_angle) else response.counter_positioning_angle

    if not any((complaints, praise, personas, needs, consensus, angle)):
        return None

    return CompetitorReviewContext(
        brand_name=c.brand_name,
        product_name=c.product_name,
        overall_sentiment_consensus=consensus,
        buyer_personas=personas,
        top_praise_drivers=praise,
        top_complaint_drivers=complaints,
        unmet_customer_needs=needs,
        counter_positioning_angle=angle,
    )


async def analyze_competitor_review_context(
    report: SWOTReportDelta,
    corpus: list[str],
    merchant_context: dict[str, Any],
    llm: Any,
) -> tuple[SWOTReportDelta, list[str]]:
    """
    Attaches `review_context` to each displayed competitor.

    One LLM call per competitor: the themes are per-rival and a single batched call either
    truncates the evidence or blurs the rivals together. A failure on one competitor leaves the
    rest intact -- the step is additive, so it never fails the run.
    """
    if not report.competitors:
        return report, []

    diagnostics: list[str] = []
    analyzed = 0
    skipped: list[str] = []

    for c in report.competitors:
        passages = collect_review_passages(c, corpus)
        if not passages and not (c.strengths_mined or c.weaknesses_mined):
            skipped.append(c.brand_name)
            continue

        context: CompetitorReviewContext | None = None
        if llm is not None and passages:
            try:
                context = await _analyze_one(c, passages, merchant_context, llm)
            except Exception as exc:
                logger.warning("Review context synthesis failed for %s: %s", c.brand_name, exc)
                diagnostics.append(
                    f"[REVIEW_CONTEXT] {c.brand_name}: synthesis skipped ({type(exc).__name__}); "
                    "falling back to mined quotes."
                )

        if context is None:
            context = _fallback_context(c)
        if context is None:
            skipped.append(c.brand_name)
            continue

        c.review_context = context
        analyzed += 1
        diagnostics.append(
            f"[REVIEW_CONTEXT] {c.brand_name}: {len(context.top_complaint_drivers)} complaint "
            f"theme(s), {len(context.top_praise_drivers)} praise theme(s), "
            f"{len(context.buyer_personas)} persona(s), {len(context.unmet_customer_needs)} unmet need(s) "
            f"from {len(passages)} review passage(s)."
        )

    if skipped:
        diagnostics.append(
            f"[REVIEW_CONTEXT] No review evidence for: {', '.join(skipped)}."
        )
    diagnostics.append(
        f"[REVIEW_CONTEXT] Review context attached to {analyzed}/{len(report.competitors)} competitors."
    )
    return report, diagnostics
