"""
Unit tests for Search API Circuit Breaker and Failure Redistribution.

Verifies:
- Failure counting and tripping at the configured threshold (default 2 failures).
- Bypassing tripped providers on subsequent calls.
- Workload redistribution to working providers when an API fails or is tripped.
- Dynamic failover when an engine fails mid-query.
- Resetting failure counters on success before tripping.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
import pytest

from orchestrator.agents.market_research.ingestion.search_client import (
    SearchCircuitBreaker,
    SearchQuery,
    execute_tavily_search,
    get_search_circuit_breaker,
)
from orchestrator.core.config import get_settings


def _mock_ddg(hits: list[dict] | None = None):
    client = AsyncMock()
    client.search = AsyncMock(
        return_value=hits
        if hits is not None
        else [{"title": "DDG Hit", "href": "https://ddg.example.com/1", "body": "ddg content"}]
    )
    return client


def _mock_tavily_success(hits: list[dict] | None = None):
    client = AsyncMock()
    client.search = AsyncMock(
        return_value={
            "results": hits
            if hits is not None
            else [{"title": "Tavily Hit", "url": "https://tavily.example.com/1", "content": "tavily content", "score": 0.9}]
        }
    )
    return client


def _mock_tavily_failing(exc: Exception | None = None):
    client = AsyncMock()
    client.search = AsyncMock(side_effect=exc or ConnectionError("Tavily API down"))
    return client


def _mock_you_success(hits: list[dict] | None = None):
    client = AsyncMock()
    client.search = AsyncMock(
        return_value={
            "results": {
                "web": hits
                if hits is not None
                else [{"title": "You Hit", "url": "https://you.example.com/1", "snippets": ["you snippet"]}]
            }
        }
    )
    return client


def _mock_you_failing(exc: Exception | None = None):
    client = AsyncMock()
    client.search = AsyncMock(side_effect=exc or ConnectionError("You.com API down"))
    return client


class TestSearchCircuitBreakerUnit:
    def test_circuit_breaker_trips_after_two_failures(self):
        cb = SearchCircuitBreaker(max_failures=2)
        assert cb.is_available("tavily")
        assert cb.get_failures("tavily") == 0

        # First failure: not tripped yet
        cb.record_failure("tavily", RuntimeError("503 Service Unavailable"))
        assert cb.is_available("tavily")
        assert cb.get_failures("tavily") == 1
        assert not cb.is_tripped("tavily")

        # Second failure: tripped!
        cb.record_failure("tavily", RuntimeError("503 Service Unavailable"))
        assert not cb.is_available("tavily")
        assert cb.is_tripped("tavily")
        assert "tavily" in cb.get_tripped_providers()

    def test_success_resets_failures_before_tripping(self):
        cb = SearchCircuitBreaker(max_failures=2)
        cb.record_failure("you", RuntimeError("Timeout"))
        assert cb.get_failures("you") == 1

        cb.record_success("you")
        assert cb.get_failures("you") == 0
        assert cb.is_available("you")

        # Still requires 2 new failures to trip
        cb.record_failure("you")
        assert cb.is_available("you")
        cb.record_failure("you")
        assert cb.is_tripped("you")

    def test_reset_clears_all_tripped_states(self):
        cb = SearchCircuitBreaker(max_failures=2)
        cb.record_failure("tavily")
        cb.record_failure("tavily")
        assert cb.is_tripped("tavily")

        cb.reset()
        assert not cb.is_tripped("tavily")
        assert cb.is_available("tavily")
        assert cb.get_failures("tavily") == 0


@pytest.mark.asyncio
class TestSearchRedistributionAndFailover:
    async def test_tavily_trips_after_two_failures_and_redistributes_to_ddg(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "duckduckgo_mode", "fallback")
        cb = SearchCircuitBreaker(max_failures=2)
        broken_tavily = _mock_tavily_failing()
        working_ddg = _mock_ddg([{"title": "DDG Recovery", "href": "https://ddg.com/rescue", "body": "recovered"}])

        query1 = SearchQuery(vector="core_competitors", query="crm software")
        query2 = SearchQuery(vector="pricing", query="crm pricing")
        query3 = SearchQuery(vector="gripe_mining", query="crm complaints")

        # Query 1: Tavily failure 1 -> DDG handles it
        res1 = await execute_tavily_search([query1], tavily_client=broken_tavily, ddg_client=working_ddg, circuit_breaker=cb)
        assert len(res1) == 1
        assert res1[0].provider == "duckduckgo"
        assert cb.get_failures("tavily") == 1
        assert cb.is_available("tavily")
        assert broken_tavily.search.await_count == 1

        # Query 2: Tavily failure 2 -> Trips breaker! DDG handles it
        res2 = await execute_tavily_search([query2], tavily_client=broken_tavily, ddg_client=working_ddg, circuit_breaker=cb)
        assert len(res2) == 1
        assert res2[0].provider == "duckduckgo"
        assert cb.is_tripped("tavily")
        assert broken_tavily.search.await_count == 2

        # Query 3: Tavily is tripped -> NEVER CALLED AGAIN! Directly distributed to working engines
        res3 = await execute_tavily_search([query3], tavily_client=broken_tavily, ddg_client=working_ddg, circuit_breaker=cb)
        assert len(res3) == 1
        assert res3[0].provider == "duckduckgo"
        # Crucial check: tavily call count MUST NOT increase beyond 2
        assert broken_tavily.search.await_count == 2

    async def test_tavily_trips_and_redistributes_to_working_you_client(self, monkeypatch):
        cb = SearchCircuitBreaker(max_failures=2)
        broken_tavily = _mock_tavily_failing()
        working_you = _mock_you_success([{"title": "You Found It", "url": "https://you.com/found", "description": "from you"}])

        # Pre-trip Tavily with 2 failures
        cb.record_failure("tavily")
        cb.record_failure("tavily")
        assert cb.is_tripped("tavily")

        queries = [SearchQuery(vector="core_competitors", query="test query")]
        results = await execute_tavily_search(
            queries,
            tavily_client=broken_tavily,
            you_client=working_you,
            circuit_breaker=cb,
        )

        # Tavily was never called because it was tripped
        broken_tavily.search.assert_not_awaited()
        # You.com took over the search
        working_you.search.assert_awaited_once()
        assert len(results) == 1
        assert results[0].provider == "you"
        assert results[0].url == "https://you.com/found"

    async def test_you_trips_after_two_failures_and_tavily_handles_workload(self, monkeypatch):
        cb = SearchCircuitBreaker(max_failures=2)
        broken_you = _mock_you_failing()
        working_tavily = _mock_tavily_success()

        # Two failing queries for You.com
        q = [SearchQuery(vector="v", query="q")]
        await execute_tavily_search(q, tavily_client=working_tavily, you_client=broken_you, circuit_breaker=cb)
        await execute_tavily_search(q, tavily_client=working_tavily, you_client=broken_you, circuit_breaker=cb)

        assert cb.is_tripped("you")
        assert broken_you.search.await_count == 2

        # Third query: You.com is bypassed, Tavily handles query
        broken_you.search.reset_mock()
        results = await execute_tavily_search(q, tavily_client=working_tavily, you_client=broken_you, circuit_breaker=cb)

        broken_you.search.assert_not_awaited()
        assert any(r.provider == "tavily" for r in results)

    async def test_duckduckgo_trips_after_two_failures_and_is_not_called_again(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "duckduckgo_mode", "always")
        cb = SearchCircuitBreaker(max_failures=2)
        working_tavily = _mock_tavily_success()
        broken_ddg = AsyncMock()
        broken_ddg.search = AsyncMock(side_effect=Exception("DDG rate limited"))

        q = [SearchQuery(vector="v", query="q")]
        # Run twice to trigger 2 DDG failures
        await execute_tavily_search(q, tavily_client=working_tavily, ddg_client=broken_ddg, circuit_breaker=cb)
        await execute_tavily_search(q, tavily_client=working_tavily, ddg_client=broken_ddg, circuit_breaker=cb)

        assert cb.is_tripped("duckduckgo")

        # 3rd run: DDG must not be called
        broken_ddg.search.reset_mock()
        results = await execute_tavily_search(q, tavily_client=working_tavily, ddg_client=broken_ddg, circuit_breaker=cb)

        broken_ddg.search.assert_not_awaited()
        assert len(results) == 1
        assert results[0].provider == "tavily"
