"""
Campaign planner: turns the planning context (personas, research, listings, merchant facts) into a
CampaignPlan, then checks it.

  1. decide_mode     — validate / traction / scale, by rule, before any planning. The LLM is told
                       the mode and cannot change it.
  2. compute_economics — break-even and the most an order can cost, from the merchant's numbers.
  3. plan            — one structured LLM call (main model) when a key is available; otherwise,
                       or when the LLM's plan still fails validation after one repair, the
                       rules plan built from the same context.
  4. validate_plan   — Python owns the arithmetic and the evidence rules: spend within budget,
                       reserve kept in validate mode, every channel and message tied to a real
                       persona with evidence, no projected ROI/ROAS, channels that fit the business.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from orchestrator.agents.campaign_strategy.money import fmt_money
from orchestrator.schemas.persona import PersonaInput
from orchestrator.schemas.strategy import (
    CampaignPlan,
    MessageTest,
    PlanChannel,
    PlanMode,
    PlanPhase,
    ReadinessItem,
    UnitEconomics,
)

logger = logging.getLogger(__name__)

# Payment fees + expected returns when the merchant has not given their own figure.
DEFAULT_VARIABLE_COST_PCT = 0.12
RESERVE_SHARE = {"validate": 0.10, "traction": 0.10, "scale": 0.05}


@dataclass
class PlanningInputs:
    merchant_context: dict[str, Any]
    budget: float
    currency: str
    campaign_days: int
    personas: list[PersonaInput]
    market_listings: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    swot_report: Any = None
    is_b2b: bool = False

    @property
    def persona_ids(self) -> set[str]:
        return {p.persona_id for p in self.personas}

    def persona(self, role: str) -> PersonaInput | None:
        return next((p for p in self.personas if p.role == role), None)


def is_b2b_business(merchant_context: dict[str, Any]) -> bool:
    text = " ".join(str(merchant_context.get(k) or "") for k in ("business_model", "category", "campaign_type")).lower()
    return any(k in text for k in ("b2b", "saas", "enterprise", "agency", "consult", "lead_gen", "professional_services"))


# ── 1. Mode ─────────────────────────────────────────────────────────────────────

def decide_mode(merchant_context: dict[str, Any], budget: float, price: float | None) -> tuple[PlanMode, str]:
    stage = str(merchant_context.get("launch_stage") or "").lower()
    has_sales = bool(merchant_context.get("product_sales") or merchant_context.get("sales_data"))
    if price and budget < 3 * price:
        return "validate", f"Budget covers fewer than 3 units of the product's price; it can test demand, not buy scale."
    if stage == "regular_orders" and merchant_context.get("unit_cost") not in (None, ""):
        return "scale", "Regular orders and known unit cost: spend can follow proven economics."
    if stage == "regular_orders" or (stage == "launched_few_sales") or has_sales:
        return "traction", "Some sales exist: find the message and channel that repeat them before scaling."
    return "validate", "No proven sales yet: prove who buys and why before spending for reach."


# ── 2. Economics ────────────────────────────────────────────────────────────────

def compute_economics(merchant_context: dict[str, Any], budget: float, price: float | None) -> UnitEconomics:
    unit_cost = _float(merchant_context.get("unit_cost"))
    var_pct = _float(merchant_context.get("variable_cost_pct"))
    var_pct = var_pct / 100 if var_pct and var_pct > 1 else (var_pct if var_pct is not None else DEFAULT_VARIABLE_COST_PCT)
    if price is None or unit_cost is None:
        return UnitEconomics(
            price=price, unit_cost=unit_cost, variable_cost_pct=var_pct,
            note="Give the unit cost (product + fulfilment) to see break-even and the most an order may cost.",
        )
    contribution = price - unit_cost - price * var_pct
    if contribution <= 0:
        return UnitEconomics(
            price=price, unit_cost=unit_cost, variable_cost_pct=var_pct, contribution_per_unit=round(contribution, 2),
            note="Each order loses money before marketing; fix price or cost before buying traffic.",
        )
    orders = int(-(-budget // contribution))  # ceil
    return UnitEconomics(
        price=price, unit_cost=unit_cost, variable_cost_pct=var_pct,
        contribution_per_unit=round(contribution, 2), orders_to_break_even=orders,
        max_affordable_cac=round(contribution, 2),
        note=f"Includes {var_pct:.0%} of price for payment fees and returns; excludes fixed overhead and salaries.",
    )


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(re.sub(r"[^\d.]", "", str(value)))
    except ValueError:
        return None


# ── 3a. Rules plan (no LLM, or LLM failed) ─────────────────────────────────────

_SPLITS: dict[str, list[tuple[str, float]]] = {
    "validate": [("content", 0.25), ("research", 0.10), ("ad_spend", 0.40), ("creator", 0.15)],
    "traction": [("content", 0.15), ("ad_spend", 0.55), ("creator", 0.15), ("retarget", 0.05)],
    "scale": [("content", 0.10), ("ad_spend", 0.60), ("creator", 0.10), ("retarget", 0.15)],
}

_CHANNELS_D2C = {
    "organic": ("Instagram Reels + WhatsApp Business (organic)", ["3 Reels a week with real product footage",
                "WhatsApp catalog, quick replies and labels for enquiries"]),
    "content": ("Product photography & short-form video assets", ["Close-ups of material, construction, fit",
                "One styled-outfit video per message test"]),
    "research": ("Customer interviews & fit trials", ["10-15 interviews with the primary persona",
                 "Wear trials to substantiate comfort/fit claims"]),
    "ad_spend": ("Meta (Instagram/Facebook) ads — message test", ["Champion vs challenger creative, same audience",
                 "One or two metros first, not nationwide"]),
    "creator": ("Nano-creator collaborations (barter / revenue share)", ["Approach 10-15 creators the persona follows",
                "Honest product content; product cost counts as spend"]),
    "retarget": ("Retargeting engaged visitors", ["Show proof (reviews, fit guide) to people who engaged"]),
}
_CHANNELS_B2B = {
    "organic": ("LinkedIn founder posts + direct outreach (organic)", ["Weekly point-of-view posts",
                "Personal outreach to 20 target accounts a week"]),
    "content": ("Proof assets: case study, comparison page", ["One comparison page against the rival buyers leave",
                "One case study with real numbers"]),
    "research": ("Customer discovery calls", ["10 calls with the primary persona to confirm pains and objections"]),
    "ad_spend": ("Search / LinkedIn ads — message test", ["Champion vs challenger message, same audience",
                 "High-intent queries only"]),
    "creator": ("Partner & community placements", ["Niche newsletters or communities the persona reads"]),
    "retarget": ("Retargeting engaged visitors", ["Proof-led follow-up to visitors who engaged"]),
}


def rules_plan(inputs: PlanningInputs, mode: PlanMode, economics: UnitEconomics) -> CampaignPlan:
    primary = inputs.persona("primary")
    challenger = inputs.persona("challenger")
    pid = primary.persona_id if primary else "audience"
    budget = inputs.budget
    reserve = round(budget * RESERVE_SHARE[mode], 2)
    catalog = _CHANNELS_B2B if inputs.is_b2b else _CHANNELS_D2C
    listing_evidence = inputs.market_listings[:2]
    persona_channels = [f"{primary.name} discovers/buys via: {', '.join(primary.preferred_channels[:3])}"] \
        if primary and primary.preferred_channels else []

    channels = [PlanChannel(
        channel=catalog["organic"][0], persona_id=pid, budget=0, spend_type="organic",
        purpose="Build a credible presence and an enquiry-to-order path before paid traffic arrives.",
        tactics=catalog["organic"][1], evidence=persona_channels or ["Lowest-cost way to collect objections and intent"],
    )]
    for kind, share in _SPLITS[mode]:
        name, tactics = catalog[kind]
        channels.append(PlanChannel(
            channel=name,
            persona_id=challenger.persona_id if kind == "creator" and challenger else pid,
            budget=round(budget * share, 2),
            spend_type="ad_spend" if kind == "retarget" else kind,  # type: ignore[arg-type]
            purpose=_PURPOSE[kind],
            tactics=tactics,
            evidence=(listing_evidence if kind in ("ad_spend", "retarget") else []) + persona_channels
            or [f"Mode '{mode}': {_PURPOSE[kind].lower()}"],
        ))

    tests = _message_tests(inputs, primary, challenger)
    phases = _phases(inputs, mode, channels, reserve)
    readiness = _readiness(inputs, mode)
    metrics = ["Qualified enquiries (fit the persona, asked about size/price/delivery)",
               "Add-to-cart / checkout starts", "Orders and cost per order"]
    if economics.max_affordable_cac:
        metrics.append(f"Cost per order vs ceiling of {fmt_money(economics.max_affordable_cac, inputs.currency)} "
                       f"(contribution per unit)")
    return CampaignPlan(
        primary_persona_id=pid,
        challenger_persona_id=challenger.persona_id if challenger else None,
        rationale=(f"{mode.title()} plan: {_MODE_WHY[mode]} Primary persona: "
                   f"{primary.name if primary else 'the stated audience'}"
                   + (f"; challenger: {challenger.name}." if challenger else ".")),
        channels=channels, reserve=reserve, message_tests=tests, phases=phases, readiness=readiness,
        success_metrics=metrics, questions_for_merchant=inputs.unknowns[:5], generated_by="rules",
    )


_PURPOSE = {
    "content": "Produce the creative the message tests need, from real product footage.",
    "research": "Confirm the persona's pains and objections before scaling any claim.",
    "ad_spend": "Run champion vs challenger messages to find which one produces buying intent.",
    "creator": "Borrow trust from voices the persona already follows.",
    "retarget": "Convert people who engaged but did not buy, with proof.",
}
_MODE_WHY = {
    "validate": "the budget buys learning, not scale, so it proves who buys and why first and keeps a reserve.",
    "traction": "sales exist, so it isolates the message and channel that repeat them.",
    "scale": "economics are known, so spend follows the winning channel within the affordable cost per order.",
}


def _message_tests(inputs: PlanningInputs, primary: PersonaInput | None, challenger: PersonaInput | None) -> list[MessageTest]:
    angles = list(getattr(inputs.swot_report, "suggested_ad_angles", None) or [])
    objections = (primary.objections if primary else []) or []
    value_prop = str(inputs.merchant_context.get("primary_value_prop") or "").strip()
    product = str(inputs.merchant_context.get("product_name") or "the product")
    tests: list[MessageTest] = []
    pid = primary.persona_id if primary else "audience"
    if angles:
        a = angles[0]
        tests.append(MessageTest(
            test_id="t1", persona_id=pid, angle=a.based_on_weakness or a.hook, hook=a.hook,
            cta=f"Explore {product}", role="champion",
            proof_needed="Product evidence for the claim (specs, wear test, reviews).",
            evidence=[f"Rival gap: {a.based_on_weakness}" if a.based_on_weakness else f"Research ad angle vs {a.target_rival}"],
        ))
    elif objections:
        tests.append(MessageTest(
            test_id="t1", persona_id=pid, angle=f"Answer: {objections[0]}",
            hook=f"{objections[0].capitalize()}? Not with {product}.", cta=f"Explore {product}", role="champion",
            proof_needed=f"Evidence that {product} solves '{objections[0]}'.",
            evidence=[f"Recurring rival complaint: {objections[0]}"],
        ))
    second = angles[1] if len(angles) > 1 else None
    target = challenger or primary
    if second:
        tests.append(MessageTest(
            test_id="t2", persona_id=target.persona_id if target else pid, angle=second.based_on_weakness or second.hook,
            hook=second.hook, cta=f"Discover {product}", role="challenger",
            proof_needed="Product evidence for the claim.",
            evidence=[f"Rival gap: {second.based_on_weakness}" if second.based_on_weakness else "Research ad angle"],
        ))
    elif value_prop:
        tests.append(MessageTest(
            test_id="t2", persona_id=target.persona_id if target else pid, angle="Core value proposition",
            hook=value_prop[:90], cta=f"Discover {product}", role="challenger",
            proof_needed="Documented specs or process behind the claim.", evidence=["Merchant's stated value proposition"],
        ))
    return tests


def _phases(inputs: PlanningInputs, mode: PlanMode, channels: list[PlanChannel], reserve: float) -> list[PlanPhase]:
    d = inputs.campaign_days
    a, b = max(1, d // 3), max(2, (2 * d) // 3)
    spend: dict[str, float] = {}
    for c in channels:
        spend[c.spend_type] = spend.get(c.spend_type, 0) + c.budget
    p1 = spend.get("content", 0) + spend.get("research", 0)
    p2 = round(spend.get("ad_spend", 0) * 0.6 + spend.get("creator", 0), 2)
    p3 = round(inputs.budget - reserve - p1 - p2, 2)
    m = lambda x: fmt_money(x, inputs.currency)  # noqa: E731
    return [
        PlanPhase(
            name="Phase 1: Readiness & persona validation", days=f"Days 1-{a}", budget_ceiling=round(p1, 2),
            objective="Confirm the primary persona's objections and make the buying path credible.",
            actions=["Clear the blocking readiness items", "Interview/trial with the primary persona",
                     "Publish organic content; collect enquiries and objections"],
            decision_gate="Go to paid tests only when blocking readiness items are done and enquiries show the "
                          "persona's interest; otherwise fix the offer or persona first.",
        ),
        PlanPhase(
            name="Phase 2: Message tests", days=f"Days {a + 1}-{b}", budget_ceiling=p2,
            objective="Find which message produces qualified enquiries and orders, not just views.",
            actions=["Run champion vs challenger with the same audience, budget and landing page",
                     "Start creator outreach for the persona", "Log enquiries, carts, orders, cost per order"],
            decision_gate="Keep the message with more qualified enquiries/orders per spend; stop the loser. "
                          "If neither produces intent, pause spend and revisit price/proof.",
        ),
        PlanPhase(
            name="Phase 3: Double down & convert", days=f"Days {b + 1}-{d}", budget_ceiling=max(p3, 0),
            objective="Put remaining spend behind the winner and convert warm prospects.",
            actions=["Shift spend to the winning message/channel", "Follow up every unconverted enquiry",
                     "Collect reviews and customer content", f"Release the {m(reserve)} reserve only if cost per "
                     "order is within the affordable ceiling"],
            decision_gate="End-of-campaign review: cost per order vs contribution decides next quarter's budget.",
        ),
    ]


_READINESS_RULES = [
    (r"siz|fit|width", "Publish a size & fit guide and a no-hassle size exchange",
     "Buyers in this category complain about {o}."),
    (r"break.?in|stiff|comfort|blister|pain", "Substantiate comfort claims with a wear test before advertising them",
     "Rivals are criticised for {o}; an unproven comfort claim repeats their mistake."),
    (r"price|expens|unknown|trust|brand|fake|quality", "Show trust signals: real photos, materials, reviews, contact and returns",
     "The persona hesitates over {o}."),
    (r"deliver|ship|late", "State delivery times and tracking up front", "Rivals draw complaints about {o}."),
    (r"return|refund|exchange", "Offer and state a clear return/exchange policy", "Rivals draw complaints about {o}."),
]


def _readiness(inputs: PlanningInputs, mode: PlanMode) -> list[ReadinessItem]:
    items: list[ReadinessItem] = []
    seen: set[str] = set()
    objections = [o for p in inputs.personas if p.role in ("primary", "challenger") for o in p.objections]
    for o in objections:
        for pattern, item, why in _READINESS_RULES:
            if item not in seen and re.search(pattern, o, re.I):
                seen.add(item)
                items.append(ReadinessItem(item=item, reason=why.format(o=o), blocking=mode == "validate"))
    for line in inputs.market_listings:
        if line.startswith("No COD on"):
            items.append(ReadinessItem(item="Decide on cash-on-delivery", reason=line))
        if line.startswith("Discounting:"):
            items.append(ReadinessItem(item="Decide your discount policy before launch ads", reason=line))
    if inputs.merchant_context.get("stock_ready") is False:
        items.insert(0, ReadinessItem(item="Stock and sizes ready to ship", reason="Ads before stock waste the budget.",
                                      blocking=True))
    return items


# ── 3b. LLM plan ────────────────────────────────────────────────────────────────

PLANNER_SYSTEM = """You are a senior performance-marketing strategist planning one campaign.
Use ONLY the context given: personas, research findings, marketplace listings, merchant facts.
Rules:
- The mode is fixed. 'validate' = prove who buys and why on a small budget, keep the reserve, favour
  organic + small paid tests; 'traction' = find the repeatable message/channel; 'scale' = spend behind
  proven economics.
