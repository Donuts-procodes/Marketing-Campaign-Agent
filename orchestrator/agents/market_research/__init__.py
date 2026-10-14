"""
Market Research & Competitive Intelligence Agent Package.

Modular Clean Architecture:
  - ingestion/: Web search, crawling, ad library scrapers, and URL guards.
  - workflow/: Execution loops, candidate ranking, and subagent crew containers.
  - intelligence/:
      * validation/: Anti-hallucination checks, verbatim quotes, recency, and DQS scoring.
      * profiling/: Deep competitor inspection, e-comm buying patterns, and review themes.
      * market_mapping/: Parameter taxonomy, niche wedge finder, threat watch, and classification.
      * advisory/: SWOT synthesis, unit economics, executive summaries, and ad copy.
  - normalizers/: Currency parser, display validator, diffing, and delta merger.
"""

from orchestrator.agents.market_research.agent import execute_market_research
from orchestrator.agents.market_research.workflow.research_loop import (
    execute_research_loop,
    ResearchLoopResult,
    split_named,
)
from orchestrator.agents.market_research.workflow.subagents import ResearchCrew
from orchestrator.agents.market_research.intelligence.validation.scoring import (
    calculate_dqs,
    DQSResult,
)
from orchestrator.agents.market_research.intelligence.market_mapping.taxonomy import (
    reason_dynamic_parameters,
    calculate_attribute_density,
)
from orchestrator.agents.market_research.intelligence.advisory.synthesis import (
    synthesize_swot_with_llm,
)

__all__ = [
    "execute_market_research",
    "execute_research_loop",
    "ResearchLoopResult",
    "split_named",
    "calculate_dqs",
    "DQSResult",
    "ResearchCrew",
    "reason_dynamic_parameters",
    "calculate_attribute_density",
    "synthesize_swot_with_llm",
]
