from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from orchestrator.agents.campaign_strategy.hydration import hydrate_campaign_context_from_mongo
from orchestrator.agents.campaign_strategy.intel import mine_competitor_campaigns
from orchestrator.agents.campaign_strategy.options import generate_campaign_options
from orchestrator.schemas.research import (
    CompetitorProfile,
    CompetitorReviewContext,
    LeapBenchmark,
    SWOTReportDelta,
)
from orchestrator.schemas.strategy import CompetitorCampaignIntel


@pytest.mark.asyncio
async def test_hydrate_context_extracts_clients_sales_and_icp():
    merchant_context = {
        "product_name": "CloudSync Pro",
        "category": "Enterprise Cloud Migration",
        "client_data": ["Acme Corp ($50k ARR)", "Stripe partner team"],
        "product_sales": "$1.2M GMV / $350k ARR",
        "target_audience": "VP of Infrastructure & Enterprise DevOps Directors",
        "primary_value_prop": "Zero-downtime database replication",
    }
    swot = SWOTReportDelta(
        competitors=[
            CompetitorProfile(
                brand_name="Fivetran",
                product_name="Fivetran Enterprise",
                pricing_model="Usage-based credits",
                leap_benchmark=LeapBenchmark(
                    brand_name="Fivetran",
                    origin_story="Small YC batch startup",
                    current_scale="$150M+ ARR",
                    flagship_clients=["DocuSign", "Square", "ASICS"],
                ),
                review_context=CompetitorReviewContext(
                    brand_name="Fivetran",
                    buyer_personas=["Data Engineering Leads", "Cloud Architects"],
                    top_complaint_drivers=[],
                ),
            )
        ]
    )

    ctx, hydrated_swot, audience_intel = await hydrate_campaign_context_from_mongo(merchant_context, swot)

    assert len(audience_intel["user_client_data"]) == 2
    assert "Acme Corp" in audience_intel["user_client_data"][0]
    assert audience_intel["product_sales"] == "$1.2M GMV / $350k ARR"
    assert "DevOps Directors" in audience_intel["merchant_icp"]
    assert "DocuSign" in audience_intel["competitor_clients"]["Fivetran Enterprise"]
    assert "Data Engineering Leads" in audience_intel["competitor_consumers"]["Fivetran Enterprise"]
    assert "Usage-based credits" in audience_intel["competitor_icps"]["Fivetran Enterprise"]


@pytest.mark.asyncio
async def test_hydrate_context_loads_from_mongo_storage():
    mock_storage = AsyncMock()
    mock_storage.load_run.return_value = {
        "job_id": "job_123",
        "merchant_context": {
            "product_name": "MongoHydrated App",
            "category": "Data Tools",
            "client_data": ["Retrieved Logo 1", "Retrieved Logo 2"],
            "target_audience": "Chief Data Officers",
        },
        "report": {
            "competitors": [
                {
                    "brand_name": "RivalDB",
                    "product_name": "RivalDB Cloud",
                    "pricing_model": "$500/mo",
                    "core_claims": ["Fast queries"],
                }
            ],
            "dqs_score": 0.9,
            "assumptions_tagged": 0,
            "swot": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []},
        },
    }

    with patch("orchestrator.core.storage.get_storage", return_value=mock_storage):
        ctx, hydrated_swot, intel = await hydrate_campaign_context_from_mongo(
            {"product_name": "MongoHydrated App"},
            None,
            job_id="job_123",
        )

        assert hydrated_swot is not None
        assert len(hydrated_swot.competitors) == 1
        assert hydrated_swot.competitors[0].brand_name == "RivalDB"
        assert len(intel["user_client_data"]) == 2
        assert intel["merchant_icp"] == "Chief Data Officers"


@pytest.mark.asyncio
async def test_mine_competitor_campaigns_never_guesses_ad_spend_or_benchmarks():
    merchant_context = {
        "product_name": "Acme Tool",
        "category": "B2B SaaS",
        "target_audience": "CTOs & Engineering Directors",
    }
    swot = SWOTReportDelta(
        competitors=[
            CompetitorProfile(
                brand_name="LegacyCo",
                product_name="LegacyCo Enterprise",
                annual_revenue="$50M-$100M",
                employee_count="200-500",
                leap_benchmark=LeapBenchmark(
                    brand_name="LegacyCo",
                    flagship_clients=["General Electric", "Pfizer"],
                ),
                review_context=CompetitorReviewContext(
                    brand_name="LegacyCo",
                    buyer_personas=["Enterprise IT Directors"],
                ),
            )
        ]
    )

    intel_list = await mine_competitor_campaigns(merchant_context, swot, max_competitors=1)
    assert len(intel_list) == 1
    intel = intel_list[0]
    # No page stated their ad spend or CPCs, so nothing is guessed from revenue or headcount.
    assert intel.estimated_monthly_ad_spend is None
    assert intel.platform_cost_benchmarks == {}
    assert "General Electric" in intel.competitor_flagship_clients
    assert "Enterprise IT Directors" in intel.competitor_consumer_feedback


def test_generate_campaign_options_weaves_sub_goals_and_spend():
    merchant_context = {
        "product_name": "SpeedAPI",
        "category": "Developer APIs",
        "primary_value_prop": "10x lower latency",
        "goal": "Capture market share from SlowAPI",
        "campaign_type": "competitor_takeover",
        "campaign_days": 45,
    }
    intel = [
        CompetitorCampaignIntel(
            competitor_name="SlowAPI",
            campaign_themes=["Enterprise Authority"],
            detected_channels=["Google Search Ads", "LinkedIn Sponsored Content"],
            active_offers_and_hooks=["Guided Demo"],
            blindspots=["Sluggish latency and bloated contracts"],
            sample_evidence=["SlowAPI claims enterprise reliability."],
            estimated_monthly_ad_spend="$30,000 / month",
            platform_cost_benchmarks={"Google Search Ads": "$4.50 CPC", "LinkedIn Ads": "$12.00 CPC"},
            competitor_flagship_clients=["Legacy Corp", "Mega Bank"],
            competitor_consumer_feedback=["High API Latency", "Support delays"],
        )
    ]

    options = generate_campaign_options(
        merchant_context,
        intel,
        user_budget=15000.0,
        campaign_days=45,
        sub_goals=["Sign 20 high-growth fintech accounts", "Zero customer churn during trial"],
    )

    assert len(options) == 3
    opt_a = options[0]
    assert any("Sign 20 high-growth fintech accounts" in adv for adv in opt_a.advantages)
    assert any("SlowAPI" in adv for adv in opt_a.advantages)
    assert any("Legacy Corp" in adv for adv in opt_a.advantages)
