"""
Loop 3 Verification: Market Research Agent node execution with mocked externals.

All Tavily, CrawlAPI, and LLM calls are mocked — no live API keys required.
Tests verify the agent's internal flow: query building, DQS gating, retry logic,
assumption tagging, and output schema conformance.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.agents.market_research.agent import execute_market_research
from orchestrator.agents.market_research.pipeline.loop import (
    _extract_brand_from_url,
    extract_preliminary_competitors as _extract_preliminary_competitors,
)
from orchestrator.agents.market_research.discovery.search import TavilySearchResult
from orchestrator.schemas.research import (
    CompetitorProfile,
    MarketPositioningGap,
    SWOTAnalysis,
    SWOTReportDelta,
)
from orchestrator.schemas.state import StrategyState


# ── Fixtures & Helpers ────────────────────────────────────────────────────────

MOCK_MERCHANT_CONTEXT = {
    "product_name": "ErgoMouse V2",
    "category": "B2B Ergonomic Computer Peripherals",
    "primary_value_prop": "Patented 57-degree neutral wrist angle with mechanical switches",
    "price_usd": 129.00,
    "known_competitors": ["Logitech Lift", "Logitech MX Master 3S"],
}


def _make_base_state(**overrides) -> StrategyState:
    base: StrategyState = {
        "merchant_context": MOCK_MERCHANT_CONTEXT,
        "swot_report": None,
        "dqs_retries": 0,
        "errors": [],
    }
    return cast(StrategyState, {**base, **overrides})


def _make_search_results(
    count: int = 5,
    include_pricing: bool = True,
    include_gripes: bool = True,
) -> list[TavilySearchResult]:
    """Generate mock TavilySearchResult list with controllable data quality."""
    results = []
    for i in range(count):
        results.append(TavilySearchResult(
            vector="alternative_discovery",
            title=f"Competitor Product {i}",
            url=f"https://competitor{i}.com/product",
            snippet=f"A great ergonomic mouse alternative for B2B buyers.",
            score=0.8 - (i * 0.05),
        ))

    if include_pricing:
        for i in range(3):
            results.append(TavilySearchResult(
                vector="pricing_scrape",
                title=f"Pricing for Product {i}",
                url=f"https://competitor{i}.com/pricing",
                snippet=f"Starting at ${49 + i * 20}/mo. Free tier available. Enterprise pricing on request.",
                score=0.75,
            ))

    if include_gripes:
        for i in range(3):
            results.append(TavilySearchResult(
                vector="gripe_mining",
                title=f"Reddit thread about Product {i}",
                url=f"https://reddit.com/r/ergonomics/post{i}",
                snippet=f"I really wish this mouse had better scroll wheel. The weight is an issue for long sessions and the battery drains too fast.",
                score=0.6,
            ))

    results.append(TavilySearchResult(
        vector="messaging_claims",
        title="Logitech Lift marketing",
        url="https://logitech.com/lift",
        snippet="Designed for all-day comfort with a 57-degree vertical design.",
        score=0.7,
    ))

    return results


def _make_mock_llm_response() -> SWOTReportDelta:
    """Pre-built SWOTReportDelta that the mock LLM returns."""
    return SWOTReportDelta(
        competitors=[
            CompetitorProfile(
                brand_name="Logitech",
                product_name="Lift",
                pricing_model="one-time $69.99",
                core_claims=["57-degree vertical design", "quiet clicks"],
                weaknesses_mined=["no mechanical switches", "limited DPI range"],
                sources=["https://logitech.com/lift"],
            ),
            CompetitorProfile(
                brand_name="Logitech",
                product_name="MX Master 3S",
                pricing_model="one-time $99.99",
                core_claims=["8000 DPI", "USB-C", "multi-device"],
                weaknesses_mined=["heavy at 141g", "not truly ergonomic"],
                sources=["https://logitech.com/mx-master-3s"],
            ),
            CompetitorProfile(
                brand_name="Microsoft",
                product_name="Sculpt Ergonomic Mouse",
                pricing_model="one-time $49.99",
                core_claims=["thumb scoop", "Windows button"],
                weaknesses_mined=["uses AA batteries", "no Bluetooth 5"],
                sources=["https://microsoft.com/sculpt"],
            ),
        ],
        swot=SWOTAnalysis(
            strengths=["Patented 57-degree angle", "Mechanical switches"],
            weaknesses=["Unknown brand in B2B space"],
            opportunities=["B2B ergonomic niche underserved by Logitech"],
            threats=["Logitech brand loyalty", "Price sensitivity in B2B procurement"],
        ),
        positioning_gap=MarketPositioningGap(
            quadrant="Premium-Ergonomic-Mechanical",
            hook_angle="The only mechanical ergo mouse under $150",
        ),
        dqs_score=0.0,
        assumptions_tagged=False,
        source_urls=[],
    )


class _MockStructuredLLM:
    """Simulates ChatOpenAI().with_structured_output(SWOTReportDelta)."""

    def __init__(self, response: SWOTReportDelta):
        self._response = response

    async def ainvoke(self, messages: list) -> SWOTReportDelta:
        return self._response


class _MockBaseLLM:
    """Simulates ChatOpenAI() — returns a _MockStructuredLLM from with_structured_output."""

    def __init__(self, response: SWOTReportDelta):
        self._response = response

    def with_structured_output(self, schema):
        return _MockStructuredLLM(self._response)


def _mock_tavily_client(results: list[TavilySearchResult]):
    """Build a mock Tavily client that returns pre-built results."""
    async def _search(**kwargs):
        return {
            "results": [
                {"title": r.title, "url": r.url, "content": r.snippet, "score": r.score}
                for r in results
            ]
        }

    client = AsyncMock()
    client.search = _search
    return client


def _mock_crawl_client():
    """Build a mock CrawlAPI client that returns synthetic markdown."""
    async def _fetch(url, **kwargs):
        body = f"# Mock content for {url}\n" + "Some product details and pricing info here. " * 8
        return {"url": url, "status": 200, "body": body}

    client = MagicMock()
    client.configured = True
    client.can_render_js = False
    client.fetch = _fetch
    return client


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPreliminaryCompetitorExtraction:
    def test_extracts_from_search_results(self):
        results = _make_search_results(count=3, include_pricing=True, include_gripes=True)
        competitors = _extract_preliminary_competitors(results)
        assert len(competitors) > 0
        assert all(isinstance(c, CompetitorProfile) for c in competitors)

    def test_deduplicates_by_url(self):
        results = [
            TavilySearchResult(vector="alternative_discovery", title="A", url="https://a.com", snippet="test", score=0.8),
            TavilySearchResult(vector="pricing_scrape", title="A again", url="https://a.com", snippet="pricing $50", score=0.7),
        ]
        competitors = _extract_preliminary_competitors(results)
        assert len(competitors) == 1

    def test_detects_pricing_keywords(self):
        results = [
            TavilySearchResult(
                vector="pricing_scrape",
                title="Pricing Page",
                url="https://example.com/pricing",
                snippet="Starting at $49/mo with a free tier",
                score=0.8,
            ),
        ]
        competitors = _extract_preliminary_competitors(results)
        assert competitors[0].pricing_model == "detected"

    def test_no_pricing_sets_none(self):
        results = [
            TavilySearchResult(
                vector="alternative_discovery",
                title="Some Product",
                url="https://example.com/features",
                snippet="A great ergonomic mouse with many features",
                score=0.8,
            ),
        ]
        competitors = _extract_preliminary_competitors(results)
        assert competitors[0].pricing_model is None


class TestBrandExtraction:
    def test_standard_url(self):
        assert _extract_brand_from_url("https://www.logitech.com/lift") == "Logitech"

    def test_subdomain(self):
        assert _extract_brand_from_url("https://store.microsoft.com/sculpt") == "Microsoft"

    def test_country_second_level_domain(self):
        assert _extract_brand_from_url("https://www.argos.co.uk/product/1") == "Argos"

    def test_no_www(self):
        assert _extract_brand_from_url("https://reddit.com/r/ergonomics") == "Reddit"

    def test_invalid_url(self):
        result = _extract_brand_from_url("not-a-url")
        assert isinstance(result, str)


@pytest.mark.asyncio
class TestExecuteMarketResearch:
    async def test_happy_path_returns_valid_delta(self):
        """Full pipeline with mocked externals — should return a valid state delta."""
        search_results = _make_search_results(count=5, include_pricing=True, include_gripes=True)
        state = _make_base_state()

        result = await execute_market_research(
            state,
            tavily_client=_mock_tavily_client(search_results),
            crawl_client=_mock_crawl_client(),
            llm=_MockBaseLLM(_make_mock_llm_response()),
        )

        assert "swot_report" in result
        assert "dqs_retries" in result
        assert "errors" in result
        assert isinstance(result["swot_report"], SWOTReportDelta)

    async def test_output_has_source_urls(self):
        search_results = _make_search_results(count=5, include_pricing=True, include_gripes=True)
        state = _make_base_state()

        result = await execute_market_research(
            state,
            tavily_client=_mock_tavily_client(search_results),
            crawl_client=_mock_crawl_client(),
            llm=_MockBaseLLM(_make_mock_llm_response()),
        )

        assert len(result["swot_report"].source_urls) > 0

    async def test_dqs_score_populated(self):
        search_results = _make_search_results(count=5, include_pricing=True, include_gripes=True)
        state = _make_base_state()

        result = await execute_market_research(
            state,
            tavily_client=_mock_tavily_client(search_results),
            crawl_client=_mock_crawl_client(),
            llm=_MockBaseLLM(_make_mock_llm_response()),
        )

        assert 0.0 <= result["swot_report"].dqs_score <= 1.0


@pytest.mark.asyncio
class TestSynthesisFallbackInventsNothing:
    """
    When synthesis fails the run still returns, but it must report only what was observed.
    A templated SWOT reads like a finding, and the grounding gate validates competitor
    fields rather than SWOT prose, so anything asserted here would go unchallenged.
    """

    @staticmethod
    def _llm_that_fails_synthesis():
        class _FailsOnSynthesis:
            def with_structured_output(self, schema, **_kw):
                if schema is SWOTReportDelta:
                    return self
                return _MockStructuredLLM(_make_mock_llm_response())

            async def ainvoke(self, _messages):
                raise RuntimeError("synthesis model unavailable")

        return _FailsOnSynthesis()

    async def _run(self):
        return await execute_market_research(
            _make_base_state(),
            tavily_client=_mock_tavily_client(_make_search_results()),
            crawl_client=_mock_crawl_client(),
            llm=self._llm_that_fails_synthesis(),
        )

    async def test_run_still_completes_and_is_flagged(self):
        report = (await self._run())["swot_report"]
        assert isinstance(report, SWOTReportDelta)
        assert report.assumptions_tagged is True
        assert any("synthesis fallback" in d.lower() for d in report.dqs_diagnostics)

    async def test_no_invented_market_assertions(self):
        report = (await self._run())["swot_report"]
        swot_text = " ".join(
            report.swot.strengths + report.swot.weaknesses
            + report.swot.opportunities + report.swot.threats
        ).lower()
        # Previously hardcoded claims that no source ever supported.
        assert "aggressive competitor advertising" not in swot_text
        assert "market awareness and domain search visibility" not in swot_text

    async def test_unverifiable_sections_left_empty(self):
        report = (await self._run())["swot_report"]
        # The merchant's own weaknesses and opportunities require the synthesis that failed.
        assert report.swot.weaknesses == []
        assert report.swot.opportunities == []
        # An uncontested-quadrant claim is a synthesis conclusion, not an observation.
        assert report.positioning_gap is None

    async def test_reports_what_was_actually_observed(self):
        report = (await self._run())["swot_report"]
        # The merchant's own value prop is their claim, attributed as such.
        assert any("merchant-stated" in s.lower() for s in report.swot.strengths)
        # Threats name only competitors that discovery actually returned.
        if report.competitors:
            assert any("discovered" in t.lower() for t in report.swot.threats)

    async def test_fallback_still_runs_grounding_gate(self):
        """The fallback path must not skip anti-hallucination checks on competitor data."""
        report = (await self._run())["swot_report"]
        for comp in report.competitors:
            # Grounding prunes any source URL not in the verified set.
            assert all(u in report.source_urls for u in comp.sources)

    async def test_low_quality_data_triggers_assumptions(self):
        """Empty search results → DQS = 0.0, exhausts retries, tags assumptions."""
        empty_results: list[TavilySearchResult] = []
        state = _make_base_state()

        result = await execute_market_research(
            state,
            tavily_client=_mock_tavily_client(empty_results),
            crawl_client=_mock_crawl_client(),
            llm=_MockBaseLLM(_make_mock_llm_response()),
        )

        assert result["swot_report"].assumptions_tagged is True
        assert result["dqs_retries"] == 3

    async def test_retries_increment_on_low_dqs(self):
        """Sparse results should cause retries up to max."""
        sparse_results = [
            TavilySearchResult(
                vector="alternative_discovery",
                title="One result",
                url="https://single.com",
                snippet="Just one competitor found",
                score=0.5,
            ),
        ]
        state = _make_base_state()

        result = await execute_market_research(
            state,
            tavily_client=_mock_tavily_client(sparse_results),
            crawl_client=_mock_crawl_client(),
            llm=_MockBaseLLM(_make_mock_llm_response()),
        )

        assert result["dqs_retries"] >= 1

    async def test_existing_retries_carried_forward(self):
        """If state already has dqs_retries=2, agent should exhaust after 1 more."""
        empty_results: list[TavilySearchResult] = []
        state = _make_base_state(dqs_retries=2)

        result = await execute_market_research(
            state,
            tavily_client=_mock_tavily_client(empty_results),
            crawl_client=_mock_crawl_client(),
            llm=_MockBaseLLM(_make_mock_llm_response()),
        )

        assert result["dqs_retries"] == 3
        assert result["swot_report"].assumptions_tagged is True

    async def test_llm_failure_returns_degraded_report(self):
        """If LLM synthesis throws, agent should return a degraded SWOTReportDelta."""

        class _FailingLLM:
            def with_structured_output(self, schema):
                return self

            async def ainvoke(self, messages):
                raise RuntimeError("LLM inference timeout")

        search_results = _make_search_results(count=5, include_pricing=True, include_gripes=True)
        state = _make_base_state()

        result = await execute_market_research(
            state,
            tavily_client=_mock_tavily_client(search_results),
            crawl_client=_mock_crawl_client(),
            llm=_FailingLLM(),
        )

        assert isinstance(result["swot_report"], SWOTReportDelta)
        assert result["swot_report"].assumptions_tagged is True
        assert any("LLM synthesis" in d for d in result["swot_report"].dqs_diagnostics)
        assert any("LLM synthesis" in e for e in result["errors"])

    async def test_tavily_failure_logs_error_and_continues(self):
        """If Tavily raises, agent should log error and proceed with empty results."""

        async def _exploding_search(**kwargs):
            raise ConnectionError("Tavily API unreachable")

        broken_tavily = AsyncMock()
        broken_tavily.search = _exploding_search

        state = _make_base_state()

        result = await execute_market_research(
            state,
            tavily_client=broken_tavily,
            crawl_client=_mock_crawl_client(),
            llm=_MockBaseLLM(_make_mock_llm_response()),
        )

        assert isinstance(result["swot_report"], SWOTReportDelta)
        assert result["swot_report"].assumptions_tagged is True

    async def test_output_dict_keys_match_state_contract(self):
        """Returned dict must only contain keys present in StrategyState."""
        search_results = _make_search_results()
        state = _make_base_state()

        result = await execute_market_research(
            state,
            tavily_client=_mock_tavily_client(search_results),
            crawl_client=_mock_crawl_client(),
            llm=_MockBaseLLM(_make_mock_llm_response()),
        )

        valid_keys = set(StrategyState.__annotations__.keys())
        for key in result:
            assert key in valid_keys, f"Unexpected key '{key}' in agent output delta"
