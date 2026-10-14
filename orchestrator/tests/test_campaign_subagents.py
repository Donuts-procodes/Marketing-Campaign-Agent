"""Persona agent, messaging, content QA and scheduler."""

import asyncio
from datetime import date

from orchestrator.agents.audience_persona.agent import _Personas, audience_points, execute_audience_persona, ground_personas
from orchestrator.agents.campaign_strategy.messaging import _Messaging, write_messaging
from orchestrator.agents.content.qa import check_asset
from orchestrator.agents.content.scheduler import plan_schedule
from orchestrator.schemas.content import ContentAsset, ContentPack
from orchestrator.schemas.research import AudienceProfile, IdealCustomerProfile, SourcedPoint, SWOTReportDelta
from orchestrator.schemas.strategy import CampaignPlan, CampaignStrategyBrief, PlanPhase


def _report():
    audience = AudienceProfile(
        icp=IdealCustomerProfile(name="First-job office goers", why=[SourcedPoint(text="x", source_url="https://a.in/1")]),
        pains=[SourcedPoint(text="Soles wear out fast", source_url="https://a.in/2")],
        triggers=[SourcedPoint(text="New job joining", source_url="https://a.in/3")],
        channels=[{"text": "Instagram", "reason": "discovery", "source_url": "https://a.in/4"}],
    )
    return SWOTReportDelta.model_construct(competitors=[], audience=audience, market_overview=None,
                                           wedge_scan=None, positioning_gap=None)


def test_personas_keep_only_supported_ones_and_their_sources():
    points = audience_points(_report())
    assert [p[0] for p in points][:2] == ["A1", "A2"]
    raw = _Personas.model_validate({"personas": [
        {"name": "Fresh graduate", "role": "primary", "refs": ["A1", "a2"]},
        {"name": "Unsupported", "role": "primary", "refs": ["A99"]},
        {"name": "Weekend buyer", "role": "primary", "refs": ["A3"]},
    ]})
    personas = ground_personas(raw, points)
    assert [(p.name, p.role) for p in personas] == [("Fresh graduate", "primary"), ("Weekend buyer", "later")]
    assert personas[0].evidence == ["https://a.in/1", "https://a.in/2"]


def test_persona_agent_falls_back_to_research_without_a_model():
    out = asyncio.run(execute_audience_persona({"swot_report": _report(), "merchant_context": {}}))
    assert out["persona_profiles"][0]["name"] == "First-job office goers"


def test_messaging_needs_a_model_and_a_core_message():
    class LLM:
        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, messages):
            return _Messaging.model_validate({"positioning": "p", "core_message": "Comfort that lasts the workday",
                                              "pillars": [{"title": "Lasts", "needs_proof": True}, {"title": ""}]})

    m = asyncio.run(write_messaging({}, _report(), [], LLM()))
    assert m.core_message.startswith("Comfort") and [p.title for p in m.pillars] == ["Lasts"]
    assert asyncio.run(write_messaging({}, _report(), [], None)) is None


def test_content_qa_flags_limits_placeholders_unbacked_numbers_and_rivals():
    email = ContentAsset(asset_id="e", channel="email", kind="email", name="E", subject="x" * 70,
                         body="Now ₹1,999 with [add warranty period]. Better than Bata.", cta="Shop")
    issues = check_asset(email, {"price": 2499}, ["Bata"])
    text = " ".join(issues)
    assert "70 characters" in text and "[add warranty period]" in text and "1,999" in text and "Bata" in text
    ok = ContentAsset(asset_id="o", channel="email", kind="email", name="O", subject="Hi", body="Now ₹2,499", cta="Shop")
    assert check_asset(ok, {"price": 2499}, []) == []


def test_scheduler_places_assets_inside_their_phases():
    plan = CampaignPlan(primary_persona_id="p", rationale="r", phases=[
        PlanPhase(name="Launch", days="Days 1-10", budget_ceiling=0, objective="o", decision_gate="g"),
        PlanPhase(name="Scale", days="Days 11-30", budget_ceiling=0, objective="o", decision_gate="g"),
    ])
    brief = CampaignStrategyBrief(executive_summary="s", primary_positioning_pillar="p", plan=plan, campaign_days=30)
    pack = ContentPack(assets=[
        ContentAsset(asset_id="a", channel="email", kind="email", name="1", phase="Launch"),
        ContentAsset(asset_id="b", channel="email", kind="email", name="2", phase="Scale"),
        ContentAsset(asset_id="c", channel="email", kind="email", name="3", status="published"),
    ])
    assert plan_schedule(pack, brief, {"start_date": "2026-11-01"}) == 2
    a, b, c = pack.assets
    assert a.scheduled_for == "2026-11-01T10:00:00" and b.scheduled_for.startswith("2026-11-11")
    assert c.scheduled_for is None
    assert date.fromisoformat(b.scheduled_for[:10]) > date.fromisoformat(a.scheduled_for[:10])
