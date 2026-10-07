"""
Tests for the Market Research Agent's tool subagents and coordinating crew.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.agents.market_research.agent import execute_market_research
from orchestrator.tests.mock_clients import create_standalone_mock_clients
from orchestrator.agents.market_research.discovery.search import SearchQuery
from orchestrator.agents.market_research.pipeline.subagents import (
    AdIntelSubagent,
    CrawlSubagent,
    ResearchCrew,
    SearchSubagent,
)


class _Recorder:
    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    async def __call__(self, message: str, level: str = "INFO") -> None:
        self.lines.append((level, message))


@pytest.mark.asyncio
async def test_crawl_subagent_never_rescrapes_a_url():
    crawl_client = MagicMock()
    crawl_client.configured = True
    crawl_client.fetch = AsyncMock(return_value={"body": "# page " + "real words " * 20})
    crawl = CrawlSubagent(crawl_client)

    first = await crawl.run(["https://a.com", "https://b.com", "https://a.com"])
    second = await crawl.run(["https://a.com", "https://c.com"])

    assert [p["url"] for p in first] == ["https://a.com", "https://b.com"]
    assert [p["url"] for p in second] == ["https://c.com"]
    assert crawl_client.fetch.await_count == 3


@pytest.mark.asyncio
async def test_crawl_falls_back_to_tavily_extract_for_failed_urls():
    crawl_client = MagicMock()
    crawl_client.configured = True

    async def _fetch(url, **kwargs):
        if "blocked" in url:
            raise ConnectionError("403")
        return {"body": "crawlapi page " + "word " * 40}

    crawl_client.fetch = _fetch
    tavily = AsyncMock()
    tavily.extract = AsyncMock(
        return_value={"results": [{"url": "https://blocked.com", "raw_content": "tavily page " + "word " * 40}]}
    )
    recorder = _Recorder()
    crawl = CrawlSubagent(crawl_client, recorder, tavily_client=tavily)

    pages = await crawl.run(["https://ok.com", "https://blocked.com"])

    assert sorted(p["url"] for p in pages) == ["https://blocked.com", "https://ok.com"]
    tavily.extract.assert_awaited_once()
    assert tavily.extract.await_args.kwargs["urls"] == ["https://blocked.com"]
    assert "crawlapi 1" in recorder.lines[-1][1] and "tavily_extract 1" in recorder.lines[-1][1]


@pytest.mark.asyncio
async def test_search_subagent_logs_tagged_progress():
    tavily = AsyncMock()
    tavily.search = AsyncMock(return_value={"results": [{"title": "T", "url": "https://x.com", "content": "c"}]})
    recorder = _Recorder()
    search = SearchSubagent(tavily, recorder)

    results = await search.run([SearchQuery(vector="pricing_scrape", query="q")], round_number=2)

    assert len(results) == 1
    assert any(line[1].startswith("[TAVILY_SEARCH] Round 2: 1 queries (pricing_scrape) returned 1 results") for line in recorder.lines)
    assert search.calls == 1


@pytest.mark.asyncio
async def test_ad_intel_subagent_contains_failures(monkeypatch):
    import orchestrator.agents.market_research.pipeline.subagents as subagents

    async def _boom(**kwargs):
        raise ConnectionError("tavily down")

    monkeypatch.setattr(subagents, "search_competitor_ad_hooks", _boom)
    recorder = _Recorder()
    ad_intel = AdIntelSubagent(None, recorder)

    from orchestrator.schemas.research import CompetitorProfile

    result = await ad_intel.run([CompetitorProfile(brand_name="A", product_name="B")], "cat")

    assert result.hooks_by_competitor == {} and result.documents == []
    assert recorder.lines[-1][0] == "WARN"
    assert recorder.lines[-1][1].startswith("[AD_INTELLIGENCE]")
    assert ad_intel.errors and "tavily down" in ad_intel.errors[0]


@pytest.mark.asyncio
async def test_research_agent_reports_progress_from_every_subagent():
    tavily, crawl_client, llm = create_standalone_mock_clients()
    recorder = _Recorder()
    state = {
        "merchant_context": {"product_name": "ErgoMouse", "category": "Peripherals", "primary_value_prop": "v"},
        "swot_report": None,
        "dqs_retries": 0,
        "errors": [],
    }

    result = await execute_market_research(
        state, tavily_client=tavily, crawl_client=crawl_client, llm=llm, on_progress=recorder
    )

    tags = {msg.split("]")[0].lstrip("[") for _, msg in recorder.lines}
    assert {
        "DYNAMIC_PARAMS",
        "TAVILY_SEARCH",
        "DEEP_SEARCH",
        "DQS_EVAL",
        "AD_INTELLIGENCE",
        "LLM_SYNTH",
        "DATA_VALIDATION",
    } <= tags
    assert result["swot_report"].competitors


def test_crew_aggregates_member_errors():
    crew = ResearchCrew.build()
    crew.search.errors.append("search broke")
    crew.crawl.errors.append("crawl broke")
    assert crew.errors == ["search broke", "crawl broke"]
