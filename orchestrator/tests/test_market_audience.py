"""Market and audience analysis keeps only points tied to a document we supplied or the merchant brief."""

import asyncio

from orchestrator.agents.market_research.ingestion.search_client import TavilySearchResult
from orchestrator.agents.market_research.intelligence.advisory.market_audience import (
    _Response,
    analyze_market_and_audience,
    build_market_queries,
    ground_response,
)
from orchestrator.schemas.research import SWOTReportDelta


def test_points_without_a_supplied_source_are_dropped():
    resp = _Response.model_validate({
        "market": {
            "summary": "Formal shoes are moving online.",
            "key_findings": [
                {"text": "Buyers compare prices across Myntra and Amazon", "ref": "D1"},
                {"text": "Market grows 18% a year", "ref": ""},          # no source
                {"text": "Invented stat", "ref": "D9"},                   # never supplied
            ],
            "trends": [{"text": "Comfort soles in office wear", "ref": "D1", "signal": "booming"}],
        },
        "audience": {
            "icp": {"name": "Young office goers", "why": [{"text": "Stated target", "ref": "M"}]},
            "segments": [
                {"name": "First job", "size_note": "2 million", "ref": "M"},   # merchant: size dropped
                {"name": "Weddings", "size_note": "40% of sales", "ref": "D1"},
            ],
            "pains": [{"text": "Soles wear out in months", "ref": "d1"}],
            "channels": [{"text": "Instagram", "reason": "discovery", "ref": "D1"}],
        },
    })
    market, audience, dropped = ground_response(resp, {"D1": "https://example.in/report"})
    assert [p.text for p in market.key_findings] == ["Buyers compare prices across Myntra and Amazon"]
    assert dropped == 2
    assert market.trends[0].signal == "rising" and market.trends[0].source_url == "https://example.in/report"
    assert audience.icp.why[0].from_merchant is True
    assert [(g.name, g.size_note) for g in audience.segments] == [("First job", None), ("Weddings", "40% of sales")]
    assert audience.pains[0].source_url == "https://example.in/report"  # ref matching ignores case


def test_market_queries_follow_category_and_country():
    qs = build_market_queries({"category": "formal leather shoes", "target_geography": "India"})
    assert len(qs) == 4 and all("formal leather shoes" in q.query and "India" in q.query for q in qs)
    assert build_market_queries({}) == []


def test_runs_market_searches_and_stores_grounded_result():
    class LLM:
        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, messages):
            assert "D1" in messages[1]["content"]
            return _Response.model_validate({"market": {"key_findings": [{"text": "Prices cluster at ₹2-3k", "ref": "D1"}]}})

    async def search(queries):
        return [TavilySearchResult(vector="market_audience", title="Shoe market India", url="https://x.in/a", snippet="Most pairs sell at ₹2-3k")]

    report = SWOTReportDelta.model_construct(competitors=[], market_overview=None, audience=None)
    report, notes = asyncio.run(analyze_market_and_audience(report, {"category": "shoes"}, LLM(), search))
    assert report.market_overview.key_findings[0].source_url == "https://x.in/a"
    assert "1 document" in notes[0]
    _, skipped = asyncio.run(analyze_market_and_audience(report, {}, None))
    assert "needs a language model" in skipped[0]
