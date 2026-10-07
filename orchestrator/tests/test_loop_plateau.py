"""
Research loop early-exit behaviour.

Each extra round costs a search plus a crawl and enlarges the synthesis corpus, so a round
that neither finds a new competitor nor improves DQS is pure cost. A measured run went
32 -> 44 -> 48 -> 48 competitors with DQS 0.77 -> 0.77 -> 0.76 -> 0.76; the last round
added nothing.

These tests use stub subagents, so no network, no API keys and no LLM.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.agents.market_research.discovery.search import TavilySearchResult
from orchestrator.agents.market_research.pipeline.loop import execute_research_loop
from orchestrator.schemas.research import DynamicParameterTaxonomy


class _StubSearch:
    """Returns a controllable number of distinct competitor-bearing results per round.

    Titles avoid words like "review" and "best", which the listicle filter treats as a sign
    the page is an article *about* vendors rather than a vendor's own site.
    """

    errors: list[str] = []

    def __init__(self, per_round: list[int]) -> None:
        self.per_round = per_round
        self.rounds_run = 0
        self.errors = []

    async def run(self, queries: list[Any], round_number: int = 0) -> list[TavilySearchResult]:
        count = self.per_round[min(self.rounds_run, len(self.per_round) - 1)]
        self.rounds_run += 1
        return [
            TavilySearchResult(
                vector="alternative_discovery",
                title=f"Brand{i} Platform",
                url=f"https://brand{i}.com/",
                snippet=f"Brand{i} builds software for teams and ships it fast.",
                score=0.9,
            )
            for i in range(count)
        ]


class _StubCrawl:
    def __init__(self) -> None:
        self.calls = 0
        self.errors: list[str] = []

    async def run(self, urls: list[str]) -> list[dict[str, Any]]:
        self.calls += 1
        return []


def _taxonomy() -> DynamicParameterTaxonomy:
    return DynamicParameterTaxonomy(
        critical_jtbd_drivers=["speed", "price", "support", "quality"],
        minor_attributes=[f"attr{i}" for i in range(5)],
    )


@pytest.mark.asyncio
async def test_plateau_stops_before_exhausting_retries():
    """A stalled run exits early instead of paying for rounds that cannot help."""
    # Same yield every round: no new competitors, no DQS movement.
    search = _StubSearch(per_round=[8])
    crawl = _StubCrawl()

    result = await execute_research_loop(
        merchant_context={"product_name": "Acme", "category": "CRM"},
        initial_taxonomy=_taxonomy(),
        search_agent=search,
        crawl_agent=crawl,
    )

    # Round 0 establishes the baseline, round 1 detects the plateau and breaks.
    assert search.rounds_run == 2, "should stop as soon as a round adds nothing"
    assert result.retries_used < 3


@pytest.mark.asyncio
async def test_growing_rounds_are_not_cut_short():
    """A round that keeps finding competitors must not be mistaken for a plateau."""
    search = _StubSearch(per_round=[5, 9, 14, 20])
    crawl = _StubCrawl()

    await execute_research_loop(
        merchant_context={"product_name": "Acme", "category": "CRM"},
        initial_taxonomy=_taxonomy(),
        search_agent=search,
        crawl_agent=crawl,
    )

    assert search.rounds_run > 2, "a still-improving loop was stopped early"


@pytest.mark.asyncio
async def test_plateau_respects_the_minimum_competitor_floor():
    """Below the minimum competitor count the loop keeps trying rather than settling."""
    search = _StubSearch(per_round=[2])  # under research_min_competitors (5)
    crawl = _StubCrawl()

    search_runs_before = search.rounds_run
    await execute_research_loop(
        merchant_context={"product_name": "Acme", "category": "CRM"},
        initial_taxonomy=_taxonomy(),
        search_agent=search,
        crawl_agent=crawl,
    )

    assert search.rounds_run - search_runs_before > 2, (
        "a thin result set should keep retrying, not plateau-stop"
    )


@pytest.mark.asyncio
async def test_first_competitors_hook_fires_once_and_early():
    """Ad intelligence is kicked off from this hook, so it must fire on the first round only."""
    search = _StubSearch(per_round=[8])
    crawl = _StubCrawl()
    calls: list[int] = []

    async def _hook(competitors: list[Any]) -> None:
        calls.append(len(competitors))

    await execute_research_loop(
        merchant_context={"product_name": "Acme", "category": "CRM"},
        initial_taxonomy=_taxonomy(),
        search_agent=search,
        crawl_agent=crawl,
        on_first_competitors=_hook,
    )

    assert len(calls) == 1, "hook must fire exactly once"
    assert calls[0] > 0


@pytest.mark.asyncio
async def test_failing_hook_does_not_break_the_loop():
    """A broken ad-intelligence kickoff must not take the research run down with it."""
    search = _StubSearch(per_round=[8])
    crawl = _StubCrawl()

    async def _boom(competitors: list[Any]) -> None:
        raise RuntimeError("ad intel exploded")

    result = await execute_research_loop(
        merchant_context={"product_name": "Acme", "category": "CRM"},
        initial_taxonomy=_taxonomy(),
        search_agent=search,
        crawl_agent=crawl,
        on_first_competitors=_boom,
    )

    assert result.preliminary_competitors, "loop should finish despite the hook failing"
