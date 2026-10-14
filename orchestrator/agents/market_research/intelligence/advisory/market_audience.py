"""
Market overview and audience: the marketing half of the research.

Competitor profiles say who the rivals are. A campaign also needs to know what the market is
doing and who to sell to. This step runs a few market searches (trends, buyer behaviour, where
people buy, in the merchant's country), then makes one model call over:
  - those search excerpts,
  - what rivals' customers praise and complain about, and the buyer types reviews describe,
  - rivals' buying patterns and marketplace listings,
  - the merchant's own brief.

Every point must name the document it came from (D1, D2…) or the merchant's brief (M). A point
whose reference is not one we supplied is dropped, so a statistic the model remembers rather
than read ("market growing 18% YoY") never reaches the dashboard. Sizes are only kept when a
source states them.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.agents.market_research.ingestion.search_client import SearchQuery, TavilySearchResult
from orchestrator.core.clock import today as clock_today
from orchestrator.schemas.research import (
    AudienceProfile,
    AudienceSegment,
    IdealCustomerProfile,
    MarketOverview,
    MarketTrend,
    ReachChannel,
    SourcedPoint,
    SWOTReportDelta,
)

logger = logging.getLogger(__name__)

SearchFn = Callable[[list[SearchQuery]], Awaitable[list[TavilySearchResult]]]

VECTOR = "market_audience"
MAX_DOCS = 30
DOC_CHARS = 700

PROMPT = """\
You are the market and audience analyst for a marketing campaign. Using ONLY the numbered \
documents and the merchant brief, write:

market: summary (2-3 sentences), key_findings, positioning_opportunities (openings the merchant \
can claim that rivals leave uncovered), trends (each with signal rising/falling/new/steady).
audience: the ICP (who to win first, with attributes such as age band, city tier, income, \
occasion, and why), segments (name, definition, what triggers them to buy), pains, motivations, \
behaviors, triggers, barriers, channels (where to reach them, and why), preferred_message (one \
sentence on what to lead with).

