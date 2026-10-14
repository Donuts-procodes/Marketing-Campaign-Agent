"""
Persona contract between the Audience/Persona Agent and the Campaign Strategy Agent.

The persona agent (built separately) writes `state["persona_profiles"]`; the strategy agent reads
it through `agents.campaign_strategy.context.load_personas`, which maps whatever shape arrives onto
PersonaInput. Until that agent ships, personas are derived from the research report and marked
`source="research_derived"` so the UI never passes them off as the persona agent's output.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PersonaInput(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    persona_id: str
    name: str = Field(description="Short label, e.g. 'Upgrading corporate professional'")
    description: str = ""
    demographics: dict[str, str] = Field(default_factory=dict, description="Age band, city tier, role, income…")
    pains: list[str] = Field(default_factory=list)
    motivations: list[str] = Field(default_factory=list)
    objections: list[str] = Field(
        default_factory=list, description="Why they would NOT buy, e.g. 'unknown brand at this price', 'sizing risk'"
    )
    preferred_channels: list[str] = Field(default_factory=list, description="Where they discover and buy")
    buying_triggers: list[str] = Field(default_factory=list, description="What tips them into buying")
    evidence: list[str] = Field(default_factory=list, description="Source URLs or quotes behind the persona")
    source: Literal["persona_agent", "research_derived", "merchant_input"] = "persona_agent"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    # Set by the strategy agent, not the persona agent: how well this persona fits THIS campaign
    # (price fit, evidence, reachability on affordable channels, gap rivals leave open).
    fit_score: float | None = Field(default=None, ge=0.0, le=1.0)
    role: Literal["primary", "challenger", "later"] | None = None
