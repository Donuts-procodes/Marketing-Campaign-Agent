"""
Tool subagents for the Market Research Agent.

Each subagent owns exactly one external tool or reasoning step, reports its own tagged
progress lines (e.g. "[TAVILY_SEARCH] ..."), times its work, and contains its own failures
so the coordinating research agent can decide how to proceed.

    ResearchCrew
      ├── TaxonomySubagent   (LLM)        dynamic parameter framework
      ├── SearchSubagent     (Tavily)     multi-vector web search
      ├── CrawlSubagent      (CrawlAPI, Tavily Extract fallback)  deep search, never re-scrapes a URL
      ├── AdIntelSubagent    (Meta/LinkedIn/Google ad libraries + Tavily)  competitor ad hooks
      ├── SynthesisSubagent  (LLM)        SWOT synthesis
      ├── GroundingSubagent  (local)      anti-hallucination validation
      ├── ReviewContextSubagent (LLM)     root causes, personas & counter-angles behind reviews
      ├── FreshnessSubagent  (local)      dates undated profiles, flags stale evidence
      ├── PricingNormalizerSubagent (regex + LLM fallback)  comparable prices
      ├── ExecutiveSummarySubagent (LLM)  dashboard summary from the finished data
      ├── SnapshotDiffSubagent (local)    review-count / ad / price moves between scans
      ├── AdCopyGeneratorSubagent (LLM)   ad concepts tied to documented rival weaknesses
      ├── WedgeFinderSubagent (search + light LLM)  Tier 1: every player in the niche, incl. new launches
      └── ThreatMonitorSubagent (local)   Tier 2: momentum on the peer rivals most likely to overtake
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

from orchestrator.agents.market_research.ingestion.ad_intelligence import AdIntelResult, search_competitor_ad_hooks
from orchestrator.agents.market_research.ingestion.page_extractor import extract_pages
from orchestrator.agents.market_research.intelligence.validation.grounding import validate_information_grounding
from orchestrator.agents.market_research.intelligence.validation.claim_validator import ValidatorVerdict, validate_report
from orchestrator.agents.market_research.progress import ProgressFn, _report
from orchestrator.agents.market_research.ingestion.search_client import (
    SearchQuery,
    SearchSessionCache,
    TavilySearchResult,
    execute_tavily_search,
)
from orchestrator.agents.market_research.intelligence.advisory.synthesis import synthesize_swot_with_llm
from orchestrator.agents.market_research.intelligence.market_mapping.relevance_filter import apply_relevance_scores, curate_dashboard_insights
from orchestrator.agents.market_research.intelligence.market_mapping.taxonomy import reason_dynamic_parameters
from orchestrator.core.config import get_settings, research_limit
from orchestrator.schemas.research import (
    CompetitorProfile,
    DashboardInsights,
    DynamicParameterTaxonomy,
    SWOTReportDelta,
)

logger = logging.getLogger(__name__)


class ToolSubagent:
    """Base class: tagged progress reporting, timing and error bookkeeping."""

    tag: ClassVar[str] = "SUBAGENT"

    def __init__(self, on_progress: ProgressFn | None = None) -> None:
        self.on_progress = on_progress
        self.errors: list[str] = []
        self.calls = 0
        self.total_seconds = 0.0

    async def log(self, message: str, level: str = "INFO") -> None:
        await _report(self.on_progress, f"[{self.tag}] {message}", level)

    async def fail(self, message: str, exc: BaseException) -> None:
        logger.warning("%s: %s: %s", self.tag, message, exc)
        self.errors.append(f"{self.tag}: {message}: {exc}")
        await self.log(f"{message} ({type(exc).__name__})", level="WARN")

    def _start(self) -> float:
        self.calls += 1
        return time.perf_counter()

    def _stop(self, started: float) -> float:
        elapsed = time.perf_counter() - started
        self.total_seconds += elapsed
        return elapsed


class TaxonomySubagent(ToolSubagent):
    tag = "DYNAMIC_PARAMS"

    def __init__(self, llm: Any = None, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(self, merchant_context: dict[str, Any]) -> DynamicParameterTaxonomy:
        started = self._start()
        taxonomy = await reason_dynamic_parameters(merchant_context, llm=self.llm)
        elapsed = self._stop(started)
        await self.log(
            f"{len(taxonomy.critical_jtbd_drivers)} critical drivers, "
            f"{len(taxonomy.minor_attributes)} minor attributes ({elapsed:.1f}s)"
        )
        return taxonomy


class SearchSubagent(ToolSubagent):
    tag = "TAVILY_SEARCH"

    def __init__(self, tavily_client: Any = None, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.tavily_client = tavily_client
        self.session_cache = SearchSessionCache()

    async def run(self, queries: list[SearchQuery], round_number: int = 0) -> list[TavilySearchResult]:
        started = self._start()

        # Emit each query before dispatching so the live console shows exactly
        # what is being searched and which sites are targeted.
        for i, q in enumerate(queries, 1):
            domain_hint = (
                " → " + ", ".join(q.include_domains[:3]) if q.include_domains else ""
            )
            time_hint = f" [{q.time_range}]" if q.time_range else ""
            await self.log(
                f"Round {round_number} query {i}/{len(queries)} [{q.vector}]{time_hint}{domain_hint}: {q.query}"
            )

        try:
            results = await execute_tavily_search(
                queries,
                tavily_client=self.tavily_client,
                session_cache=self.session_cache,
            )
        except Exception as exc:
            self._stop(started)
            await self.fail(f"Round {round_number} search failed", exc)
            return []
        elapsed = self._stop(started)
        vectors = sorted({q.vector for q in queries})
        by_engine: dict[str, int] = {}
        for r in results:
            by_engine[r.provider] = by_engine.get(r.provider, 0) + 1
        engines = ", ".join(f"{name} {count}" for name, count in sorted(by_engine.items()))
        await self.log(
            f"Round {round_number}: {len(queries)} queries ({', '.join(vectors)}) "
            f"returned {len(results)} results ({elapsed:.1f}s)" + (f" via {engines}" if engines else "")
        )
        return results


class CrawlSubagent(ToolSubagent):
    tag = "DEEP_SEARCH"

    def __init__(
        self,
        crawl_client: Any = None,
        on_progress: ProgressFn | None = None,
        tavily_client: Any = None,
    ) -> None:
        super().__init__(on_progress)
        self.crawl_client = crawl_client
        self.tavily_client = tavily_client
        self.scraped_urls: set[str] = set()

    async def run(self, urls: list[str]) -> list[dict[str, Any]]:
        """Scrapes only URLs this subagent has not scraped before."""
        new_urls = [u for u in dict.fromkeys(urls) if u not in self.scraped_urls]
        self.scraped_urls.update(new_urls)
        if not new_urls:
            await self.log("No new pages to scrape")
            return []

        # Emit the list of URLs queued for deep extraction.
        for i, url in enumerate(new_urls, 1):
            await self.log(f"Queue {i}/{len(new_urls)}: {url}")

        started = self._start()
        try:
            pages = await extract_pages(
                new_urls, crawl_client=self.crawl_client, tavily_client=self.tavily_client
            )
        except Exception as exc:
            self._stop(started)
            await self.fail("Page extraction failed", exc)
            return []
        elapsed = self._stop(started)
        by_provider: dict[str, int] = {}
        for p in pages:
            by_provider[p.provider] = by_provider.get(p.provider, 0) + 1
        providers = ", ".join(f"{name} {count}" for name, count in sorted(by_provider.items())) or "none"
        await self.log(
            f"Scraped {len(pages)}/{len(new_urls)} new pages via {providers} "
            f"({len(self.scraped_urls)} total, {elapsed:.1f}s)"
        )
        return [{"url": p.url, "markdown": p.markdown} for p in pages]


class AdIntelSubagent(ToolSubagent):
    tag = "AD_INTELLIGENCE"

    def __init__(
        self,
        tavily_client: Any = None,
        on_progress: ProgressFn | None = None,
        crawl_client: Any = None,
    ) -> None:
        super().__init__(on_progress)
        self.tavily_client = tavily_client
        self.crawl_client = crawl_client

    async def run(
        self,
        competitors: list[CompetitorProfile],
        category: str,
        target_geography: str | None = None,
    ) -> AdIntelResult:
        if not competitors:
            await self.log("No competitors to research ads for")
            return AdIntelResult()
        started = self._start()
        try:
            result = await search_competitor_ad_hooks(
                competitors=competitors,
                category=category,
                tavily_client=self.tavily_client,
                crawl_client=self.crawl_client,
                target_geography=target_geography,
            )
        except Exception as exc:
            self._stop(started)
            await self.fail("Ad search failed; continuing without ad hooks", exc)
            return AdIntelResult()
        elapsed = self._stop(started)
        for skipped in result.skipped:
            await self.log(f"Skipped {skipped}", level="WARN")
        hooks = result.hooks_by_competitor
        total = sum(len(h) for h in hooks.values())
        await self.log(
            f"Collected {total} real ad hooks across {len(hooks)} competitors, "
            f"{len(result.documents)} ad-library page(s) ({elapsed:.1f}s)"
        )
        return result


class SynthesisSubagent(ToolSubagent):
    tag = "LLM_SYNTH"

    def __init__(self, llm: Any, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(
        self,
        merchant_context: dict[str, Any],
        search_results: list[TavilySearchResult],
        extracted_pages: list[dict[str, Any]],
        taxonomy: DynamicParameterTaxonomy,
        ad_hooks_by_comp: dict[str, list[str]],
    ) -> SWOTReportDelta:
        """Raises on failure: the coordinator owns the degraded-report fallback."""
        await self.log(
            f"Synthesizing SWOT from {len(search_results)} results and {len(extracted_pages)} pages"
        )
        started = self._start()
        report = await synthesize_swot_with_llm(
            merchant_context=merchant_context,
            search_results=search_results,
            extracted_pages=extracted_pages,
            taxonomy=taxonomy,
            ad_hooks_by_comp=ad_hooks_by_comp,
            llm=self.llm,
        )
        elapsed = self._stop(started)
        await self.log(f"Produced {len(report.competitors)} competitor profiles ({elapsed:.1f}s)")
        return report


class GroundingSubagent(ToolSubagent):
    tag = "DATA_VALIDATION"

    async def run(
        self,
        report: SWOTReportDelta,
        scraped_text: list[str],
        verified_urls: set[str],
    ) -> tuple[SWOTReportDelta, list[str]]:
        started = self._start()
        report, diagnostics = validate_information_grounding(
            report=report,
            scraped_text=scraped_text,
            verified_urls=verified_urls,
            max_age_days=get_settings().recency_max_age_days,
        )
        elapsed = self._stop(started)
        await self.log(
            f"Grounding check made {len(diagnostics)} correction(s) ({elapsed * 1000:.0f}ms)",
            level="WARN" if diagnostics else "INFO",
        )
        return report, diagnostics


class ValidatorSubagent(ToolSubagent):
    """Adversarial critic: rejects items their own source passage does not support."""

    tag = "VALIDATOR"

    def __init__(self, llm: Any, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(
        self, report: SWOTReportDelta, corpus: list[str], round_number: int = 0
    ) -> tuple[SWOTReportDelta, ValidatorVerdict, list[str]]:
        if self.llm is None:
            return report, ValidatorVerdict(), []
        started = self._start()
        report, verdict, diagnostics = await validate_report(report, corpus, self.llm)
        elapsed = self._stop(started)
        gaps = ", ".join(f"{g.field.replace('_mined', '').replace('_model', '')} for {g.competitor}" for g in verdict.gaps)
        await self.log(
            f"Round {round_number}: rejected {len(diagnostics)} item(s)"
            + (f"; asked for more evidence: {gaps}" if gaps else "; no gaps worth another search")
            + f" ({elapsed:.1f}s)",
            level="WARN" if diagnostics else "INFO",
        )
        return report, verdict, diagnostics


class RelevanceSubagent(ToolSubagent):
    tag = "RELEVANCE_FILTER"

    def __init__(self, llm: Any, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(
        self,
        report: SWOTReportDelta,
        merchant_context: dict[str, Any],
    ) -> SWOTReportDelta:
        started = self._start()
        try:
            insights = await curate_dashboard_insights(report, merchant_context, self.llm)
            # Highlighted weaknesses are checked against the complaints actually mined, so the
            # dashboard's headline panel keeps the same factual guarantee as the rest.
            mined = [w for c in report.competitors for w in c.weaknesses_mined]
            report = apply_relevance_scores(report, insights, grounding_texts=mined, prune_irrelevant=True)
        except Exception as exc:
            self._stop(started)
            await self.fail("Relevance filtering failed; showing all data unfiltered", exc)
            return report
        elapsed = self._stop(started)
        primary_count = len(insights.primary_competitor_indices)
        await self.log(
            f"Curated dashboard: {primary_count} primary competitors, "
            f"{len(insights.highlight_weaknesses)} highlighted weaknesses, "
            f"{len(insights.recommended_actions)} actions ({elapsed:.1f}s)"
        )
        return report


class DisplayFilterValidatorSubagent(ToolSubagent):
    tag = "FILTER_VALIDATOR"

    def __init__(self, llm: Any, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(
        self,
        report: SWOTReportDelta,
        corpus: list[str],
    ) -> tuple[SWOTReportDelta, list[str]]:
        started = self._start()
        from orchestrator.agents.market_research.normalizers.display_validator import (
            filter_validate_and_repair_display_data,
        )
        report, diagnostics = await filter_validate_and_repair_display_data(report, corpus, self.llm)
        elapsed = self._stop(started)
        repairs = [d for d in diagnostics if d.startswith("[DATA_REPAIR]")]
        await self.log(
            f"Display data validated: {len(repairs)} repair(s) applied ({elapsed:.1f}s)",
            level="WARN" if repairs else "INFO",
        )
        return report, diagnostics


class ReviewContextSubagent(ToolSubagent):
    """Synthesizes why customers praise/complain, who they are, and how to beat them."""

    tag = "REVIEW_CONTEXT"

    def __init__(self, llm: Any, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(
        self,
        report: SWOTReportDelta,
        corpus: list[str],
        merchant_context: dict[str, Any],
    ) -> SWOTReportDelta:
        started = self._start()
        from orchestrator.agents.market_research.intelligence.profiling.review_context import (
            analyze_competitor_review_context,
        )
        try:
            report, diagnostics = await analyze_competitor_review_context(
                report, corpus, merchant_context, self.llm
            )
        except Exception as exc:
            self._stop(started)
            # Additive step: a failure costs context on the Customers tab, never the report.
            await self.fail("Review context synthesis failed; keeping mined quotes only", exc)
            return report
        elapsed = self._stop(started)
        for line in diagnostics:
            await self.log(line.removeprefix(f"[{self.tag}] "))
        with_context = sum(1 for c in report.competitors if c.review_context)
        await self.log(
            f"Review context synthesized for {with_context}/{len(report.competitors)} "
            f"competitors ({elapsed:.1f}s)"
        )
        return report


class _DiagnosticSubagent(ToolSubagent):
    """
    Shared shape for the post-synthesis report passes: run one analysis function, relay its
    diagnostic lines to the console, and contain any failure. Every one of these steps is
    additive, so a crash costs that step's output and never the report.
    """

    failure_message: ClassVar[str] = "Step failed; report left unchanged"

    async def _execute(self, fn, report: SWOTReportDelta, *args: Any) -> tuple[SWOTReportDelta, list[str]]:
        started = self._start()
        try:
            report, diagnostics = await fn(report, *args)
        except Exception as exc:
            self._stop(started)
            await self.fail(self.failure_message, exc)
            return report, []
        elapsed = self._stop(started)
        for line in diagnostics:
            await self.log(line.removeprefix(f"[{self.tag}] "))
        logger.debug("%s finished in %.1fs", self.tag, elapsed)
        return report, diagnostics


class FreshnessSubagent(_DiagnosticSubagent):
    """Dates profiles grounding could not and flags evidence too old to trust. No LLM."""

    tag = "FRESHNESS_AUDIT"
    failure_message = "Freshness audit failed; dates left as grounding set them"

    async def run(self, report: SWOTReportDelta, corpus: list[str]) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.intelligence.validation.freshness import audit_report_freshness

        max_age = get_settings().recency_max_age_days

        async def audit(r: SWOTReportDelta, c: list[str]) -> tuple[SWOTReportDelta, list[str]]:
            return r, audit_report_freshness(r, c, max_age_days=max_age)

        return await self._execute(audit, report, corpus)


class PricingNormalizerSubagent(_DiagnosticSubagent):
    """Parses pricing text into comparable amounts; LLM only for prose the regex misses."""

    tag = "PRICE_NORM"
    failure_message = "Pricing normalization failed; raw pricing text kept"

    def __init__(self, llm: Any = None, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(self, report: SWOTReportDelta) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.normalizers.pricing_normalizer import normalize_report_pricing

        return await self._execute(normalize_report_pricing, report, self.llm)


class ExecutiveSummarySubagent(_DiagnosticSubagent):
    """Rewrites the dashboard summary once every other step has finished."""

    tag = "EXEC_SUMMARY"
    failure_message = "Executive summary failed; relevance filter's draft kept"

    def __init__(self, llm: Any = None, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(
        self, report: SWOTReportDelta, merchant_context: dict[str, Any]
    ) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.intelligence.advisory.executive_summary import write_executive_summary

        return await self._execute(write_executive_summary, report, merchant_context, self.llm)


class SnapshotDiffSubagent(_DiagnosticSubagent):
    """Records review-count, ad-creative and normalized-price moves since the last scan. No LLM."""

    tag = "CHANGE_DETECT"
    failure_message = "Change detection failed; merge's change log kept"

    async def run(
        self, report: SWOTReportDelta, prior_report: SWOTReportDelta | None
    ) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.normalizers.snapshot_diff import diff_report

        async def diff(r: SWOTReportDelta, prior: SWOTReportDelta | None) -> tuple[SWOTReportDelta, list[str]]:
            _, diagnostics = diff_report(r, prior)
            return r, diagnostics

        return await self._execute(diff, report, prior_report)


class AdCopyGeneratorSubagent(_DiagnosticSubagent):
    """Writes ad concepts, each tied to a rival weakness found in the research."""

    tag = "AD_COPY"
    failure_message = "Ad copy generation failed; report shipped without ad angles"

    def __init__(self, llm: Any = None, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(
        self, report: SWOTReportDelta, merchant_context: dict[str, Any]
    ) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.intelligence.advisory.ad_copywriter import generate_ad_angles

        return await self._execute(generate_ad_angles, report, merchant_context, self.llm)


class WedgeFinderSubagent(_DiagnosticSubagent):
    """Tier 1: broad sweep of the merchant's niche, aimed at small and newly launched brands."""

    tag = "WEDGE_FINDER"
    failure_message = "Wedge scan failed; report shipped without the niche map"

    def __init__(self, tavily_client: Any = None, llm: Any = None, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.tavily_client = tavily_client
        self.llm = llm

    async def run(
        self,
        report: SWOTReportDelta,
        *,
        merchant_context: dict[str, Any],
        bench: list[CompetitorProfile],
        corpus: list[str],
        baseline: SWOTReportDelta | None = None,
        baseline_run_at: str | None = None,
    ) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.intelligence.market_mapping.wedge_finder import scan_wedge

        settings = get_settings()
        if not settings.wedge_scan_enabled:
            return report, []

        async def search(queries: list[SearchQuery]) -> list[TavilySearchResult]:
            for i, q in enumerate(queries, 1):
                domains = " → " + ", ".join(q.include_domains[:3]) if q.include_domains else ""
                await self.log(f"Query {i}/{len(queries)} [{q.vector}]{domains}: {q.query}")
            return await execute_tavily_search(queries, tavily_client=self.tavily_client)

        async def scan(r: SWOTReportDelta) -> tuple[SWOTReportDelta, list[str]]:
            r.wedge_scan, notes = await scan_wedge(
                merchant_context, r.competitors, bench, corpus, search, self.llm,
                baseline=baseline, baseline_date=baseline_run_at,
                max_candidates=settings.wedge_max_candidates,
            )
            return r, notes

        return await self._execute(scan, report)


class ThreatMonitorSubagent(_DiagnosticSubagent):
    """Tier 2: momentum scoring on the peer rivals most likely to overtake. No LLM."""

    tag = "THREAT_MONITOR"
    failure_message = "Threat watch failed; report shipped without momentum tracking"

    async def run(
        self,
        report: SWOTReportDelta,
        *,
        merchant_context: dict[str, Any],
        corpus: list[str],
        baseline: SWOTReportDelta | None = None,
        baseline_run_at: str | None = None,
    ) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.intelligence.market_mapping.threat_monitor import assign_cohorts, build_threat_watch

        async def watch(r: SWOTReportDelta) -> tuple[SWOTReportDelta, list[str]]:
            r.threat_watch, notes = build_threat_watch(
                r, corpus, merchant_context, wedge=r.wedge_scan, baseline=baseline,
                baseline_run_at=baseline_run_at, watch_size=get_settings().threat_watch_size,
            )
            return r, notes + assign_cohorts(r)

        return await self._execute(watch, report)


class LeapBenchmarkSubagent(_DiagnosticSubagent):
    """Analyzes breakout competitors that made a major leap in scale, clients, deals, and valuation."""

    tag = "LEAP_BENCHMARK"
    failure_message = "Breakout leap benchmark analysis failed; report shipped without leap benchmarks"

    def __init__(self, llm: Any = None, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(
        self,
        report: SWOTReportDelta,
        corpus: list[str],
        merchant_context: dict[str, Any],
    ) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.intelligence.profiling.leap_analyzer import analyze_leap_benchmarks

        return await self._execute(
            analyze_leap_benchmarks, report, corpus, merchant_context, self.llm
        )


class ProfileCompleterSubagent(_DiagnosticSubagent):
    """Finds each rival's missing facts and keeps only values with a verified source sentence."""

    tag = "PROFILE_COMPLETER"
    failure_message = "Profile completion failed; profiles kept as researched"

    def __init__(
        self, search: SearchSubagent, crawl: CrawlSubagent, llm: Any = None, on_progress: ProgressFn | None = None
    ) -> None:
        super().__init__(on_progress)
        self.search = search
        self.crawl = crawl
        self.llm = llm
        self.new_texts: list[str] = []
        self.new_urls: list[str] = []

    async def run(
        self,
        report: SWOTReportDelta,
        documents: list[tuple[str, str]],
        merchant_context: dict[str, Any] | None = None,
    ) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.intelligence.advisory import archetype
        from orchestrator.agents.market_research.intelligence.profiling.profile_completer import complete_profiles

        settings = get_settings()
        if not settings.profile_completion_enabled:
            return report, []

        async def complete(r: SWOTReportDelta) -> tuple[SWOTReportDelta, list[str]]:
            r, notes, self.new_texts, self.new_urls = await complete_profiles(
                r, documents,
                search_fn=lambda qs, rnd: self.search.run(qs, round_number=100 + rnd),
                crawl_fn=self.crawl.run,
                llm=self.llm,
                rounds=research_limit(settings, "profile_completion_rounds"),
                pages_per_competitor=settings.profile_pages_per_competitor,
                service_like=archetype.is_service_like(archetype.resolve(merchant_context)),
            )
            return r, notes

        return await self._execute(complete, report)


class ListingSubagent(_DiagnosticSubagent):
    """Reads each rival's own-site and marketplace listings: price, MRP, offers, rating, terms."""

    tag = "LISTINGS"
    failure_message = "Channel listing scan failed; buying patterns kept as researched"

    def __init__(
        self, search: SearchSubagent, crawl: CrawlSubagent, on_progress: ProgressFn | None = None, llm: Any = None
    ) -> None:
        super().__init__(on_progress)
        self.search = search
        self.crawl = crawl
        self.llm = llm  # picks the market's stores out of discovery searches

    async def run(
        self, report: SWOTReportDelta, merchant_context: dict[str, Any], documents: list[tuple[str, str]]
    ) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.intelligence.profiling.listing_intel import collect_channel_listings

        settings = get_settings()
        if not settings.channel_listings_enabled:
            return report, []

        ai_search_fn = None
        if settings.ai_price_search_enabled and settings.openai_api_key:
            from orchestrator.agents.market_research.ingestion.search_client import market_for
            from orchestrator.agents.market_research.intelligence.profiling.listing_intel import marketplaces_for
            from orchestrator.agents.market_research.intelligence.profiling.price_search import make_ai_price_search

            market = market_for(merchant_context)
            ai_search_fn = make_ai_price_search(
                settings.openai_api_key,
                settings.ai_price_search_model,
                market[1].title() if market else None,
                dict(marketplaces_for(merchant_context)),
            )

        async def collect(r: SWOTReportDelta) -> tuple[SWOTReportDelta, list[str]]:
            return await collect_channel_listings(
                r, merchant_context, documents,
                search_fn=lambda qs: self.search.run(qs, round_number=200),
                crawl_fn=self.crawl.run,
                max_per_competitor=settings.channel_listings_per_competitor,
                ai_search_fn=ai_search_fn,
                llm=self.llm,
            )

        return await self._execute(collect, report)


class BuyingPatternSubagent(_DiagnosticSubagent):
    """Analyzes commercial buying patterns, sales channels, unit economics, and buyer triggers for product companies."""

    tag = "BUYING_PATTERN"
    failure_message = "Commercial buying pattern analysis failed; report shipped without buying pattern insights"

    def __init__(self, llm: Any = None, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.llm = llm

    async def run(
        self,
        report: SWOTReportDelta,
        corpus: list[str],
        merchant_context: dict[str, Any],
    ) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.intelligence.profiling.buying_patterns import analyze_buying_patterns

        return await self._execute(
            analyze_buying_patterns, report, corpus, merchant_context, self.llm
        )


class MarketAudienceSubagent(_DiagnosticSubagent):
    """Market overview and audience (ICP, segments, pains, channels), each point sourced."""

    tag = "MARKET_AUDIENCE"
    failure_message = "Market and audience analysis failed; report kept without it"

    def __init__(self, search: SearchSubagent, llm: Any = None, on_progress: ProgressFn | None = None) -> None:
        super().__init__(on_progress)
        self.search = search
        self.llm = llm

    async def run(
        self, report: SWOTReportDelta, merchant_context: dict[str, Any]
    ) -> tuple[SWOTReportDelta, list[str]]:
        from orchestrator.agents.market_research.intelligence.advisory.market_audience import (
            analyze_market_and_audience,
        )

        return await self._execute(
            analyze_market_and_audience, report, merchant_context, self.llm,
            lambda qs: self.search.run(qs, round_number=300),
        )


@dataclass
class ResearchCrew:
    """The set of tool subagents the Market Research Agent coordinates."""

    taxonomy: TaxonomySubagent
    search: SearchSubagent
    crawl: CrawlSubagent
    ad_intel: AdIntelSubagent
    synthesis: SynthesisSubagent
    grounding: GroundingSubagent
    validator: ValidatorSubagent
    relevance: RelevanceSubagent
    display_validator: DisplayFilterValidatorSubagent
    review_context: ReviewContextSubagent
    freshness: FreshnessSubagent
    pricing: PricingNormalizerSubagent
    exec_summary: ExecutiveSummarySubagent
    snapshot_diff: SnapshotDiffSubagent
    ad_copy: AdCopyGeneratorSubagent
    wedge_finder: WedgeFinderSubagent
    threat_monitor: ThreatMonitorSubagent
    leap_benchmark: LeapBenchmarkSubagent
    buying_patterns: BuyingPatternSubagent
    # Built from this crew's own search and crawl subagents (see build), so it shares the
    # crawl's never-re-fetch memory instead of re-reading pages the research already has.
    profile_completer: ProfileCompleterSubagent | None = None
    listings: ListingSubagent | None = None
    market_audience: MarketAudienceSubagent | None = None
    members: list[ToolSubagent] = field(init=False)

    def __post_init__(self) -> None:
        self.members = [
            self.taxonomy, self.search, self.crawl, self.ad_intel,
            self.synthesis, self.grounding, self.validator, self.relevance,
            self.display_validator, self.review_context, self.freshness,
            self.pricing, self.exec_summary, self.snapshot_diff, self.ad_copy,
            self.wedge_finder, self.threat_monitor, self.leap_benchmark,
            self.buying_patterns,
        ]

    @classmethod
    def build(
        cls,
        *,
        tavily_client: Any = None,
        crawl_client: Any = None,
        llm: Any = None,
        fast_llm: Any = None,
        on_progress: ProgressFn | None = None,
    ) -> ResearchCrew:
        """`fast_llm` (defaults to `llm`) runs the light steps; synthesis and the validator keep `llm`."""
        fast_llm = fast_llm if fast_llm is not None else llm
        crew = cls(
            taxonomy=TaxonomySubagent(fast_llm, on_progress),
            search=SearchSubagent(tavily_client, on_progress),
            crawl=CrawlSubagent(crawl_client, on_progress, tavily_client=tavily_client),
            ad_intel=AdIntelSubagent(tavily_client, on_progress, crawl_client=crawl_client),
            synthesis=SynthesisSubagent(llm, on_progress),
            grounding=GroundingSubagent(on_progress),
            validator=ValidatorSubagent(llm, on_progress),
            relevance=RelevanceSubagent(fast_llm, on_progress),
            display_validator=DisplayFilterValidatorSubagent(llm, on_progress),
            review_context=ReviewContextSubagent(llm, on_progress),
            freshness=FreshnessSubagent(on_progress),
            pricing=PricingNormalizerSubagent(fast_llm, on_progress),
            exec_summary=ExecutiveSummarySubagent(llm, on_progress),
            snapshot_diff=SnapshotDiffSubagent(on_progress),
            ad_copy=AdCopyGeneratorSubagent(llm, on_progress),
            wedge_finder=WedgeFinderSubagent(tavily_client, fast_llm, on_progress),
            threat_monitor=ThreatMonitorSubagent(on_progress),
            leap_benchmark=LeapBenchmarkSubagent(llm, on_progress),
            buying_patterns=BuyingPatternSubagent(fast_llm, on_progress),
        )
        crew.profile_completer = ProfileCompleterSubagent(crew.search, crew.crawl, llm, on_progress)
        crew.members.append(crew.profile_completer)
        crew.listings = ListingSubagent(crew.search, crew.crawl, on_progress, llm=fast_llm)
        crew.members.append(crew.listings)
        crew.market_audience = MarketAudienceSubagent(crew.search, llm, on_progress)
        crew.members.append(crew.market_audience)
        return crew

    @property
    def errors(self) -> list[str]:
        return [err for member in self.members for err in member.errors]

    def usage_summary(self) -> str:
        return ", ".join(
            f"{m.tag.lower()}={m.calls} call(s)/{m.total_seconds:.1f}s" for m in self.members if m.calls
        )
