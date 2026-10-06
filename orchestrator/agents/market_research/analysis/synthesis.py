"""
LLM synthesis for competitive SWOT analysis, positioning gap quadrants, and hook angles.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from orchestrator.agents.market_research.analysis.untrusted import (
    UNTRUSTED_CONTENT_PROTOCOL,
    fence_untrusted,
)
from orchestrator.agents.market_research.discovery.search import TavilySearchResult
from orchestrator.core.clock import today_iso
from orchestrator.core.config import get_settings
from orchestrator.schemas.research import DynamicParameterTaxonomy, SWOTReportDelta

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """\
You are a senior competitive intelligence analyst. You MUST strictly prioritize FACTUAL, \
VERIFIABLE web data over AI-generated or speculative assumptions.

CRITICAL FACTUAL DATA PROTOCOLS:
1. STRICT FACT EXTRACTION: Every competitor profile, claim, price point, technical spec, and user complaint \
MUST be directly extracted from the provided web crawl extracts, ad search results, or search snippets.
2. DYNAMIC ATTRIBUTE POPULATION: For every discovered competitor, actively populate 'dynamic_attributes' mapping \
relevant Critical JTBD Drivers and Minor Attributes to concrete facts stated in their crawl text or snippets. \
For software/services, extract stated technology frameworks, compliance certifications (SOC2, HIPAA, ISO), delivery models, \
target team sizes, or SLA guarantees. For eCommerce/hardware, extract specs, materials, and metrics. \
Do not leave dynamic_attributes empty if the scraped pages mention any relevant capabilities or offerings.
3. EXHAUSTIVE CORE CLAIMS: Extract 2 to 4 prominent feature claims, value propositions, or slogans directly stated on \
each competitor's scraped web pages. DO NOT leave core_claims empty if their page describes their product benefits.
4. ACCURATE PRICING & TIERS: If a price amount is stated ($X, €Y, or /mo), report the exact amount and model (e.g. '$299.00 one-time', \
'$49/seat/mo'). If tiers are mentioned without a dollar figure, state the tier names (e.g. 'Free / Pro / Enterprise tiers'). Only set \
pricing_model to null if the page is completely silent on commercial cost.
5. VERBATIM EVIDENCE: For each competitor, populate 'factual_evidence' with 2-4 direct verbatim excerpts \
from the scraped pages or search snippets that cite their actual features, pricing, or reviews.
6. REAL USER COMPLAINTS: Weaknesses MUST be quoted or extracted from actual user complaints, Reddit/G2 reviews, \
or forum threads in the provided data. NEVER invent speculative or hypothetical flaws.
7. ACTIVE AD HOOKS: Copy ad hooks VERBATIM from the Competitor Ad Intelligence section or the ad-library pages \
(Meta Ad Library, LinkedIn Ad Library, Google Ads Transparency) in the extracted content, keeping their source label. \
Never write, rephrase or imagine ad copy; if a competitor has no ad data, leave ad_hooks empty.
8. EVIDENCE CITATIONS: Ensure every competitor profile includes the exact source URLs where their facts were discovered.
9. NO GENERATED DATA: Only include competitors that appear in the provided data. Claims, complaints and evidence \
must be quoted from the provided text, not paraphrased. Empty fields are correct when the data is silent. \
Any statement not found in the provided sources is removed by an automated check.
10. RECENCY IS MEASURED AGAINST THE STATED CURRENT DATE: The user message gives today's real date. Judge whether \
a price, claim or product is current against THAT date, never against your own training data, which is older than \
this run. When a source carries a publication date, prefer the most recent source on a conflict and set as_of to \
that date (YYYY-MM-DD). Do not describe data as "current" or "latest" when its source is visibly older than the \
stated date — report what the source says and let as_of carry the age.

