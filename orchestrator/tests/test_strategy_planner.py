import pytest

from orchestrator.agents.campaign_strategy.agent import execute_campaign_strategy
from orchestrator.agents.campaign_strategy.context import load_personas
from orchestrator.agents.campaign_strategy.planner import (
    PlanningInputs,
    build_plan,
    compute_economics,
    decide_mode,
    validate_plan,
)
from orchestrator.schemas.research import (
    AdAngle,
    BuyingPatternIntelligence,
    ChannelListing,
    CompetitorProfile,
    CompetitorReviewContext,
    ReviewAspect,
    SWOTReportDelta,
)
from orchestrator.schemas.strategy import CampaignPlan, MessageTest, PlanChannel

AURELIUS = {
    "product_name": "Sovereign Oxford",
    "category": "Formal leather footwear",
    "business_model": "d2c_ecommerce",
    "primary_value_prop": "Hand-finished full-grain leather oxfords built for all-day comfort",
    "target_geography": "Delhi-NCR, India",
    "budget": "10000",
    "price": 7499,
    "campaign_days": 90,
}


def _report() -> SWOTReportDelta:
    return SWOTReportDelta(
        competitors=[
            CompetitorProfile(
                brand_name="Bridlen", product_name="Bridlen Oxford",
                review_context=CompetitorReviewContext(
                    brand_name="Bridlen",
                    buyer_personas=["Corporate professionals upgrading formal shoes"],
                    top_complaint_drivers=[ReviewAspect(topic="Stiff break-in"), ReviewAspect(topic="Sizing runs small")],
                ),
                buying_patterns=BuyingPatternIntelligence(sales_channels=["myntra.com", "Instagram"]),
                channel_listings=[ChannelListing(competitor="Bridlen", site="myntra.com", currency="INR",
                                                 mrp=8999, selling_price=5399, discount_pct=40, cod_available=False)],
            ),
        ],
        suggested_ad_angles=[
            AdAngle(hook="Formal shoes that don't punish your workday", based_on_weakness="Stiff break-in",
                    target_rival="Bridlen"),
            AdAngle(hook="Craft you can see up close", based_on_weakness="Generic mass-market finish"),
        ],
    )


def _inputs(mode_ctx=AURELIUS) -> PlanningInputs:
    report = _report()
    personas = load_personas({}, report, mode_ctx)
    return PlanningInputs(
        merchant_context=dict(mode_ctx), budget=10000.0, currency="INR", campaign_days=90,
        personas=personas, market_listings=["myntra.com: rivals sell at ₹5,399"], unknowns=["Unit cost"],
        swot_report=report, is_b2b=False,
    )


# ── Mode & economics ──────────────────────────────────────────────────────────

def test_mode_follows_stage_and_budget_vs_price():
    assert decide_mode(AURELIUS, 10000, 7499)[0] == "validate"          # budget < 3 units
    assert decide_mode({"launch_stage": "launched_few_sales"}, 200000, 7499)[0] == "traction"
    assert decide_mode({"launch_stage": "regular_orders", "unit_cost": 3000}, 200000, 7499)[0] == "scale"
    assert decide_mode({}, 200000, 7499)[0] == "validate"                # no sales evidence


def test_economics_only_with_merchant_numbers():
    assert compute_economics(AURELIUS, 10000, 7499).orders_to_break_even is None
    e = compute_economics({**AURELIUS, "unit_cost": 3600, "variable_cost_pct": 12}, 10000, 7499)
    # 7499 - 3600 - 12% of 7499 = 2999.12 → 4 orders cover ₹10,000
    assert e.contribution_per_unit == pytest.approx(2999.12)
    assert e.orders_to_break_even == 4 and e.max_affordable_cac == pytest.approx(2999.12)
    loss = compute_economics({**AURELIUS, "unit_cost": 7400}, 10000, 7499)
    assert loss.orders_to_break_even is None and "loses money" in loss.note


