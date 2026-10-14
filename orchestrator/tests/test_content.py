"""Content written from an approved strategy: channel mapping, limits, edits and per-channel approval."""

import asyncio

import pytest

from orchestrator.agents.content.writer import _Drafts, channel_key, plan_channels, write_content
from orchestrator.schemas.content import ContentPack
from orchestrator.schemas.strategy import CampaignPlan, CampaignStrategyBrief, PlanChannel
from orchestrator.services.campaign_service import CampaignJob, CampaignJobConflictError, CampaignService


def _brief(**kw) -> CampaignStrategyBrief:
    plan = CampaignPlan(primary_persona_id="p1", rationale="r", channels=[
        PlanChannel(channel="Meta ads test", persona_id="p1", budget=100, purpose="test hooks"),
        PlanChannel(channel="Email to past buyers", persona_id="p1", budget=0, purpose="reactivate"),
        PlanChannel(channel="Google Search ads", persona_id="p1", budget=100, purpose="capture intent"),
        PlanChannel(channel="Nano-creator barter", persona_id="p1", budget=50, purpose="ugc"),
    ])
    return CampaignStrategyBrief(executive_summary="s", primary_positioning_pillar="Comfort all day", plan=plan, **kw)


class _LLM:
    def __init__(self):
        self.channels = []

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        import json

        task = json.loads(messages[1]["content"])
        self.channels.append(task["channel"])
        if task["channel"] == "google_ads":
            return _Drafts.model_validate({"assets": [{"name": "Search", "headlines": [
                "Comfort All Day Shoes", "This headline is far too long for Google", "Comfort All Day Shoes"],
                "descriptions": ["Leather shoes built for the workday."]}]})
        return _Drafts.model_validate({"assets": [{"name": f"{task['channel']} 1", "body": "Hi", "hashtags": ["shoes"]}]})


def test_plan_channels_map_to_writable_channels_in_order():
    assert channel_key("Retargeting on Instagram") == "meta_ads"
    assert channel_key("Nano-creator barter") is None
    assert [k for k, _ in plan_channels(_brief())] == ["meta_ads", "email", "google_ads"]


def test_write_content_enforces_search_ad_limits_and_needs_a_model():
    llm = _LLM()
    pack = asyncio.run(write_content(_brief(), None, {"product_name": "Oxford"}, llm))
    assert sorted(llm.channels) == ["email", "google_ads", "meta_ads"]
    search = next(a for a in pack.assets if a.channel == "google_ads")
    assert search.headlines == ["Comfort All Day Shoes"]  # over 30 chars and duplicates dropped
    assert next(a for a in pack.assets if a.channel == "meta_ads").hashtags == ["#shoes"]
    empty = asyncio.run(write_content(_brief(), None, {}, None))
    assert empty.assets == [] and "language model" in empty.notes[0]


@pytest.fixture
def service_with_pack(monkeypatch):
    from orchestrator.core import storage

    class _Store:
        async def save_run(self, run):
            pass

        async def append_event(self, job_id, event):
            pass

    monkeypatch.setattr(storage, "get_storage", lambda: _Store())
    monkeypatch.setattr("orchestrator.services.campaign_service.get_storage", lambda: _Store())
    service = CampaignService()
    job = CampaignJob(job_id="j1", merchant_context={})
    job.strategy_brief = _brief(approval_status="APPROVED_AND_DISPATCHED")
    job.content_pack = asyncio.run(write_content(job.strategy_brief, None, {}, _LLM()))
    service._jobs["j1"] = job
    return service, job


def test_channel_approval_and_edits_send_a_channel_back_to_review(service_with_pack):
    service, job = service_with_pack
    email = next(a for a in job.content_pack.assets if a.channel == "email")
    pack = asyncio.run(service.set_channel_approval("j1", "email", True))
    assert pack.approved_channels == ["email"] and email.status == "approved"

    edited = asyncio.run(service.edit_asset("j1", email.asset_id, {"subject": "New", "status": "published"}))
    assert edited.subject == "New" and edited.status == "draft"  # status is not editable
    assert job.content_pack.approved_channels == []


def test_content_cannot_be_rewritten_before_strategy_approval(service_with_pack):
    service, job = service_with_pack
    job.strategy_brief.approval_status = "PENDING_APPROVAL"
    with pytest.raises(CampaignJobConflictError):
        asyncio.run(service.generate_content("j1"))
    assert isinstance(job.content_pack, ContentPack)