Rules:
- Every point carries ref: the id of the document that supports it ("D3") or "M" for the \
merchant brief. No ref, no point.
- Never state a number (market size, growth %, share, count) unless that document states it.
- Pains and barriers come from what real customers say about rivals; quote their substance.
- Be specific to this product and market. No generic marketing advice.
- Fewer, well-supported points beat many weak ones. Empty lists are fine.
"""


class _Point(BaseModel):
    text: str
    ref: str = ""


class _Trend(_Point):
    signal: str = "rising"


class _Channel(_Point):
    reason: str = ""


class _Segment(BaseModel):
    name: str
    definition: str = ""
    trigger: str = ""
    size_note: str | None = None
    ref: str = ""


class _ICP(BaseModel):
    name: str = ""
    description: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    why: list[_Point] = Field(default_factory=list)
    fit_signals: list[str] = Field(default_factory=list)
    low_fit_signals: list[str] = Field(default_factory=list)


class _Market(BaseModel):
    summary: str = ""
    key_findings: list[_Point] = Field(default_factory=list)
    positioning_opportunities: list[_Point] = Field(default_factory=list)
    trends: list[_Trend] = Field(default_factory=list)


class _Audience(BaseModel):
    icp: _ICP | None = None
    segments: list[_Segment] = Field(default_factory=list)
    pains: list[_Point] = Field(default_factory=list)
    motivations: list[_Point] = Field(default_factory=list)
    behaviors: list[_Point] = Field(default_factory=list)
    triggers: list[_Point] = Field(default_factory=list)
    barriers: list[_Point] = Field(default_factory=list)
    channels: list[_Channel] = Field(default_factory=list)
    preferred_message: str = ""


class _Response(BaseModel):
    market: _Market = Field(default_factory=_Market)
    audience: _Audience = Field(default_factory=_Audience)


def build_market_queries(merchant_context: dict[str, Any]) -> list[SearchQuery]:
    """A handful of market-level searches: trends, buyer behaviour, where people buy."""
    category = str(merchant_context.get("category") or merchant_context.get("product_name") or "").strip()
    if not category:
        return []
    where = str(merchant_context.get("target_geography") or "").strip()
    place = f" {where}" if where and where.lower() not in ("global", "worldwide") else ""
    year = clock_today().year
    return [
        SearchQuery(vector=VECTOR, query=f"{category} market trends{place} {year}", search_depth="basic"),
        SearchQuery(vector=VECTOR, query=f"{category} consumer buying behaviour{place} survey", search_depth="basic"),
        SearchQuery(vector=VECTOR, query=f"why people buy {category}{place} what matters most", search_depth="basic"),
        SearchQuery(vector=VECTOR, query=f"where do people buy {category} online{place}", search_depth="basic"),
    ]


def _review_docs(report: SWOTReportDelta) -> list[tuple[str, str]]:
    """What rivals' customers say, as documents with the rival's first source as their url."""
    docs = []
    for comp in report.competitors:
        rc = comp.review_context
        lines = []
        if rc:
            lines += [f"Complaint: {a.topic} — {a.summary}" for a in (rc.top_complaint_drivers or [])[:4]]
            lines += [f"Praise: {a.topic} — {a.summary}" for a in (rc.top_praise_drivers or [])[:3]]
            lines += [f"Buyer type: {p}" for p in (rc.buyer_personas or [])[:3]]
            lines += [f"Unmet need: {n}" for n in (rc.unmet_customer_needs or [])[:3]]
        lines += [f"Complaint: {w}" for w in (comp.weaknesses_mined or [])[:3]]
        bp = comp.buying_patterns
        if bp:
            if bp.sales_channels:
                lines.append(f"Sells through: {', '.join(bp.sales_channels[:6])}")
            if bp.buying_triggers:
                lines.append(f"Buying triggers: {', '.join(bp.buying_triggers[:4])}")
        for listing in comp.channel_listings[:3]:
            if listing.selling_price:
                lines.append(f"Listed on {listing.site} at {listing.currency or ''} {listing.selling_price:,.0f}")
        if lines and comp.sources:
            docs.append((comp.sources[0], f"About rival {comp.brand_name}:\n" + "\n".join(lines)))
    return docs


def _merchant_brief(merchant_context: dict[str, Any]) -> str:
    keys = ("product_name", "category", "primary_value_prop", "goal", "target_geography", "price",
            "currency", "existing_customer_profiles", "sales_channel", "launch_stage", "products")
    brief = {k: merchant_context.get(k) for k in keys if merchant_context.get(k)}
    dossier = str(merchant_context.get("dossier") or "")[:2000]
    if dossier:
        brief["documents_excerpt"] = dossier
    return json.dumps(brief, ensure_ascii=False, default=str)


def _resolve(ref: str, urls: dict[str, str]) -> tuple[str | None, bool] | None:
    """(source_url, from_merchant) for a valid ref; None for a ref we never supplied."""
    ref = (ref or "").strip().upper()
    if ref == "M":
        return None, True
    if ref in urls:
        return urls[ref], False
    return None


def _points(raw: list[_Point], urls: dict[str, str], limit: int = 6) -> list[SourcedPoint]:
    out = []
    for p in raw:
        hit = _resolve(p.ref, urls)
        if hit and p.text.strip():
            out.append(SourcedPoint(text=p.text.strip(), source_url=hit[0], from_merchant=hit[1]))
    return out[:limit]


def ground_response(resp: _Response, urls: dict[str, str]) -> tuple[MarketOverview, AudienceProfile, int]:
    """Keeps only points whose ref is a document we supplied or the merchant brief."""
    supplied = sum(
        len(x) for x in (
            resp.market.key_findings, resp.market.positioning_opportunities, resp.market.trends,
            resp.audience.pains, resp.audience.motivations, resp.audience.behaviors,
            resp.audience.triggers, resp.audience.barriers, resp.audience.channels,
        )
    )
    trends = []
    for t in resp.market.trends:
        hit = _resolve(t.ref, urls)
        if hit and t.text.strip():
            signal = t.signal if t.signal in ("rising", "falling", "new", "steady") else "rising"
            trends.append(MarketTrend(text=t.text.strip(), source_url=hit[0], from_merchant=hit[1], signal=signal))
    market = MarketOverview(
        summary=resp.market.summary.strip(),
        key_findings=_points(resp.market.key_findings, urls),
        positioning_opportunities=_points(resp.market.positioning_opportunities, urls),
        trends=trends[:6],
    )
    channels = []
    for c in resp.audience.channels:
        hit = _resolve(c.ref, urls)
        if hit and c.text.strip():
            channels.append(ReachChannel(text=c.text.strip(), reason=c.reason.strip(), source_url=hit[0], from_merchant=hit[1]))
    segments = []
    for g in resp.audience.segments:
        hit = _resolve(g.ref, urls)
        if hit and g.name.strip():
            # A size is kept only when it came from a document, never from the model's head.
            size = g.size_note if g.size_note and hit[0] else None
            segments.append(AudienceSegment(name=g.name.strip(), definition=g.definition, trigger=g.trigger,
                                            size_note=size, source_url=hit[0]))
    icp = None
    if resp.audience.icp and resp.audience.icp.name.strip():
        i = resp.audience.icp
        icp = IdealCustomerProfile(name=i.name.strip(), description=i.description, attributes=i.attributes,
                                   why=_points(i.why, urls), fit_signals=i.fit_signals[:6],
                                   low_fit_signals=i.low_fit_signals[:5])
    audience = AudienceProfile(
        icp=icp,
        segments=segments[:5],
        pains=_points(resp.audience.pains, urls),
        motivations=_points(resp.audience.motivations, urls),
        behaviors=_points(resp.audience.behaviors, urls),
        triggers=_points(resp.audience.triggers, urls),
        barriers=_points(resp.audience.barriers, urls),
        channels=channels[:6],
        preferred_message=resp.audience.preferred_message.strip(),
    )
    kept = sum(
        len(x) for x in (
            market.key_findings, market.positioning_opportunities, market.trends, audience.pains,
            audience.motivations, audience.behaviors, audience.triggers, audience.barriers, audience.channels,
        )
    )
    return market, audience, supplied - kept


async def analyze_market_and_audience(
    report: SWOTReportDelta,
    merchant_context: dict[str, Any],
    llm: Any,
    search_fn: SearchFn | None = None,
) -> tuple[SWOTReportDelta, list[str]]:
    if llm is None:
        return report, ["[MARKET_AUDIENCE] Skipped: needs a language model."]

    docs: list[tuple[str, str]] = []
    if search_fn is not None and (queries := build_market_queries(merchant_context)):
        try:
            for r in await search_fn(queries):
                if r.url and r.snippet:
                    docs.append((r.url, f"{r.title}\n{r.snippet}"[:DOC_CHARS]))
        except Exception as exc:
            logger.warning("Market searches failed: %s", exc)
    docs += _review_docs(report)
    seen: set[str] = set()
    unique = [(u, t) for u, t in docs if not (u in seen or seen.add(u))][:MAX_DOCS]
    if not unique and not merchant_context.get("primary_value_prop"):
        return report, ["[MARKET_AUDIENCE] Not enough material for a market or audience read."]

    urls = {f"D{i + 1}": u for i, (u, _) in enumerate(unique)}
    payload = {
        "merchant_brief": _merchant_brief(merchant_context),
        "documents": [{"id": f"D{i + 1}", "url": u, "text": t[:DOC_CHARS]} for i, (u, t) in enumerate(unique)],
    }
    try:
        resp = await llm.with_structured_output(_Response).ainvoke([
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ])
        if not isinstance(resp, _Response):
            resp = _Response.model_validate(resp)
    except Exception as exc:
        logger.warning("Market/audience analysis failed: %s", exc)
        return report, [f"[MARKET_AUDIENCE] Analysis failed ({type(exc).__name__}); report kept without it."]

    market, audience, dropped = ground_response(resp, urls)
    report.market_overview = market
    report.audience = audience
    note = f"[MARKET_AUDIENCE] Market and audience read from {len(unique)} document(s)"
    note += f"; dropped {dropped} unsourced point(s)." if dropped else "."
    return report, [note]
