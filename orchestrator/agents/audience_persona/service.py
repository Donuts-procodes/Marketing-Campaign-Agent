"""
Audience Persona Agent Microservice.

Exposes the audience persona & ICP enrichment agent as an autonomous HTTP microservice.
Run with:
    uvicorn orchestrator.agents.audience_persona.service:app --host 0.0.0.0 --port 8002
"""

from __future__ import annotations

from orchestrator.agents.audience_persona.agent import execute_audience_persona
from orchestrator.agents.microservice import create_agent_microservice

app = create_agent_microservice(
    agent_name="audience_persona",
    execute_fn=execute_audience_persona,
    description="Autonomous Audience Persona & ICP Profiling Agent Microservice",
    version="1.0.0",
    service_endpoint="http://agent_audience_persona:8002",
    models=["gpt-4o"],
    tools=[
        "Apollo.io B2B Firmographic Enricher",
        "Social & Reddit Community Miner",
        "Objection & Friction Tagging Engine",
    ],
    capabilities=[
        "icp_archetype_generation",
        "apollo_b2b_enrichment",
        "objection_tagging",
        "buying_committee_mapping",
    ],
    input_schema="StrategyState (merchant_context, swot_report)",
    output_schema="PersonaReportDelta (persona_profiles, objections)",
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("orchestrator.agents.audience_persona.service:app", host="0.0.0.0", port=8002, reload=True)
