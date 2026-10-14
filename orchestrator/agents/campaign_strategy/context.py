"""
Planning context: everything the earlier agents produced, in the shape the strategy planner reads.

  - Personas: the Audience/Persona Agent's `state["persona_profiles"]` when present; otherwise
    provisional personas derived from the research (review buyer personas, complaints, buying
    channels), marked `source="research_derived"`. `load_personas` is the only place that knows
    the persona agent's output shape — when that agent lands, adjust `_coerce_persona` and nothing
    downstream changes.
  - Market listings: where rivals sell, at what selling price, with which offers and terms.
  - Unknowns: the facts only the merchant can give that would change the plan.
"""

from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Any

from orchestrator.agents.campaign_strategy.money import fmt_money
from orchestrator.schemas.persona import PersonaInput

# ── Personas ────────────────────────────────────────────────────────────────────

_ALIASES = {
    "persona_id": ("persona_id", "id", "key", "slug"),
    "name": ("name", "title", "archetype", "label", "persona_name"),
    "description": ("description", "summary", "bio", "narrative"),
    "demographics": ("demographics", "demographic", "profile"),
    "pains": ("pains", "pain_points", "frustrations", "problems"),
    "motivations": ("motivations", "goals", "desires", "jobs_to_be_done", "jtbd"),
    "objections": ("objections", "barriers", "hesitations", "concerns"),
    "preferred_channels": ("preferred_channels", "channels", "media_habits", "where_they_shop"),
    "buying_triggers": ("buying_triggers", "triggers", "purchase_triggers"),
    "evidence": ("evidence", "sources", "source_urls", "citations"),
    "confidence": ("confidence", "confidence_score"),
}


def _get(raw: Any, key: str) -> Any:
    if isinstance(raw, dict):
        return raw.get(key)
    return getattr(raw, key, None)


def _coerce_persona(raw: Any, index: int) -> PersonaInput | None:
    """Maps one persona-agent record onto PersonaInput, whatever its field names."""
    if isinstance(raw, PersonaInput):
        return raw
    data: dict[str, Any] = {}
    for field, aliases in _ALIASES.items():
        for alias in aliases:
            value = _get(raw, alias)
            if value not in (None, "", [], {}):
                data[field] = value
                break
    if not data.get("name"):
        return None
    for field in ("pains", "motivations", "objections", "preferred_channels", "buying_triggers", "evidence"):
        value = data.get(field)
        if isinstance(value, str):
            data[field] = [value]
    if isinstance(data.get("demographics"), dict):
        data["demographics"] = {str(k): str(v) for k, v in data["demographics"].items()}
    else:
        data.pop("demographics", None)
    confidence = data.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
            data["confidence"] = confidence / 100 if confidence > 1 else confidence
        except (TypeError, ValueError):
            data.pop("confidence")
    data.setdefault("persona_id", f"persona_{index + 1}")
    data["persona_id"] = str(data["persona_id"])
    return PersonaInput(source="persona_agent", **data)


