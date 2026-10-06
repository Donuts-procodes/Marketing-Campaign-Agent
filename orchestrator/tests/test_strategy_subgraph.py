"""
Loop 4 & 5 Verification: Strategy SubGraph construction, topology, and flow tests.
"""

from __future__ import annotations

import pytest
from langgraph.graph import END, START

from orchestrator.agents.market_research.agent import execute_market_research
from orchestrator.tests.mock_clients import create_standalone_mock_clients
from orchestrator.core.config import get_settings
from orchestrator.main_standalone import run_standalone_orchestrator
from orchestrator.schemas.research import SWOTReportDelta
from orchestrator.schemas.state import StrategyState
from orchestrator.subgraphs.strategy import build_strategy_subgraph, strategy_subgraph


class TestStrategySubGraphTopology:
    def test_graph_nodes_registered(self):
        """Verify all active and future stub nodes are registered in the compiled graph."""
        graph = strategy_subgraph.get_graph()
        node_names = set(graph.nodes.keys())

        assert "market_research" in node_names
        assert "audience_persona" in node_names
        assert "campaign_strategy" in node_names

    def test_graph_has_start_and_end(self):
        """Verify graph begins at START and terminates at END."""
        graph = strategy_subgraph.get_graph()
        edges = list(graph.edges)

        # Check edge from __start__ to market_research
        start_edges = [e for e in edges if e.source == START]
        assert len(start_edges) == 1
        assert start_edges[0].target == "market_research"

        # Check edge from campaign_strategy to __end__
        end_edges = [e for e in edges if e.target == END]
        assert len(end_edges) == 1
        assert end_edges[0].source == "campaign_strategy"

    def test_linear_stub_handoff_edges(self):
        """Verify market_research -> audience_persona -> campaign_strategy chain."""
        graph = strategy_subgraph.get_graph()
        edges = {(e.source, e.target) for e in graph.edges}

        assert ("market_research", "audience_persona") in edges
        assert ("audience_persona", "campaign_strategy") in edges

    def test_draw_ascii_runs(self):
        """Verify ascii graph rendering succeeds without error."""
        ascii_art = strategy_subgraph.get_graph().draw_ascii()
        assert "market_research" in ascii_art
        assert "audience_persona" in ascii_art
        assert "campaign_strategy" in ascii_art


@pytest.mark.asyncio
class TestStrategySubGraphExecution:
    async def test_end_to_end_flow_with_mock_node(self):
        """Test full execution of the graph through all 3 nodes (1 active + 2 stubs)."""
        tavily, crawl_client, llm = create_standalone_mock_clients()

        async def mock_node(state: StrategyState) -> dict:
            return await execute_market_research(state, tavily_client=tavily, crawl_client=crawl_client, llm=llm)

        graph = build_strategy_subgraph(market_research_node=mock_node)

        state_input: StrategyState = {
            "merchant_context": {
                "product_name": "ErgoMouse V2",
                "category": "B2B Ergonomic Computer Peripherals",
                "known_competitors": ["Logitech Lift"],
            },
            "swot_report": None,
            "dqs_retries": 0,
            "errors": [],
            "persona_profiles": None,
            "campaign_brief": None,
            "media_brief": None,
        }

        result = await graph.ainvoke(state_input)

        # 1. Active node populated swot_report
        assert result.get("swot_report") is not None
        assert isinstance(result["swot_report"], SWOTReportDelta)
        assert len(result["swot_report"].competitors) == 2

        # 2. Future slots remained None as pass-throughs
        assert result.get("persona_profiles") is None
        assert result.get("campaign_brief") is None
        assert result.get("media_brief") is None

        # 3. Context preserved
        assert result["merchant_context"]["product_name"] == "ErgoMouse V2"

    async def test_standalone_runner_refuses_to_run_without_keys(self, monkeypatch):
        """The standalone harness never falls back to sample data."""
        monkeypatch.setattr(get_settings(), "tavily_api_key", "")

        with pytest.raises(SystemExit, match="no sample data"):
            await run_standalone_orchestrator({"product_name": "P", "category": "C"})
