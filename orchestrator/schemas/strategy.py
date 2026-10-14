from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from orchestrator.schemas.persona import PersonaInput


class TargetMetric(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(description="KPI or target metric name, e.g. Customer Acquisition Cost (CAC)")
    target_value: str = Field(description="Quantifiable target, e.g. '< $450 CPA' or '120 Enterprise MQLs'")
    baseline: str | None = Field(default=None, description="Current or market benchmark baseline")
    measurement_window: str = Field(default="90 days", description="Measurement timeframe")
    is_sub_goal: bool = Field(default=False, description="Flag indicating if this metric tracks a user-defined sub-goal")


class ChannelAllocation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel: str = Field(
        description="Marketing distribution channel"
    )
    budget_percentage: int = Field(ge=0, le=100, description="Percentage of total campaign spend (0-100)")
    recommended_spend_usd: float | None = Field(default=None, description="Recommended budget allocation, in the brief's currency (legacy field name)")
    rationale: str = Field(description="Strategic justification based on audience habits and competitor blindspots")
    projected_roi: str | None = Field(default=None, description="Expected return or efficiency benchmark")
    promotion_tactics: list[str] = Field(
        default_factory=list,
        description="Specific promotional tactics and conversion mechanisms deployed on this channel",
    )
    payee_platform: str = Field(
        default="",
        description="Platform or vendor receiving this spend (e.g. LinkedIn Ads, Google Ads, Apollo.io)",
    )
    purchased_inventory: str = Field(
        default="",
        description="Concrete deliverables or ad inventory acquired (e.g. PPC search clicks, B2B lead enrichment, retargeting impressions)",
    )
    spend_type: Literal["ad_spend", "data_tooling", "asset_production"] = Field(
        default="ad_spend",
        description="Category of expenditure: direct ad media spend, data/software tooling, or creative asset production",
    )


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


class StrategyPrediction(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Null unless computed from the merchant's own data (sales history, unit economics). A guessed
    # ROI or CAC reads as a promise; the brief says what it is missing instead.
    projected_cac: str | None = Field(default=None, description="Customer acquisition cost, only from merchant data")
    projected_roi: str | None = Field(default=None, description="Return on spend, only from merchant data")
    conversion_velocity: str | None = Field(default=None, description="Conversion cycle time, only from merchant data")
    risk_level: Literal["Low", "Medium", "High"] = Field(default="Medium", description="Risk assessment level")
    break_even_timeline: str | None = Field(default=None, description="Break-even, only when unit economics are known")
    basis: str = Field(
        default="Not enough merchant data to project outcomes; the plan's tests produce the baseline.",
        description="Where the numbers above come from, or why they are empty",
    )


class CompetitorCampaignIntel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    competitor_name: str = Field(description="Name of the analyzed competitor")
    campaign_themes: list[str] = Field(default_factory=list, description="Core themes observed in competitor campaigns")
    detected_channels: list[str] = Field(default_factory=list, description="Advertising/distribution channels detected")
    active_offers_and_hooks: list[str] = Field(default_factory=list, description="Active promo hooks, free trials, or lead magnets")
    blindspots: list[str] = Field(default_factory=list, description="Gaps, omissions, or weaknesses in their campaigning")
    sample_evidence: list[str] = Field(default_factory=list, description="Excerpts or landing page findings scraped")
    estimated_monthly_ad_spend: str | None = Field(default=None, description="Estimated competitor monthly advertising spend or budget range")
    platform_cost_benchmarks: dict[str, str] = Field(default_factory=dict, description="Estimated CPC, CPA, or CPM benchmarks across platforms (Google, LinkedIn, Meta)")
    competitor_flagship_clients: list[str] = Field(default_factory=list, description="Marquee or enterprise clients acquired by competitor")
    competitor_consumer_feedback: list[str] = Field(default_factory=list, description="Consumer praise, complaints, and churn triggers")
    competitor_icp: str | None = Field(default=None, description="Target customer profile / ICP addressed by competitor")
    merchant_icp: str | None = Field(default=None, description="Target customer profile / ICP addressed by merchant")


class CampaignStrategyOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    option_id: str = Field(description="Unique identifier for the strategic option, e.g. 'opt_disrupter'")
    title: str = Field(description="Display title, e.g. 'Option A: Aggressive Incumbent Disrupter'")
    theme: str = Field(description="High-level tactical theme")
    tagline: str = Field(description="Short one-line pitch")
    recommended: bool = Field(default=False, description="Flag if recommended by the agent based on budget and market gaps")
    budget_allocation_summary: str = Field(description="Summary of budget allocation across channels")
    channel_matrix: list[ChannelAllocation] = Field(default_factory=list, description="Full channel allocation breakdown")
    advantages: list[str] = Field(default_factory=list, description="Key strategic advantages and pros")
    disadvantages: list[str] = Field(default_factory=list, description="Trade-offs, limitations, and cons")
    constraints: list[str] = Field(default_factory=list, description="Budget, timeline, resource, or compliance constraints")
    opportunities: list[str] = Field(default_factory=list, description="Market opportunities and competitor blindspots exploited")
    suggested_channels: list[str] = Field(
        default_factory=list,
        description="Recommended distribution channels for this strategy",
    )
    promotion_means: list[str] = Field(
        default_factory=list,
        description="Suggested tactical promotional vehicles, offers, and conversion mechanisms",
    )
    prediction: StrategyPrediction = Field(description="Projected outcome and efficiency metrics")


class SubagentDeployment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: str = Field(description="Unique identifier for the subagent, e.g. 'subagent_ad_creative'")
    name: str = Field(description="Display title, e.g. 'Ad Creative & Copywriting Subagent'")
    role: str = Field(description="Specific operational responsibility")
    status: Literal["idle", "ready", "running", "completed"] = Field(
        default="ready", description="Execution status of this subagent"
    )
    target_channels: list[str] = Field(default_factory=list, description="Marketing channels this subagent manages")
    deliverables: list[str] = Field(default_factory=list, description="Outputs or assets generated by this subagent")
    estimated_hours_saved: str = Field(default="15-20 hrs/wk", description="Estimated human labor replaced by this subagent")


class TacticalOutreachBlueprint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    playbook_id: str = Field(description="Unique play ID, e.g. 'play_linkedin_execs'")
    channel_name: str = Field(description="Channel / platform name, e.g. 'LinkedIn Sponsored & InMail'")
    who_target_profile: str = Field(
        description="Who to reach out to: specific ICP job titles, company seniority, and buying triggers"
    )
    where_platform: str = Field(
        description="Where to reach out: specific ad network, inbox, or platform placement"
    )
    how_mechanism: str = Field(
        description="How to reach out: concrete outreach sequence, hook, conversion offer, or collateral"
    )
    budget_allocation_usd: float = Field(
        description="Budget for this outreach stream, in the brief's currency (legacy field name)"
    )
    budget_share_pct: int = Field(
        description="Percentage of campaign budget dedicated to this outreach stream"
    )
    duration_and_cadence: str = Field(
        description="For how long and cadence: campaign flight length, touchpoint intervals, and frequency caps"
    )
    expected_cpa: str = Field(
        default="",
        description="Target CPA, CPL, or conversion benchmark"
    )
    assigned_subagent: str = Field(
        description="Specialized AI subagent assigned to run this outreach stream autonomously"
    )


PlanMode = Literal["validate", "traction", "scale"]


class PlanChannel(BaseModel):
    """One channel in the plan, tied to the persona it reaches and the evidence for choosing it."""

    model_config = ConfigDict(from_attributes=True)

    channel: str = Field(description="e.g. 'Instagram Reels (organic)', 'Meta ads test', 'Nano-creator barter'")
    persona_id: str = Field(description="persona_id from the planning context this channel reaches")
    budget: float = Field(ge=0, description="Spend ceiling, in the brief's currency")
    spend_type: Literal["ad_spend", "creator", "content", "tools", "research", "organic"] = "ad_spend"
    purpose: str = Field(description="What this channel must prove or produce")
    tactics: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(
        default_factory=list,
        description="Why this channel: a listing/buying-pattern finding, a persona channel, a rival gap",
    )


class MessageTest(BaseModel):
    """A message hypothesis to test: one persona × one angle, with what must back it up."""

    model_config = ConfigDict(from_attributes=True)

    test_id: str
    persona_id: str
    angle: str = Field(description="e.g. 'Comfort for the workday'")
    hook: str
    cta: str
    role: Literal["champion", "challenger"] = "champion"
    proof_needed: str = Field(default="", description="What the merchant must be able to show for this claim")
    evidence: list[str] = Field(default_factory=list, description="Rival complaint, review theme or listing gap it answers")


class PlanPhase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    days: str = Field(description="e.g. 'Days 1-30'")
    budget_ceiling: float = Field(ge=0, description="Maximum spend in this phase; not a target")
    objective: str
    actions: list[str] = Field(default_factory=list)
    decision_gate: str = Field(description="What must be true to move to the next phase, and what happens if not")


class ReadinessItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item: str = Field(description="Fix or prove before spending, e.g. 'Publish a size/fit guide'")
    reason: str = Field(description="The evidence that makes it necessary, e.g. rivals' sizing complaints")
    blocking: bool = Field(default=False, description="True when ads should wait for it")


class CampaignPlan(BaseModel):
    """The decision layer of the brief: grounded in personas, research and listings."""

    model_config = ConfigDict(from_attributes=True)

    primary_persona_id: str
    challenger_persona_id: str | None = None
    rationale: str = Field(description="Why this persona, these channels and this split, in 2-4 sentences")
    channels: list[PlanChannel] = Field(default_factory=list)
    reserve: float = Field(default=0, ge=0, description="Held back until a test earns it, in the brief's currency")
    message_tests: list[MessageTest] = Field(default_factory=list)
    phases: list[PlanPhase] = Field(default_factory=list)
    readiness: list[ReadinessItem] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list, description="What is tracked weekly, buyer intent first")
    questions_for_merchant: list[str] = Field(default_factory=list)
    generated_by: Literal["llm", "rules"] = "rules"
    validation_notes: list[str] = Field(default_factory=list, description="What the validator fixed or flagged")


class UnitEconomics(BaseModel):
    """Break-even from the merchant's own numbers; absent inputs leave it uncomputed."""

    model_config = ConfigDict(from_attributes=True)

    price: float | None = None
    unit_cost: float | None = None
    variable_cost_pct: float = Field(default=0.0, description="Payment fees + expected returns, as a share of price")
    contribution_per_unit: float | None = None
    orders_to_break_even: int | None = None
    max_affordable_cac: float | None = Field(default=None, description="Contribution per unit: spend above this per order loses money")
    note: str = ""


class MessagingPillar(BaseModel):
    title: str
    message: str = ""
    proof: str = Field(default="", description="What backs the claim")
    needs_proof: bool = Field(default=False, description="True when the merchant's brief does not hold that proof yet")


class MessagingStrategy(BaseModel):
    """What every asset says: positioning, the core line, and three pillars."""

    positioning: str = ""
    core_message: str = ""
    pillars: list[MessagingPillar] = Field(default_factory=list)


class CampaignStrategyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    executive_summary: str = Field(description="Strategic executive narrative synthesizing research into strategy")
    primary_positioning_pillar: str = Field(description="Core overarching brand wedge")
    target_metrics: list[TargetMetric] = Field(default_factory=list, description="Measurable KPI targets")
    channel_matrix: list[ChannelAllocation] = Field(default_factory=list, description="Channel priority and spend allocations")
    suggested_channels: list[str] = Field(
        default_factory=list,
        description="Consolidated list of suggested distribution channels",
    )
    promotion_means: list[str] = Field(
        default_factory=list,
        description="Consolidated list of suggested promotional means, conversion vehicles, and offers",
    )
    strategic_angles: list[StrategicAngle] = Field(default_factory=list, description="Positioning angles ready for copy generation")
    execution_calendar: list[PhaseMilestone] = Field(default_factory=list, description="Phased launch timeline and milestones")
    budget_assumptions: list[str] = Field(default_factory=list, description="Assumptions and constraints regarding budget/pricing")
    user_budget: float | None = Field(default=None, description="Campaign budget, in `currency`")
    currency: str = Field(default="USD", description="ISO code every amount in this brief is in")
    personas_used: list[PersonaInput] = Field(
        default_factory=list,
        description="Personas the plan targets, ranked; `source` says whether they came from the persona agent",
    )
    market_listings: list[str] = Field(
        default_factory=list,
        description="What rivals' marketplace/D2C listings show: price position, offer norms, where they sell",
    )
    mode: PlanMode | None = Field(default=None, description="validate / traction / scale, decided before planning")
    plan: CampaignPlan | None = Field(default=None, description="Grounded campaign plan (personas, tests, gates)")
    economics: UnitEconomics | None = None
    unknowns: list[str] = Field(
        default_factory=list,
        description="Facts the plan is missing that would change it (margin, stock, sales channel, stage)",
    )
    campaign_days: int = Field(default=90, description="Campaign duration in days")
    sub_goals: list[str] = Field(default_factory=list, description="Specific user-defined or decomposed sub-goals")
    core_goal: str | None = Field(default=None, description="Core business objective or goal")
    campaign_type: str | None = Field(default=None, description="Type of campaign (e.g. product_launch, lead_gen, brand_awareness)")
    competitor_campaign_intel: list[CompetitorCampaignIntel] = Field(
        default_factory=list, description="Scraped and discovered competitor campaign intelligence"
    )
    campaign_options: list[CampaignStrategyOption] = Field(
        default_factory=list, description="Comparative strategy options with pros, cons, constraints, and predictions"
    )
    selected_option_id: str | None = Field(
        default=None, description="ID of the campaign option selected by the user"
    )
    subagents_roster: list[SubagentDeployment] = Field(
        default_factory=list, description="List of autonomous subagents provisioned to execute this campaign"
    )
    outreach_blueprint: list[TacticalOutreachBlueprint] = Field(
        default_factory=list,
        description="Actionable 5-pillar outreach blueprint answering Who, Where, How, In What Budget, and For How Long",
    )
    messaging: MessagingStrategy | None = Field(default=None, description="Positioning, core message and pillars")
    budget_given: bool = Field(default=True, description="False when the merchant gave no budget and figures use a starter test size")
    approval_status: Literal["PENDING_APPROVAL", "APPROVED", "APPROVED_AND_DISPATCHED"] = Field(
        default="PENDING_APPROVAL", description="Human-in-the-loop review status"
    )


class StrategyCustomizeRequest(BaseModel):
    budget: float | None = Field(default=None, ge=100.0, description="Custom budget, in the brief's currency")
    selected_option_id: str | None = Field(default=None, description="Selected campaign strategy option ID")
    custom_goal: str | None = Field(default=None, description="Optional revised campaign objective")
    campaign_days: int | None = Field(default=None, ge=3, le=365, description="Custom campaign duration in days")
    sub_goals: list[str] | None = Field(default=None, description="User-added or customized sub-goals")
    campaign_type: str | None = Field(default=None, description="Updated campaign type")
    custom_option: CampaignStrategyOption | None = Field(
        default=None, description="User-created custom campaign strategy option"
    )

