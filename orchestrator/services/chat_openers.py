"""
What the agent says first when the merchant arrives on a step, and the questions it suggests.

Composed from the campaign's own data with no model call, so it is instant, free and cannot
invent anything: each line is a figure or finding the step already holds. Lines with nothing
behind them are left out; a step with no data says what it is waiting for.
"""

from __future__ import annotations

from statistics import median
from typing import Any

_SYMBOL = {"INR": "₹", "USD": "$", "GBP": "£", "EUR": "€"}


def _money(v: float, ccy: str | None) -> str:
    return f"{_SYMBOL.get(ccy or '', (ccy + ' ') if ccy else '')}{v:,.0f}"


def _research(job: Any) -> tuple[list[str], list[str]]:
    r = job.last_swot_report
    lines: list[str] = []
    if r is None:
        return ["The research is still running; I'll summarise it here when it's done."], []
    if r.demand and r.demand.mood:
        lines.append(r.demand.mood)
    # Typical price per rival, in the merchant's currency where a rate was applied.
    typical: list[tuple[str, float, str | None]] = []
    for c in r.competitors:
        prices, ccy = [], None
        for l in c.channel_listings:
            if l.selling_price is None:
                continue
            if l.price_in_merchant_currency is not None:
                prices.append(l.price_in_merchant_currency)
                ccy = l.merchant_currency
            elif not l.merchant_currency:
                prices.append(l.selling_price)
                ccy = ccy or l.currency
        if prices:
            typical.append((c.brand_name, median(prices), ccy))
    if len(typical) >= 2:
        lo, hi = min(typical, key=lambda t: t[1]), max(typical, key=lambda t: t[1])
        lines.append(f"Cheapest typical price: **{lo[0]}** at {_money(lo[1], lo[2])}; dearest: **{hi[0]}** at {_money(hi[1], hi[2])}.")
    if r.market_overview and r.market_overview.positioning_opportunities:
        lines.append(f"Opening worth a look: {r.market_overview.positioning_opportunities[0].text}")
    unknown = sum(1 for c in r.competitors for s in c.fact_status.values() if s.status == "not_stated")
    if unknown:
        lines.append(f"{unknown} competitor fact(s) aren't published anywhere we looked; ask me to search again for any of them.")
    names = [c.brand_name for c in r.competitors[:2]]
    suggestions = ["Who is cheapest for my products?", "What's trending in my category right now?"]
    if names:
        suggestions.append(f"What do {names[0]}'s customers complain about?")
    suggestions.append("Which competitor is the biggest threat and why?")
    return lines, suggestions


def _strategy(job: Any) -> tuple[list[str], list[str]]:
    b = job.strategy_brief
    if b is None:
        return ["The strategy is being built from the research; it appears here when ready."], []
    lines: list[str] = []
    if b.messaging and b.messaging.core_message:
        lines.append(f"Core message: **“{b.messaging.core_message}”**")
        need = [p.title for p in b.messaging.pillars if p.needs_proof]
        if need:
            lines.append(f"Pillar(s) that need proof from you: {', '.join(need)}.")
    primary = next((p for p in b.personas_used if p.role == "primary"), None)
    if primary:
        lines.append(f"Primary persona: **{primary.name}**.")
    for u in (b.unknowns or [])[:2]:
        lines.append(u)
    if b.approval_status == "PENDING_APPROVAL":
        lines.append("Nothing is written until you approve the strategy.")
    return lines, ["Why this primary persona?", "Make the campaign 30 days", "What should I prove before running ads?",
                   "What changes if I double the budget?"]


def _content(job: Any) -> tuple[list[str], list[str]]:
    pack = job.content_pack
    if pack is None:
        return ["Content is written after the strategy is approved."], []
    if not pack.assets:
        return [" ".join(pack.notes) or "No content was written."], ["Write the content again"]
    flagged = [a for a in pack.assets if a.qa_issues]
    holes = sum(1 for a in pack.assets for q in a.qa_issues if q.startswith("Fill in"))
    channels = sorted({a.channel for a in pack.assets})
    lines = [f"{len(pack.assets)} assets across {len(channels)} channel(s); "
             f"{len(pack.approved_channels)} channel(s) approved."]
    if flagged:
        lines.append(f"{len(flagged)} asset(s) have QA notes" + (f", {holes} with [placeholders] for you to fill." if holes else "."))
    first = channels[0].replace("_", " ") if channels else "email"
    return lines, ["Fix the issues on the flagged assets", f"Make the {first} copy shorter", f"Approve {first}"]


def _schedule(job: Any) -> tuple[list[str], list[str]]:
    pack = job.content_pack
    planned = sorted(a.scheduled_for for a in (pack.assets if pack else []) if a.scheduled_for)
    if not planned:
        return ["Nothing is planned yet; approve content first."], []
    return ([f"{len(planned)} asset(s) planned, starting {planned[0][:10]}.",
             "No channel account is connected, so nothing will publish yet."],
            ["Move everything a week later", "Send the emails at 8am"])


def _live(job: Any) -> tuple[list[str], list[str]]:
    pack = job.content_pack
    live = [a for a in (pack.assets if pack else []) if a.status == "published"]
    if not live:
        return ["Nothing has been published yet, so there are no results to read."], []
    return [f"{len(live)} asset(s) are live."], ["How is each channel doing?"]


_STEPS = {"research": _research, "strategy": _strategy, "content": _content, "schedule": _schedule, "live": _live}


def opening(job: Any, step: str) -> dict[str, Any]:
    lines, suggestions = _STEPS.get(step, _research)(job)
    return {"step": step, "message": "\n".join(f"- {l}" if len(lines) > 1 else l for l in lines), "suggestions": suggestions}