{untrusted_protocol}
"""

SYNTHESIS_SYSTEM_PROMPT = SYNTHESIS_SYSTEM_PROMPT.format(
    untrusted_protocol=UNTRUSTED_CONTENT_PROTOCOL
)


async def synthesize_swot_with_llm(
    merchant_context: dict[str, Any],
    search_results: list[TavilySearchResult],
    extracted_pages: list[dict[str, Any]],
    taxonomy: DynamicParameterTaxonomy | None = None,
    ad_hooks_by_comp: dict[str, list[str]] | None = None,
    llm: Any = None,
) -> SWOTReportDelta:
    """
    Calls LLM with structured output to produce a SWOTReportDelta.
    """
    settings = get_settings()

    if llm is None:
        from orchestrator.core.llm import build_chat_model

        llm = build_chat_model()

    structured_llm = llm.with_structured_output(SWOTReportDelta, method="function_calling")

    # Search snippets and page bodies are third-party text: fenced and neutralised so the
    # model reads them as evidence, not as instructions addressed to it.
    search_context = "\n\n".join(
        fence_untrusted(
            f"[{r.vector}] {r.title}\n{r.snippet}", url=r.url, index=i
        )
        for i, r in enumerate(search_results)
    )

    page_context = "\n\n".join(
        fence_untrusted(p["markdown"][:3000], url=p.get("url", ""), index=1000 + i)
        for i, p in enumerate(extracted_pages)
        if p.get("markdown")
    )

    taxonomy_context = ""
    if taxonomy:
        taxonomy_context = (
            f"## Dynamic Parameter Framework\n"
            f"Critical JTBD Drivers: {', '.join(taxonomy.critical_jtbd_drivers)}\n"
            f"Minor Specification Attributes: {', '.join(taxonomy.minor_attributes)}\n"
            f"For each competitor, fill dynamic_attributes using these exact parameter names as keys, "
            f"only where the provided data states a value.\n\n"
        )

    ad_context = ""
    if ad_hooks_by_comp:
        ad_context = (
            f"## Competitor Ad Intelligence & Marketing Hooks\n{json.dumps(ad_hooks_by_comp, indent=2)}\n\n"
        )

    # Peer-scale guidance: steer the profile set toward similarly-sized rivals and away from
    # out-of-scale incumbents that may still appear in the crawl corpus.
    from orchestrator.agents.market_research.discovery.search import derive_scale_signals

    scale = derive_scale_signals(merchant_context)
    scale_context = ""
    if scale.tier not in ("unknown", "enterprise"):
        scale_context = (
            f"## Peer-Scale Guidance\n"
            f"The merchant is a {scale.tier}-scale {scale.archetype} business. Prioritize competitors "
            f"of comparable scale (similar team size, pricing tier, and customer segment). Treat global "
            f"incumbents that merely dominate the category's search results — far larger firms the "
            f"merchant does not realistically compete with — as out of scope: omit them from the "
            f"competitor profiles even if they appear in the crawl data, unless the merchant named them "
            f"as a known competitor. This is a scope filter only; never invent facts to fill the gap.\n\n"
        )

    prompt_context = dict(merchant_context)
    dossier = prompt_context.get("dossier")
    if isinstance(dossier, str) and len(dossier) > settings.max_dossier_prompt_chars:
        prompt_context["dossier"] = dossier[: settings.max_dossier_prompt_chars] + " [...truncated]"

    user_message = (
        f"## Current Date\n"
        f"Today is {today_iso()}. Assess recency against this date, not your training data.\n\n"
        f"## Merchant Product & Goal\n"
        f"{json.dumps(prompt_context, indent=2)}\n\n"
        f"{scale_context}"
        f"{taxonomy_context}"
        f"{ad_context}"
        f"## Web Search Results\n{search_context}\n\n"
        f"## Extracted Page Content\n{page_context}\n\n"
        f"Produce a complete SWOTReportDelta comparing the merchant's product against "
        f"the top discovered competitors, with dynamic attributes, active ad hooks, "
        f"factual evidence excerpts, SWOT analysis, positioning gap, and source URLs."
    )

    result = await structured_llm.ainvoke([
        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ])

    if isinstance(result, SWOTReportDelta):
        return result
    return SWOTReportDelta.model_validate(result)
