import pytest

from orchestrator.agents.market_research.ingestion.search_client import (
    SearchQuery,
    SearchCircuitBreaker,
    execute_tavily_search,
    query_key,
)
from orchestrator.core.config import get_settings


class _Tavily:
    def __init__(self, n=8):
        self.calls, self.n = [], n

    async def search(self, **kw):
        self.calls.append(kw["query"])
        return {"results": [{"title": "t", "url": f"https://site{i}.com/p", "content": "x"} for i in range(self.n)]}


class _You:
    def __init__(self):
        self.calls = 0

    async def search(self, query, count=10):
        self.calls += 1
        return {"hits": []}


class _DDG:
    def __init__(self, n):
        self.calls, self.n = 0, n

    async def search(self, query, max_results=10, timelimit=None):
        self.calls += 1
        return [{"title": "d", "href": f"https://free{i}.com/", "body": "y"} for i in range(self.n)]


def test_query_key_ignores_order_case_and_quotes():
    a = SearchQuery(vector="a", query='"Acme" (pricing OR cost)')
    b = SearchQuery(vector="b", query="acme cost OR pricing")
    assert query_key(a) == query_key(b)
    assert query_key(a) != query_key(SearchQuery(vector="a", query='"Acme" (pricing OR cost)', time_range="year"))


@pytest.mark.asyncio
async def test_near_duplicates_hit_engine_once_and_each_vector_gets_results(monkeypatch):
    monkeypatch.setattr(get_settings(), "duckduckgo_mode", "off")
    tavily = _Tavily()
    qs = [SearchQuery(vector="v1", query="acme pricing"), SearchQuery(vector="v2", query="Pricing ACME")]
    results = await execute_tavily_search(qs, tavily_client=tavily, circuit_breaker=SearchCircuitBreaker())
    assert len(tavily.calls) == 1
    assert {r.vector for r in results} == {"v1", "v2"}


@pytest.mark.asyncio
async def test_cascade_skips_second_paid_engine_when_first_is_enough(monkeypatch):
    monkeypatch.setattr(get_settings(), "duckduckgo_mode", "off")
    tavily, you = _Tavily(n=8), _You()
    await execute_tavily_search(
        [SearchQuery(vector="pricing_scrape", query="acme pricing")],
        tavily_client=tavily, you_client=you, circuit_breaker=SearchCircuitBreaker(),
    )
    assert len(tavily.calls) == 1 and you.calls == 0


@pytest.mark.asyncio
async def test_free_first_discovery_skips_paid_when_ddg_is_enough(monkeypatch):
    monkeypatch.setattr(get_settings(), "duckduckgo_mode", "fallback")
    tavily, ddg = _Tavily(), _DDG(n=8)
    results = await execute_tavily_search(
        [SearchQuery(vector="alternative_discovery", query="best crm alternatives")],
        tavily_client=tavily, ddg_client=ddg, circuit_breaker=SearchCircuitBreaker(),
    )
    assert ddg.calls == 1 and tavily.calls == []
    assert results and all(r.provider == "duckduckgo" for r in results)


@pytest.mark.asyncio
async def test_free_first_tops_up_with_paid_when_ddg_is_thin(monkeypatch):
    monkeypatch.setattr(get_settings(), "duckduckgo_mode", "fallback")
    tavily, ddg = _Tavily(), _DDG(n=1)
    await execute_tavily_search(
        [SearchQuery(vector="alternative_discovery", query="best crm alternatives")],
        tavily_client=tavily, ddg_client=ddg, circuit_breaker=SearchCircuitBreaker(),
    )
    assert len(tavily.calls) == 1
