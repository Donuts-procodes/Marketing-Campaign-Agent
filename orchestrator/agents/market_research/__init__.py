"""
Market Research & Competitive Intelligence Agent Package.

Modular Architecture:
  - agent.py: Top-level agent orchestrator coordinating research crew and DAG nodes.
  - service.py: HTTP microservice wrapper for autonomous container deployment.
  - loop.py: Multi-iteration DQS convergence search loop.
  - subagents.py: Specialised crew members (taxonomy, search, crawler, ad intel, synthesis, grounding).
  - tools/engines:
      * search.py (Tavily, You.com, DuckDuckGo)
      * crawlapi.py & crawler.py (Firecrawl, Crawlbase, Tavily Extract)
      * ad_intelligence.py (Meta, LinkedIn, Google ad libraries)
  - evaluation & synthesis:
      * taxonomy.py (Dynamic JTBD and minor specs reasoning)
      * scoring.py (DQS 4-dimension composite formula)
      * synthesis.py (Evidence-grounded SWOT and positioning matrix)
      * grounding.py (Anti-hallucination verbatim check)
"""

from orchestrator.agents.market_research.agent import execute_market_research
from orchestrator.agents.market_research.pipeline.loop import execute_research_loop, ResearchLoopResult
from orchestrator.agents.market_research.analysis.scoring import calculate_dqs, DQSResult
from orchestrator.agents.market_research.pipeline.subagents import ResearchCrew
from orchestrator.agents.market_research.analysis.taxonomy import (
    reason_dynamic_parameters,
    calculate_attribute_density,
)
from orchestrator.agents.market_research.analysis.synthesis import synthesize_swot_with_llm

__all__ = [
    "execute_market_research",
    "execute_research_loop",
    "ResearchLoopResult",
    "calculate_dqs",
    "DQSResult",
    "ResearchCrew",
    "reason_dynamic_parameters",
    "calculate_attribute_density",
    "synthesize_swot_with_llm",
]
