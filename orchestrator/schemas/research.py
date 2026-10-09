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


class ReviewAspect(BaseModel):
    """
    One recurring theme across a competitor's reviews, with the mechanism behind it.

    `weaknesses_mined` holds verbatim gripes, which tells a merchant what was said but not why
    it keeps being said. An aspect groups the gripes into a theme and names the trigger, so the
    pattern is actionable rather than anecdotal.
    """

    topic: str = Field(..., description="Short theme label, e.g. 'Filter lifespan & clogging'")
    sentiment: str = Field(
        default="mixed",
        description="'negative', 'positive' or 'mixed' — the consensus on this theme",
    )
    summary: str = Field(default="", description="One-to-two sentence consensus finding on this theme")
    root_cause: str = Field(
        default="",
        description="The underlying mechanism or trigger behind it — a design limit, a billing "
        "policy, a support process — not a restatement of the complaint",
    )
    affected_personas: list[str] = Field(
        default_factory=list,
        description="Which buyer segments this theme hits, e.g. 'renters', 'high-TDS well water homes'",
    )
    sample_quotes: list[str] = Field(
        default_factory=list,
        description="Verbatim review excerpts from the evidence corpus backing this theme",
    )
    merchant_opportunity: str = Field(
        default="",
        description="Concrete counter-positioning move the merchant can make on this theme",
    )


class CompetitorReviewContext(BaseModel):
    """Synthesized context behind one competitor's customer reviews."""

    brand_name: str = Field(..., description="Brand this review context belongs to")
    product_name: str = Field(default="", description="Specific product reviewed")
    overall_sentiment_consensus: str = Field(
        default="",
        description="What reviewers collectively conclude: why they buy and why they churn",
    )
    buyer_personas: list[str] = Field(
        default_factory=list,
        description="Who is actually reviewing and buying this rival, inferred from review text",
    )
    top_praise_drivers: list[ReviewAspect] = Field(
        default_factory=list,
        description="Recurring themes customers praise, strongest first",
    )
    top_complaint_drivers: list[ReviewAspect] = Field(
        default_factory=list,
        description="Recurring themes customers complain about, most damaging first",
    )
    unmet_customer_needs: list[str] = Field(
        default_factory=list,
        description="What reviewers asked for and did not get — the feature wishlist",
    )
    counter_positioning_angle: str = Field(
        default="",
        description="The single strongest message for winning this rival's dissatisfied buyers",
    )


class PricingTier(BaseModel):
    """
    `pricing_model` parsed into comparable parts.

    The raw string stays on the profile for display; this is what sorting, price-range bars
    and "who is cheapest?" read, so "$49/mo billed annually" and "$59/month" compare as numbers.
    """

    tier_name: str | None = Field(default=None, description="Plan name when stated, e.g. 'Pro'")
    amount: float | None = Field(default=None, description="Lowest stated paid price, as a number")
    currency: str | None = Field(default=None, description="ISO code, e.g. 'USD'")
    period: str | None = Field(
        default=None,
        description="'monthly', 'annual', 'one_time', 'project', 'hourly', 'usage' or null",
    )
    monthly_equivalent: float | None = Field(
        default=None,
        description="amount normalized to a monthly figure when the period allows it, else null",
    )
    has_free_tier: bool = Field(default=False, description="True when a free plan or trial is stated")
    raw: str = Field(default="", description="The pricing_model string this was parsed from")


class LeapBenchmark(BaseModel):
    """
    A competitor that originated as a similar boutique/indie peer in this wedge,
    but took a big leap in scale, marquee enterprise clients, high-value deals,
    partner networks, and market valuation.
    """

    brand_name: str = Field(..., description="Brand of the breakout competitor")
    origin_story: str = Field(
        default="",
        description="How they started out similar to the merchant (e.g. 5-person Rails boutique, small regional studio)",
    )
    current_scale: str = Field(
        default="",
        description="Current estimated scale, valuation, revenue tier, or headcount (e.g. '$30M+ revenue, 150+ staff')",
    )
    flagship_clients: list[str] = Field(
        default_factory=list,
        description="Marquee enterprise or unicorn clients they landed (e.g. ['Robinhood', 'Postmates', 'Subaru'])",
    )
    network_and_deals: list[str] = Field(
        default_factory=list,
        description="High-value alliances, ecosystem partner tiers, or awards (e.g. ['AWS Premier Partner', 'Apple Design Award'])",
    )
    pricing_power_leap: str = Field(
        default="",
        description="How their pricing and contract sizes expanded beyond boutique rates (e.g. '$150–$250/hr with $25k+ project floor')",
    )
    leap_catalysts: list[str] = Field(
        default_factory=list,
        description="Key strategic inflection points behind their breakthrough (e.g. open source tools, enterprise pivot, YC network)",
    )
    merchant_takeaway_playbook: list[str] = Field(
        default_factory=list,
        description="Actionable steps the merchant can borrow to execute a similar leap in this market",
    )