def derive_personas_from_research(swot_report: Any, merchant_context: dict[str, Any]) -> list[PersonaInput]:
    """
    Provisional personas from the research: the buyer types rivals' reviewers describe, with the
    complaints and unmet needs they voice, and where the category actually sells. Lower confidence
    than the persona agent's output, and labelled so.
    """
    competitors = getattr(swot_report, "competitors", None) or []
    persona_votes: Counter[str] = Counter()
    complaints: Counter[str] = Counter()
    needs: Counter[str] = Counter()
    triggers: Counter[str] = Counter()
    channels: Counter[str] = Counter()
    evidence: dict[str, list[str]] = {}

    for comp in competitors:
        ctx = getattr(comp, "review_context", None)
        if ctx:
            for p in ctx.buyer_personas or []:
                key = p.strip()
                if key:
                    persona_votes[key] += 1
                    evidence.setdefault(key, []).append(f"Reviews of {comp.brand_name}")
            for aspect in ctx.top_complaint_drivers or []:
                complaints[aspect.topic] += 1
            for need in ctx.unmet_customer_needs or []:
                needs[need] += 1
        bp = getattr(comp, "buying_patterns", None)
        if bp:
            channels.update(bp.sales_channels or [])
            triggers.update(bp.buying_triggers or [])
        for listing in getattr(comp, "channel_listings", None) or []:
            channels[listing.site] += 1

    common_objections = [c for c, _ in complaints.most_common(4)]
    common_channels = [c for c, _ in channels.most_common(4)]
    common_triggers = [t for t, _ in triggers.most_common(3)]
    personas: list[PersonaInput] = []
    for i, (name, votes) in enumerate(persona_votes.most_common(3)):
        personas.append(PersonaInput(
            persona_id=f"research_{i + 1}",
            name=name[:120],
            description=f"Buyer type described in reviews of {votes} rival(s).",
            pains=[n for n, _ in needs.most_common(3)],
            objections=common_objections,
            preferred_channels=common_channels,
            buying_triggers=common_triggers,
            evidence=evidence.get(name, [])[:5],
            source="research_derived",
            confidence=min(0.6, 0.2 + 0.1 * votes),
        ))

    # The market/audience step's ICP is the best-evidenced buyer we have: lead with it.
    audience = getattr(swot_report, "audience", None)
    if audience is not None and audience.icp is not None and audience.icp.name:
        personas.insert(0, PersonaInput(
            persona_id="research_icp",
            name=audience.icp.name[:120],
            description=audience.icp.description,
            demographics=dict(audience.icp.attributes),
            pains=[p.text for p in audience.pains][:4] or [n for n, _ in needs.most_common(3)],
            motivations=[p.text for p in audience.motivations][:4],
            objections=[p.text for p in audience.barriers][:4] or common_objections,
            preferred_channels=[c.text for c in audience.channels][:4] or common_channels,
            buying_triggers=[p.text for p in audience.triggers][:4] or common_triggers,
            evidence=[p.source_url for p in audience.icp.why if p.source_url][:5],
            source="research_derived",
            confidence=0.6,
        ))

    icp = str(merchant_context.get("target_audience") or merchant_context.get("merchant_icp") or "").strip()
    if icp:
        personas.insert(0, PersonaInput(
            persona_id="merchant_icp",
            name=icp[:120],
            description="Target audience as stated by the merchant.",
            objections=common_objections,
            preferred_channels=common_channels,
            buying_triggers=common_triggers,
            source="merchant_input",
            confidence=0.5,
        ))
    return personas


def load_personas(
    state: dict[str, Any], swot_report: Any, merchant_context: dict[str, Any]
) -> list[PersonaInput]:
    raw = state.get("persona_profiles") or []
    personas = [p for i, r in enumerate(raw) if (p := _coerce_persona(r, i)) is not None]
    if not personas:
        personas = derive_personas_from_research(swot_report, merchant_context)
    return rank_personas(personas, swot_report)


_SOURCE_WEIGHT = {"persona_agent": 0.3, "merchant_input": 0.25, "research_derived": 0.1}


def rank_personas(personas: list[PersonaInput], swot_report: Any = None) -> list[PersonaInput]:
    """
    Orders personas by fit for THIS campaign and marks one primary and one challenger: a small
    budget spread over five personas proves nothing. Fit = source trust + evidence + whether the
    persona's channels match where the category actually sells.
    """
    market_channels = {c.lower() for c in _market_channels(swot_report)}
    for p in personas:
        evidence = min(len(p.evidence), 5) / 5 * 0.25
        overlap = (
            len({c.lower() for c in p.preferred_channels} & market_channels) / max(len(p.preferred_channels), 1)
            if market_channels else 0.5
        ) * 0.2
        p.fit_score = round(min(1.0, _SOURCE_WEIGHT[p.source] + evidence + overlap + (p.confidence or 0.3) * 0.25), 2)
    ranked = sorted(personas, key=lambda p: p.fit_score or 0, reverse=True)
    for i, p in enumerate(ranked):
        p.role = "primary" if i == 0 else "challenger" if i == 1 else "later"
    return ranked


def _market_channels(swot_report: Any) -> list[str]:
    channels: list[str] = []
    for comp in getattr(swot_report, "competitors", None) or []:
        bp = getattr(comp, "buying_patterns", None)
        if bp:
            channels.extend(bp.sales_channels or [])
        channels.extend(l.site for l in getattr(comp, "channel_listings", None) or [])
    return channels


# ── Market listings ─────────────────────────────────────────────────────────────

