"""Store discovery: a country's popular stores come from search, grounded; global stores without a country."""

import asyncio

from orchestrator.agents.market_research.ingestion.search_client import TavilySearchResult
from orchestrator.agents.market_research.intelligence.profiling import store_discovery
from orchestrator.agents.market_research.intelligence.profiling.listing_intel import resolve_stores
from orchestrator.agents.market_research.intelligence.profiling.store_discovery import _Stores


class _LLM:
    calls = 0

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        _LLM.calls += 1
        return _Stores.model_validate({"stores": [
            {"host": "https://www.bol.com/nl/", "type": "marketplace"},
            {"host": "coolblue.nl", "type": "marketplace"},
            {"host": "madeupstore.nl", "type": "marketplace"},   # not in any result
            {"host": "statista.com", "type": "marketplace"},     # not a store
        ]})


async def _search(queries):
    assert all("Netherlands" in q.query or "netherlands" in q.query for q in queries)
    return [
        TavilySearchResult(vector="store_discovery", title="Top webshops in Nederland",
                           url="https://www.statista.com/x", snippet="bol.com and Coolblue lead online retail"),
    ]


def test_unlisted_country_discovers_grounded_stores_and_caches(monkeypatch):
    monkeypatch.setattr(store_discovery, "_cache", {})
    _LLM.calls = 0
    notes: list[str] = []
    ctx = {"target_geography": "Netherlands", "category": "headphones"}
    stores, currency = asyncio.run(resolve_stores(ctx, _search, _LLM(), notes))
    assert [h for h, _ in stores] == ["bol.com", "coolblue.nl"]
    assert currency == "EUR"
    asyncio.run(resolve_stores(ctx, _search, _LLM(), []))
    assert _LLM.calls == 1  # second run served from cache


def test_no_country_uses_global_stores_and_known_markets_keep_their_seed(monkeypatch):
    monkeypatch.setattr(store_discovery, "_cache", {})
    notes: list[str] = []
    stores, currency = asyncio.run(resolve_stores({"category": "shoes"}, _search, _LLM(), notes))
    assert stores[0][0] == "amazon.com" and currency is None and "global" in notes[-1]

    async def nothing(queries):
        return []

    india, inr = asyncio.run(resolve_stores({"target_geography": "India", "category": "shoes"}, nothing, None, []))
    assert ("amazon.in", "marketplace") in india and inr == "INR"
