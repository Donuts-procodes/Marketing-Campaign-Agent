from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class TargetMetric(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(description="KPI or target metric name, e.g. Customer Acquisition Cost (CAC)")
    target_value: str = Field(description="Quantifiable target, e.g. '< $450 CPA' or '120 Enterprise MQLs'")
    baseline: str | None = Field(default=None, description="Current or market benchmark baseline")
    measurement_window: str = Field(default="90 days", description="Measurement timeframe")


class ChannelAllocation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel: Literal["email", "linkedin", "retarget", "search", "content"] = Field(
        description="Marketing distribution channel"
    )
    budget_percentage: int = Field(ge=0, le=100, description="Percentage of total campaign spend (0-100)")
    recommended_spend_usd: float | None = Field(default=None, description="Recommended budget allocation in USD")
    rationale: str = Field(description="Strategic justification based on audience habits and competitor blindspots")
    projected_roi: str | None = Field(default=None, description="Expected return or efficiency benchmark")


class StrategicAngle(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    angle_title: str = Field(description="Concise angle title, e.g. '14-Day Zero-Downtime Migration'")
    target_wedge: str = Field(description="Specific target audience wedge or segment")
    competitor_weakness: str = Field(description="Rival weakness or pricing gap being exploited")
    hook: str = Field(description="Primary advertising or outreach copy hook")
    messaging_pillar: str = Field(description="Supporting proof point or value proposition")


class PhaseMilestone(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    phase_name: str = Field(description="Milestone phase name, e.g. 'Phase 1: Foundation & Alpha Wedge'")
    weeks: str = Field(description="Time window, e.g. 'Weeks 1-3'")
    focus: str = Field(description="Strategic focus and key objective")
    deliverables: list[str] = Field(default_factory=list, description="Concrete outputs to deploy")


class CampaignStrategyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    executive_summary: str = Field(description="Strategic executive narrative synthesizing research into strategy")
    primary_positioning_pillar: str = Field(description="Core overarching brand wedge")
    target_metrics: list[TargetMetric] = Field(default_factory=list, description="Measurable KPI targets")
    channel_matrix: list[ChannelAllocation] = Field(default_factory=list, description="Channel priority and spend allocations")
    strategic_angles: list[StrategicAngle] = Field(default_factory=list, description="Positioning angles ready for copy generation")
    execution_calendar: list[PhaseMilestone] = Field(default_factory=list, description="Phased launch timeline and milestones")
    budget_assumptions: list[str] = Field(default_factory=list, description="Assumptions and constraints regarding budget/pricing")
    approval_status: Literal["PENDING_APPROVAL", "APPROVED"] = Field(
        default="PENDING_APPROVAL", description="Human-in-the-loop review status"
    )