def summarize_listings(swot_report: Any, merchant_context: dict[str, Any], currency: str) -> list[str]:
    """Plain findings a planner can act on: price position per site, offer norms, return terms."""
    listings = [l for comp in getattr(swot_report, "competitors", None) or [] for l in comp.channel_listings or []]
    listings = [l for l in listings if not l.currency or l.currency.upper() == currency]
    if not listings:
        return []
    lines: list[str] = []

    by_site: dict[str, list[float]] = {}
    for l in listings:
        if l.selling_price:
            by_site.setdefault(l.site, []).append(l.selling_price)
    own_price = merchant_price(merchant_context)
    for site, prices in sorted(by_site.items(), key=lambda kv: -len(kv[1])):
        mid = median(prices)
        line = (f"{site}: rivals sell at {fmt_money(min(prices), currency)}–{fmt_money(max(prices), currency)} "
                f"(median {fmt_money(mid, currency)}, {len(prices)} listing(s))")
        if own_price:
            gap = (own_price - mid) / mid * 100
            line += f"; your {fmt_money(own_price, currency)} is {abs(gap):.0f}% {'above' if gap > 0 else 'below'} the median"
        lines.append(line)

    discounts = [l.discount_pct for l in listings if l.discount_pct]
    if discounts:
        lines.append(f"Discounting: {len(discounts)}/{len(listings)} listings show a discount "
                     f"(median {median(discounts):.0f}% off MRP) — buyers here expect a markdown.")
    offers = Counter(o.lower()[:60] for l in listings for o in l.offers)
    if offers:
        lines.append("Common offers: " + "; ".join(o for o, _ in offers.most_common(3)))
    returns = [l.returns_policy for l in listings if l.returns_policy]
    if returns:
        lines.append(f"Return terms seen: {'; '.join(dict.fromkeys(r[:60] for r in returns[:3]))}")
    no_cod = [l.site for l in listings if l.cod_available is False]
    if no_cod:
        lines.append(f"No COD on: {', '.join(sorted(set(no_cod)))} — COD is an opening if you can offer it.")
    traction = [f"{l.competitor} on {l.site} ({l.velocity_signal or f'{l.review_count:,} reviews'})"
                for l in listings if l.velocity_signal or (l.review_count or 0) >= 100]
    if traction:
        lines.append("Visible traction: " + "; ".join(traction[:4]))
    return lines


def merchant_price(merchant_context: dict[str, Any]) -> float | None:
    for key in ("price", "price_usd"):
        value = merchant_context.get(key)
        if value not in (None, ""):
            try:
                return float(re.sub(r"[^\d.]", "", str(value)))
            except ValueError:
                continue
    return None


# ── Unknowns ────────────────────────────────────────────────────────────────────

def find_unknowns(merchant_context: dict[str, Any], personas: list[PersonaInput]) -> list[str]:
    unknowns = []
    if merchant_price(merchant_context) is None:
        unknowns.append("Selling price per unit — needed to compare against rival listings.")
    if merchant_context.get("unit_cost") in (None, ""):
        unknowns.append("Unit cost (product + fulfilment) — needed for break-even and a real CAC ceiling.")
    if not merchant_context.get("launch_stage"):
        unknowns.append("Launch stage (pre-launch / few sales / regular orders) — decides validate vs scale.")
    if not merchant_context.get("sales_channel"):
        unknowns.append("Where customers will buy (own site, Instagram/WhatsApp, marketplace, offline).")
    if merchant_context.get("stock_ready") is None:
        unknowns.append("Whether stock and sizes are ready — ads before stock waste the budget.")
    if not any(p.source == "persona_agent" for p in personas):
        unknowns.append("Persona agent output — personas here are provisional, derived from research.")
    return unknowns


# ── Plan → brief ────────────────────────────────────────────────────────────────

_LEGACY_SPEND_TYPE = {"ad_spend": "ad_spend", "creator": "ad_spend", "content": "asset_production",
                      "tools": "data_tooling", "research": "data_tooling", "organic": "asset_production"}


