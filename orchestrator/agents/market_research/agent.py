"""
Market Research Agent node — wires dynamic parameter discovery, multi-iteration research loop,
ad intelligence search, LLM synthesis, and factual grounding into a single LangGraph-compatible callable.

Stateless: accepts StrategyState, returns a partial state-update delta.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Ensure project root is on sys.path when executed directly as a standalone script
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from orchestrator.agents.market_research.analysis.classification import classify_campaign_context
from orchestrator.agents.market_research.pipeline.loop import ResearchLoopResult, execute_research_loop, split_named
from orchestrator.agents.market_research.progress import ProgressFn, _report
from orchestrator.agents.market_research.analysis.relevance_filter import rank_by_category_fit
from orchestrator.agents.market_research.analysis.scoring import calculate_dqs
from orchestrator.agents.market_research.pipeline.subagents import ResearchCrew
from orchestrator.agents.market_research.analysis.taxonomy import (
    calculate_attribute_density,
    revise_taxonomy_from_evidence,
)
from orchestrator.core.config import get_settings
from orchestrator.core.llm import LLMConfigurationError, build_chat_model
from orchestrator.schemas.research import (
    SWOTAnalysis,
    SWOTReportDelta,
)
from orchestrator.schemas.state import StrategyState

if TYPE_CHECKING:
    from orchestrator.schemas.api import BYOKConfig

logger = logging.getLogger(__name__)


def _norm_brand(name: str) -> str:
    return " ".join((name or "").lower().split())


def _compact(name: str) -> str:
    return "".join(ch for ch in re.sub(r"\(.*?\)", "", (name or "").lower()) if ch.isalnum())


async def _fill_validator_gaps(
    crew: Any,
    report: Any,
    gaps: list[Any],
    merchant_context: dict[str, Any],
    taxonomy: Any,
    round_number: int,
) -> tuple[list[str], list[str]]:
    """
    One targeted research round for the competitors the validator found incomplete: missing-data
    searches, a short crawl of their own pages, and the findings folded into their profiles.
    Returns the new evidence texts and URLs, which the grounding gate must see before anything
    from them is kept.
    """
    from orchestrator.agents.market_research.discovery.crawler import extract_competitor_target_urls
    from orchestrator.agents.market_research.discovery.search import build_missing_data_queries
    from orchestrator.agents.market_research.pipeline.loop import (
        _extract_price,
        enrich_competitors_from_pages,
        extract_preliminary_competitors,
        merge_duplicate_competitors,
    )

    wanted = {g.competitor for g in gaps}
    targets = [c for c in report.competitors if c.brand_name in wanted]
    queries = build_missing_data_queries(merchant_context, targets, taxonomy, iteration=round_number)
    if not targets or not queries:
        return [], []

    results = await crew.search.run(queries, round_number=round_number)
    urls = extract_competitor_target_urls(targets, results, pages_per_competitor=2, max_urls=2 * len(targets))
    pages = await crew.crawl.run(urls) if urls else []
    enrich_competitors_from_pages(targets, pages)

    found = merge_duplicate_competitors(extract_preliminary_competitors(results, [c.brand_name for c in targets]))
    for comp in targets:
        for f in (f for f in found if _compact(f.brand_name) == _compact(comp.brand_name)):
            for field in ("weaknesses_mined", "strengths_mined", "core_claims"):
                setattr(comp, field, list(dict.fromkeys([*getattr(comp, field), *getattr(f, field)])))
            if (not comp.pricing_model or comp.pricing_model == "detected") and f.pricing_model and f.pricing_model != "detected":
                comp.pricing_model = f.pricing_model
            comp.sources = list(dict.fromkeys([*comp.sources, *f.sources]))
        # Search-stage extraction only marks pricing as "mentioned"; when the crawl added
        # nothing, read the amount from a snippet that names this rival. Grounding re-checks it.
        if not comp.pricing_model or comp.pricing_model == "detected":
            brand = comp.brand_name.lower()
            for r in results:
                if brand in f"{r.title} {r.snippet}".lower() and (price := _extract_price(r.snippet or "")):
                    comp.pricing_model = price
                    comp.sources = list(dict.fromkeys([*comp.sources, r.url]))
                    break

    texts = [r.snippet for r in results if r.snippet] + [p["markdown"] for p in pages if p.get("markdown")]
    new_urls = [r.url for r in results if r.url] + [p["url"] for p in pages if p.get("url")]
    return texts, new_urls


def attach_ad_hooks(competitors: list[Any], hooks_by_comp: dict[str, list[str]]) -> None:
    """
    Merges collected ad hooks into the final profiles, matched by brand rather than exact
    product name. Hooks are filed under the product name the competitor had when ad lookups
    ran; synthesis rewrites it ("Praxent" -> "Praxent Services"), and exact matching then
    silently discarded every hook that ad intelligence had found.
    """
    keyed = [(_compact(k), hooks) for k, hooks in hooks_by_comp.items() if hooks and len(_compact(k)) >= 3]
    for comp in competitors:
        names = {n for n in (_compact(comp.brand_name), _compact(comp.product_name)) if len(n) >= 3}
        for key, hooks in keyed:
            if any(key == n or n.startswith(key) or key.startswith(n) for n in names):
                comp.ad_hooks = list(dict.fromkeys([*comp.ad_hooks, *hooks]))


async def execute_market_research(
    state: StrategyState,
    *,
    tavily_client: Any = None,
    crawl_client: Any = None,
    llm: Any = None,
    llm_config: BYOKConfig | None = None,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """
    LangGraph node: Market & Competitor Research Agent.

    Coordinates a crew of tool subagents (see subagents.py): taxonomy, search, crawl,
    ad intelligence, synthesis and grounding. This function owns the workflow and the
    decisions between steps; each subagent owns one tool.

    End-to-End Workflow:
      1. Context & Goal Understanding: Reason 4-8 Critical JTBD Drivers & 15-25 Minor Specs.
      2. Multi-Iteration Loop (loop.py): Search & Scrape -> Parameter Update -> DQS Validation -> Convergence.
      3. Competitor Selection: Curate top rivals from converged findings.
      4. Ad Intelligence: Real ad copy from the Meta, LinkedIn and Google ad libraries plus web mentions.
      5. LLM Synthesis: Produce evidence-grounded SWOT matrix comparing merchant against top rivals.
      6. Factual Grounding Gate: Zero false-confidence verification & verbatim citation anchoring.
    """
    settings = get_settings()
    merchant_context = state.get("merchant_context", {})
    dqs_retries = state.get("dqs_retries", 0)
    errors: list[str] = list(state.get("errors", []))
    prior_report: SWOTReportDelta | None = state.get("prior_report")
    prior_run_at: str | None = state.get("prior_run_at")
    run_mode: str | None = state.get("run_mode")
    is_update = run_mode == "update" and prior_report is not None
    # The last finished run for this product, loaded on every run (not only updates). Only the
    # wedge scan and threat watch read it -- they need a previous reading to measure movement --
    # so a fresh run still never merges old findings into the new report.
    baseline_report: SWOTReportDelta | None = state.get("baseline_report") or prior_report
    baseline_run_at: str | None = state.get("baseline_run_at") or prior_run_at

    llm_error: str | None = None
    # An injected model (tests, callers) serves every step; otherwise light steps get the fast one.
    fast_llm = llm
    if llm is None:
        try:
            llm = build_chat_model(llm_config)
            fast_llm = build_chat_model(llm_config, fast=True)
        except LLMConfigurationError as exc:
            llm_error = str(exc)
            errors.append(f"LLM configuration error: {exc}")
            await _report(on_progress, f"[LLM_CONFIG] {exc}", "ERROR")

    crew = ResearchCrew.build(
        tavily_client=tavily_client,
        crawl_client=crawl_client,
        llm=llm,
        fast_llm=fast_llm,
        on_progress=on_progress,
    )

    # Phase 0: Classify the campaign archetype. The intake form has no campaign-type selector,
    # so business model, campaign type, price model and geography are inferred here from the
    # merchant's own context. Anything the caller did supply is left untouched.
    merchant_context, classification, filled_fields = await classify_campaign_context(
        merchant_context, llm=fast_llm
    )
    if filled_fields:
        await _report(
            on_progress,
            f"[CAMPAIGN_CLASSIFIED] Inferred {', '.join(filled_fields)} -> "
            f"business_model={merchant_context.get('business_model') or 'n/a'}, "
            f"campaign_type={merchant_context.get('campaign_type') or 'n/a'}, "
            f"price_model={merchant_context.get('price_model') or 'n/a'}"
            + (f" ({classification.rationale})" if classification.rationale else ""),
        )
    if classification.user_intent or classification.marketing_capabilities:
        caps_str = ", ".join(classification.marketing_capabilities) if classification.marketing_capabilities else "general"
        await _report(
            on_progress,
            f"[INTENT_UNDERSTOOD] Goal: \"{classification.user_intent or 'Market Strategy'}\" | Capabilities: [{caps_str}]",
        )

    # Phase 1: Taxonomy subagent builds the dynamic parameter framework
    taxonomy = await crew.taxonomy.run(merchant_context)

    # The rivals the merchant named, recorded before update runs add the prior report's rivals
    # to known_competitors. Only these are guaranteed a profile on top of the agent's own
    # discoveries; treating re-seeded rivals the same way would grow the report every refresh.
    merchant_named = [n.strip() for n in (merchant_context.get("known_competitors") or []) if n and n.strip()]
    merchant_context = {**merchant_context, "merchant_named_competitors": merchant_named}

    # Phase 2: Execute dedicated multi-iteration convergence loop
    # For update runs, seed known competitors from the prior report so the search
    # targets those brands directly and uses time-bounded queries for recency.
    if is_update and prior_report:
        prior_known = [c.brand_name for c in prior_report.competitors if c.brand_name]
        existing_known = merchant_context.get("known_competitors") or []
        merchant_context = {
            **merchant_context,
            "known_competitors": list(dict.fromkeys(prior_known + existing_known)),
        }
        await _report(
            on_progress,
            f"[NODE] Update mode: seeding {len(prior_known)} competitors from prior run, "
            f"using time-bounded queries",
        )

    # Ad intelligence needs only competitor names, so it starts as soon as the first round
    # produces them and runs alongside the remaining rounds. Measured sequentially it was 67s
    # of a 258s run; overlapped, it hides behind crawl time already being spent.
    category_for_ads: str = str(merchant_context.get("category") or "")
    target_geo: str | None = (
        str(merchant_context.get("target_geography"))
        if merchant_context.get("target_geography")
        else None
    )
    ad_intel_task: asyncio.Task[Any] | None = None
    # Who the early pass looked up, whether or not they run ads. Keying the top-up on "has
    # hooks" re-ran every competitor without ads: 24s of duplicate lookups per run.
    ad_looked_up: set[str] = set()

    async def _start_ad_intel_early(early: list[Any]) -> None:
        nonlocal ad_intel_task
        cap = settings.research_max_competitors
        shortlist = early[:cap] if cap and cap > 0 else early
        if not shortlist:
            return
        ad_looked_up.update(c.product_name for c in shortlist)
        ad_intel_task = asyncio.create_task(
            crew.ad_intel.run(
                shortlist,
                category_for_ads,
                target_geography=target_geo,
            )
        )

    async def _revise_taxonomy(current: Any, evidence: list[str]) -> Any:
        return await revise_taxonomy_from_evidence(
            current, merchant_context, evidence, llm=fast_llm
        )

    loop_result: ResearchLoopResult = await execute_research_loop(
        merchant_context=merchant_context,
        initial_taxonomy=taxonomy,
        initial_retries=dqs_retries,
        on_progress=on_progress,
        search_agent=crew.search,
        crawl_agent=crew.crawl,
        is_update=is_update,
        prior_run_at=prior_run_at,
        on_first_competitors=_start_ad_intel_early,
        revise_taxonomy=_revise_taxonomy if llm is not None else None,
        judge_category_fit=(
            (lambda cands: rank_by_category_fit(cands, merchant_context, fast_llm)) if fast_llm is not None else None
        ),
    )
    taxonomy = loop_result.taxonomy

    # Phase 3: Curate competitor list (minimum 5, no max limit when <= 0)
    limit = settings.research_max_competitors
    use_limit = bool(limit and limit > 0)
    # Two quotas: every rival the merchant named (up to a cap) PLUS `limit` the agent found
    # itself. One shared cut let named rivals, always ranked first, take every slot.
    named_profiles, named_overflow, discovered = split_named(
        loop_result.preliminary_competitors, merchant_named, settings.research_max_named_competitors
    )
    for c in named_profiles + named_overflow:
        c.named_by_merchant = True
    top_competitors = named_profiles + (discovered[:limit] if use_limit else discovered)
    # Everyone the loop discovered but the cut-off excluded. Kept as the bench so
    # "find more competitors" can serve the next in line instead of re-searching.
    bench_competitors = named_overflow + (discovered[limit:] if use_limit else [])
    if merchant_named:
        await _report(
            on_progress,
            f"[COMPETITOR_LIST] Researching the {len(named_profiles)} rival(s) you named "
            f"plus {len(top_competitors) - len(named_profiles)} found independently"
            + (f"; {len(named_overflow)} more named rival(s) are past the cap of "
               f"{settings.research_max_named_competitors} and wait in reserve" if named_overflow else ""),
        )
    if bench_competitors:
        await _report(
            on_progress,
            f"[COMPETITOR_BENCH] {len(top_competitors)} selected for deep analysis; "
            f"{len(bench_competitors)} held in reserve for 'find more'",
        )

    # Phase 4: Ad intelligence. The early task covers whoever was known after round 1; only
    # competitors discovered in later rounds still need a lookup, so the overlapped work is
    # kept and topped up rather than repeated.
    ad_intel = None
    if ad_intel_task is not None:
        try:
            ad_intel = await ad_intel_task
        except Exception as exc:
            logger.warning("Early ad intelligence failed, falling back to a full pass: %s", exc)
            errors.append(f"Ad intelligence error: {exc}")

    if ad_intel is None:
        ad_intel = await crew.ad_intel.run(
            top_competitors, category_for_ads,
            target_geography=target_geo,
        )
    else:
        uncovered = [
            c for c in top_competitors
            if c.product_name not in ad_intel.hooks_by_competitor and c.product_name not in ad_looked_up
        ]
        if uncovered:
            await _report(
                on_progress,
                f"[AD_INTELLIGENCE] Topping up {len(uncovered)} competitor(s) found after the first round",
            )
            top_up = await crew.ad_intel.run(
                uncovered, category_for_ads,
                target_geography=target_geo,
            )
            ad_intel.hooks_by_competitor.update(top_up.hooks_by_competitor)
            ad_intel.documents.extend(top_up.documents)
            ad_intel.skipped.extend(s for s in top_up.skipped if s not in ad_intel.skipped)

    ad_hooks_by_comp = ad_intel.hooks_by_competitor
    # Ad-library pages are evidence like any other crawled page.
    evidence_pages = loop_result.extracted_pages + ad_intel.documents
    all_source_urls = list(dict.fromkeys(loop_result.all_source_urls + [d["url"] for d in ad_intel.documents]))

    # The raw corpus every factual claim is checked against. Hoisted out of the try so the
    # synthesis-failure path can run the same grounding gate rather than skipping it.
    raw_text_corpus = [r.snippet for r in loop_result.search_results] + [
        p["markdown"] for p in evidence_pages if p.get("markdown")
    ]

    # Phase 5: Synthesis subagent produces the evidence-grounded SWOT
    try:
        if llm is None:
            raise LLMConfigurationError(llm_error or "No LLM available")
        report_delta = await crew.synthesis.run(
            merchant_context=merchant_context,
            search_results=loop_result.search_results,
            extracted_pages=evidence_pages,
            taxonomy=taxonomy,
            ad_hooks_by_comp=ad_hooks_by_comp,
        )

        attach_ad_hooks(report_delta.competitors, ad_hooks_by_comp)

        # Phase 6: Factual Grounding & Anti-Hallucination Gate
        report_delta, grounding_notes = await crew.grounding.run(
            report_delta, raw_text_corpus, set(all_source_urls)
        )

        # Phase 6b: Adversarial validator. Grounding proves the words exist in some page; the
        # validator checks each item against that passage (right company, real customer voice,
        # meaning intact) and may send the research back once for the gaps it names.
        report_delta, verdict, validator_notes = await crew.validator.run(report_delta, raw_text_corpus)
        for round_number in range(1, settings.validator_max_rounds + 1):
            if not verdict.gaps:
                break
            await _report(
                on_progress,
                f"[VALIDATOR] Sending the research back for: "
                + ", ".join(f"{g.competitor} ({g.field.replace('_mined', '').replace('_model', '')})" for g in verdict.gaps),
            )
            new_texts, new_urls = await _fill_validator_gaps(
                crew, report_delta, verdict.gaps, merchant_context, taxonomy, round_number
            )
            if not new_texts:
                break
            raw_text_corpus.extend(new_texts)
            all_source_urls = list(dict.fromkeys(all_source_urls + new_urls))
            report_delta, grounding_notes = await crew.grounding.run(
                report_delta, raw_text_corpus, set(all_source_urls)
            )
            report_delta, verdict, notes = await crew.validator.run(report_delta, raw_text_corpus, round_number)
            validator_notes.extend(notes)
        report_delta.validation_diagnostics = grounding_notes + validator_notes

        def _note(lines: list[str]) -> None:
            if lines:
                report_delta.validation_diagnostics = (report_delta.validation_diagnostics or []) + lines

        # Phase 6b2: Profile completion — the validator's job is to remove what the evidence does
        # not support; this one finds what is missing. For every rival it lists the empty facts
        # (price, rating, reviews, founded, HQ, team size, revenue, funding), searches where they
        # are published, and keeps a value only when its source sentence is verified on a
        # fetched page. Whatever stays empty is recorded with the reason it is empty.
        if crew.profile_completer is not None:
            completion_docs: list[tuple[str, str]] = [
                (r.url or "", f"{r.title}\n{r.snippet}") for r in loop_result.search_results if r.snippet
            ] + [(p.get("url") or "", p["markdown"]) for p in evidence_pages if p.get("markdown")]
            report_delta, notes = await crew.profile_completer.run(report_delta, completion_docs)
            _note(notes)
            raw_text_corpus.extend(crew.profile_completer.new_texts)
            all_source_urls = list(dict.fromkeys(all_source_urls + crew.profile_completer.new_urls))

        # Phase 6c: Freshness audit — dates profiles grounding could not (product-name and
        # "Updated <date>" matches) and flags evidence too old to trust. Deterministic.
        report_delta, notes = await crew.freshness.run(report_delta, raw_text_corpus)
        _note(notes)

        # Phase 7: LLM Relevance Filter — curate which data is most useful for the merchant dashboard
        if llm is not None:
            report_delta = await crew.relevance.run(report_delta, merchant_context)

        # Phase 7b: Display Filter-Validator — checks display data correctness & completeness,
        # prompting the LLM repair subagent to find and fix any missing or inaccurate data from
        # evidence. Runs even without an LLM: the placeholder scrub ("N/A", "not available") is
        # pure code, and leaving those strings in is what put them on the dashboard.
        report_delta, display_diagnostics = await crew.display_validator.run(
            report_delta, raw_text_corpus
        )
        if display_diagnostics:
            report_delta.validation_diagnostics = (
                (report_delta.validation_diagnostics or []) + display_diagnostics
            )

        # Phase 7c: Pricing normalizer — after the display validator has repaired pricing, so
        # the parse sees the best text available; makes prices sortable and comparable.
        report_delta, notes = await crew.pricing.run(report_delta)
        _note(notes)

        # Phase 7d: Review Context — reads the review evidence a second time to synthesize why
        # customers praise or complain, who they are, and the counter-angle each theme opens up.
        # Runs on the final display set, so it never spends tokens on a competitor that was cut.
        report_delta = await crew.review_context.run(
            report_delta, raw_text_corpus, merchant_context
        )

        # Phase 7e: Breakout Leap Benchmark — compares merchant against breakout peers who started
        # in the same wedge but scaled to high net worth, enterprise client rosters, and partner deals.
        report_delta, notes = await crew.leap_benchmark.run(
            report_delta, raw_text_corpus, merchant_context
        )
        _note(notes)

        # Phase 7f: Executive summary — rewritten last among the analysis steps, so it can cite
        # repaired prices, review themes, and leap benchmarks the relevance filter's draft never saw.
        report_delta, notes = await crew.exec_summary.run(report_delta, merchant_context)
        _note(notes)

        # Phase 8 (update runs only): merge prior run's findings into the new report.
        # Competitors not re-found in recent data are carried forward so the report
        # stays complete; enriched competitors get the union of old + new evidence.
        if is_update and prior_report:
            from orchestrator.agents.market_research.analysis.merge import merge_reports
            report_delta = merge_reports(report_delta, prior_report, prior_run_at)
            await _report(
                on_progress,
                f"[NODE] Merged prior run data: {len(report_delta.competitors)} total competitors",
            )
            # Phase 8b: Snapshot diff — the moves merge does not record (review volume, new ad
            # creative, normalized monthly price).
            report_delta, notes = await crew.snapshot_diff.run(report_delta, prior_report)
            _note(notes)

        # Phase 9: Ad copy — the report ends in concepts the merchant can launch, each tied to
        # a rival weakness the research actually found.
        report_delta, notes = await crew.ad_copy.run(report_delta, merchant_context)
        _note(notes)

        final_dqs = calculate_dqs(
            competitors=report_delta.competitors,
            source_urls=all_source_urls,
            threshold=settings.dqs_threshold,
        )
        report_delta.dqs_score = final_dqs.score
        report_delta.assumptions_tagged = loop_result.assumptions_tagged
        report_delta.source_urls = all_source_urls
        report_delta.dqs_diagnostics = final_dqs.diagnostics
        report_delta.dynamic_taxonomy = taxonomy
        report_delta.attribute_density = calculate_attribute_density(report_delta.competitors, taxonomy)

    except Exception as exc:
        logger.error("LLM synthesis failed: %s", exc)
        errors.append(f"LLM synthesis error: {exc}")
        await _report(
            on_progress, "[LLM_SYNTH] Synthesis failed; returning search-stage findings only", "ERROR"
        )
        attach_ad_hooks(top_competitors, ad_hooks_by_comp)

        # Synthesis is the step that turns evidence into analysis. Without it we report only
        # what was actually observed and leave the rest empty — a templated SWOT reads like a
        # finding, and the grounding gate below only validates competitor fields, not SWOT
        # prose, so an invented conclusion here would survive unchallenged.
        discovered = [c.brand_name for c in top_competitors if c.brand_name]

        strengths = []
        raw_vp = merchant_context.get("primary_value_prop")
        value_prop = raw_vp.strip() if isinstance(raw_vp, str) else (str(raw_vp).strip() if raw_vp else "")
        if value_prop:
            # The merchant's own claim about itself, attributed as such — not a market finding.
            strengths.append(f"Merchant-stated value proposition: {value_prop}")

        threats = []
        if discovered:
            threats.append(f"Competitors discovered in this market: {', '.join(discovered[:5])}")

        report_delta = SWOTReportDelta(
            competitors=top_competitors,
            swot=SWOTAnalysis(
                strengths=strengths,
                # Determining the merchant's own weaknesses and opportunities requires the
                # synthesis step that just failed; competitor gripes live on their profiles.
                weaknesses=[],
                opportunities=[],
                threats=threats,
            ),
            # An uncontested-quadrant claim is a synthesis conclusion; the UI already renders
            # a neutral placeholder when this is absent.
            positioning_gap=None,
            dqs_score=loop_result.dqs_result.score,
            assumptions_tagged=True,
            source_urls=loop_result.all_source_urls,
            dqs_diagnostics=loop_result.dqs_result.diagnostics
            + [
                f"LLM synthesis fallback used ({type(exc).__name__}): SWOT analysis and "
                f"positioning gap omitted. Only directly observed competitor data is reported."
            ],
            dynamic_taxonomy=taxonomy,
            attribute_density=loop_result.attribute_density,
        )

        # The fallback path runs the same anti-hallucination gate as the main path, so
        # competitor claims, prices and source URLs are verified here too.
        try:
            report_delta, _ = await crew.grounding.run(
                report_delta, raw_text_corpus, set(all_source_urls)
            )
        except Exception as grounding_exc:  # never let the guard itself break the run
            logger.error("Grounding gate failed on synthesis fallback: %s", grounding_exc)
            errors.append(f"Grounding error on fallback: {grounding_exc}")

        # Profile facts do not depend on synthesis. Completion verifies every value against its
        # source sentence in code, and reads directory profiles by pattern when no model is up,
        # so a run whose synthesis failed still gets complete, checked profiles.
        if crew.profile_completer is not None:
            fallback_docs: list[tuple[str, str]] = [
                (r.url or "", f"{r.title}\n{r.snippet}") for r in loop_result.search_results if r.snippet
            ] + [(p.get("url") or "", p["markdown"]) for p in evidence_pages if p.get("markdown")]
            report_delta, completion_notes = await crew.profile_completer.run(report_delta, fallback_docs)
            report_delta.validation_diagnostics = (report_delta.validation_diagnostics or []) + completion_notes
            raw_text_corpus.extend(crew.profile_completer.new_texts)

    # Phase 10: Tier 1 wedge scan — a broad sweep of the niche for small and newly launched
    # brands the competitor shortlist can miss. Runs on whichever report the run produced, so
    # the niche map survives even a synthesis failure.
    report_delta, wedge_notes = await crew.wedge_finder.run(
        report_delta,
        merchant_context=merchant_context,
        bench=bench_competitors,
        corpus=raw_text_corpus,
        baseline=baseline_report,
        baseline_run_at=baseline_run_at,
    )
    # Phase 11: Tier 2 threat watch — momentum on the peer rivals most likely to overtake,
    # measured against the last run. Deterministic, so every score is re-checkable.
    report_delta, threat_notes = await crew.threat_monitor.run(
        report_delta,
        merchant_context=merchant_context,
        corpus=raw_text_corpus,
        baseline=baseline_report,
        baseline_run_at=baseline_run_at,
    )
    if wedge_notes or threat_notes:
        report_delta.validation_diagnostics = (
            (report_delta.validation_diagnostics or []) + wedge_notes + threat_notes
        )

    errors.extend(crew.errors)
    logger.info("Research crew usage: %s", crew.usage_summary())

    # The bench may contain brands the merge or grounding step promoted into the report;
    # drop those so "find more" never re-serves a competitor already on the board.
    on_board = {_norm_brand(c.brand_name) for c in report_delta.competitors}
    bench_competitors = [
        c for c in bench_competitors if _norm_brand(c.brand_name) not in on_board
    ]

    return {
        "swot_report": report_delta,
        "dqs_retries": loop_result.retries_used,
        "errors": errors,
        "bench_competitors": bench_competitors,
    }


# ── Standalone CLI Runner ─────────────────────────────────────────────────────

async def _main(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    with open(args.input, encoding="utf-8") as f:
        payload = json.load(f)

    state: StrategyState = {
        "merchant_context": payload,
        "swot_report": None,
        "dqs_retries": 0,
        "errors": [],
    }

    output = await execute_market_research(state)

    report: SWOTReportDelta = output["swot_report"]
    print("\n" + "=" * 60)
    print("MARKET RESEARCH REPORT DELTA")
    print("=" * 60)
    print(f"DQS Score:          {report.dqs_score:.4f}")
    print(f"Spec Density:       {report.attribute_density * 100:.1f}%")
    print(f"Assumptions Tagged: {report.assumptions_tagged}")
    print(f"Competitors:        {len(report.competitors)}")
    for comp in report.competitors:
        print(f"\n- {comp.brand_name} {comp.product_name}")
        print(f"  Price:     {comp.pricing_model or 'unlisted'}")
        print(f"  Claims:    {comp.core_claims}")
        print(f"  Gripes:    {comp.weaknesses_mined}")
        print(f"  Ad Hooks:  {comp.ad_hooks}")
        print(f"  Evidence:  {comp.factual_evidence}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Market Research Agent CLI")
    parser.add_argument("--input", type=str, required=True, help="Path to merchant context JSON file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    asyncio.run(_main(parser.parse_args()))
