"""
Campaign Strategy Agent node.

Coordinates the 4 strategy thought loops:
  1. Context Hydration & Objective Decomposition (hydration.py)
  2. Strategic Synthesis & Channel Matrix Fit (synthesis.py)
  3. Budget Optimization & Phased Execution Calendar (optimizer.py)
  4. Governance Gate & Approval-ready Campaign Brief (schemas/strategy.py)

Stateless LangGraph-compatible callable: accepts StrategyState, returns updated delta.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Coroutine

import re
from orchestrator.agents.campaign_strategy.hydration import (
    decompose_objectives,
    hydrate_campaign_context_from_mongo,
)
from orchestrator.agents.campaign_strategy.context import (
    merchant_price,
    apply_plan_to_brief,
    find_unknowns,
    load_personas,
    summarize_listings,
)
from orchestrator.agents.campaign_strategy.intel import mine_competitor_campaigns
from orchestrator.agents.campaign_strategy.money import fmt_money, resolve_currency
from orchestrator.agents.campaign_strategy.planner import (
    PlanningInputs,
    build_plan,
    compute_economics,
    decide_mode,
    is_b2b_business,
)
from orchestrator.agents.campaign_strategy.options import generate_campaign_options
from orchestrator.agents.campaign_strategy.optimizer import consolidate_strategy_brief
from orchestrator.agents.campaign_strategy.synthesis import (
    derive_channel_matrix,
    synthesize_strategic_angles,
)
from orchestrator.core.llm import LLMConfigurationError, build_chat_model, has_llm_credentials
from orchestrator.schemas.research import SWOTReportDelta
from orchestrator.schemas.state import StrategyState
from orchestrator.schemas.strategy import CampaignStrategyBrief

if TYPE_CHECKING:
    from orchestrator.schemas.api import BYOKConfig

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, str], Coroutine[Any, Any, None]]


async def _report(
    on_progress: ProgressFn | None, message: str, level: str = "INFO"
) -> None:
    if on_progress:
        try:
            await on_progress(message, level)
        except Exception:
            pass


async def execute_campaign_strategy(
    state: StrategyState,
    *,
    llm: Any = None,
    llm_config: BYOKConfig | None = None,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """
    Executes the autonomous Campaign Strategy planning loops.

    Consumes merchant context and upstream SWOT report.
    Produces an approval-ready CampaignStrategyBrief with comparative options.
    """
    raw_merchant_context: dict[str, Any] = state.get("merchant_context", {})
    raw_swot_report: SWOTReportDelta | None = state.get("swot_report")

    # Hydrate client data, product sales, competitor client lists, consumer data, and ICPs from Mongo
    merchant_context, swot_report, audience_intel = await hydrate_campaign_context_from_mongo(
        raw_merchant_context,
        raw_swot_report,
        job_id=state.get("job_id"),
    )

    product_name = merchant_context.get("product_name") or "Product"
    # One currency for the whole brief; builders read it from merchant_context.
    currency = resolve_currency(merchant_context, swot_report)
    merchant_context["currency"] = currency

    # Parse and normalize user budget and campaign days
    budget_given = bool(merchant_context.get("budget"))
    raw_budget = merchant_context.get("budget") or "10000"
    clean_budget_str = re.sub(r"[^\d.]", "", str(raw_budget))
    try:
        user_budget = float(clean_budget_str) if clean_budget_str else 10000.0
    except ValueError:
        user_budget = 10000.0

    raw_days = merchant_context.get("campaign_days") or 90
    try:
        campaign_days = max(7, int(raw_days))
    except (ValueError, TypeError):
        campaign_days = 90

    sub_goals: list[str] = merchant_context.get("sub_goals") or []
    campaign_type = merchant_context.get("campaign_type") or "general"
    core_goal = merchant_context.get("goal") or "Accelerate market traction"

    await _report(
        on_progress,
        f"[STRATEGY_START] Initializing Campaign Strategy Agent for {product_name} (Budget: {fmt_money(user_budget, currency)}, Duration: {campaign_days} days)",
    )

    # Personas: the persona agent's output when present, else provisional ones from the research.
    personas = load_personas(state, swot_report, merchant_context)
    persona_sources = sorted({p.source for p in personas})
    await _report(
        on_progress,
        f"[PERSONAS] {len(personas)} persona(s) from {', '.join(persona_sources) or 'none'}"
        + (f"; primary: {personas[0].name}" if personas else ""),
    )
    market_listings = summarize_listings(swot_report, merchant_context, currency)
    if market_listings:
        await _report(on_progress, f"[LISTINGS] {len(market_listings)} marketplace/D2C pricing finding(s) in context")
    unknowns = find_unknowns(merchant_context, personas)

    # Loop 1: Objective Decomposition & KPI Target Metrics
    await _report(
        on_progress,
        "[STRATEGY_DECOMP] Loop 1: Decomposing business goals into quantifiable target metrics",
    )
    target_metrics = decompose_objectives(
        merchant_context,
        campaign_days=campaign_days,
        sub_goals=sub_goals,
    )
    await _report(
        on_progress,
        f"[STRATEGY_METRICS] Generated {len(target_metrics)} core KPI targets (CAC, Velocity, Payback)",
    )

    # Loop 2a: Mine Competitor Campaigns via Search Engines & Scrapers
    await _report(
        on_progress,
        "[COMPETITOR_INTEL] Scanning competitor ad spend, platform cost benchmarks, and campaign hooks",
    )
    competitor_intel = await mine_competitor_campaigns(
        merchant_context,
        swot_report,
    )
    await _report(
        on_progress,
        f"[COMPETITOR_INTEL_DONE] Analyzed campaign patterns & messaging blindspots across {len(competitor_intel)} competitor(s)",
    )

    # Loop 2b: Strategic Angles & Channel Priority Matrix
    await _report(
        on_progress,
        "[STRATEGY_SYNTHESIS] Loop 2: Correlating competitor gaps to derive strategic messaging angles",
    )
    strategic_angles = synthesize_strategic_angles(merchant_context, swot_report)

    await _report(
        on_progress,
        f"[CHANNEL_FIT] Loop 2: Synthesizing multi-channel allocation matrix scaled to {fmt_money(user_budget, currency)} budget",
    )
    channel_matrix = derive_channel_matrix(merchant_context, swot_report, user_budget=user_budget)

    # Loop 2c: Comparative Campaign Options (Adv, Dis, Constraints, Opps, Prediction)
    await _report(
        on_progress,
        "[STRATEGY_OPTIONS] Formulating 3 comparative strategy options with trade-offs and predictions",
    )
    campaign_options = generate_campaign_options(
        merchant_context,
        competitor_intel,
        user_budget,
        campaign_days=campaign_days,
        sub_goals=sub_goals,
    )

    # Loop 3: Budget Optimization & Phased Execution Calendar
    await _report(
        on_progress,
        f"[BUDGET_OPTIMIZED] Loop 3: Calculating {campaign_days}-day phased execution roadmap and spend allocations",
    )
    brief = consolidate_strategy_brief(
        merchant_context,
        swot_report,
        target_metrics,
        channel_matrix,
        strategic_angles,
        competitor_intel=competitor_intel,
        campaign_options=campaign_options,
        user_budget=user_budget,
        campaign_days=campaign_days,
        sub_goals=sub_goals,
        campaign_type=campaign_type,
        core_goal=core_goal,
    )

    brief.currency = currency
    brief.personas_used = personas
    brief.market_listings = market_listings
    brief.unknowns = unknowns

    # Loop 4: mode → economics → grounded plan (LLM when a key is available, rules otherwise) → validator.
    price = merchant_price(merchant_context)
    mode, mode_reason = decide_mode(merchant_context, user_budget, price)
    economics = compute_economics(merchant_context, user_budget, price)
    await _report(on_progress, f"[STRATEGY_MODE] {mode.upper()}: {mode_reason}")

    active_llm = llm
    if active_llm is None and has_llm_credentials(llm_config):
        try:
            active_llm = build_chat_model(llm_config)
        except LLMConfigurationError:
            active_llm = None

    inputs = PlanningInputs(
        merchant_context=merchant_context, budget=user_budget, currency=currency, campaign_days=campaign_days,
        personas=personas, market_listings=market_listings, unknowns=unknowns, swot_report=swot_report,
        is_b2b=is_b2b_business(merchant_context),
    )
    plan = await build_plan(inputs, mode, economics, llm=active_llm)
    await _report(
        on_progress,
        f"[STRATEGY_PLAN] {plan.generated_by.upper()} plan: {len(plan.channels)} channel(s), "
        f"{len(plan.message_tests)} message test(s), {len(plan.readiness)} readiness item(s), "
        f"reserve {fmt_money(plan.reserve, currency)}"
        + (f"; validator: {len(plan.validation_notes)} note(s)" if plan.validation_notes else ""),
    )
    apply_plan_to_brief(brief, plan, mode, economics, mode_reason, user_budget)

    # No budget given: say the figures use a starter test size instead of presenting them as the merchant's.
    brief.budget_given = budget_given
    if not budget_given:
        brief.unknowns = [
            f"No budget given: amounts assume a starter test budget of {fmt_money(user_budget, currency)}. "
            "Set your budget to resize the plan.",
            *brief.unknowns,
        ]

    # Loop 5: messaging — positioning, core message and pillars every asset will carry.
    from orchestrator.agents.campaign_strategy.messaging import write_messaging

    brief.messaging = await write_messaging(merchant_context, swot_report, personas, active_llm)
    if brief.messaging:
        await _report(
            on_progress,
            f"[MESSAGING] Core message: \"{brief.messaging.core_message}\" · {len(brief.messaging.pillars)} pillar(s)"
            + (f", {sum(p.needs_proof for p in brief.messaging.pillars)} need proof from you"
               if any(p.needs_proof for p in brief.messaging.pillars) else ""),
        )

    await _report(
        on_progress,
        f"[STRATEGY_COMPLETE] Strategy brief compiled ({len(brief.strategic_angles)} angles, {len(brief.channel_matrix)} channels) — Pending Founder Approval",
    )

    return {
        "strategy_brief": brief,
        "campaign_brief": brief.model_dump(),
    }
