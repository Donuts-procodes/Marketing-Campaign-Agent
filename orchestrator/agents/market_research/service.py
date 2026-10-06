"""
Market Research Agent Microservice.

Exposes the market research & competitive intelligence agent as an autonomous HTTP microservice.
Run with:
    uvicorn orchestrator.agents.market_research.service:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

from orchestrator.agents.market_research.agent import execute_market_research
from orchestrator.agents.microservice import create_agent_microservice

app = create_agent_microservice(
    agent_name="market_research",
    execute_fn=execute_market_research,
    description="Autonomous Market Research & Competitor Intelligence Agent Microservice",
    version="1.0.0",
    service_endpoint="http://agent_market_research:8001",
    models=["gpt-4o", "gpt-4o-mini"],
    tools=[
        "Tavily Async Multi-Vector Client",
        "You.com Web Search",
        "Firecrawl / Crawlbase Deep Search (Tavily Extract fallback)",
        "Ad Library Search (Meta, LinkedIn, Google)",
        "Dynamic Parameter Taxonomy Reasoner",
        "DQS Weighted Scoring Engine (4-dimension)",
        "Factual Grounding & Anti-Hallucination Gate",
    ],
    capabilities=[
        "dynamic_parameter_taxonomy",
        "tavily_multi_vector_search",
        "crawlapi_deep_search",
        "iterative_dqs_convergence",
        "competitor_ad_intelligence",
        "factual_grounding_validation",
        "swot_synthesis",
    ],
    input_schema="StrategyState (merchant_context, dqs_retries)",
    output_schema="SWOTReportDelta (competitors, swot, positioning_gap, dynamic_taxonomy)",
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("orchestrator.agents.market_research.service:app", host="0.0.0.0", port=8001, reload=True)
