"""Chat acts on content and schedule only through confirm cards; openers come from the data."""

import asyncio

from orchestrator.schemas.content import ContentAsset, ContentPack
from orchestrator.schemas.research import SWOTReportDelta
from orchestrator.services.campaign_service import CampaignJob, CampaignService
from orchestrator.services.chat_openers import opening
from orchestrator.services.chat_tools import ChatToolbox


def _pack():
    return ContentPack(assets=[
        ContentAsset(asset_id="email-1", channel="email", kind="email", name="Email 1", subject="Hi",
                     scheduled_for="2026-11-01T10:00:00", qa_issues=["Fill in before publishing: [add warranty]."]),
        ContentAsset(asset_id="li-1", channel="linkedin", kind="post", name="Post 1", body="x",
                     scheduled_for="2026-11-02T09:00:00"),
    ])


def _run(box, name, args):
    async def go():
        return [f async for f in box.run(name, args)]
    return asyncio.run(go())


def test_content_cards_are_checked_against_the_real_pack():
    box = ChatToolbox(SWOTReportDelta.model_construct(competitors=[]), _pack())
    card = _run(box, "propose_rewrite_asset", {"asset_id": "email-1", "instruction": "shorter"})[0]["action"]
    assert card["kind"] == "rewrite_asset" and card["payload"]["asset_id"] == "email-1"
    assert "error" in _run(box, "propose_rewrite_asset", {"asset_id": "nope", "instruction": "x"})[0]["result"]
    approve = _run(box, "propose_channel_approval", {"channel": "email"})[0]["action"]
    assert "1 QA note" in approve["detail"]
    bad_time = _run(box, "propose_reschedule", {"time_of_day": "25:00"})[0]["result"]
    assert "HH:MM" in bad_time["error"]
    empty = ChatToolbox(SWOTReportDelta.model_construct(competitors=[]), None)
    assert "strategy must be approved" in _run(empty, "propose_channel_approval", {"channel": "email"})[0]["result"]["error"]


def test_reschedule_moves_planned_assets_only(monkeypatch):
    class Store:
        async def save_run(self, run): ...
        async def append_event(self, job_id, event): ...

    monkeypatch.setattr("orchestrator.services.campaign_service.get_storage", lambda: Store())
    svc = CampaignService()
    job = CampaignJob(job_id="j", merchant_context={})
    job.content_pack = _pack()
    job.content_pack.assets[1].status = "published"
    svc._jobs["j"] = job
    asyncio.run(svc.reschedule_assets("j", shift_days=7, time_of_day="08:00"))
    email, post = job.content_pack.assets
    assert email.scheduled_for == "2026-11-08T08:00:00" and post.scheduled_for == "2026-11-02T09:00:00"


def test_openers_say_only_what_the_data_holds():
    job = CampaignJob(job_id="j", merchant_context={})
    job.content_pack = _pack()
    o = opening(job, "content")
    assert "2 assets across 2 channel(s)" in o["message"] and "[placeholders]" in o["message"]
    assert o["suggestions"]
    assert "approved" in opening(CampaignJob(job_id="k", merchant_context={}), "content")["message"]
    assert "still running" in opening(CampaignJob(job_id="k", merchant_context={}), "research")["message"]
