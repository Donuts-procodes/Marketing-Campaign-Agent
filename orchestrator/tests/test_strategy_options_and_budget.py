from __future__ import annotations

import pytest

from orchestrator.agents.campaign_strategy.intel import mine_competitor_campaigns
from orchestrator.agents.campaign_strategy.options import generate_campaign_options
from orchestrator.agents.campaign_strategy.promotions import (
    get_option_promotions,
    get_static_promotions,
)
from orchestrator.agents.campaign_strategy.optimizer import consolidate_strategy_brief
from orchestrator.agents.campaign_strategy.synthesis import derive_channel_matrix
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta
from orchestrator.schemas.strategy import (
    CampaignStrategyBrief,
    CampaignStrategyOption,
    CompetitorCampaignIntel,
    TacticalOutreachBlueprint,
)


def test_generate_campaign_options_scales_budget_and_provides_predictions_and_promotions():
    merchant_context = {
        "product_name": "DevFlow Studio",
        "category": "Enterprise Web Development",
        "goal": "Capture market share from legacy agencies",
    }
    competitor_intel = [
        CompetitorCampaignIntel(
            competitor_name="LegacyCorp",
            detected_channels=["Google Ads", "LinkedIn Sponsored"],
            active_offers_and_hooks=["Sign 12-month retainer get 10% off", "Enterprise SLA guarantee"],
            blindspots=["Rigid vendor lock-in", "Slow sprint velocity"],
        )
    ]
    options = generate_campaign_options(
        merchant_context=merchant_context,
        competitor_intel=competitor_intel,
        user_budget=15000.0,
    )

    assert len(options) == 3
    ids = [opt.option_id for opt in options]
    assert len(set(ids)) == 3

    for opt in options:
        assert len(opt.channel_matrix) > 0
        allocated = sum(c.recommended_spend_usd or 0 for c in opt.channel_matrix)
        assert allocated > 0
        assert len(opt.advantages) >= 3
        assert len(opt.disadvantages) >= 2
        assert len(opt.constraints) >= 2
        assert len(opt.opportunities) >= 2

        # Check static suggested channels and promotion means
        assert len(opt.suggested_channels) >= 3
        assert len(opt.promotion_means) >= 3

        # Check channel promotion tactics, payee, and inventory
        for ch in opt.channel_matrix:
            assert len(ch.promotion_tactics) >= 1
            assert len(ch.payee_platform) > 0
            assert len(ch.purchased_inventory) > 0

        # Without merchant sales data or unit economics nothing is projected, and the
        # prediction says why instead of inventing an ROI.
        pred = opt.prediction
        assert pred.projected_cac is None and pred.projected_roi is None
        assert pred.break_even_timeline is None
        assert "merchant data" in pred.basis
        assert pred.risk_level in ["Low", "Medium", "High"]


def test_generate_campaign_options_fallback_on_zero_budget():
    merchant_context = {"product_name": "DevFlow Studio"}
    options = generate_campaign_options(
        merchant_context=merchant_context,
        competitor_intel=[],
        user_budget=0.0,
    )
    assert len(options) == 3
    for opt in options:
        allocated = sum(c.recommended_spend_usd or 0 for c in opt.channel_matrix)
        assert allocated > 0
        assert len(opt.suggested_channels) >= 3
        assert len(opt.promotion_means) >= 3


def test_static_promotions_knowledge_base():
    b2b = get_static_promotions(business_model="b2b_saas", category="software")
    assert len(b2b["suggested_channels"]) >= 4
    assert len(b2b["promotion_means"]) >= 4
    assert "linkedin" in b2b["tactics_by_channel"]

    ecom = get_static_promotions(business_model="d2c_ecommerce", category="fashion")
    assert len(ecom["suggested_channels"]) >= 4
    assert len(ecom["promotion_means"]) >= 4

    channels_a, means_a = get_option_promotions("opt_disrupter", "LegacyRival", "Agency Services")
    assert len(channels_a) >= 3
    assert len(means_a) >= 3
    assert any("LegacyRival" in m for m in means_a)