def apply_plan_to_brief(brief: Any, plan: Any, mode: str, economics: Any, mode_reason: str, budget: float) -> None:
    """
    Attaches the grounded plan and mirrors it into the fields the dashboard already renders
    (channel matrix, calendar, assumptions, executive summary), so the UI shows the plan, not the
    old template, without a UI change.
    """
    from orchestrator.schemas.strategy import (
        CampaignStrategyOption,
        ChannelAllocation,
        PhaseMilestone,
        StrategicAngle,
        StrategyPrediction,
        TacticalOutreachBlueprint,
    )

    ccy = brief.currency
    brief.mode = mode
    brief.plan = plan
    brief.economics = economics
    personas = {p.persona_id: p.name for p in brief.personas_used}

    brief.channel_matrix = [
        ChannelAllocation(
            channel=c.channel,
            budget_percentage=round(c.budget / budget * 100) if budget else 0,
            recommended_spend_usd=c.budget,
            rationale=f"{c.purpose} (for: {personas.get(c.persona_id, c.persona_id)})",
            promotion_tactics=c.tactics,
            spend_type=_LEGACY_SPEND_TYPE.get(c.spend_type, "ad_spend"),
        )
        for c in plan.channels
    ]
    brief.suggested_channels = [c.channel for c in plan.channels]
    brief.execution_calendar = [
        PhaseMilestone(
            phase_name=p.name, weeks=p.days,
            focus=f"{p.objective} (ceiling {fmt_money(p.budget_ceiling, ccy)})",
            deliverables=[*p.actions, f"Gate: {p.decision_gate}"],
        )
        for p in plan.phases
    ]
    if plan.message_tests:
        brief.strategic_angles = [
            StrategicAngle(
                angle_title=f"[{t.role}] {t.angle}",
                target_wedge=personas.get(t.persona_id, t.persona_id),
                competitor_weakness="; ".join(t.evidence) or "—",
                hook=t.hook,
                messaging_pillar=f"{t.cta}. Proof needed: {t.proof_needed}" if t.proof_needed else t.cta,
            )
            for t in plan.message_tests
        ] + list(brief.strategic_angles)
    assumptions = [f"Mode: {mode} — {mode_reason}",
                   f"Reserve of {fmt_money(plan.reserve, ccy)} is held until a test earns it."]
    if economics.orders_to_break_even:
        assumptions.append(
            f"Break-even: {economics.orders_to_break_even} orders at {fmt_money(economics.contribution_per_unit, ccy)} "
            f"contribution each; cost per order above {fmt_money(economics.max_affordable_cac, ccy)} loses money."
        )
    elif economics.note:
        assumptions.append(economics.note)
    brief.budget_assumptions = assumptions + list(brief.budget_assumptions)
    brief.executive_summary = f"{brief.campaign_days}-day {mode} plan. {plan.rationale}"

    persona_by_id = {p.persona_id: p for p in brief.personas_used}
    brief.outreach_blueprint = [
        TacticalOutreachBlueprint(
            playbook_id=f"play_{i + 1}",
            channel_name=c.channel,
            who_target_profile=_who(persona_by_id.get(c.persona_id), c.persona_id),
            where_platform=c.channel,
            how_mechanism="; ".join(c.tactics) or c.purpose,
            budget_allocation_usd=c.budget,
            budget_share_pct=round(c.budget / budget * 100) if budget else 0,
            duration_and_cadence=f"{brief.campaign_days}-day campaign; spend released phase by phase against its gate",
            expected_cpa="Set from the first test flight's cost per result",
            assigned_subagent="Campaign execution subagent",
        )
        for i, c in enumerate(plan.channels)
    ]
    # The grounded plan leads the comparison and is selected; template options stay as alternatives.
    grounded = CampaignStrategyOption(
        option_id="opt_grounded",
        title=f"Recommended: {mode.title()} plan for {personas.get(plan.primary_persona_id, 'the primary persona')}",
        theme=f"{mode.title()} — persona-led, evidence-backed",
        tagline=plan.rationale[:200],
        recommended=True,
        budget_allocation_summary=" • ".join(
            f"{fmt_money(c.budget, ccy)} {c.channel}" for c in plan.channels if c.budget
        ) + f" • {fmt_money(plan.reserve, ccy)} reserve",
        channel_matrix=brief.channel_matrix,
        advantages=[f"Answers: {r.reason}" for r in plan.readiness[:3]] or ["Built from research and personas"],
        disadvantages=["Small tests give directional signals, not statistical certainty."],
        constraints=[f"Unknown: {u}" for u in brief.unknowns[:3]] or ["Phase ceilings, not targets"],
        opportunities=brief.market_listings[:3] or [t.angle for t in plan.message_tests],
        suggested_channels=brief.suggested_channels,
        promotion_means=[t.hook for t in plan.message_tests],
        prediction=StrategyPrediction(risk_level="Medium" if mode == "validate" else "Low"),
    )
    for opt in brief.campaign_options:
        opt.recommended = False
    brief.campaign_options = [grounded, *[o for o in brief.campaign_options if o.option_id != "opt_grounded"]]
    brief.selected_option_id = "opt_grounded"


def _who(persona: Any, fallback: str) -> str:
    if persona is None:
        return fallback
    parts = [persona.name]
    if persona.pains:
        parts.append(f"pains: {', '.join(persona.pains[:2])}")
    if persona.objections:
        parts.append(f"objections: {', '.join(persona.objections[:2])}")
    return "; ".join(parts)
    if plan.questions_for_merchant:
        brief.unknowns = list(dict.fromkeys([*brief.unknowns, *plan.questions_for_merchant]))
