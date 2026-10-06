"""
LangGraph Strategy Sub-Orchestrator.

Orchestrates the Strategy pipeline:
  START -> market_research -> audience_persona (stub) -> campaign_strategy (stub) -> END

Stateless compute: takes hydrated StrategyState and outputs updated StrategyState.
"""

from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from orchestrator.agents.market_research.agent import execute_market_research
from orchestrator.agents.remote import RemoteAgentNode
from orchestrator.agents.stubs import (
    stub_audience_persona_agent,
    stub_campaign_strategy_agent,
)
from orchestrator.core.config import get_settings
from orchestrator.schemas.state import StrategyState


def build_strategy_subgraph(
    market_research_node: Callable[..., Any] | None = None,
    audience_persona_node: Callable[..., Any] | None = None,
    campaign_strategy_node: Callable[..., Any] | None = None,
) -> CompiledStateGraph:
    """
    Construct and compile the Strategy Sub-Orchestrator LangGraph.

    Args:
        market_research_node: Optional callable to override the default market research node.
        audience_persona_node: Optional callable to override the default persona node.
        campaign_strategy_node: Optional callable to override the default campaign node.

    Returns:
        CompiledStateGraph ready for async invocation (`ainvoke`).
    """
    settings = get_settings()
    builder = StateGraph(StrategyState)

    # 1. Market Research Agent Node (Microservice over HTTP or in-process fallback)
    research_fn = market_research_node or RemoteAgentNode(
        agent_name="market_research",
        service_url=settings.market_research_service_url,
        fallback_fn=execute_market_research,
    )
    builder.add_node("market_research", research_fn)

    # 2. Audience Persona Agent Node (Microservice over HTTP or in-process fallback)
    persona_fn = audience_persona_node or RemoteAgentNode(
        agent_name="audience_persona",
        service_url=settings.audience_persona_service_url,
        fallback_fn=stub_audience_persona_agent,
    )
    builder.add_node("audience_persona", persona_fn)

    # 3. Campaign Strategy Agent Node (Microservice over HTTP or in-process fallback)
    campaign_fn = campaign_strategy_node or RemoteAgentNode(
        agent_name="campaign_strategy",
        service_url=settings.campaign_strategy_service_url,
        fallback_fn=stub_campaign_strategy_agent,
    )
    builder.add_node("campaign_strategy", campaign_fn)

    # 4. Wire linear flow across slots
    builder.add_edge(START, "market_research")
    builder.add_edge("market_research", "audience_persona")
    builder.add_edge("audience_persona", "campaign_strategy")
    builder.add_edge("campaign_strategy", END)

    return builder.compile()


# Canonical default compiled instance
strategy_subgraph: CompiledStateGraph = build_strategy_subgraph()