@pytest.mark.asyncio
async def test_mine_competitor_campaigns_heuristic_fallback():
    merchant_context = {
        "product_name": "DevFlow Studio",
        "category": "Enterprise Software",
    }
    swot = SWOTReportDelta(
        competitors=[
            CompetitorProfile(
                brand_name="LegacyTech",
                product_name="LegacyTech Enterprise",
                strengths_mined=["Brand awareness"],
                weaknesses_mined=["Outdated tech stack", "High pricing"],
            ),
            CompetitorProfile(
                brand_name="QuickDev",
                product_name="QuickDev App Builder",
                strengths_mined=["Cheap prices"],
                weaknesses_mined=["Poor code quality"],
            ),
        ]
    )
    intel = await mine_competitor_campaigns(
        merchant_context=merchant_context,
        swot_report=swot,
    )
    assert len(intel) == 2
    for item in intel:
        assert isinstance(item, CompetitorCampaignIntel)
        assert len(item.detected_channels) >= 2
        assert len(item.active_offers_and_hooks) >= 2
        assert len(item.blindspots) >= 2


def test_derive_channel_matrix_respects_user_budget_and_attaches_tactics():
    merchant_context = {
        "product_name": "DevFlow Studio",
        "category": "Enterprise Web & Mobile Development",
    }
    channels = derive_channel_matrix(
        merchant_context=merchant_context,
        swot_report=None,
        user_budget=20000.0,
    )
    assert len(channels) > 0
    total_allocated = sum(c.recommended_spend_usd or 0.0 for c in channels)
    assert pytest.approx(total_allocated, rel=1e-2) == 20000.0
    for c in channels:
        assert len(c.promotion_tactics) >= 1


def test_consolidate_strategy_brief_builds_outreach_blueprint_and_subagents():
    merchant_context = {
        "product_name": "LogiTrack Cloud",
        "category": "Enterprise Logistics Management",
    }
    channels = derive_channel_matrix(
        merchant_context=merchant_context,
        swot_report=None,
        user_budget=25000.0,
    )
    brief = consolidate_strategy_brief(
        merchant_context=merchant_context,
        swot_report=None,
        target_metrics=[],
        channel_matrix=channels,
        strategic_angles=[],
        user_budget=25000.0,
    )
    assert isinstance(brief, CampaignStrategyBrief)
    assert len(brief.subagents_roster) == 6
    assert len(brief.outreach_blueprint) == 4

    # Verify 5W/1H blueprint structure: who, where, how, budget, for how long
    for play in brief.outreach_blueprint:
        assert isinstance(play, TacticalOutreachBlueprint)
        assert len(play.who_target_profile) > 10
        assert len(play.where_platform) > 5
        assert len(play.how_mechanism) > 10
        assert play.budget_allocation_usd > 0
        assert play.budget_share_pct > 0
        assert len(play.duration_and_cadence) > 10
        assert len(play.assigned_subagent) > 5

    # Total allocated across outreach plays equals the budget
    total_blueprint_spend = sum(p.budget_allocation_usd for p in brief.outreach_blueprint)
    assert pytest.approx(total_blueprint_spend, rel=1e-2) == 25000.0


