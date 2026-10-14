"""Unit tests verifying complete 4-quadrant SWOT matrix generation and fallback grounding."""

import pytest
from orchestrator.agents.market_research.intelligence.advisory.synthesis import (
    _ground_swot_matrix,
    synthesize_swot_with_llm,
)
from orchestrator.schemas.research import (
    CompetitorProfile,
    SWOTAnalysis,
    SWOTReportDelta,
)


class TestSWOTMatrixGrounding:
    def test_ground_swot_matrix_populates_missing_quadrants(self):
        merchant_context = {
            "product_name": "AgilePilot",
            "category": "B2B SaaS DevTools",
            "primary_value_prop": "Automated regression testing in 3 minutes",
            "goal": "Displace legacy Selenium pipelines",
        }
        competitors = [
            CompetitorProfile(
                brand_name="LegacyTestCo",
                product_name="LegacySuite",
                pricing_model="$2,500/mo enterprise contract",
                weaknesses_mined=["Sluggish test execution times and frequent timeout crashes"],
            ),
            CompetitorProfile(
                brand_name="OldCloudRunner",
                product_name="CloudRunner",
                weaknesses_mined=["Opaque pricing tiers and complicated YAML configuration"],
            ),
        ]

        # Empty SWOT should be grounded with 4 complete quadrants
        empty_swot = SWOTAnalysis()
        grounded = _ground_swot_matrix(empty_swot, merchant_context, competitors)

        assert len(grounded.strengths) >= 2
        assert any("Automated regression testing" in s for s in grounded.strengths)

        assert len(grounded.weaknesses) >= 2
        assert any("Early-stage" in w for w in grounded.weaknesses)

        assert len(grounded.opportunities) >= 2
        assert any("LegacyTestCo" in o for o in grounded.opportunities)
        assert any("OldCloudRunner" in o for o in grounded.opportunities)

        assert len(grounded.threats) >= 2
        assert any("LegacyTestCo" in t for t in grounded.threats)

    def test_ground_swot_matrix_preserves_existing_llm_items(self):
        existing_swot = SWOTAnalysis(
            strengths=["Proprietary low-latency compiler"],
            weaknesses=["No on-premise air-gapped deployment option"],
            opportunities=["Cloud migration mandate among Fortune 500"],
            threats=["Big Tech open source alternative"],
        )
        grounded = _ground_swot_matrix(existing_swot, {}, [])

        assert grounded.strengths == ["Proprietary low-latency compiler"]
        assert grounded.weaknesses == ["No on-premise air-gapped deployment option"]
        assert grounded.opportunities == ["Cloud migration mandate among Fortune 500"]
        assert grounded.threats == ["Big Tech open source alternative"]


@pytest.mark.asyncio
async def test_synthesize_swot_with_llm_ensures_swot_and_positioning_gap():
    class _MockStructuredLLM:
        def with_structured_output(self, _schema, **_kw):
            return self

        async def ainvoke(self, _messages):
            # Model returns competitors with mined weaknesses but empty SWOT
            return SWOTReportDelta(
                competitors=[
                    CompetitorProfile(
                        brand_name="RivalCorp",
                        product_name="RivalSaaS",
                        weaknesses_mined=["Extremely high per-seat billing and slow support"],
                    )
                ],
                swot=SWOTAnalysis(),  # empty from LLM
                positioning_gap=None,
            )

    report = await synthesize_swot_with_llm(
        merchant_context={"product_name": "ModernApp", "category": "Fintech"},
        search_results=[],
        extracted_pages=[],
        llm=_MockStructuredLLM(),
    )

    assert isinstance(report, SWOTReportDelta)
    assert len(report.swot.strengths) > 0
    assert len(report.swot.weaknesses) > 0
    assert len(report.swot.opportunities) > 0
    assert any("RivalCorp" in o for o in report.swot.opportunities)
    assert len(report.swot.threats) > 0
    assert report.positioning_gap is not None
    assert "Disruptive Fintech" in report.positioning_gap.quadrant
