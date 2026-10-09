"""
Tools the report chat can call.

`verify_claim` runs immediately: it re-fetches a competitor's own source pages and checks a
statement against them. Everything that changes the report or spends research credits is
only *proposed*: the tool validates it (a proposed edit is dry-run on a copy of the report)
and returns a confirmation card for the dashboard. Nothing changes until the merchant
confirms that card, which calls the normal endpoint.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from orchestrator.agents.market_research.analysis.grounding import find_support_excerpt
from orchestrator.schemas.api import EditableField, ReportEdit
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta
from orchestrator.services.report_edits import FIELD_WORDS, ReportEditError, apply_report_edits

logger = logging.getLogger(__name__)

_MAX_VERIFY_PAGES = 3


class verify_claim(BaseModel):  # noqa: N801 — the class name is the tool name the model sees
    """Re-check one statement about a competitor against that competitor's source pages,
    fetched again right now. Use when the merchant doubts a fact ("are you sure?", "is this
    still true?"). Takes a few seconds."""

    competitor: str = Field(..., description="Competitor name exactly as in the report")
    statement: str = Field(..., description="The fact to check, quoted as closely as possible from the report")


class propose_refresh(BaseModel):  # noqa: N801
    """Offer to re-run the whole research from scratch. Nothing runs until the merchant
    confirms the card. Use when they ask to refresh, update or redo the research."""

    reason: str = Field(default="", description="Why, in the merchant's words")


class propose_research_competitors(BaseModel):  # noqa: N801
    """Offer to research more competitors and add them to the report: the named companies,
    or with no names, the next best ones found. Nothing runs until the merchant confirms."""

    names: list[str] = Field(default_factory=list, max_length=5, description="Company names, or empty for the next best")


class lookup_competitor_intel(BaseModel):  # noqa: N801
    """Search the live web for verified intelligence about a competitor or product:
    customer ratings, review scores, price points, buyer praise/complaints, or technical specifications.
    Use this when a fact or metric is missing from the active report, or when the merchant asks for
    specific ratings/reviews/prices that need live web search. Takes a few seconds."""

    competitor: str = Field(..., description="Competitor or product name, e.g. 'AquaTru' or 'AquaTru Carafe'")
    query: str = Field(
        ...,
        description="Search query focused on the needed intelligence, e.g. 'AquaTru Carafe customer rating review score'",
    )


class propose_edit(BaseModel):  # noqa: N801
    """Offer to correct or update the report: remove an item (complaint, praise, claim, ad,
    evidence, milestone), set or clear a price, set a customer rating, or remove a competitor.
    Nothing changes until the merchant confirms the card."""

    op: Literal["remove_item", "set_price", "set_rating", "remove_competitor"]
    competitor: str = Field(..., description="Competitor name exactly as in the report")
    field: EditableField | None = Field(default=None, description="For remove_item: which list the item is in")
    value: str | None = Field(
        default=None,
        description="For remove_item: the item text. For set_price: the correct price. For set_rating: the rating out of 5 (e.g. '4.6').",
    )


class propose_update_merchant_context(BaseModel):  # noqa: N801
    """Offer to update the campaign goal or initial merchant parameters (Human-In-The-Loop):
    update the goal, product name, category, price, target audience, primary value prop, or description.
    Nothing changes until the merchant confirms the card."""

    field: str = Field(
        ...,
        description="The field to update, e.g. 'goal', 'product_name', 'category', 'price_usd', 'target_audience', 'primary_value_prop', 'description'",
    )
    value: str = Field(..., description="The new value for this field requested by the merchant")
    reasoning: str = Field(default="", description="Strategic reasoning for this change and how it affects the campaign")


CHAT_TOOLS = [
    lookup_competitor_intel,
    verify_claim,
    propose_refresh,
    propose_research_competitors,
    propose_edit,
    propose_update_merchant_context,
]



def _norm(name: str) -> str:
    return " ".join((name or "").lower().split())


class ChatToolbox:
    """Runs tool calls for one chat reply. `run` yields UI frames, then one {"result": ...} for the model."""

    def __init__(self, report: SWOTReportDelta) -> None:
        self.report = report
        self.frames_sent = False

    def _competitor(self, name: str) -> CompetitorProfile | None:
        return next((c for c in self.report.competitors if _norm(c.brand_name) == _norm(name)), None)

    def _unknown(self, name: str) -> dict[str, Any]:
        names = ", ".join(c.brand_name for c in self.report.competitors)
        return {"error": f"No competitor named '{name}' in this report. It has: {names}."}

    def _card(self, kind: str, title: str, detail: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.frames_sent = True
        return {"action": {"id": uuid.uuid4().hex, "kind": kind, "title": title, "detail": detail, "payload": payload}}

    async def run(self, name: str, args: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        try:
            if name == "lookup_competitor_intel":
                async for frame in self._lookup_intel(lookup_competitor_intel.model_validate(args)):
                    yield frame
                return
            if name == "verify_claim":
                async for frame in self._verify(verify_claim.model_validate(args)):
                    yield frame
                return
            if name == "propose_refresh":
                yield self._card(
                    "refresh",
                    "Re-run the research",
                    "Searches the web again and rebuilds this report. Takes a few minutes and uses search credits.",
                    {},
                )
                yield {"result": {"status": "awaiting_confirmation", "card": "Re-run the research"}}
                return
            if name == "propose_research_competitors":
                for frame in self._research(propose_research_competitors.model_validate(args)):
                    yield frame
                return
            if name == "propose_edit":
                for frame in self._edit(propose_edit.model_validate(args)):
                    yield frame
                return
            if name == "propose_update_merchant_context":
                for frame in self._update_context(propose_update_merchant_context.model_validate(args)):
                    yield frame
                return
            yield {"result": {"error": f"Unknown tool '{name}'."}}
        except ValidationError as exc:
            yield {"result": {"error": f"Invalid arguments: {exc.errors()[0].get('msg', 'invalid')}"}}

    def _update_context(self, call: propose_update_merchant_context) -> list[dict[str, Any]]:
        clean_field = call.field.replace("_", " ").title()
        title = f"Update Campaign {clean_field}"
        detail = f"Set {call.field.replace('_', ' ')} to \"{call.value}\"."
        if call.reasoning:
            detail += f" Reasoning: {call.reasoning}"
        card = self._card(
            "update_context",
            title,
            detail,
            {"field": call.field, "value": call.value, "reasoning": call.reasoning},
        )
        return [
            card,
            {"result": {"status": "awaiting_confirmation", "card": title, "field": call.field, "value": call.value}},
        ]

    def _research(self, call: propose_research_competitors) -> list[dict[str, Any]]:
        names = [n.strip() for n in dict.fromkeys(call.names) if n.strip()]
        already = [n for n in names if self._competitor(n)]
        names = [n for n in names if not self._competitor(n)]
        if already and not names:
            return [{"result": {"error": f"Already in the report: {', '.join(already)}."}}]
        title = f"Research {', '.join(names)}" if names else "Research the next rivals"
        card = self._card(
            "research",
            title,
            "Finds and profiles them like the others — website, prices, reviews and ads — then adds them to this report.",
            {"names": names},
        )
        return [card, {"result": {"status": "awaiting_confirmation", "card": title, "skipped_already_present": already}}]

    def _edit(self, call: propose_edit) -> list[dict[str, Any]]:
        edit = ReportEdit(op=call.op, competitor=call.competitor, field=call.field, value=call.value)
        try:
            # Dry run on a copy: a card is only offered for an edit that would succeed.
            _, applied = apply_report_edits(self.report.model_copy(deep=True), [edit])
        except ReportEditError as exc:
            return [{"result": {"error": str(exc)}}]
        title = {
            "remove_item": f"Remove a {FIELD_WORDS.get(call.field or '', 'item')} from {call.competitor}",
            "set_price": f"Correct {call.competitor}'s price",
            "set_rating": f"Set {call.competitor}'s rating",
            "remove_competitor": f"Remove {call.competitor} from the report",
        }[call.op]
        card = self._card("edit", title, applied[0], {"edits": [edit.model_dump()]})
        return [card, {"result": {"status": "awaiting_confirmation", "card": title, "change": applied[0]}}]

    async def _verify(self, call: verify_claim) -> AsyncIterator[dict[str, Any]]:
        comp = self._competitor(call.competitor)
        if comp is None:
            yield {"result": self._unknown(call.competitor)}
            return
        # Only URLs the research itself recorded: the model cannot point the crawler anywhere.
        urls = [u for u in comp.sources if u.startswith("https://")][:_MAX_VERIFY_PAGES]
        if not urls:
            yield {"result": {"verdict": "no_sources", "competitor": comp.brand_name}}
            return

        self.frames_sent = True
        yield {"status": f"Re-checking {comp.brand_name}'s sources ({len(urls)} page{'s' if len(urls) > 1 else ''})…"}
        from orchestrator.agents.market_research.discovery.crawler import extract_pages

        try:
            pages = await extract_pages(urls)
        except Exception as exc:
            logger.warning("Live source check failed for %s: %s", comp.brand_name, exc)
            pages = []

        verdict, url, passage = ("not_found" if pages else "unreachable"), None, None
        for page in pages:
            passage = find_support_excerpt(call.statement, [page.markdown])
            if passage:
                verdict, url = "confirmed", page.url
                break
        check = {
            "competitor": comp.brand_name,
            "statement": call.statement[:200],
            "verdict": verdict,
            "url": url,
            "pages_checked": len(pages),
        }
        yield {"check": check}
        yield {"result": {**check, "passage": (passage or "")[:400]}}

    async def _lookup_intel(self, call: lookup_competitor_intel) -> AsyncIterator[dict[str, Any]]:
        self.frames_sent = True
        yield {"status": f"Conducting deep live intelligence for {call.competitor}…"}
        from orchestrator.agents.market_research.discovery.search import SearchQuery, execute_tavily_search
        from orchestrator.agents.market_research.pipeline.loop import (
            _extract_price,
            _extract_rating,
            _extract_review_count,
            _is_complaint,
            _is_praise,
        )

        query_str = call.query.strip() if call.query else f"{call.competitor} customer reviews ratings"
        is_broad = any(w in query_str.lower() for w in ("all", "more", "data", "profile", "overview", "deep", "everything", "specs", "price", "research"))

        queries = [SearchQuery(vector="competitor_intel", query=query_str, search_depth="advanced")]
        if is_broad:
            queries.extend([
                SearchQuery(vector="intel_pricing", query=f"{call.competitor} price cost retail replacement filter", search_depth="advanced"),
                SearchQuery(vector="intel_complaints", query=f"{call.competitor} complaints problems negative issues reviews", search_depth="advanced"),
                SearchQuery(vector="intel_specs", query=f"{call.competitor} specifications technology certifications NSF", search_depth="advanced"),
            ])

        try:
            hits = await execute_tavily_search(queries)
        except Exception as exc:
            logger.warning("Live intel search failed for %s (%r): %s", call.competitor, query_str, exc)
            hits = []

        sources: list[dict[str, Any]] = []
        extracted_ratings: list[str] = []
        extracted_prices: list[str] = []
        customer_complaints: list[str] = []
        customer_praise: list[str] = []

        for h in hits:
            combined = f"{h.title} {h.snippet}"
            rating = _extract_rating(combined)
            count = _extract_review_count(combined)
            price = _extract_price(h.snippet)

            if rating and rating not in extracted_ratings:
                extracted_ratings.append(rating)
            if price and price not in extracted_prices:
                extracted_prices.append(price)
            if _is_complaint(h.snippet) and len(customer_complaints) < 5:
                complaint_text = h.snippet[:180].strip()
                if complaint_text not in customer_complaints:
                    customer_complaints.append(complaint_text)
            if _is_praise(h.snippet) and len(customer_praise) < 5:
                praise_text = h.snippet[:180].strip()
                if praise_text not in customer_praise:
                    customer_praise.append(praise_text)

            if len(sources) < 8:
                sources.append({
                    "title": h.title,
                    "url": h.url,
                    "snippet": h.snippet[:250],
                    "detected_rating": rating,
                    "detected_price": price,
                })

        yield {
            "result": {
                "competitor": call.competitor,
                "query": query_str,
                "results_found": len(hits),
                "extracted_ratings": extracted_ratings,
                "extracted_prices": extracted_prices,
                "customer_complaints": customer_complaints,
                "customer_praise": customer_praise,
                "top_sources": sources,
            }
        }
