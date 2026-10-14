"""
Why a run scored 0.77 and could not climb.

Two defects, both about *acquiring* data rather than about the scoring maths:

  1. The loop gated on `pricing_model == "detected"` -- a placeholder meaning "a snippet
     looked price-shaped" -- so it believed pricing was covered, converged, and never fired
     the targeted pricing retry. Synthesis is strict, so the delivered report had real
     pricing for 1 of 3 rivals and scored below the gate that had passed it.
  2. Crawl slots were handed out by score alone, so one dominant site could take the whole
     budget and the other competitors got no page at all -- least of all a pricing page.
"""

from __future__ import annotations

from orchestrator.agents.market_research.intelligence.validation.scoring import (
    PLACEHOLDER_PRICING,
    calculate_dqs,
)
from orchestrator.agents.market_research.ingestion.page_extractor import extract_target_urls
from orchestrator.agents.market_research.ingestion.search_client import TavilySearchResult
from orchestrator.schemas.research import CompetitorProfile


def _competitors(pricing, n=3):
    return [
        CompetitorProfile(
            brand_name=f"B{i}",
            product_name=f"P{i}",
            pricing_model=pricing,
            weaknesses_mined=["slow support"],
            sources=[f"https://b{i}.com"],
            factual_evidence=["quoted evidence"],
        )
        for i in range(n)
    ]


_SOURCES = [f"https://host{i}.com" for i in range(6)]


class TestPlaceholderPricingDoesNotSatisfyTheGate:
    def test_detected_placeholder_scores_zero_for_pricing(self):
        result = calculate_dqs(_competitors(PLACEHOLDER_PRICING), _SOURCES)
        assert result.p_pricing == 0.0
        assert any("P_pricing" in d for d in result.diagnostics)

    def test_run_of_placeholders_does_not_pass_the_threshold(self):
        """It must keep iterating instead of shipping a report with no real prices."""
        assert calculate_dqs(_competitors(PLACEHOLDER_PRICING), _SOURCES).passed is False

    def test_real_prices_score_full_credit(self):
        result = calculate_dqs(_competitors("$399.99", n=5), _SOURCES)
        assert result.p_pricing == 1.0
        assert result.passed is True

    def test_placeholder_and_real_prices_are_counted_differently(self):
        placeholder = calculate_dqs(_competitors(PLACEHOLDER_PRICING, n=5), _SOURCES)
        real = calculate_dqs(_competitors("$49/mo", n=5), _SOURCES)
        assert real.score > placeholder.score

    def test_mixed_set_counts_only_the_real_ones(self):
        comps = _competitors("$19/mo", n=2) + _competitors(PLACEHOLDER_PRICING, n=3)
        # MIN_PRICING_FULL is 4, so two real prices is half credit.
        assert calculate_dqs(comps, _SOURCES).p_pricing == 0.5


class TestCrawlBudgetIsSpreadAcrossCompetitors:
    def test_one_dominant_site_cannot_take_every_slot(self):
        results = [
            TavilySearchResult(
                vector="pricing_scrape", title="t", url=f"https://big.com/p{i}",
                snippet="", score=0.9 - i * 0.01,
            )
            for i in range(10)
        ] + [
            TavilySearchResult(
                vector="pricing_scrape", title="t", url=f"https://rival{i}.com/pricing",
                snippet="", score=0.5,
            )
            for i in range(5)
        ]
        urls = extract_target_urls(results, max_urls=10)
        hosts = {u.split("/")[2] for u in urls}
        assert len(hosts) >= 6, "every competitor should get a page before any gets a second"
        assert all(f"rival{i}.com" in hosts for i in range(5))

    def test_still_respects_max_urls(self):
        results = [
            TavilySearchResult(
                vector="pricing_scrape", title="t", url=f"https://h{i}.com/a",
                snippet="", score=0.5,
            )
            for i in range(30)
        ]
        assert len(extract_target_urls(results, max_urls=7)) == 7

    def test_highest_scoring_page_within_a_host_still_comes_first(self):
        results = [
            TavilySearchResult(vector="pricing_scrape", title="t", url="https://a.com/low", snippet="", score=0.2),
            TavilySearchResult(vector="pricing_scrape", title="t", url="https://a.com/high", snippet="", score=0.9),
        ]
        assert extract_target_urls(results, max_urls=2)[0] == "https://a.com/high"

    def test_deduplicates_and_handles_empty(self):
        dupe = [
            TavilySearchResult(vector="pricing_scrape", title="t", url="https://a.com/x", snippet="", score=0.9),
            TavilySearchResult(vector="gripe_mining", title="t", url="https://a.com/x", snippet="", score=0.8),
        ]
        assert extract_target_urls(dupe, max_urls=5) == ["https://a.com/x"]
        assert extract_target_urls([], max_urls=5) == []
