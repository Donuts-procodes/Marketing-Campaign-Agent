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

from orchestrator.agents.campaign_strategy.hydration import decompose_objectives
from orchestrator.agents.campaign_strategy.optimizer import consolidate_strategy_brief
from orchestrator.agents.campaign_strategy.synthesis import (
    derive_channel_matrix,
    synthesize_strategic_angles,
)
from orchestrator.core.llm import LLMConfigurationError, build_chat_model
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
    Produces an approval-ready CampaignStrategyBrief.
    """
    merchant_context: dict[str, Any] = state.get("merchant_context", {})
    swot_report: SWOTReportDelta | None = state.get("swot_report")
    product_name = merchant_context.get("product_name") or "Product"

    await _report(
        on_progress,
        f"[STRATEGY_START] Initializing Campaign Strategy Agent for {product_name}",
    )

    # Loop 1: Objective Decomposition & KPI Target Metrics
    await _report(
        on_progress,
        "[STRATEGY_DECOMP] Loop 1: Decomposing business goals into quantifiable target metrics",
    )
    target_metrics = decompose_objectives(merchant_context)
    await _report(
        on_progress,
        f"[STRATEGY_METRICS] Generated {len(target_metrics)} core KPI targets (CAC, Velocity, Payback)",
    )

    # Loop 2: Strategic Angles & Channel Priority Matrix
    await _report(
        on_progress,
        "[STRATEGY_SYNTHESIS] Loop 2: Correlating competitor gaps to derive strategic messaging angles",
    )
    strategic_angles = synthesize_strategic_angles(merchant_context, swot_report)

    await _report(
        on_progress,
        "[CHANNEL_FIT] Loop 2: Synthesizing multi-channel allocation matrix based on category unit economics",
    )
    channel_matrix = derive_channel_matrix(merchant_context, swot_report)

    # Loop 3: Budget Optimization & Phased Execution Calendar
    await _report(
        on_progress,
        "[BUDGET_OPTIMIZED] Loop 3: Calculating 90-day phased execution roadmap and spend allocations",
    )
    brief = consolidate_strategy_brief(
        merchant_context,
        swot_report,
        target_metrics,
        channel_matrix,
        strategic_angles,
    )

    # Optional BYOK LLM reasoning enrichment if available
    active_llm = llm
    if active_llm is None and llm_config is not None:
        try:
            active_llm = build_chat_model(llm_config, fast=True)
        except LLMConfigurationError:
            active_llm = None

    if active_llm is not None:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            prompt = (
                f"You are a Principal Product Marketing Strategist. Given product '{product_name}' "
                f"in category '{merchant_context.get('category')}' with goal '{merchant_context.get('goal')}', "
                f"refine this 2-sentence executive positioning summary to maximize high-converting conviction:\n"
                f"{brief.executive_summary}"
            )
            response = await active_llm.ainvoke([
                SystemMessage(content="Return only the refined 2-sentence executive summary. Do not include quotes or intro."),
                HumanMessage(content=prompt),
            ])
            refined_text = response.content.strip() if hasattr(response, "content") else str(response).strip()
            if refined_text and len(refined_text) > 30:
                brief.executive_summary = refined_text
                await _report(
                    on_progress,
                    "[STRATEGY_CAG] LLM reasoning refined executive positioning summary",
                )
        except Exception as exc:
            logger.debug("LLM summary refinement skipped: %s", exc)

    await _report(
        on_progress,
        f"[STRATEGY_COMPLETE] Strategy brief compiled ({len(brief.strategic_angles)} angles, {len(brief.channel_matrix)} channels) — Pending Founder Approval",
    )

    return {
        "strategy_brief": brief,
        "campaign_brief": brief.model_dump(),
    }
