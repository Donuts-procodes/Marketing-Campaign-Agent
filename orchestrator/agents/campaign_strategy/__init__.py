"""
Campaign Strategy Agent Package.

Modular Architecture:
  - agent.py: Top-level agent orchestrator coordinating strategy loops and LangGraph nodes.
  - hydration.py: Loop 1 - Context hydration and KPI objective decomposition.
  - synthesis.py: Loop 2 - Strategic angle derivation and channel priority matrix.
  - optimizer.py: Loop 3 - Budget optimization and 90-day execution calendar.
  - service.py: HTTP microservice wrapper for autonomous deployment.
"""

from orchestrator.agents.campaign_strategy.agent import execute_campaign_strategy
from orchestrator.agents.campaign_strategy.hydration import decompose_objectives
from orchestrator.agents.campaign_strategy.optimizer import (
    build_budget_assumptions,
    build_execution_calendar,
    consolidate_strategy_brief,
)
from orchestrator.agents.campaign_strategy.synthesis import (
    derive_channel_matrix,
    synthesize_strategic_angles,
)

__all__ = [
    "build_budget_assumptions",
    "build_execution_calendar",
    "consolidate_strategy_brief",
    "decompose_objectives",
    "derive_channel_matrix",
    "execute_campaign_strategy",
    "synthesize_strategic_angles",
]