def test_dynamic_campaign_days_sub_goals_and_core_understanding():
    from orchestrator.agents.campaign_strategy.hydration import decompose_objectives

    merchant_context = {
        "product_name": "PromptCraft AI",
        "category": "Developer Tools",
        "primary_value_prop": "Generate verified production TypeScript types directly from Figma schemas in seconds",
        "goal": "Acquire first 1,000 developers and 50 team workspaces",
        "campaign_type": "product_launch",
        "campaign_days": 14,
        "sub_goals": ["50 team workspaces converted", "CPA under $15 per signup"],
    }

    target_metrics = decompose_objectives(
        merchant_context,
        campaign_days=14,
        sub_goals=["50 team workspaces converted", "CPA under $15 per signup"],
    )

    # Sub-goals must be prioritized as target metrics
    sub_metrics = [m for m in target_metrics if m.is_sub_goal]
    assert len(sub_metrics) == 2
    assert any("50 team workspaces" in m.name for m in sub_metrics)

    channels = derive_channel_matrix(merchant_context, swot_report=None, user_budget=12000.0)
    options = generate_campaign_options(
        merchant_context=merchant_context,
        competitor_intel=[],
        user_budget=12000.0,
        campaign_days=14,
        sub_goals=["50 team workspaces converted"],
    )

    assert len(options) == 3
    # Launch archetype customizes option titles and themes
    assert "Launch" in options[0].title
    assert "Launch" in options[0].theme
    assert "14 days" in options[0].constraints[0]

    brief = consolidate_strategy_brief(
        merchant_context=merchant_context,
        swot_report=None,
        target_metrics=target_metrics,
        channel_matrix=channels,
        strategic_angles=[],
        campaign_options=options,
        user_budget=12000.0,
        campaign_days=14,
        sub_goals=["50 team workspaces converted", "CPA under $15 per signup"],
        campaign_type="product_launch",
        core_goal=merchant_context["goal"],
    )

    # Brief metadata
    assert brief.campaign_days == 14
    assert brief.sub_goals == ["50 team workspaces converted", "CPA under $15 per signup"]
    assert brief.campaign_type == "product_launch"

    # Core idea and goal reflected in executive summary and positioning pillar
    assert "14-day" in brief.executive_summary
    assert "PromptCraft AI" in brief.executive_summary
    assert "Figma schemas" in brief.executive_summary
    assert "1,000 developers" in brief.executive_summary
    assert "Figma schemas" in brief.primary_positioning_pillar

    # Execution calendar partitions into days for 14-day campaign
    assert len(brief.execution_calendar) == 3
    assert brief.execution_calendar[0].weeks == "Days 1 - 3"
    assert brief.execution_calendar[1].weeks == "Days 4 - 10"
    assert brief.execution_calendar[2].weeks == "Days 11 - 14"
    # Sub-goals embedded in deliverables
    all_deliverables = [d for p in brief.execution_calendar for d in p.deliverables]
    assert any("50 team workspaces" in d for d in all_deliverables)

    # Outreach blueprint durations formatted to 14 days
    for play in brief.outreach_blueprint:
        assert "14-day" in play.duration_and_cadence


def test_custom_option_in_strategy_customize_request():
    from orchestrator.schemas.strategy import StrategyCustomizeRequest, ChannelAllocation, StrategyPrediction

    custom_opt = CampaignStrategyOption(
        option_id="opt_custom_123",
        title="Custom Option D: Founder-Led Direct Wedge",
        theme="Direct Founder Concierge",
        tagline="Direct migration concierge with zero SLA downtime",
        recommended=False,
        budget_allocation_summary="$4,000 LinkedIn (40%) • $3,000 Search (30%) • $3,000 Outbound (30%)",
        channel_matrix=[
            ChannelAllocation(channel="LinkedIn", budget_percentage=40, recommended_spend_usd=4000, rationale="Decision makers"),
            ChannelAllocation(channel="Search", budget_percentage=30, recommended_spend_usd=3000, rationale="Intent queries"),
            ChannelAllocation(channel="Outbound", budget_percentage=30, recommended_spend_usd=3000, rationale="Cold sequence"),
        ],
        advantages=["Direct access to founders", "Fastest conversion velocity"],
        disadvantages=["Requires executive attention"],
        constraints=["14-day flight minimum"],
        opportunities=["Exploit competitor lock-in"],
        suggested_channels=["LinkedIn", "Search", "Outbound"],
        promotion_means=["Free Migration Audit"],
        prediction=StrategyPrediction(
            projected_cac="$500",
            projected_roi="4.0x",
            conversion_velocity="< 14 days",
            risk_level="Medium",
            break_even_timeline="2 months",
        ),
    )

    req = StrategyCustomizeRequest(
        budget=10000.0,
        campaign_days=45,
        sub_goals=["Sign 20 enterprise switchers"],
        selected_option_id="opt_custom_123",
        custom_option=custom_opt,
    )

    assert req.custom_option is not None
    assert req.custom_option.option_id == "opt_custom_123"
    assert req.custom_option.title == "Custom Option D: Founder-Led Direct Wedge"
    assert len(req.custom_option.channel_matrix) == 3


