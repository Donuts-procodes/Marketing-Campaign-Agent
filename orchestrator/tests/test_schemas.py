"""Loop 1 Verification: Schema serialization and typed-default round-trip tests."""

from __future__ import annotations

import json
import pytest

from orchestrator.schemas.research import (
    CompetitorProfile,
    MarketPositioningGap,
    SWOTAnalysis,
    SWOTReportDelta,
)
from orchestrator.schemas.state import StrategyState


class TestCompetitorProfile:
    def test_minimal_construction(self):
        cp = CompetitorProfile(brand_name="Logitech", product_name="MX Master 3S")
        assert cp.brand_name == "Logitech"
        assert cp.pricing_model is None
        assert cp.core_claims == []
        assert cp.weaknesses_mined == []
        assert cp.sources == []

    def test_full_round_trip(self):
        data = {
            "brand_name": "Logitech",
            "product_name": "MX Master 3S",
            "pricing_model": "one-time $99",
            "core_claims": ["8000 DPI sensor", "USB-C fast charge"],
            "weaknesses_mined": ["heavy at 141g", "no mechanical switches"],
            "sources": ["https://logitech.com/mx-master-3s"],
        }
        cp = CompetitorProfile.model_validate(data)
        roundtripped = CompetitorProfile.model_validate_json(cp.model_dump_json())
        assert roundtripped == cp

    def test_rejects_missing_required_fields(self):
        with pytest.raises(Exception):
            CompetitorProfile.model_validate({})


class TestSWOTAnalysis:
    def test_defaults_to_empty_lists(self):
        swot = SWOTAnalysis()
        assert swot.strengths == []
        assert swot.weaknesses == []
        assert swot.opportunities == []
        assert swot.threats == []

    def test_serialization_round_trip(self):
        swot = SWOTAnalysis(
            strengths=["patented wrist angle"],
            weaknesses=["unknown brand"],
            opportunities=["B2B ergonomic niche underserved"],
            threats=["Logitech brand loyalty"],
        )
        roundtripped = SWOTAnalysis.model_validate_json(swot.model_dump_json())
        assert roundtripped == swot


class TestMarketPositioningGap:
    def test_construction(self):
        gap = MarketPositioningGap(
            quadrant="Premium-Ergonomic-Mechanical",
            hook_angle="The only mechanical ergo mouse under $150",
        )
        assert gap.quadrant == "Premium-Ergonomic-Mechanical"

    def test_rejects_missing_fields(self):
        with pytest.raises(Exception):
            MarketPositioningGap.model_validate({})


class TestSWOTReportDelta:
    def test_empty_defaults(self):
        delta = SWOTReportDelta()
        assert delta.competitors == []
        assert delta.dqs_score == 0.0
        assert delta.assumptions_tagged is False
        assert delta.positioning_gap is None
        assert delta.source_urls == []
        assert delta.dqs_diagnostics == []

    def test_dqs_score_clamping(self):
        with pytest.raises(Exception):
            SWOTReportDelta(dqs_score=1.5)
        with pytest.raises(Exception):
            SWOTReportDelta(dqs_score=-0.1)

    def test_full_assembly_round_trip(self):
        delta = SWOTReportDelta(
            competitors=[
                CompetitorProfile(brand_name="Logitech", product_name="MX Master 3S"),
                CompetitorProfile(brand_name="Logitech", product_name="Lift"),
            ],
            swot=SWOTAnalysis(
                strengths=["patented angle"],
                weaknesses=["low awareness"],
                opportunities=["B2B niche"],
                threats=["brand loyalty"],
            ),
            positioning_gap=MarketPositioningGap(
                quadrant="Premium-Ergo-Mechanical",
                hook_angle="Only mechanical ergo under $150",
            ),
            dqs_score=0.87,
            assumptions_tagged=False,
            source_urls=["https://example.com/pricing"],
            dqs_diagnostics=[],
        )
        raw_json = delta.model_dump_json()
        parsed = json.loads(raw_json)
        assert len(parsed["competitors"]) == 2
        assert parsed["dqs_score"] == 0.87

        roundtripped = SWOTReportDelta.model_validate_json(raw_json)
        assert roundtripped.competitors[0].brand_name == "Logitech"
        assert roundtripped.positioning_gap is not None
        assert roundtripped.positioning_gap.quadrant == "Premium-Ergo-Mechanical"


class TestStrategyState:
    def test_typed_dict_construction(self):
        state: StrategyState = {
            "merchant_context": {"product_name": "ErgoMouse V2"},
            "swot_report": None,
            "dqs_retries": 0,
            "errors": [],
            "persona_profiles": None,
            "campaign_brief": None,
            "media_brief": None,
        }
        assert state["merchant_context"]["product_name"] == "ErgoMouse V2"
        assert state["swot_report"] is None
        assert state["dqs_retries"] == 0
        assert state["errors"] == []

    def test_partial_state_update_merge(self):
        base_state: StrategyState = {
            "merchant_context": {"product_name": "ErgoMouse V2"},
            "swot_report": None,
            "dqs_retries": 0,
            "errors": [],
        }
        delta = {
            "swot_report": SWOTReportDelta(dqs_score=0.91),
            "dqs_retries": 1,
        }
        merged = {**base_state, **delta}
        assert merged["dqs_retries"] == 1
        assert merged["swot_report"].dqs_score == 0.91
        assert merged["merchant_context"]["product_name"] == "ErgoMouse V2"

    def test_future_slots_default_none(self):
        state: StrategyState = {
            "merchant_context": {},
            "swot_report": None,
            "dqs_retries": 0,
            "errors": [],
            "persona_profiles": None,
            "campaign_brief": None,
            "media_brief": None,
        }
        assert state["persona_profiles"] is None
        assert state["campaign_brief"] is None
        assert state["media_brief"] is None
