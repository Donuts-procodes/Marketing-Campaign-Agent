"""Dashboard relevance curation: ranking, bounds, and the factual guard on highlights."""

from __future__ import annotations

import pytest

from orchestrator.agents.market_research.analysis.relevance_filter import apply_relevance_scores
from orchestrator.schemas.research import (
    CompetitorProfile,
    CompetitorRelevance,
    DashboardInsights,
    SWOTReportDelta,
)


def _competitors(n: int, **kw) -> list[CompetitorProfile]:
    return [CompetitorProfile(brand_name=f"B{i}", product_name=f"P{i}", **kw) for i in range(n)]


def _report(n: int, **kw) -> SWOTReportDelta:
    return SWOTReportDelta(competitors=_competitors(n, **kw))


class TestScoreBounds:
    def test_scores_stay_within_schema_bounds(self):
        """relevance_score is declared ge=0 le=1; pydantic does not re-validate assignment."""
        out = apply_relevance_scores(_report(10), DashboardInsights(primary_competitor_indices=[5, 6, 7, 8, 9]))
        scores = [c.relevance_score for c in out.competitors]
        assert max(scores) <= 1.0
        assert min(scores) >= 0.0

    def test_primaries_never_rank_below_secondaries(self):
        """Regression: positional decay once scored non-primaries above primaries."""
        out = apply_relevance_scores(_report(10), DashboardInsights(primary_competitor_indices=[5, 6, 7, 8, 9]))
        scores = [c.relevance_score for c in out.competitors]
        primaries, secondaries = scores[:5], scores[5:]
        assert min(primaries) >= max(secondaries)

    def test_competitors_sorted_by_relevance(self):
        out = apply_relevance_scores(_report(6), DashboardInsights(primary_competitor_indices=[4, 5]))
        scores = [c.relevance_score for c in out.competitors]
        assert scores == sorted(scores, reverse=True)


class TestInvalidIndices:
    def test_out_of_range_index_does_not_empty_the_primary_set(self):
        """Regression: a hallucinated index used to leave zero primaries on the dashboard."""
        out = apply_relevance_scores(_report(3), DashboardInsights(primary_competitor_indices=[99]))
        assert out.dashboard_insights.primary_competitor_indices != []

    def test_mixed_valid_and_invalid_indices_keeps_the_valid_ones(self):
        out = apply_relevance_scores(_report(4), DashboardInsights(primary_competitor_indices=[1, 99, -3]))
        assert len(out.dashboard_insights.primary_competitor_indices) == 1
        assert out.competitors[0].brand_name == "B1"

    def test_falls_back_to_model_scores_when_no_valid_index(self):
        insights = DashboardInsights(
            primary_competitor_indices=[42],
            competitor_relevance=[
                CompetitorRelevance(index=0, score=0.1),
                CompetitorRelevance(index=1, score=0.9),
            ],
        )
        out = apply_relevance_scores(_report(2), insights)
        # Highest-scored competitor should lead despite the bogus primary index.
        assert out.competitors[0].brand_name == "B1"

    def test_empty_competitor_list_is_safe(self):
        out = apply_relevance_scores(_report(0), DashboardInsights(primary_competitor_indices=[0, 1]))
        assert out.competitors == []
        assert out.dashboard_insights is not None


class TestModelSuppliedRelevance:
    def test_uses_model_scores_and_reasons(self):
        insights = DashboardInsights(
            primary_competitor_indices=[2],
            competitor_relevance=[
                CompetitorRelevance(index=0, score=0.2, reason="Global MNC, not a peer"),
                CompetitorRelevance(index=1, score=0.5, reason="Adjacent segment"),
                CompetitorRelevance(index=2, score=0.95, reason="Direct head-to-head rival"),
            ],
        )
        out = apply_relevance_scores(_report(3), insights)
        assert out.competitors[0].brand_name == "B2"
        assert out.competitors[0].relevance_reason == "Direct head-to-head rival"
        assert out.competitors[-1].relevance_score == pytest.approx(0.2)

    def test_secondary_score_is_capped_below_primary(self):
        """A model score of 0.99 on a non-primary must not outrank the primaries."""
        insights = DashboardInsights(
            primary_competitor_indices=[0],
            competitor_relevance=[CompetitorRelevance(index=1, score=0.99, reason="hyped")],
        )
        out = apply_relevance_scores(_report(2), insights)
        assert out.competitors[0].brand_name == "B0"
        assert out.competitors[1].relevance_score <= out.competitors[0].relevance_score


class TestHighlightGrounding:
    """The dashboard's headline panel must not introduce a complaint no source made."""

    MINED = [
        "Support tickets go unanswered for days according to several reviewers.",
        "The mobile app crashes when exporting large reports.",
    ]

    def test_keeps_weaknesses_that_restate_mined_complaints(self):
        insights = DashboardInsights(
            primary_competitor_indices=[0],
            highlight_weaknesses=["The mobile app crashes when exporting large reports."],
        )
        out = apply_relevance_scores(_report(1), insights, grounding_texts=self.MINED)
        assert out.dashboard_insights.highlight_weaknesses == [
            "The mobile app crashes when exporting large reports."
        ]

    def test_drops_invented_weaknesses(self):
        insights = DashboardInsights(
            primary_competitor_indices=[0],
            highlight_weaknesses=["Their servers are located offshore and leak customer data."],
        )
        out = apply_relevance_scores(_report(1), insights, grounding_texts=self.MINED)
        assert out.dashboard_insights.highlight_weaknesses == []

    def test_without_grounding_texts_highlights_pass_through(self):
        """Opt-in guard: callers that have no mined corpus keep existing behaviour."""
        insights = DashboardInsights(
            primary_competitor_indices=[0], highlight_weaknesses=["anything at all"]
        )
        out = apply_relevance_scores(_report(1), insights)
        assert out.dashboard_insights.highlight_weaknesses == ["anything at all"]
