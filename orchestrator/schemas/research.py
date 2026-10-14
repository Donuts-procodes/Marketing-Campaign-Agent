from __future__ import annotations
import re
from typing import Literal, Any

from pydantic import BaseModel, Field, field_validator


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
    commercial_motion: str | None = Field(
        default=None,
        description="Commercial sales motion: 'plg_freemium', 'flat_subscription', 'usage_based', 'sales_gated', 'service_retainer', or null",
    )
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


class BuyingPatternIntelligence(BaseModel):
    """Observable commercial buying pattern, channel distribution, and price architecture."""

    sales_channels: list[str] = Field(
        default_factory=list,
        description="Active sales channels: Brand D2C Website, Amazon Storefront, Walmart, Myntra, TikTok Shop, etc.",
    )
    price_architecture: dict[str, str] = Field(
        default_factory=dict,
        description="Entry price, flagship SKU price, Average Order Value (AOV) indicators, and bundles.",
    )
    promotional_incentives: list[str] = Field(
        default_factory=list,
        description="Active buyer incentives: e.g. '15% off first order', Free shipping over $100, BOGO, Klarna/EMI.",
    )
    sales_velocity_signals: list[str] = Field(
        default_factory=list,
        description="Observed traction signals: Amazon '1k+ bought in past month', review count velocity, Best Seller Rank badges.",
    )
    buying_triggers: list[str] = Field(
        default_factory=list,
        description="Key hesitation reducers: '30-day wear test guarantee', size/fit guides, free exchange policy, durability warranty.",
    )
    trial_structure: str | None = Field(
        default=None,
        description="B2B trial or pilot structure, e.g. '14-day free trial no credit card', 'Interactive sandbox', 'Proof of Concept'.",
    )
    procurement_hurdles: list[str] = Field(
        default_factory=list,
        description="Vendor procurement obstacles: e.g. 'Mandatory annual upfront contract', 'SOC2 / Security questionnaire required', 'Sales-assisted procurement gate'.",
    )
    contract_incentives: list[str] = Field(
        default_factory=list,
        description="Contract commitments or incentives: e.g. '20% off annual commitment', 'Usage volume tiering', 'Custom MSA redlines'.",
    )
    reverse_engineered_strategy: str = Field(
        default="",
        description="Synthesized customer acquisition strategy deduced from their channels, pricing, velocity, and buying incentives.",
    )


class ListingItem(BaseModel):
    """One product card on a store's search, category or brand page."""

    name: str
    url: str = ""
    selling_price: float
    mrp: float | None = None
    rating: float | None = None
    image_url: str | None = None
    avg_90d: float | None = Field(default=None, description="Keepa: 90-day average price (Amazon)")
    min_90d: float | None = None
    sales_rank: int | None = Field(default=None, description="Keepa: current Amazon sales rank (lower sells more)")
    matched_product: str | None = Field(default=None, description="The merchant product this item is closest to")
    variants: int = Field(default=1, description="Size/colour variants folded into this item")


