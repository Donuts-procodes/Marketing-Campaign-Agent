"""Demand: direction, seasonality and mood come from the search-interest figures only."""

import asyncio
from datetime import date, timedelta

from orchestrator.agents.market_research.ingestion.google_trends import TrendsError
from orchestrator.agents.market_research.intelligence.market_mapping.demand import analyse_series, read_demand
from orchestrator.schemas.research import SWOTReportDelta


def _weeks(values, start=date(2025, 10, 12)):
    return [((start + timedelta(weeks=i)).isoformat(), v) for i, v in enumerate(values)]


def test_rising_demand_and_peak_months():
    pts = _weeks([40] * 26 + [50] * 13 + [60] * 13)  # last quarter 60 vs 50 before
    s = analyse_series(pts)
    assert s["direction"] == "rising" and s["change_pct"] == 20.0
    assert len(s["peak_months"]) == 2


def test_mood_is_composed_from_the_figures_and_failures_say_unavailable():
    async def fetch(kw, geo):
        assert geo == "IN"
        return {"points": _weeks([60] * 39 + [45] * 13), "rising": [("derby shoes", "+50%")], "top": ["formal shoes"]}

    report = SWOTReportDelta.model_construct(competitors=[], demand=None)
    report, notes = asyncio.run(read_demand(report, {"category": "formal shoes", "target_geography": "India"}, fetch))
    d = report.demand
    assert d.direction == "falling" and d.change_pct == -25.0
    assert d.mood.startswith("Demand is cooling: searches are down 25%") and "derby shoes" in d.mood

    async def blocked(kw, geo):
        raise TrendsError("explore HTTP 429")

    report = SWOTReportDelta.model_construct(competitors=[], demand=None)
    report, notes = asyncio.run(read_demand(report, {"category": "formal leather shoes"}, blocked))
    assert report.demand.available is False and "429" in report.demand.unavailable_reason and report.demand.series == []
