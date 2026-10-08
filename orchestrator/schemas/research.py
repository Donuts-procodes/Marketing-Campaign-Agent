from __future__ import annotations

from pydantic import BaseModel, Field


class DynamicParameterTaxonomy(BaseModel):
    """Dynamically generated parameter framework for a specific product category."""

    critical_jtbd_drivers: list[str] = Field(
        default_factory=list,
        description="4 to 8 critical dealbreaker parameters for this specific industry",
    )
    minor_attributes: list[str] = Field(
        default_factory=list,
        description="15 to 25 technical, commercial, or feature attributes to track",
    )


class CampaignClassification(BaseModel):
    """
    Campaign archetype inferred from the merchant's own context by the classifier.

    Deliberately free-text, not enums: the model describes the campaign in its own words so
    novel archetypes are not forced into a fixed list. Downstream code keyword-matches these.
    """

    business_model: str = Field(
        default="",
        description="How the business makes money — e.g. b2b_saas, d2c_ecommerce, local_service, "
        "professional_services, marketplace, mobile_app, creator_infoproduct",
    )
    campaign_type: str = Field(
        default="",
        description="What this campaign is trying to do — e.g. brand_launch, product_launch, "
        "lead_gen, competitor_takeover, ecommerce_sales, retention, rebrand",
    )
    price_model: str = Field(
        default="",
        description="Pricing structure — e.g. monthly_subscription, one_time, hourly_rate, "
        "retainer, usage_based, fixed_project, free_quote",
    )
    target_geography: str = Field(
        default="",
        description="Target market or service area stated or implied — e.g. 'United States', "
        "'Global', 'Austin, TX'. Empty when the context does not indicate one.",
    )
    rationale: str = Field(
        default="",
        description="One sentence citing the context that drove this classification",
    )
    normalized_category: str = Field(
        default="",
        description="Clean, concise 2-5 word industry/market category if original category was conversational or a goal statement",
    )
    normalized_product_name: str = Field(
        default="",
        description="Clean brand or product name if original was conversational or identical to the goal",
    )
    user_intent: str = Field(
        default="",
        description="Concise 1-2 sentence understanding of what the user specifically wants the AI engine to accomplish based on their prompt/goal",
    )
    marketing_capabilities: list[str] = Field(
        default_factory=list,
        description="Specific marketing capabilities requested by the user, e.g. ['competitor_intelligence', 'pricing_analysis', 'lead_generation', 'ad_copywriting', 'positioning_strategy', 'audience_personas']",
    )


class CompetitorChange(BaseModel):
    """
    One observed difference between two scans of the same competitor.

    Re-running research for a product used to union old and new data, so a price moving from
    $49 to $59 silently became "$59" and the move itself -- the most actionable thing a repeat
    scan can tell a merchant -- was discarded. Each entry records one such move.
    """

    observed_at: str = Field(..., description="ISO date of the run that noticed the change")
    field: str = Field(..., description="Which part of the profile moved, e.g. 'pricing_model'")
    previous: str | None = Field(default=None, description="Value held before this run")
    current: str | None = Field(default=None, description="Value found by this run")
    source: str | None = Field(
        default=None,
        description="'merchant' when the merchant corrected the value; empty when a scan observed it",
    )


class CompetitorProfile(BaseModel):
    """Structured profile extracted per discovered competitor."""

    brand_name: str = Field(..., description="Parent brand (e.g. Logitech)")
    product_name: str = Field(..., description="Specific competing product (e.g. MX Master 3S)")
    pricing_model: str | None = Field(
        default=None,
        description="Pricing structure — e.g. 'one-time $99', 'freemium + $15/mo pro tier'",
    )
    core_claims: list[str] = Field(
        default_factory=list,
        description="Key marketing / value-prop claims scraped from competitor pages",
    )
    weaknesses_mined: list[str] = Field(
        default_factory=list,
        description="User-reported complaints, gripes, and review pain points",
    )
    strengths_mined: list[str] = Field(
        default_factory=list,
        description="User-reported praise from the same review and forum pages the complaints "
        "come from: what customers say this competitor actually does well",
    )
    rating: str | None = Field(
        default=None,
        description="Average review score on a 0-5 scale as stated on a review page, or null",
    )
    review_count: int | None = Field(
        default=None,
        description="Number of reviews behind the rating, or null when no page states one",
    )
    dynamic_attributes: dict[str, str | None] = Field(
        default_factory=dict,
        description="Dynamic critical and minor parameters populated from crawl data",
    )
    ad_hooks: list[str] = Field(
        default_factory=list,
        description="Active ad creatives, copy angles, and messaging hooks mined from ad libraries",
    )
    factual_evidence: list[str] = Field(
        default_factory=list,
        description="Verbatim factual excerpts and citations extracted directly from crawl corpus backing this profile",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Provenance URLs backing this profile's data points",
    )
    as_of: str | None = Field(
        default=None,
        description="ISO date (YYYY-MM-DD) of the most recent dated evidence backing this "
        "profile, or null when no source carried a publication date",
    )
    relevance_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="LLM-assigned relevance to the merchant (0.0 = noise, 1.0 = primary rival)",
    )
    relevance_reason: str = Field(
        default="",
        description="One sentence on why this rival matters to the merchant, shown on the dashboard",
    )
    founded: str | None = Field(
        default=None,
        description="Founding year or date as stated on the competitor's own pages, or null",
    )
    milestones: list[str] = Field(
        default_factory=list,
        description="Dated company or product events stated on their pages: launches, funding, "
        "acquisitions, version releases. Each entry leads with its date.",
    )
    change_history: list[CompetitorChange] = Field(
        default_factory=list,
        description="What moved between our own scans of this competitor. Accumulated across "
        "runs, so it is the one history no single page states.",
    )