- Every channel and message test names a persona_id from the context and cites evidence (a listing
  finding, a rival complaint, a persona channel or objection). No evidence, no channel.
- Choose channels where this persona and this category actually buy (listings, buying patterns).
  Do not use LinkedIn/outbound for consumer products, or Instagram creators for enterprise software,
  unless the evidence says so.
- Amounts are in the given currency. Channel budgets + reserve must not exceed the budget. Phase
  budgets are ceilings.
- Never project ROI, ROAS, CAC or revenue. Success metrics are things to measure.
- Message tests: one champion and one challenger, each with hook, CTA and the proof the merchant must show.
- Readiness items turn persona objections and rival complaints into things to fix before spending.
- Questions for the merchant: only facts missing from the context that would change the plan."""


async def llm_plan(llm: Any, inputs: PlanningInputs, mode: PlanMode, economics: UnitEconomics,
                   issues: list[str] | None = None, draft: CampaignPlan | None = None) -> CampaignPlan:
    payload: dict[str, Any] = {
        "merchant": {k: inputs.merchant_context.get(k) for k in (
            "product_name", "category", "primary_value_prop", "goal", "price", "target_geography",
            "target_audience", "launch_stage", "sales_channel", "stock_ready", "business_model")},
        "mode": mode, "budget": inputs.budget, "currency": inputs.currency, "campaign_days": inputs.campaign_days,
        "required_reserve_min": round(inputs.budget * RESERVE_SHARE[mode], 2),
        "economics": economics.model_dump(),
        "personas": [p.model_dump(exclude={"demographics"}) for p in inputs.personas[:5]],
        "marketplace_listings": inputs.market_listings,
        "research": _research_digest(inputs.swot_report),
        "unknowns": inputs.unknowns,
    }
    if issues and draft:
        payload["previous_plan"] = draft.model_dump()
        payload["fix_these_issues"] = issues
    structured = llm.with_structured_output(CampaignPlan)
    result = await structured.ainvoke([
        {"role": "system", "content": PLANNER_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)[:60000]},
    ])
    plan = result if isinstance(result, CampaignPlan) else CampaignPlan.model_validate(result)
    plan.generated_by = "llm"
    return plan


def _research_digest(swot_report: Any) -> dict[str, Any]:
    comps = getattr(swot_report, "competitors", None) or []
    digest = []
    for c in comps[:8]:
        rc = getattr(c, "review_context", None)
        bp = getattr(c, "buying_patterns", None)
        digest.append({
            "rival": c.brand_name, "product": c.product_name, "pricing": c.pricing_model,
            "complaints": [a.topic for a in (rc.top_complaint_drivers if rc else [])][:4] or c.weaknesses_mined[:4],
            "praise": [a.topic for a in (rc.top_praise_drivers if rc else [])][:3],
            "unmet_needs": (rc.unmet_customer_needs if rc else [])[:3],
            "sales_channels": (bp.sales_channels if bp else [])[:5],
            "offers": (bp.promotional_incentives if bp else [])[:4],
            "claims": c.core_claims[:3],
        })
    angles = [{"hook": a.hook, "weakness": a.based_on_weakness, "rival": a.target_rival}
              for a in (getattr(swot_report, "suggested_ad_angles", None) or [])[:5]]
    return {"competitors": digest, "suggested_ad_angles": angles}


# ── 4. Validator ────────────────────────────────────────────────────────────────

_PROJECTION = re.compile(r"\b\d+(?:\.\d+)?\s*x\s*(?:roas|roi|return)|\broi of\b|\broas of\b", re.I)
_B2B_ONLY = re.compile(r"linkedin|inmail|cold email|outbound|apollo|clay", re.I)


def validate_plan(plan: CampaignPlan, inputs: PlanningInputs, mode: PlanMode) -> tuple[CampaignPlan, list[str]]:
    """Fixes what arithmetic can fix; returns the issues only a re-plan can fix."""
    notes: list[str] = []
    issues: list[str] = []
    ids = inputs.persona_ids
    primary = inputs.persona("primary")
    fallback_id = primary.persona_id if primary else plan.primary_persona_id

    if ids and plan.primary_persona_id not in ids:
        notes.append(f"Primary persona '{plan.primary_persona_id}' is not in the context; set to '{fallback_id}'.")
        plan.primary_persona_id = fallback_id
    for item in [*plan.channels, *plan.message_tests]:
        if ids and item.persona_id not in ids:
            label = getattr(item, "channel", None) or getattr(item, "test_id", "")
            notes.append(f"'{label}' targeted unknown persona '{item.persona_id}'; set to the primary.")
            item.persona_id = fallback_id

    for c in plan.channels:
        if not c.evidence:
            issues.append(f"Channel '{c.channel}' cites no evidence.")
        if not inputs.is_b2b and _B2B_ONLY.search(c.channel) and not any(_B2B_ONLY.search(e) for e in c.evidence):
            issues.append(f"Channel '{c.channel}' is a B2B channel for a consumer product with no evidence for it.")
    for t in plan.message_tests:
        if not t.evidence:
            issues.append(f"Message test '{t.test_id}' cites no evidence.")

    text = " ".join([plan.rationale, *plan.success_metrics, *(c.purpose for c in plan.channels)])
    if _PROJECTION.search(text):
        issues.append("Plan projects ROI/ROAS; remove projections and state what will be measured.")

    # Money: reserve first, then channels scaled into what is left; phase ceilings likewise.
    min_reserve = round(inputs.budget * RESERVE_SHARE[mode], 2)
    if mode == "validate" and plan.reserve < min_reserve:
        notes.append(f"Reserve raised to {fmt_money(min_reserve, inputs.currency)} (validate mode keeps "
                     f"{RESERVE_SHARE[mode]:.0%} back).")
        plan.reserve = min_reserve
    spend = sum(c.budget for c in plan.channels)
    room = max(inputs.budget - plan.reserve, 0)
    if spend > room + 0.5:
        factor = room / spend if spend else 0
        for c in plan.channels:
            c.budget = round(c.budget * factor, 2)
        notes.append(f"Channel budgets scaled to fit {fmt_money(room, inputs.currency)} after the reserve.")
    phase_total = sum(p.budget_ceiling for p in plan.phases)
    if phase_total > inputs.budget + 0.5:
        factor = inputs.budget / phase_total
        for p in plan.phases:
            p.budget_ceiling = round(p.budget_ceiling * factor, 2)
        notes.append("Phase ceilings scaled to the budget.")

    plan.validation_notes = [*plan.validation_notes, *notes]
    return plan, issues


# ── Orchestration ───────────────────────────────────────────────────────────────

async def build_plan(
    inputs: PlanningInputs, mode: PlanMode, economics: UnitEconomics, llm: Any = None
) -> CampaignPlan:
    fallback = rules_plan(inputs, mode, economics)
    if llm is None:
        plan, _ = validate_plan(fallback, inputs, mode)
        return plan
    try:
        plan, issues = validate_plan(await llm_plan(llm, inputs, mode, economics), inputs, mode)
        if issues:
            draft = plan
            plan, issues = validate_plan(
                await llm_plan(llm, inputs, mode, economics, issues=issues, draft=draft), inputs, mode
            )
        if not issues:
            return plan
        logger.info("LLM plan still failing validation (%s); using rules plan", "; ".join(issues))
        fallback.validation_notes = [f"LLM plan rejected: {i}" for i in issues]
    except Exception as exc:
        logger.warning("LLM campaign planner failed, using rules plan: %s", exc)
        fallback.validation_notes = [f"LLM planner unavailable ({type(exc).__name__}); rules plan used."]
    plan, _ = validate_plan(fallback, inputs, mode)
    return plan
