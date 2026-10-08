"""Campaign archetype classification and evidence-recency validation tests."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from orchestrator.agents.market_research.analysis.classification import (
    classify_campaign_context,
    classify_heuristically,
)
from orchestrator.agents.market_research.analysis.freshness import (
    extract_dates,
    extract_publication_date,
    parse_iso_date,
    score_recency,
)
from orchestrator.agents.market_research.analysis.scoring import W_RECENCY, calculate_dqs
from orchestrator.agents.market_research.pipeline.loop import is_research_converged
from orchestrator.schemas.research import CampaignClassification, CompetitorProfile


class _StubLLM:
    """Minimal structured-output LLM returning a fixed classification."""

    def __init__(self, result: CampaignClassification):
        self._result = result
        self.calls = 0

    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, _messages):
        self.calls += 1
        return self._result


class _FailingLLM:
    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, _messages):
        raise RuntimeError("model unavailable")


# ── Campaign Classification ───────────────────────────────────────────────────

class TestCampaignClassification:
    AGENCY_CTX = {
        "product_name": "DevFlow Studio",
        "category": "Web & Mobile App Development Agency",
        "primary_value_prop": "Custom SaaS builds for startups",
        "goal": "Generate qualified leads for new project enquiries",
        "price_usd": 25000,
    }

    @pytest.mark.asyncio
    async def test_fills_missing_archetype_fields_without_llm(self):
        enriched, classification, filled = await classify_campaign_context(self.AGENCY_CTX)
        assert enriched["business_model"] == "professional_services"
        assert enriched["campaign_type"] == "lead_gen"
        assert "business_model" in filled and "campaign_type" in filled
        assert classification.business_model == "professional_services"

    @pytest.mark.asyncio
    async def test_never_overwrites_caller_supplied_values(self):
        ctx = {**self.AGENCY_CTX, "business_model": "b2b_saas", "campaign_type": "rebrand"}
        enriched, _, filled = await classify_campaign_context(ctx)
        assert enriched["business_model"] == "b2b_saas"
        assert enriched["campaign_type"] == "rebrand"
        assert "business_model" not in filled and "campaign_type" not in filled

    @pytest.mark.asyncio
    async def test_all_fields_present_skips_classification_entirely(self):
        ctx = {
            **self.AGENCY_CTX,
            "business_model": "b2b_saas",
            "campaign_type": "rebrand",
            "price_model": "monthly_subscription",
            "target_geography": "Global",
        }
        llm = _StubLLM(CampaignClassification(business_model="should_not_be_used"))
        enriched, _, filled = await classify_campaign_context(ctx, llm=llm)
        assert filled == []
        assert llm.calls == 0
        assert enriched["business_model"] == "b2b_saas"

    @pytest.mark.asyncio
    async def test_uses_llm_classification_when_available(self):
        llm = _StubLLM(
            CampaignClassification(
                business_model="d2c_ecommerce",
                campaign_type="ecommerce_sales",
                price_model="one_time",
                target_geography="United States",
                rationale="Sells a physical product directly to consumers.",
            )
        )
        enriched, classification, filled = await classify_campaign_context(
            {"product_name": "GlowBerry", "category": "Skincare"}, llm=llm
        )
        assert enriched["business_model"] == "d2c_ecommerce"
        assert enriched["target_geography"] == "United States"
        assert classification.rationale
        assert set(filled) == {"business_model", "campaign_type", "price_model", "target_geography"}

    @pytest.mark.asyncio
    async def test_falls_back_to_heuristics_when_llm_fails(self):
        enriched, _, filled = await classify_campaign_context(self.AGENCY_CTX, llm=_FailingLLM())
        assert enriched["business_model"] == "professional_services"
        assert "business_model" in filled

    @pytest.mark.asyncio
    async def test_does_not_mutate_caller_context(self):
        ctx = dict(self.AGENCY_CTX)
        await classify_campaign_context(ctx)
        assert "business_model" not in ctx

    @pytest.mark.parametrize(
        "category,expected",
        [
            ("Cosmetic Dental Clinic", "local_service"),
            ("Organic Skincare eCommerce", "d2c_ecommerce"),
            ("B2B SaaS Observability Platform", "b2b_saas"),
            ("Online Course and Coaching Membership", "creator_infoproduct"),
        ],
    )
    def test_heuristics_detect_archetypes(self, category, expected):
        assert classify_heuristically({"category": category}).business_model == expected

    def test_heuristic_infers_project_pricing_from_large_price(self):
        result = classify_heuristically({"category": "Branding", "price_usd": 40000})
        assert result.price_model == "fixed_project"

    @pytest.mark.asyncio
    async def test_heuristic_extracts_user_intent_and_capabilities(self):
        ctx = {
            "product_name": "LeadEngine",
            "category": "B2B SaaS",
            "goal": "I want to increase connections to attract more customer leads",
        }
        enriched, classification, _ = await classify_campaign_context(ctx)
        assert classification.user_intent != ""
        assert "lead_generation" in classification.marketing_capabilities
        assert enriched["user_intent"] == classification.user_intent
        assert enriched["marketing_capabilities"] == classification.marketing_capabilities

    @pytest.mark.asyncio
    async def test_llm_classification_sets_user_intent_and_capabilities(self):
        llm = _StubLLM(
            CampaignClassification(
                business_model="b2b_saas",
                campaign_type="lead_gen",
                price_model="monthly_subscription",
                user_intent="Analyze competitor ad copy to drive demo bookings",
                marketing_capabilities=["competitor_intelligence", "ad_copywriting"],
            )
        )
        ctx = {"product_name": "DemoFlow", "category": "SaaS"}
        enriched, classification, _ = await classify_campaign_context(ctx, llm=llm)
        assert classification.user_intent == "Analyze competitor ad copy to drive demo bookings"
        assert classification.marketing_capabilities == ["competitor_intelligence", "ad_copywriting"]
        assert enriched["user_intent"] == classification.user_intent
        assert enriched["marketing_capabilities"] == classification.marketing_capabilities


# ── Freshness / Recency ───────────────────────────────────────────────────────

class TestDateExtraction:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Updated 2024-05-13 by the team", date(2024, 5, 13)),
            ("Posted on May 13, 2024", date(2024, 5, 13)),
            ("Published 13 May 2024", date(2024, 5, 13)),
            ("Last modified 2024/05/13", date(2024, 5, 13)),
        ],
    )
    def test_parses_common_publication_formats(self, text, expected):
        assert extract_publication_date(text) == expected

    def test_prefers_date_next_to_publication_marker(self):
        text = "Our 2008 founding story. Last updated March 2025. Est. 2008."
        assert extract_publication_date(text) == date(2025, 3, 1)

    def test_ignores_implausible_years(self):
        assert extract_dates("Version 1.2 build 1999-99-99 and item 0001-01-01") == []

    def test_returns_none_for_undated_text(self):
        assert extract_publication_date("Pricing starts at $49 per seat.") is None

    def test_parse_iso_date_handles_provider_formats(self):
        assert parse_iso_date("2024-05-13T10:30:00Z") == date(2024, 5, 13)
        assert parse_iso_date("May 13, 2024") == date(2024, 5, 13)
        assert parse_iso_date(None) is None


class TestRecencyScoring:
    def test_no_evidence_scores_zero(self):
        score, diags = score_recency([], has_evidence=False, max_age_days=548)
        assert score == 0.0
        assert any("no sources" in d for d in diags)

    def test_undated_evidence_takes_full_credit_silently(self):
        """Missing publication metadata is not proof of staleness and must not be penalized."""
        score, diags = score_recency([], has_evidence=True, max_age_days=548)
        assert score == 1.0
        assert diags == []

    def test_stale_evidence_is_penalized_and_flagged(self):
        today = date(2026, 10, 6)
        dates = [today - timedelta(days=30), today - timedelta(days=2000)]
        score, diags = score_recency(dates, has_evidence=True, max_age_days=548, today=today)
        assert score == 0.5
        assert any("R_recency" in d for d in diags)

    def test_all_fresh_scores_one(self):
        today = date(2026, 10, 6)
        dates = [today - timedelta(days=10), today - timedelta(days=100)]
        score, diags = score_recency(dates, has_evidence=True, max_age_days=548, today=today)
        assert score == 1.0
        assert diags == []


class TestDQSRecencyIntegration:
    def _full_competitors(self):
        return [
            CompetitorProfile(
                brand_name=f"Brand{i}",
                product_name=f"Product{i}",
                pricing_model=f"${i}9/mo",
                weaknesses_mined=["issue_1", "issue_2"],
                sources=[f"https://example.com/{i}"],
            )
            for i in range(5)
        ]

    def test_stale_evidence_lowers_dqs(self):
        sources = [f"https://source{i}.com" for i in range(6)]
        very_old = [date(2015, 1, 1), date(2016, 1, 1)]
        fresh = calculate_dqs(self._full_competitors(), sources)
        stale = calculate_dqs(self._full_competitors(), sources, evidence_dates=very_old)

        assert fresh.score == 1.0
        assert fresh.r_recency == 1.0
        assert stale.r_recency == 0.0
        assert stale.score == pytest.approx(1.0 - W_RECENCY)
        assert any("R_recency" in d for d in stale.diagnostics)

    def test_stale_evidence_blocks_convergence_despite_passing_dqs(self):
        """At 0.15 weight recency cannot fail DQS alone, so the loop gates on it directly."""
        sources = [f"https://source{i}.com" for i in range(6)]
        stale = calculate_dqs(
            self._full_competitors(), sources, evidence_dates=[date(2015, 1, 1)]
        )
        # DQS itself still passes the 0.80 threshold...
        assert stale.passed is True
        # ...but the recency floor stops the loop from converging on stale data.
        assert is_research_converged(stale, density=1.0, competitors_count=5, min_recency=0.5) is False
        assert is_research_converged(stale, density=1.0, competitors_count=5, min_recency=0.0) is True

    def test_undated_evidence_still_converges(self):
        """Pages without publication metadata must not stall the loop."""
        sources = [f"https://source{i}.com" for i in range(6)]
        undated = calculate_dqs(self._full_competitors(), sources, evidence_dates=[])
        assert undated.r_recency == 1.0
        assert is_research_converged(undated, density=1.0, competitors_count=5, min_recency=0.5) is True


class TestConversationalGoalDisambiguation:
    @pytest.mark.asyncio
    async def test_conversational_goal_statement_is_disambiguated(self):
        prompt_input = {
            "product_name": "i want to increase my connections to attract more customers",
            "category": "i want to increase my connections to attract more customers",
            "primary_value_prop": "i want to increase my connections to attract more customers",
        }
        enriched, classification, filled = await classify_campaign_context(prompt_input)

        assert enriched["category"] == "B2B Lead Generation & Networking Agency"
        assert enriched["goal"] == "i want to increase my connections to attract more customers"
        assert enriched["product_name"] == "Client Acquisition Service"
        assert classification.business_model == "professional_services"
        assert classification.campaign_type == "lead_gen"
        assert "category" in filled
        assert "product_name" in filled

    @pytest.mark.asyncio
    async def test_standard_business_context_is_not_disambiguated(self):
        clean_input = {
            "product_name": "DevFlow Studio",
            "category": "Web & Mobile App Development Agency",
            "primary_value_prop": "Custom apps",
            "goal": "Scale to 10 clients",
        }
        enriched, classification, filled = await classify_campaign_context(clean_input)

        assert enriched["category"] == "Web & Mobile App Development Agency"
        assert enriched["product_name"] == "DevFlow Studio"
        assert enriched["goal"] == "Scale to 10 clients"

    def test_conversational_detection_function(self):
        from orchestrator.agents.market_research.analysis.classification import is_conversational_statement

        assert is_conversational_statement("i want to increase my connections to attract more customers") is True
        assert is_conversational_statement("how to grow my online store sales") is True
        assert is_conversational_statement("we need to find new B2B clients") is True
        assert is_conversational_statement("looking to scale our outreach") is True
        assert is_conversational_statement("Web & Mobile App Development Agency") is False
        assert is_conversational_statement("SaaS Project Management Tool") is False
        assert is_conversational_statement("Local Dental Clinic") is False

