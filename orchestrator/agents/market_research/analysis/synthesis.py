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

# Order the evidence budget is spent in. pricing_scrape and gripe_mining carry the two
# fields that most often come back empty (pricing_model, weaknesses_mined), so they are
# served before the discovery results that merely repeat competitor names.
_VECTOR_PRIORITY = ("pricing_scrape", "gripe_mining", "messaging_claims", "alternative_discovery")


def _select_within_budget(
    results: list[TavilySearchResult], budget_chars: int
) -> tuple[list[TavilySearchResult], int]:
    """
    Picks the search results that fit the prompt budget, round-robin across vectors.

    The research loop appends to one accumulator every retry round, so the head of the list
    is entirely round-0 discovery and the pricing and complaint results land at the tail.
    Taking a plain prefix would therefore drop exactly the evidence the report is missing;
    cycling the vectors keeps each one represented and spends what is left on relevance.
    """
    by_vector: dict[str, list[TavilySearchResult]] = {}
    seen_urls: set[str] = set()
    for r in results:
        if r.url and r.url in seen_urls:
            continue
        if r.url:
            seen_urls.add(r.url)
        by_vector.setdefault(r.vector, []).append(r)

    for bucket in by_vector.values():
        bucket.sort(key=lambda r: r.score, reverse=True)

    order = [v for v in _VECTOR_PRIORITY if v in by_vector]
    order += [v for v in by_vector if v not in _VECTOR_PRIORITY]

    selected: list[TavilySearchResult] = []
    spent = 0
    cursors = dict.fromkeys(order, 0)
    while order:
        for vector in list(order):
            i = cursors[vector]
            bucket = by_vector[vector]
            if i >= len(bucket):
                order.remove(vector)
                continue
            cursors[vector] = i + 1
            item = bucket[i]
            cost = len(item.title) + len(item.snippet) + 120  # 120 ~ fence + vector label
            if spent + cost > budget_chars:
                order.remove(vector)
                continue
            selected.append(item)
            spent += cost

    return selected, len(results) - len(selected)


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
6. REAL USER COMPLAINTS & PAIN POINTS: 'weaknesses_mined' MUST contain clear, succinct customer pain points, \
critiques, limitations, or product grievances extracted from user complaints, Reddit/G2 reviews, or forum threads \
(e.g., 'Difficult learning curve for beginners', 'Slow support response times', 'High renewal costs', 'Not BBB accredited'). \
NEVER copy raw webpage titles (e.g. 'Title: ... | BBB Business Profile'), book titles ('# has anyone tried ... book?'), \
markdown header structures ('## Post details', '## Top Comments'), or irrelevant curriculum/table of contents snippets. \
Strip page headers and summarize the exact negative sentiment/complaint concisely into a single readable sentence per bullet.
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
11. PRIORITIZE SUCCESSFUL COMPANIES WITH SIMILAR PRODUCTS & CREATE DETAILED PROFILES:
- When selecting competitors to profile from the evidence corpus, prioritize companies offering similar products/services that have achieved proven commercial success (category leaders, breakout peers with marquee client rosters, high transaction volumes, or strong market reputations).
- Build each competitor profile in exhaustive detail:
  * brand_name & product_name: The company and specific competing product/service line.
  * founded: Establishment year as stated in evidence (e.g., '2014').
  * headquarters: City/country where their primary headquarters is located.
  * operating_locations: Array of active branch locations, service regions, or countries where they operate.
  * other_products & product_catalog_count: Other products, models, or service offerings in their catalog.
  * pricing_model: Specific commercial rates, monthly plans, or project tiers.
  * core_claims: 2-4 primary feature claims or value propositions from their web pages.
  * strengths_mined: What users praise and what drove their commercial success.
  * weaknesses_mined: Verified customer complaints, limitations, or missing capabilities.
  * dynamic_attributes: Map every critical driver and specification to concrete evidence.
  * relevance_reason: Explain why this successful rival's product directly competes with and benchmarks against the merchant.
- Synthesize profiles for at least 5 distinct direct competitors (or all discovered if 5+ available). NEVER artificially truncate to 3 or 4. Ensure EVERY field is populated from the provided extracts so the entire competitor matrix is completely filled with latest data.
12. NEVER INCLUDE THE MERCHANT ITSELF AS A COMPETITOR:
- The merchant's own business, product, or domain must NEVER be listed as a competitor profile. Competitors must be independent third-party market rivals.

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
    selected_results, dropped_results = _select_within_budget(
        list(search_results), settings.max_synthesis_snippet_chars
    )
    search_context = "\n\n".join(
        fence_untrusted(
            f"[{r.vector}] {r.title}\n{r.snippet}", url=r.url, index=i
        )
        for i, r in enumerate(selected_results)
    )

    # Pages are deep-crawled and far denser than snippets, so they get their own budget and
    # are taken in order — the crawler already prioritised them when choosing what to fetch.
    page_parts: list[str] = []
    page_spent = 0
    dropped_pages = 0
    for i, p in enumerate(extracted_pages):
        markdown = p.get("markdown")
        if not markdown:
            continue
        excerpt = markdown[: settings.max_synthesis_page_excerpt_chars]
        if page_spent + len(excerpt) > settings.max_synthesis_page_chars:
            dropped_pages += 1
            continue
        page_parts.append(fence_untrusted(excerpt, url=p.get("url", ""), index=1000 + i))
        page_spent += len(excerpt)
    page_context = "\n\n".join(page_parts)

    if dropped_results or dropped_pages:
        logger.info(
            "Synthesis corpus trimmed to prompt budget: %d/%d results, %d pages omitted",
            len(selected_results),
            len(search_results),
            dropped_pages,
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
            f"## Peer & Breakout Scale Guidance\n"
            f"The merchant is a {scale.tier}-scale {scale.archetype} business. Prioritize competitors "
            f"that match this wedge, including both direct peers and 'Breakout Leap' rivals: category "
            f"specialists that originated in this exact wedge/niche (e.g. boutique agencies or specialist tools) "
            f"and successfully leaped to marquee enterprise clients, high contract values, and market scale. "
            f"Exclude ONLY generic legacy conglomerates (e.g. IBM, Accenture, Deloitte) that never shared this "
            f"specialized wedge origin. This is a scope filter only; never invent facts to fill the gap.\n\n"
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
        + (
            "## Corpus Note\n"
            "This evidence set was trimmed to fit the context window; it is a sample, not the "
            "complete crawl. Treat a missing fact as unknown rather than as evidence that the "
            "fact is absent, and do not infer that a competitor lacks a feature, price or "
            "complaint merely because it does not appear above.\n\n"
            if (dropped_results or dropped_pages)
            else ""
        )
        + f"Produce a complete SWOTReportDelta comparing the merchant's product against "
        f"at least 5 top discovered competitors (include all discovered rivals, do not truncate), with dynamic attributes, active ad hooks, "
        f"factual evidence excerpts, SWOT analysis, positioning gap, and source URLs."
    )

    result = await structured_llm.ainvoke([
        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ])

    from orchestrator.agents.market_research.discovery.source_types import (
        is_merchant_identity,
        merchant_identifiers,
    )

    delta = result if isinstance(result, SWOTReportDelta) else SWOTReportDelta.model_validate(result)
    m_keys, m_hosts = merchant_identifiers(merchant_context)
    delta.competitors = [
        c for c in delta.competitors
        if not is_merchant_identity(c.brand_name, c.sources, m_keys, m_hosts)
        and not is_merchant_identity(c.product_name, c.sources, m_keys, m_hosts)
    ]
    return delta