class ChannelListing(BaseModel):
    """
    One place a competitor's product is sold: its own site or a marketplace page, with the price,
    offers and terms shown there on the day we read it. The same shoe is ₹6,999 with a bank offer
    on one marketplace and ₹7,499 with free exchange on the brand site; a single "price" hides that.
    Every value is read from the page text; anything not stated stays null.
    """

    competitor: str = Field(..., description="Brand the listing belongs to")
    product: str = Field(default="", description="Product/model name as listed")
    site: str = Field(..., description="Host, e.g. 'myntra.com', 'amazon.in', 'brand.com'")
    site_type: Literal["d2c", "marketplace", "quick_commerce", "social_shop", "offline_retail"] = "marketplace"
    url: str = ""
    currency: str | None = Field(default=None, description="ISO code of the prices below")
    mrp: float | None = Field(default=None, description="List/MRP price shown, if struck through or stated")
    selling_price: float | None = Field(default=None, description="Price a buyer pays before checkout offers")
    discount_pct: float | None = None
    offers: list[str] = Field(default_factory=list, description="Coupons, bank offers, BOGO, prepaid discounts")
    rating: float | None = None
    review_count: int | None = None
    velocity_signal: str | None = Field(default=None, description="e.g. '500+ bought in past month', 'Bestseller'")
    seller: str | None = Field(default=None, description="Brand-owned store vs third-party reseller")
    delivery: str | None = None
    returns_policy: str | None = None
    cod_available: bool | None = None
    observed_at: str | None = Field(default=None, description="ISO date the page was read; prices move")
    evidence: str = Field(default="", description="Text the values were read from")
    image_url: str | None = Field(default=None, description="Product photo from the listing page, when it has one")
    page_kind: Literal["product", "grid"] = Field(
        default="product",
        description="product: one product's page. grid: a search/category/brand page listing many of the "
        "rival's products; selling_price is then the median and price_from the cheapest",
    )
    price_from: float | None = Field(default=None, description="Cheapest of the rival's products on a grid page")
    product_count: int | None = Field(default=None, description="How many of the rival's products the grid page shows")
    items: list[ListingItem] = Field(default_factory=list, description="The rival's product cards on a grid page")
    merchant_currency: str | None = Field(default=None, description="Set when the listing's currency differs from the merchant's")
    price_in_merchant_currency: float | None = Field(default=None, description="selling_price converted at fx_rate")
    fx_rate: float | None = Field(default=None, description="ECB reference rate used: merchant-currency units per listing-currency unit")
    avg_90d: float | None = Field(default=None, description="Keepa: 90-day average price (Amazon product pages)")
    min_90d: float | None = None
    max_90d: float | None = None
    sales_rank: int | None = Field(default=None, description="Keepa: current Amazon sales rank (lower sells more)")
    sales_rank_drops_30d: int | None = Field(default=None, description="Keepa: rank improvements in 30 days, a proxy for sales")
    matched_product: str | None = Field(
        default=None,
        description="Which of the merchant's products this listing is compared against; null when the "
        "merchant listed a single product or none matched",
    )
    source: Literal["page", "search_snippet", "ai_search", "shopping_api"] = Field(
        default="page",
        description="page: read from the fetched listing page. search_snippet: read from the search "
        "engine's excerpt of that page (the page itself was blocked or script-rendered). ai_search: "
        "returned by a web-search model with this url as its citation, not re-read by us. shopping_api: "
        "Google Shopping offer data (SerpApi).",
    )


class CompetitorProfile(BaseModel):
    """Structured profile extracted per discovered competitor."""

    brand_name: str = Field(..., description="Parent brand (e.g. Logitech)")
    product_name: str = Field(..., description="Specific competing product (e.g. MX Master 3S)")
    buying_patterns: BuyingPatternIntelligence | None = Field(
        default=None,
        description="Observable commercial buying patterns, sales channels, unit economics, and buyer triggers",
    )
    channel_listings: list[ChannelListing] = Field(
        default_factory=list,
        description="Per-site listings (own site and marketplaces) with price, offers, rating and terms",
    )
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
    logo_url: str | None = Field(
        default=None,
        description="High-resolution brand logo URL resolved from domain favicon, OpenGraph, or CDN",
    )
    product_image_url: str | None = Field(
        default=None,
        description="Hero product image URL extracted from product listing or crawl metadata",
    )

    @field_validator("pricing_model", mode="before")
    @classmethod
    def clean_pricing_model(cls, v: Any) -> str | None:
        if v is None:
            return None
        val = str(v).strip()
        if not val or val.lower() in {
            "n/a", "na", "unknown", "none", "null", "undefined", "not specified",
            "not available", "tbd", "unspecified", "varies", "contact",
            "-", "none stated", "not stated",
        }:
            return None
        return val

    @field_validator("rating", mode="before")
    @classmethod
    def validate_rating(cls, v: Any) -> str | None:
        if v is None:
            return None
        val = str(v).strip()
        if not val or val.lower() in {
            "n/a", "na", "unknown", "none", "null", "undefined", "not specified",
            "not available", "tbd", "detected", "-",
        }:
            return None
        m = re.search(r"\b([0-5](?:\.\d{1,2})?)\b", val)
        if m:
            try:
                num = float(m.group(1))
                if 0.0 <= num <= 5.0:
                    return f"{num:.1f}" if "." in m.group(1) else str(int(num))
            except ValueError:
                pass
        return None

    @field_validator("sources", mode="before")
    @classmethod
    def validate_sources(cls, v: Any) -> list[str]:
        if not v or not isinstance(v, list):
            return []
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in v:
            s = str(item).strip()
            if (s.startswith("http://") or s.startswith("https://")) and s not in seen:
                seen.add(s)
                cleaned.append(s)
        return cleaned


