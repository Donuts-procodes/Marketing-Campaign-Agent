"""
Market demand and mood: is interest in this category rising or falling, when does it peak, and
what are people starting to search for.

Built from numbers only:
  - Google Trends weekly search interest (12 months) for the category in the merchant's country:
    direction = last 13 weeks against the 13 before; seasonality = the strongest and weakest months;
  - rising related searches (what is trending inside the category);
  - purchase signals the listings step already read ("500+ bought in past month" badges).
The mood line is composed from those figures, never written freely, and the whole block says
"unavailable" with the reason when Trends gives nothing.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any

from orchestrator.agents.market_research.ingestion.google_trends import TrendsError, fetch_trends
from orchestrator.agents.market_research.ingestion.search_client import market_for
from orchestrator.schemas.research import DemandPoint, MarketDemand, SWOTReportDelta, TrendingSearch

logger = logging.getLogger(__name__)

FLAT_BAND = 5.0  # % change within which demand counts as flat
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _keywords(merchant_context: dict[str, Any]) -> list[str]:
    category = str(merchant_context.get("category") or merchant_context.get("product_name") or "").strip().lower()
    words = category.split()
    tries = [category]
    if len(words) > 2:
        tries.append(" ".join(words[-2:]))  # "formal leather shoes" -> "leather shoes"
    return [t for t in dict.fromkeys(tries) if t]


def analyse_series(points: list[tuple[str, int]]) -> dict[str, Any]:
    """Direction, change and seasonality from weekly interest points."""
    values = [v for _, v in points]
    recent, prior = values[-13:], values[-26:-13]
    change = None
    if prior and sum(prior) > 0:
        change = round((sum(recent) / len(recent) - sum(prior) / len(prior)) / (sum(prior) / len(prior)) * 100, 1)
    direction = "flat" if change is None or abs(change) < FLAT_BAND else ("rising" if change > 0 else "falling")
    by_month: dict[int, list[int]] = defaultdict(list)
    for day, v in points:
        by_month[date.fromisoformat(day).month].append(v)
    month_avg = {m: sum(v) / len(v) for m, v in by_month.items() if v}
    ranked = sorted(month_avg, key=month_avg.get, reverse=True)
    avg = sum(values) / len(values) if values else 0
    now = values[-4:]
    return {
        "change_pct": change,
        "direction": direction,
        "peak_months": [_MONTHS[m - 1] for m in ranked[:2]],
        "low_months": [_MONTHS[m - 1] for m in ranked[-2:]] if len(ranked) > 3 else [],
        "current_vs_year_pct": round((sum(now) / len(now) - avg) / avg * 100, 1) if avg and now else None,
    }


async def add_search_volume(demand: MarketDemand, market: tuple[str, str, str] | None) -> list[str]:
    """Google Ads monthly searches, CPC and competition (DataForSEO) for the keyword and its related searches."""
    from orchestrator.agents.market_research.ingestion.data_sources import DataSourceError, search_volume
    from orchestrator.core.config import get_settings

    s = get_settings()
    if not (s.dataforseo_login and s.dataforseo_password):
        return []
    words = list(dict.fromkeys([demand.keyword, *demand.top_searches[:5], *(r.query for r in demand.rising_searches[:4])]))
    try:
        rows = await search_volume(words, market[1].title() if market else None)
    except DataSourceError as exc:
        return [f"[DEMAND] Search volumes unavailable ({exc})."]
    by_kw = {r["keyword"]: r for r in rows if r.get("keyword")}
    main = by_kw.get(demand.keyword)
    if main:
        demand.monthly_volume = main["search_volume"]
        demand.cpc = main["cpc"]
        demand.competition = main["competition"]
        demand.volume_series = [DemandPoint(date=f"{m}-01", value=v) for m, v in main["monthly"]]
    demand.keyword_volumes = [
        {"keyword": k, "volume": r["search_volume"], "cpc": r["cpc"]}
        for k, r in by_kw.items() if r.get("search_volume") is not None
    ]
    demand.keyword_volumes.sort(key=lambda r: r["volume"] or 0, reverse=True)
    return [f"[DEMAND] Google Ads volumes for {len(demand.keyword_volumes)} keyword(s)."]


def mood_line(d: MarketDemand) -> str:
    parts = []
    if d.monthly_volume is not None:
        parts.append(f"About {d.monthly_volume:,} searches a month for \"{d.keyword}\"")
    if not d.available:
        return ("; ".join(parts) + ".") if parts else ""
    if d.direction == "rising":
        parts.append(f"Demand is rising: searches are up {d.change_pct:g}% on the previous quarter")
    elif d.direction == "falling":
        parts.append(f"Demand is cooling: searches are down {abs(d.change_pct or 0):g}% on the previous quarter")
    else:
        parts.append("Demand is steady quarter on quarter")
    if d.current_vs_year_pct is not None and abs(d.current_vs_year_pct) >= FLAT_BAND:
        parts.append(f"this month runs {abs(d.current_vs_year_pct):g}% {'above' if d.current_vs_year_pct > 0 else 'below'} the yearly average")
    if d.peak_months:
        parts.append(f"interest peaks in {' and '.join(d.peak_months)}")
    line = "; ".join(parts) + "."
    if d.rising_searches:
        line += f" Rising searches: {', '.join(s.query for s in d.rising_searches[:3])}."
    return line


def _purchase_signals(report: SWOTReportDelta) -> list[str]:
    out = []
    for c in report.competitors:
        for l in c.channel_listings:
            if l.velocity_signal:
                out.append(f"{c.brand_name} on {l.site}: {l.velocity_signal}")
            if l.sales_rank:
                drops = f", sold often enough to climb the ranking {l.sales_rank_drops_30d} times in 30 days" if l.sales_rank_drops_30d else ""
                out.append(f"{c.brand_name} on {l.site}: Amazon sales rank #{l.sales_rank:,}{drops}")
    return list(dict.fromkeys(out))[:6]


async def read_demand(report: SWOTReportDelta, merchant_context: dict[str, Any], fetch=fetch_trends) -> tuple[SWOTReportDelta, list[str]]:
    market = market_for(merchant_context)
    geo = market[0] if market else ""
    keywords = _keywords(merchant_context)
    if not keywords:
        return report, ["[DEMAND] Skipped: no category to measure."]
    last_error = ""
    for kw in keywords:
        try:
            data = await fetch(kw, geo)
        except TrendsError as exc:
            last_error = str(exc)
            continue
        points = data.get("points") or []
        if len(points) < 26 or not any(v for _, v in points):
            last_error = f"too little search data for '{kw}'"
            continue
        stats = analyse_series(points)
        demand = MarketDemand(
            keyword=kw,
            geo=geo or "worldwide",
            source="Google Trends",
            series=[DemandPoint(date=d, value=v) for d, v in points],
            rising_searches=[TrendingSearch(query=q, growth=g) for q, g in data.get("rising") or [] if q],
            top_searches=[q for q in data.get("top") or [] if q][:8],
            purchase_signals=_purchase_signals(report),
            **stats,
        )
        volume_note = await add_search_volume(demand, market)
        demand.mood = mood_line(demand)
        report.demand = demand
        return report, [f"[DEMAND] {demand.mood}", *volume_note]
    report.demand = MarketDemand(
        keyword=keywords[0], geo=geo or "worldwide", source="Google Trends", available=False,
        unavailable_reason=last_error or "no data", purchase_signals=_purchase_signals(report),
    )
    # Absolute volumes still stand on their own when the trend curve is unavailable.
    volume_note = await add_search_volume(report.demand, market)
    if report.demand.monthly_volume is not None:
        report.demand.mood = mood_line(report.demand)
    return report, [f"[DEMAND] Search-interest data unavailable ({last_error or 'no data'}).", *volume_note]