# ── Rules plan (no LLM) ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rules_plan_for_aurelius_is_grounded_and_within_budget():
    inputs = _inputs()
    plan = await build_plan(inputs, "validate", compute_economics(AURELIUS, 10000, 7499))
    assert plan.generated_by == "rules"
    assert plan.reserve >= 1000
    assert sum(c.budget for c in plan.channels) + plan.reserve <= 10000 + 0.5
    assert not any("linkedin" in c.channel.lower() for c in plan.channels)
    assert all(c.persona_id in inputs.persona_ids and c.evidence for c in plan.channels)
    assert [t.role for t in plan.message_tests] == ["champion", "challenger"]
    assert plan.message_tests[0].hook.startswith("Formal shoes")
    items = " ".join(r.item for r in plan.readiness)
    assert "size & fit guide" in items and "wear test" in items       # from rival complaints
    assert all(r.blocking for r in plan.readiness if "fit guide" in r.item)
    assert sum(p.budget_ceiling for p in plan.phases) <= 10000 + 0.5


# ── Validator ─────────────────────────────────────────────────────────────────

def _llm_like_plan(**overrides) -> CampaignPlan:
    base = dict(
        primary_persona_id="ghost",
        rationale="Comfort-led test",
        channels=[PlanChannel(channel="Meta ads", persona_id="ghost", budget=9000, purpose="test",
                              evidence=["myntra listings"])],
        reserve=0,
        message_tests=[MessageTest(test_id="t1", persona_id="ghost", angle="comfort", hook="h", cta="c",
                                   evidence=["Stiff break-in"])],
    )
    base.update(overrides)
    return CampaignPlan(**base)


def test_validator_fixes_arithmetic_and_persona_ids():
    inputs = _inputs()
    plan, issues = validate_plan(_llm_like_plan(), inputs, "validate")
    assert not issues
    primary = inputs.persona("primary").persona_id
    assert plan.primary_persona_id == primary and plan.channels[0].persona_id == primary
    assert plan.reserve == 1000 and plan.channels[0].budget == pytest.approx(9000)
    assert plan.validation_notes


def test_validator_flags_what_only_a_replan_can_fix():
    plan = _llm_like_plan(
        rationale="Expect 4.2x ROAS",
        channels=[PlanChannel(channel="LinkedIn InMail", persona_id="ghost", budget=500, purpose="x")],
    )
    _, issues = validate_plan(plan, _inputs(), "validate")
    text = " ".join(issues)
    assert "no evidence" in text and "B2B channel" in text and "ROAS" in text


# ── LLM path ──────────────────────────────────────────────────────────────────

class _FakeLLM:
    def __init__(self, plans):
        self.plans, self.calls = list(plans), []

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.plans.pop(0)


@pytest.mark.asyncio
async def test_llm_plan_gets_one_repair_then_is_used():
    bad = _llm_like_plan(channels=[PlanChannel(channel="Meta ads", persona_id="ghost", budget=5000, purpose="t")])
    good = _llm_like_plan()
    llm = _FakeLLM([bad, good])
    plan = await build_plan(_inputs(), "validate", compute_economics(AURELIUS, 10000, 7499), llm=llm)
    assert plan.generated_by == "llm" and len(llm.calls) == 2
    assert "fix_these_issues" in llm.calls[1][1]["content"]


@pytest.mark.asyncio
async def test_llm_plan_that_stays_invalid_falls_back_to_rules():
    bad = _llm_like_plan(channels=[PlanChannel(channel="LinkedIn InMail", persona_id="x", budget=1, purpose="t")])
    plan = await build_plan(_inputs(), "validate", compute_economics(AURELIUS, 10000, 7499),
                            llm=_FakeLLM([bad, bad]))
    assert plan.generated_by == "rules"
    assert any("LLM plan rejected" in n for n in plan.validation_notes)


# ── End to end ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aurelius_brief_end_to_end():
    out = await execute_campaign_strategy({"merchant_context": dict(AURELIUS), "swot_report": _report()})
    brief = out["strategy_brief"]
    assert brief.currency == "INR" and brief.mode == "validate"
    assert brief.plan and brief.plan.reserve >= 1000
    assert brief.selected_option_id == "opt_grounded" and brief.campaign_options[0].recommended
    assert "₹" in brief.campaign_options[0].budget_allocation_summary
    assert not any("linkedin" in c.channel.lower() for c in brief.channel_matrix)
    assert brief.execution_calendar[0].deliverables[-1].startswith("Gate:")
    assert all(p.who_target_profile for p in brief.outreach_blueprint)
    assert brief.campaign_options[0].prediction.projected_roi is None