class SWOTAnalysis(BaseModel):
    """Evidence-grounded SWOT matrix for the merchant's competitive landscape."""

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)

    @field_validator("strengths", "weaknesses", "opportunities", "threats", mode="before")
    @classmethod
    def clean_swot_items(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for item in v:
            s = str(item).strip()
            if len(s) >= 8 and s.lower() not in {"n/a", "unknown", "none", "tbd"}:
                out.append(s)
        return out


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



class DossierAudit(BaseModel):
    """Critical audit of merchant's product claims, construction, and certification status."""

    verified_claims: list[str] = Field(default_factory=list)
    unsubstantiated_claims: list[str] = Field(
        default_factory=list,
        description="Claims that require physical lab or wear-testing verification before advertising (e.g. 'zero break-in', '12-hour comfort')",
    )
    spec_inconsistencies: list[str] = Field(
        default_factory=list,
        description="Inconsistencies detected in product descriptions (e.g. Goodyear-welted claim vs cemented hybrid sole)",
    )
    regulatory_and_compliance: list[str] = Field(
        default_factory=list,
        description="Applicable mandatory standards, certifications, and compliance requirements (e.g. BIS footwear QCO, GST brackets)",
    )


class UnitEconomicsScenario(BaseModel):
    """One price/CAC scenario in the unit contribution model."""

    label: str = Field(..., description="Scenario name (e.g. 'Base Case', 'Conservative / High Returns')")
    target_price: float = Field(..., description="Gross retail price")
    estimated_bom: float = Field(..., description="Landed manufacturing / BOM cost")
    packaging_and_shipping: float = Field(default=0.0)
    payment_fee: float = Field(default=0.0)
    returns_allowance: float = Field(default=0.0, description="Allowance for size exchanges and return logistics")
    cac: float = Field(default=0.0, description="Blended customer acquisition cost")
    net_revenue_ex_tax: float = Field(default=0.0, description="Revenue excluding applicable taxes")
    contribution_per_unit: float = Field(default=0.0, description="Net contribution before fixed overhead")
    contribution_margin_pct: float = Field(default=0.0, description="Contribution margin as a percentage")


class UnitEconomicsModel(BaseModel):
    """Unit economics simulation for merchant's flagship product."""

    scenarios: list[UnitEconomicsScenario] = Field(default_factory=list)
    tax_treatment_note: str = Field(default="")
    break_even_units_per_month: int | None = Field(default=None)
    financial_decision_rules: list[str] = Field(default_factory=list)


class LaunchRoadmapPhase(BaseModel):
    """One 30-day block in the 90-day launch roadmap."""

    phase_name: str = Field(..., description="e.g. 'Days 1–30: Validate the Product'")
    objective: str = Field(...)
    action_items: list[str] = Field(default_factory=list)
    gate_to_proceed: str = Field(..., description="Quantifiable criteria required to unlock the next phase")


class LaunchRoadmap(BaseModel):
    """Structured 30-60-90 day GTM execution roadmap."""

    phases: list[LaunchRoadmapPhase] = Field(default_factory=list)
    key_metrics_dashboard: list[dict[str, str]] = Field(default_factory=list)


class SourcedPoint(BaseModel):
    """One market or audience statement and where it came from."""

    text: str
    source_url: str | None = Field(default=None, description="Page it was read from; null when from the merchant's brief")
    from_merchant: bool = Field(default=False, description="Taken from the merchant's own brief or documents")


class MarketTrend(SourcedPoint):
    signal: Literal["rising", "falling", "new", "steady"] = "rising"


class MarketOverview(BaseModel):
    """The market around the rivals: what is moving and where the openings are. Every point is sourced."""

    summary: str = ""
    key_findings: list[SourcedPoint] = Field(default_factory=list)
    positioning_opportunities: list[SourcedPoint] = Field(default_factory=list)
    trends: list[MarketTrend] = Field(default_factory=list)


class IdealCustomerProfile(BaseModel):
    name: str = ""
    description: str = ""
    attributes: dict[str, str] = Field(default_factory=dict, description="e.g. age band, city tier, income, occasion")
    why: list[SourcedPoint] = Field(default_factory=list, description="Why this is the customer to win first")
    fit_signals: list[str] = Field(default_factory=list)
    low_fit_signals: list[str] = Field(default_factory=list)


class AudienceSegment(BaseModel):
    name: str
    definition: str = ""
    trigger: str = ""
    size_note: str | None = Field(default=None, description="Only a size stated by a source or the merchant; never estimated")
    source_url: str | None = None


class ReachChannel(SourcedPoint):
    """Where the audience can be reached (text is the channel name) and why."""

    reason: str = ""


class AudienceProfile(BaseModel):
    """Who to sell to, built from rival reviews, buying patterns, market pages and the merchant's brief."""

    icp: IdealCustomerProfile | None = None
    segments: list[AudienceSegment] = Field(default_factory=list)
    pains: list[SourcedPoint] = Field(default_factory=list)
    motivations: list[SourcedPoint] = Field(default_factory=list)
    behaviors: list[SourcedPoint] = Field(default_factory=list)
    triggers: list[SourcedPoint] = Field(default_factory=list)
    barriers: list[SourcedPoint] = Field(default_factory=list)
    channels: list[ReachChannel] = Field(default_factory=list)
    preferred_message: str = ""


class DemandPoint(BaseModel):
    date: str
    value: int = Field(description="Google Trends interest, 0-100 relative to the period's peak")


class TrendingSearch(BaseModel):
    query: str
    growth: str = Field(default="", description="As Google reports it, e.g. '+40%' or 'Breakout'")


class MarketDemand(BaseModel):
    """How demand for the category is moving, from search interest and marketplace purchase badges."""

    keyword: str
    geo: str = ""
    source: str = "Google Trends"
    available: bool = True
    unavailable_reason: str | None = None
    series: list[DemandPoint] = Field(default_factory=list)
    direction: Literal["rising", "falling", "flat"] = "flat"
    change_pct: float | None = Field(default=None, description="Last 13 weeks vs the 13 before, %")
    current_vs_year_pct: float | None = Field(default=None, description="Last 4 weeks vs the 12-month average, %")
    peak_months: list[str] = Field(default_factory=list)
    low_months: list[str] = Field(default_factory=list)
    rising_searches: list[TrendingSearch] = Field(default_factory=list)
    top_searches: list[str] = Field(default_factory=list)
    purchase_signals: list[str] = Field(default_factory=list, description="'500+ bought in past month' badges on rival listings")
    monthly_volume: int | None = Field(default=None, description="DataForSEO / Google Ads: average monthly searches for the keyword")
    cpc: float | None = Field(default=None, description="Google Ads average cost per click, in the account currency")
    competition: str | None = Field(default=None, description="Google Ads advertiser competition: LOW / MEDIUM / HIGH")
    keyword_volumes: list[dict] = Field(default_factory=list, description="[{keyword, volume, cpc}] for related searches")
    volume_series: list[DemandPoint] = Field(default_factory=list, description="Monthly search counts (absolute)")
    mood: str = Field(default="", description="One line composed from the figures above")


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
    dossier_audit: DossierAudit | None = Field(
        default=None,
        description="Critical audit of merchant product claims, specifications, and certification gaps",
    )
    unit_economics: UnitEconomicsModel | None = Field(
        default=None,
        description="Financial unit economics and contribution margin model across test price points",
    )
    market_overview: MarketOverview | None = Field(
        default=None, description="Market findings, trends and positioning openings, each with its source"
    )
    demand: MarketDemand | None = Field(default=None, description="Search-interest trend, seasonality and rising searches")
    audience: AudienceProfile | None = Field(
        default=None, description="ICP, segments, pains, triggers and channels, each with its source"
    )
    launch_roadmap: LaunchRoadmap | None = Field(
        default=None,
        description="30-60-90 day phased go-to-market validation roadmap and decision gates",
    )