class SWOTAnalysis(BaseModel):
    """Evidence-grounded SWOT matrix for the merchant's competitive landscape."""

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)


class MarketPositioningGap(BaseModel):
    """Identifies an uncontested positioning quadrant and a candidate hook angle."""

    quadrant: str = Field(
        ...,
        description="Label for the positioning gap — e.g. 'Premium-Ergonomic-Mechanical'",
    )
    hook_angle: str = Field(
        ...,
        description="Draft messaging hook exploiting this gap — e.g. "
        "'The only mechanical ergo mouse under $150'",
    )


class CompetitorRelevance(BaseModel):
    """Per-competitor relevance judgement, so the dashboard can rank and explain rivals."""

    index: int = Field(..., description="0-based index into the competitors list being scored")
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance to this merchant: 1.0 = direct head-to-head rival, "
        "<0.4 = noise the merchant does not compete with",
    )
    reason: str = Field(
        default="",
        description="One short sentence on why this rival does or does not matter to the merchant",
    )


class DashboardInsights(BaseModel):
    """LLM-curated relevance filter: highlights the most useful data for the merchant."""

    executive_summary: str = Field(
        default="",
        description="2-3 sentence merchant-focused brief of the competitive landscape",
    )
    primary_competitor_indices: list[int] = Field(
        default_factory=list,
        description="Indices into the competitors list for the most relevant rivals to show by default",
    )
    competitor_relevance: list[CompetitorRelevance] = Field(
        default_factory=list,
        description="Relevance score and reason for EVERY competitor, by index",
    )
    highlight_weaknesses: list[str] = Field(
        default_factory=list,
        description="Top 3-5 most exploitable competitor weaknesses for the merchant",
    )
    highlight_opportunities: list[str] = Field(
        default_factory=list,
        description="Top 2-3 immediate market opportunities the merchant should act on",
    )
    priority_attributes: list[str] = Field(
        default_factory=list,
        description="Which dynamic attributes matter most for the merchant's differentiation",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="3-5 concrete next-step actions for the merchant",
    )


class SWOTReportDelta(BaseModel):
    """
    Immutable delta emitted by the Market Research Agent.

    Bundled into StrategyState['swot_report'] and consumed downstream
    by the Persona and Campaign Strategy agents.
    """

    competitors: list[CompetitorProfile] = Field(default_factory=list)
    swot: SWOTAnalysis = Field(default_factory=SWOTAnalysis)
    positioning_gap: MarketPositioningGap | None = None
    dynamic_taxonomy: DynamicParameterTaxonomy | None = None
    attribute_density: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Dynamic attribute density percentage across discovered rivals",
    )
    dqs_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Data Quality Score — weighted composite (0.00–1.00)",
    )
    assumptions_tagged: bool = Field(
        default=False,
        description="True when DQS remained below threshold after max retries",
    )
    source_urls: list[str] = Field(
        default_factory=list,
        description="Deduplicated master list of all URLs used as evidence",
    )
    dqs_diagnostics: list[str] = Field(
        default_factory=list,
        description="Human-readable reasons for DQS point deductions, if any",
    )
    validation_diagnostics: list[str] = Field(
        default_factory=list,
        description="Anti-hallucination and ground-truth verification logs",
    )
    dashboard_insights: DashboardInsights | None = Field(
        default=None,
        description="LLM-curated relevance filter highlighting the most useful data for the merchant dashboard",
    )
    sample_data: bool = Field(
        default=False,
        description="True when produced by offline mock clients rather than live research",
    )
