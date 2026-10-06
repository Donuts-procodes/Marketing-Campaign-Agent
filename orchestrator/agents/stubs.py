"""
No-op pass-through stubs for future downstream agents in the Strategy pipeline.

These preserve the typed LangGraph boundary and slot contracts
without refactoring the core orchestrator plumbing.
"""

from __future__ import annotations

import logging

from orchestrator.schemas.state import StrategyState

logger = logging.getLogger(__name__)


async def stub_audience_persona_agent(state: StrategyState) -> dict:
    """
    EXTENSION POINT: Audience & Persona Research Agent.

    Consumes `state["merchant_context"]` and `state["swot_report"]`.
    Produces `state["persona_profiles"]` containing ICP archetypes and pain points.
    Currently a no-op pass-through.
    """
    logger.debug("Executing stub_audience_persona_agent (pass-through)")
    return {}


async def stub_campaign_strategy_agent(state: StrategyState) -> dict:
    """
    EXTENSION POINT: Campaign Strategy & Budgeting Agent.

    Consumes `swot_report` and `persona_profiles`.
    Produces `state["campaign_brief"]` with channel priorities, budget splits, and milestones.
    Currently a no-op pass-through.
    """
    logger.debug("Executing stub_campaign_strategy_agent (pass-through)")
    return {}
