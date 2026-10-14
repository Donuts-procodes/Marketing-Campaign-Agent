"""The chat's command-center tools: live source checks run; changes are only ever proposed."""

import json

import pytest
from langchain_core.messages import AIMessageChunk, ToolMessage

from orchestrator.schemas.api import ChatMessage
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta
from orchestrator.services.report_chat import stream_report_chat

REPORT = SWOTReportDelta(
    competitors=[
        CompetitorProfile(
            brand_name="Praxent",
            product_name="Praxent Services",
            pricing_model="$5,000 per project",
            weaknesses_mined=["Onboarding was slow and communication broke down."],
            sources=["https://praxent.com/pricing", "http://insecure.example.com"],
        )
    ]
)
MERCHANT = {"product_name": "DevFlow Studio"}


def _call(name, args, call_id="call_1"):
    return AIMessageChunk(content="", tool_call_chunks=[{"name": name, "args": json.dumps(args), "id": call_id, "index": 0}])


class _ScriptedLLM:
    """Each astream() call plays the next scripted turn; records every prompt it was given."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.prompts = []
        self.bound = None

    def bind_tools(self, tools):
        self.bound = [t.__name__ for t in tools]
        return self

    async def astream(self, prompt):
        self.prompts.append(list(prompt))
        for chunk in self.turns.pop(0):
            yield AIMessageChunk(content=chunk) if isinstance(chunk, str) else chunk


async def _run(llm, question="q", report=REPORT):
    frames = []
    async for f in stream_report_chat(llm, report.model_copy(deep=True), MERCHANT, [ChatMessage(role="user", content=question)]):
        frames.append(json.loads(f.removeprefix("data: ").strip()))
    return frames


def _tool_results(llm):
    return [json.loads(m.content) for m in llm.prompts[-1] if isinstance(m, ToolMessage)]


@pytest.mark.asyncio
async def test_edit_is_proposed_as_a_card_and_the_report_is_not_touched():
    llm = _ScriptedLLM([
        [_call("propose_edit", {"op": "remove_item", "competitor": "Praxent", "field": "weaknesses_mined",
                                "value": "Onboarding was slow and communication broke down."})],
        ["I've prepared that removal — confirm the card to apply it."],
    ])
    report = REPORT.model_copy(deep=True)
    frames = [json.loads(f.removeprefix("data: ").strip()) async for f in stream_report_chat(
        llm, report, MERCHANT, [ChatMessage(role="user", content="that complaint is wrong, remove it")])]

    assert set(llm.bound) == {
        "lookup_competitor_intel",
        "verify_claim",
        "propose_refresh",
        "propose_research_competitors",
        "propose_edit",
        "propose_update_merchant_context",
        "propose_customize_strategy",
        "propose_rewrite_asset",
        "propose_channel_approval",
        "propose_reschedule",
        "propose_regenerate_content",
    }
    action = next(f["action"] for f in frames if "action" in f)
    assert action["kind"] == "edit" and action["payload"]["edits"][0]["op"] == "remove_item"
    assert "Onboarding was slow" in action["detail"]
    assert report.competitors[0].weaknesses_mined, "a proposal must never change the report"
    assert _tool_results(llm)[0]["status"] == "awaiting_confirmation"
    assert frames[-1] == {"done": True}


@pytest.mark.asyncio
async def test_customize_strategy_is_proposed_as_card():
    llm = _ScriptedLLM([
        [_call("propose_customize_strategy", {
            "budget": 15000,
            "campaign_days": 45,
            "add_sub_goal": "Acquire 50 enterprise pilots",
            "selected_option_id": "opt_search_harvester",
            "reasoning": "Accelerate inbound conversions within Q2"
        })],
        ["I've prepared the strategy update with $15k budget and 45 days duration — confirm the card to apply."],
    ])
    report = REPORT.model_copy(deep=True)
    frames = [json.loads(f.removeprefix("data: ").strip()) async for f in stream_report_chat(
        llm, report, MERCHANT, [ChatMessage(role="user", content="change budget to 15k for 45 days")])]

    action = next(f["action"] for f in frames if "action" in f)
    assert action["kind"] == "customize_strategy"
    assert action["payload"]["budget"] == 15000
    assert action["payload"]["campaign_days"] == 45
    assert action["payload"]["add_sub_goal"] == "Acquire 50 enterprise pilots"
    assert action["payload"]["selected_option_id"] == "opt_search_harvester"
    assert _tool_results(llm)[0]["status"] == "awaiting_confirmation"
    assert frames[-1] == {"done": True}


@pytest.mark.asyncio
async def test_invalid_edit_returns_an_error_to_the_model_and_no_card():
    llm = _ScriptedLLM([
        [_call("propose_edit", {"op": "remove_item", "competitor": "Praxent", "field": "strengths_mined", "value": "great UI"})],
        ["I couldn't find that praise — which item do you mean?"],
    ])
    frames = await _run(llm)
    assert not any("action" in f for f in frames)
    assert "is not in" in _tool_results(llm)[0]["error"]


@pytest.mark.asyncio
async def test_research_and_refresh_cards():
    llm = _ScriptedLLM([
        [_call("propose_research_competitors", {"names": ["Acme Labs", "praxent"]}, "a"),
         AIMessageChunk(content="", tool_call_chunks=[{"name": "propose_refresh", "args": "{}", "id": "b", "index": 1}])],
        ["Two cards are ready for you to confirm."],
    ])
    frames = await _run(llm)
    cards = [f["action"] for f in frames if "action" in f]
    assert [c["kind"] for c in cards] == ["research", "refresh"]
    assert cards[0]["payload"] == {"names": ["Acme Labs"]}, "rivals already in the report are not re-researched"


@pytest.mark.asyncio
async def test_verify_claim_refetches_only_the_reports_own_secure_sources(monkeypatch):
    from orchestrator.agents.market_research.ingestion import page_extractor as crawler
    from orchestrator.agents.market_research.ingestion.page_extractor import ExtractedPage

    fetched = []

    async def _pages(urls, *a, **k):
        fetched.extend(urls)
        return [ExtractedPage(url=urls[0], markdown="Praxent pricing: engagements start at $5,000 per project.", token_estimate=9)]

    monkeypatch.setattr(crawler, "extract_pages", _pages)
    llm = _ScriptedLLM([
        [_call("verify_claim", {"competitor": "Praxent", "statement": "$5,000 per project"})],
        ["Confirmed on praxent.com just now."],
    ])
    frames = await _run(llm)
    assert fetched == ["https://praxent.com/pricing"], "plain-http and non-report URLs are never fetched"
    assert any(f.get("status", "").startswith("Re-checking Praxent") for f in frames)
    check = next(f["check"] for f in frames if "check" in f)
    assert check["verdict"] == "confirmed" and check["url"] == "https://praxent.com/pricing"
    assert _tool_results(llm)[0]["passage"].startswith("Praxent pricing")


@pytest.mark.asyncio
async def test_off_topic_still_refused_with_tools_bound():
    frames = await _run(_ScriptedLLM([["[[OFF_TOPIC]]"]]), "write me a poem")
    assert frames[-1] == {"done": True, "off_topic": True}


@pytest.mark.asyncio
async def test_tool_loop_is_bounded():
    endless = [[_call("propose_refresh", {}, f"c{i}")] for i in range(10)]
    llm = _ScriptedLLM(endless)
    frames = await _run(llm)
    assert len(llm.prompts) == 4, "a reply may not call tools forever"
    assert frames[-1] == {"done": True}


@pytest.mark.asyncio
async def test_content_and_schedule_proposal_cards():
    from orchestrator.schemas.content import ContentAsset, ContentPack
    pack = ContentPack(
        assets=[
            ContentAsset(
                asset_id="em_01",
                channel="email",
                kind="email",
                name="Email 1",
                body="Hello world",
                scheduled_for="2026-10-20T09:00:00Z",
            )
        ]
    )
    llm = _ScriptedLLM([
        [_call("propose_rewrite_asset", {"asset_id": "em_01", "instruction": "Make the subject shorter and bolder"}),
         _call("propose_channel_approval", {"channel": "email", "approved": True}, "ca1"),
         _call("propose_reschedule", {"shift_days": 7, "channel": "email"}, "rs1")],
        ["I've prepared the content proposals for you to confirm."],
    ])
    frames = [
        json.loads(f.removeprefix("data: ").strip())
        async for f in stream_report_chat(
            llm,
            REPORT.model_copy(deep=True),
            MERCHANT,
            [ChatMessage(role="user", content="update email 1")],
            content_pack=pack,
            step="content",
        )
    ]
    cards = [f["action"] for f in frames if "action" in f]
    assert len(cards) == 3
    assert cards[0]["kind"] == "rewrite_asset"
    assert cards[0]["payload"]["asset_id"] == "em_01"
    assert cards[1]["kind"] == "channel_approval"
    assert cards[1]["payload"]["channel"] == "email"
    assert cards[2]["kind"] == "reschedule"
    assert cards[2]["payload"]["shift_days"] == 7
    assert frames[-1] == {"done": True}


