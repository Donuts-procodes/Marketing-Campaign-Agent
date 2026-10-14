"""
Commercial Buying Pattern & Strategy Reverse-Engineering Engine.

For physical product, e-commerce, and D2C brands, competitors never publish a written
"marketing strategy". Their true marketing strategy is deduced from observable commercial patterns:
  1. Where are they selling? (Sales channels: Brand D2C, Amazon, Marketplaces, Retail)
  2. For what cost? (Unit economics: SKU tiers, bundles, discounts, free shipping thresholds)
  3. How much are they selling? (Sales velocity: "1k+ bought", review accumulation, BSR badges)
  4. Pattern of buying? (Buyer triggers: Sizing assurance, return/wear-test policies, warranty)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.agents.market_research.intelligence.advisory.archetype import (
    resolve as resolve_archetype,
)
from orchestrator.agents.market_research.ingestion.source_types import mentions, search_names
from orchestrator.schemas.research import (
    BuyingPatternIntelligence,
    CompetitorProfile,
    SWOTReportDelta,
)

logger = logging.getLogger(__name__)

BUYING_PATTERN_SYSTEM_PROMPT = """\
You are an expert commercial and merchandising strategist covering both D2C e-commerce and B2B SaaS/services. \
For the given competitor, analyze their verified scraped web extracts, pricing, product pages, and customer reviews.

Do NOT look for or invent a corporate "written marketing strategy". \
Instead, REVERSE-ENGINEER their real customer acquisition, merchandising, and procurement motions from observable facts:

1. sales_channels: Where do they sell? (e.g. "Brand Website / D2C Store", "Amazon Storefront", "Partner Ecosystem", "Self-Serve Portal", "Inside Sales / SDR").
2. price_architecture: Key price points and structures (e.g. entry SKU / tier price, flagship SKU / enterprise floor, bundles, or volume overage rates).
3. promotional_incentives: Active buyer incentives (e.g. "15% off first order", "Free shipping over $100", "20% off annual pre-pay", "Free migration").
4. sales_velocity_signals: Observable scale or momentum indicators from evidence (e.g. "1k+ bought in past month", "Amazon Best Seller #1", "10,000+ verified customer reviews", "G2 Leader badge").
5. buying_triggers: Key friction-removers that make buyers sign up (e.g. "30-day wear test guarantee", "Instant self-serve sandbox", "Free trial no credit card", "Cancel anytime").
6. trial_structure: B2B trial/pilot mechanics when applicable (e.g. "14-day free trial no CC", "Interactive demo sandbox", "Paid pilot with SLA").
7. procurement_hurdles: Documented buyer obstacles (e.g. "Mandatory annual contract", "Security compliance / SOC2 questionnaire gate", "Book a demo wall").
8. contract_incentives: Commitments or sweeteners (e.g. "Annual contract discount", "Quarterly true-up", "Custom SLA / MSA redlining").
9. reverse_engineered_strategy: A 2-3 sentence strategic synthesis describing their real commercial playbook.

Base everything on the provided passages. Do not invent facts. If a specific dimension has no data in the passages, leave its list empty or null.
"""


class _SingleCompetitorPattern(BaseModel):
    brand_name: str
    buying_pattern: BuyingPatternIntelligence


class _CompetitorBuyingPatternBundle(BaseModel):
    patterns_by_competitor: list[_SingleCompetitorPattern] = Field(default_factory=list)


def _extract_relevant_passages(comp: CompetitorProfile, corpus: list[str], max_passages: int = 10) -> list[str]:
    """Finds corpus excerpts naming this competitor that contain commerce, pricing, or review signals."""
    names = search_names(comp.brand_name) or [comp.brand_name]
    keywords = (
        "price", "mrp", "msrp", "buy", "shop", "shipping", "discount", "order",
        "amazon", "store", "seller", "reviews", "return", "policy", "warranty",
        "fit", "sizing", "bundle", "cart", "offer", "sale", "trial", "demo",
        "annual", "monthly", "seat", "contract", "tier", "plan", "procurement"
    )

    scored: list[tuple[int, str]] = []
    for text in corpus:
        if not text or not mentions(text, names):
            continue
        text_lower = text.lower()
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scored.append((score, text))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:max_passages]]


async def analyze_buying_patterns(
    report: SWOTReportDelta,
    corpus: list[str],
    merchant_context: dict[str, Any],
    llm: Any,
) -> tuple[SWOTReportDelta, list[str]]:
    """
    Analyzes commercial buying patterns and channels for competitors in the report.
    Particularly focuses on product/e-commerce brands, extracting sales channels, unit economics,
    sales velocity, and purchase triggers.
    """
    diagnostics: list[str] = []
    if not report.competitors or llm is None:
        return report, diagnostics

    # Check if context or category implies physical products or e-commerce
    cat = str(merchant_context.get("category") or "").lower()
    bmodel = str(merchant_context.get("business_model") or "").lower()
    archetype = resolve_archetype(merchant_context, f"{cat} {bmodel}")

    # Process all in-category rivals (or competitors with commerce keywords)
    targets = [
        c for c in report.competitors
        if getattr(c, "named_by_merchant", False) or (c.relevance_score is None or c.relevance_score >= 0.4)
    ]
    if not targets:
        return report, diagnostics

    tasks_payload = []
    for c in targets:
        passages = _extract_relevant_passages(c, corpus)
        if not passages:
            continue
        tasks_payload.append({
            "brand_name": c.brand_name,
            "product_name": c.product_name,
            "pricing_model": c.pricing_model or "Not stated",
            "sources": c.sources[:3],
            "evidence_excerpts": passages[:6],
        })

    if not tasks_payload:
        return report, diagnostics

    try:
        structured_llm = llm.with_structured_output(_CompetitorBuyingPatternBundle)
        user_prompt = (
            f"## Merchant Category & Context\n"
            f"Product: {merchant_context.get('product_name')}\n"
            f"Category: {cat}\n"
            f"Archetype: {archetype}\n\n"
            f"## Competitor Extracts\n"
            f"{json.dumps(tasks_payload, indent=2)}\n\n"
            f"Analyze and reverse-engineer the commercial buying pattern and channels for each competitor."
        )

        result = await structured_llm.ainvoke([
            {"role": "system", "content": BUYING_PATTERN_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])

        patterns_map: dict[str, BuyingPatternIntelligence] = {}
        for item in getattr(result, "patterns_by_competitor", []):
            patterns_map[item.brand_name.strip().lower()] = item.buying_pattern

        applied_count = 0
        for comp in report.competitors:
            key = comp.brand_name.strip().lower()
            pattern = patterns_map.get(key)
            if not pattern:
                # Try matching by product_name
                prod_key = comp.product_name.strip().lower()
                pattern = patterns_map.get(prod_key)

            if pattern:
                comp.buying_patterns = pattern
                applied_count += 1
                channels_str = ", ".join(pattern.sales_channels[:2]) if pattern.sales_channels else "D2C/Web"
                diagnostics.append(
                    f"Mapped buying patterns for {comp.brand_name}: channels=[{channels_str}]"
                )

        if applied_count > 0:
            diagnostics.append(f"Reverse-engineered commercial buying patterns for {applied_count} rival(s)")

    except Exception as exc:
        logger.warning("Buying pattern analysis encountered an issue: %s", exc)
        diagnostics.append(f"Buying pattern analysis skipped: {exc}")

    return report, diagnostics