class FieldStatus(BaseModel):
    """
    Why one profile fact holds the value it does -- or why it is empty.

    "Not available" told the merchant nothing: it hid four different situations (never looked
    for, looked and no page says it, found but rejected, never collected). Each fact now carries
    which one applies, and for a found value the verbatim sentence and page it came from.
    """

    status: str = Field(
        default="not_searched",
        description="'found' (verified), 'not_stated' (searched; no page we read states it), "
        "'removed' (found but rejected by a check), 'not_searched'",
    )
    source_url: str | None = Field(default=None, description="Page the value was read from")
    quote: str | None = Field(default=None, description="Verbatim sentence that states the value")
    reason: str = Field(default="", description="Plain-language explanation shown to the merchant")
    pages_checked: int = Field(default=0, description="Pages and snippets searched for this fact")


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
    headquarters: str | None = Field(
        default=None,
        description="Primary office location or headquarters city/country (e.g. 'Los Angeles, CA', 'Berlin, Germany')",
    )
    operating_locations: list[str] = Field(
        default_factory=list,
        description="Active operating regions, branch offices, service territories, or countries where they have a presence",
    )
    other_products: list[str] = Field(
        default_factory=list,
        description="Other notable products, models, or service lines offered by this brand",
    )
    product_catalog_count: int | None = Field(
        default=None,
        description="Total number or estimated count of products/models in their catalog",
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
    pricing_parsed: PricingTier | None = Field(
        default=None,
        description="pricing_model parsed into amount / period / currency; null when unparseable",
    )
    review_context: CompetitorReviewContext | None = Field(
        default=None,
        description="Synthesized context behind the reviews: root causes, buyer personas and "
        "counter-positioning angles. Null when no review evidence was found.",
    )
    leap_benchmark: LeapBenchmark | None = Field(
        default=None,
        description="Breakout analysis if this competitor took a big leap from similar origins to enterprise/market leader scale",
    )
    employee_count: str | None = Field(
        default=None,
        description="Team size exactly as a page states it, e.g. '50-249' or '120'. Never estimated.",
    )
    annual_revenue: str | None = Field(
        default=None,
        description="Revenue exactly as a page states it, e.g. '$10M-$50M'. Never estimated.",
    )
    funding: str | None = Field(
        default=None,
        description="Funding raised or valuation exactly as a page states it. Never estimated.",
    )
    fact_status: dict[str, FieldStatus] = Field(
        default_factory=dict,
        description="Per profile fact: found (with source and quote), not stated, removed, or "
        "not searched, so the dashboard can say why a value is missing",
    )
    named_by_merchant: bool = Field(
        default=False,
        description="True when the merchant listed this rival; it was researched on top of the "
        "rivals the agent found independently",
    )
    cohort: str = Field(
        default="",
        description="'leapfrog' (grew from the merchant's level, with evidence), 'catching_up' "
        "(peer-size rival accelerating), 'peer', 'larger', 'incumbent', or '' when unknown",
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


class AdAngle(BaseModel):
    """A ready-to-run ad concept aimed at one rival's documented weakness."""

    hook: str = Field(..., description="Headline, under ~10 words")
    body: str = Field(default="", description="One or two sentences of supporting copy")
    target_rival: str = Field(default="", description="Competitor whose buyers this targets")
    format_hint: str = Field(
        default="",
        description="Where it fits best, e.g. 'Google Search', 'Meta feed', 'LinkedIn'",
    )
    based_on_weakness: str = Field(
        default="",
        description="The rival complaint or gap this angle exploits, as found in the research",
    )


class WedgeCandidate(BaseModel):
    """
    One player in the merchant's niche, found by the broad Tier 1 scan.

    Deliberately thin: name, angle, size and when we first saw it. The point of Tier 1 is
    coverage -- not missing an emerging rival -- so depth is left to Tier 2 and to "research
    deeper", which promotes a candidate into a full profile.
    """

    brand_name: str = Field(..., description="Brand as it appears in the evidence")
    url: str | None = Field(default=None, description="Their own site or launch page, when found")
    positioning: str = Field(
        default="",
        description="Their one-line angle, from the evidence. Empty when the evidence states none.",
    )
    scale: str = Field(
        default="unknown",
        description="'peer' (similar size to the merchant), 'larger' (well ahead), 'incumbent' "
        "(category giant) or 'unknown' when the evidence does not say",
    )
    scale_evidence: str = Field(default="", description="What the scale call is based on")
    launch_date: str | None = Field(
        default=None, description="ISO date of a dated launch, funding or 'just launched' signal"
    )
    first_seen: str | None = Field(
        default=None, description="ISO date our scans first surfaced this brand"
    )
    mentions: int = Field(default=0, description="Evidence passages naming it in this scan")
    emerging: bool = Field(
        default=False,
        description="Launched or first seen recently: the rivals most likely to be missed",
    )
    deep_researched: bool = Field(
        default=False, description="True when this brand already has a full profile in the report"
    )
    sources: list[str] = Field(default_factory=list)


class WedgeScan(BaseModel):
    """Tier 1: everyone in the merchant's niche, broad and shallow."""

    wedge: str = Field(default="", description="The niche the scan was scoped to, in one line")
    scanned_at: str = Field(default="", description="ISO date of this scan")
    candidates: list[WedgeCandidate] = Field(default_factory=list)
    new_since_last_scan: list[str] = Field(
        default_factory=list, description="Brands that were not in the previous scan"
    )


class ThreatSignal(BaseModel):
    """One observable momentum signal behind a threat score."""

    key: str = Field(..., description="Stable id, e.g. 'review_velocity'")
    label: str = Field(..., description="Human label, e.g. 'Review growth'")
    value: str = Field(default="", description="Current reading, formatted for display")
    change: str = Field(default="", description="Movement since the baseline scan, when known")
    direction: str = Field(default="flat", description="'up', 'down', 'flat' or 'new'")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="This signal's 0-1 contribution")


class ThreatEntry(BaseModel):
    """Tier 2: one peer rival under momentum watch."""

    brand_name: str
    threat_score: float = Field(default=0.0, ge=0.0, le=1.0)
    momentum: str = Field(
        default="baseline",
        description="'accelerating', 'steady', 'slowing'; 'baseline' on the first scan, when "
        "there is nothing yet to measure against; 'no_data' when a baseline exists but no signal "
        "could be compared (no review counts or ads, or the last scan is under a week old)",
    )
    scale: str = Field(default="unknown")
    headline: str = Field(default="", description="One line on why this rival is worth watching")
    signals: list[ThreatSignal] = Field(default_factory=list)
    what_changed: list[str] = Field(default_factory=list, description="Moves since the last scan")
    counter_move: str = Field(default="", description="What the merchant can do about it")
    snapshot: dict[str, float | int | str | None] = Field(
        default_factory=dict,
        description="Raw readings stored so the next scan can measure velocity against them",
    )


class ThreatWatch(BaseModel):
    """Tier 2 output: the few peer rivals most likely to overtake the merchant."""

    scanned_at: str = Field(default="")
    baseline_date: str | None = Field(
        default=None, description="ISO date of the scan momentum is measured against; null on a first scan"
    )
    watched: list[ThreatEntry] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list, description="Moves that need the merchant's attention")
    method_note: str = Field(
        default="",
        description="What the signals are proxies for, so nobody reads them as revenue figures",
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
    suggested_ad_angles: list[AdAngle] = Field(
        default_factory=list,
        description="Ad concepts generated from the finished research; empty when none were grounded",
    )
    wedge_scan: WedgeScan | None = Field(
        default=None, description="Tier 1: every player found in the merchant's niche"
    )
    threat_watch: ThreatWatch | None = Field(
        default=None, description="Tier 2: momentum tracking on the peer rivals most likely to overtake"
    )
    leap_benchmarks: list[LeapBenchmark] = Field(
        default_factory=list,
        description="Aspirational breakout competitors that started similar to the merchant and took a big leap in clients, deals, and valuation",
    )
