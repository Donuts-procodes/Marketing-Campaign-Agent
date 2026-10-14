"""
Campaign Strategy Agent Microservice.

Exposes the campaign strategy & channel budget decomposition agent as an autonomous HTTP microservice.
Run with:
    uvicorn orchestrator.agents.campaign_strategy.service:app --host 0.0.0.0 --port 8003
"""

from __future__ import annotations

from orchestrator.agents.campaign_strategy.agent import execute_campaign_strategy
from orchestrator.agents.microservice import create_agent_microservice

app = create_agent_microservice(
    agent_name="campaign_strategy",
    execute_fn=execute_campaign_strategy,
    description="Autonomous Campaign Strategy & Budget Decomposition Agent Microservice",
    version="1.0.0",
    service_endpoint="http://agent_campaign_strategy:8003",
    models=["gpt-4o"],
    tools=[
        "Cross-Channel Budget Optimizer (Meta, Google, LinkedIn)",
        "CAC / LTV Scenario Simulator",
        "Milestone & Flight Date Target Scheduler",
    ],
    capabilities=[
        "channel_budget_split",
        "kpi_target_derivation",
        "creative_brief_generation",
        "media_mix_modeling",
    ],
    input_schema="StrategyState (swot_report, persona_profiles)",
    output_schema="CampaignBriefDelta (channel_budgets, kpis, schedule)",
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("orchestrator.agents.campaign_strategy.service:app", host="0.0.0.0", port=8003, reload=True)
