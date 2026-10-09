/**
 * Research domain types matching backend Pydantic models in orchestrator/schemas/research.py
 */

/** One observed difference between two scans of the same competitor. */
export interface CompetitorChange {
  observed_at: string;
  field: string;
  previous: string | null;
  current: string | null;
  /** "merchant" when you corrected the value yourself rather than a scan observing it. */
  source?: string | null;
}

/** One recurring review theme, with the mechanism behind it rather than just the gripe. */
export interface ReviewAspect {
  topic: string;
  /** "negative" | "positive" | "mixed" — free-text on the wire. */
  sentiment?: string;
  summary?: string;
  /** The design limit, policy or process that keeps producing this theme. */
  root_cause?: string;
  affected_personas?: string[];
  sample_quotes?: string[];
  /** Counter-positioning move this theme opens up for you. */
  merchant_opportunity?: string;
}

/** Synthesized context behind one rival's customer reviews. */
export interface CompetitorReviewContext {
  brand_name: string;
  product_name?: string;
  overall_sentiment_consensus?: string;
  buyer_personas?: string[];
  top_praise_drivers?: ReviewAspect[];
  top_complaint_drivers?: ReviewAspect[];
  unmet_customer_needs?: string[];
  counter_positioning_angle?: string;
}

/** pricing_model parsed into comparable parts. */
export interface PricingTier {
  tier_name?: string | null;
  amount?: number | null;
  currency?: string | null;
  /** "monthly" | "annual" | "one_time" | "project" | "hourly" | "usage" */
  period?: string | null;
  monthly_equivalent?: number | null;
  has_free_tier?: boolean;
  raw?: string;
}

/** Ready-to-run ad concept aimed at one rival's documented weakness. */
export interface AdAngle {
  hook: string;
  body?: string;
  target_rival?: string;
  format_hint?: string;
  based_on_weakness?: string;
}

/** A competitor that started as a similar peer and took a big leap in clients, deals, and scale. */
export interface LeapBenchmark {
  brand_name: string;
  origin_story?: string;
  current_scale?: string;
  flagship_clients?: string[];
  network_and_deals?: string[];
  pricing_power_leap?: string;
  leap_catalysts?: string[];
  merchant_takeaway_playbook?: string[];
}

/** Tier 1: one player found in your niche by the broad scan. */
export interface WedgeCandidate {
  brand_name: string;
  url?: string | null;
  positioning?: string;
  /** "peer" | "larger" | "incumbent" | "unknown" */
  scale?: string;
  scale_evidence?: string;
  launch_date?: string | null;
  first_seen?: string | null;
  mentions?: number;
  emerging?: boolean;
  deep_researched?: boolean;
  sources?: string[];
}

export interface WedgeScan {
  wedge?: string;
  scanned_at?: string;
  candidates: WedgeCandidate[];
  new_since_last_scan?: string[];
}

export interface ThreatSignal {
  key: string;
  label: string;
  value?: string;
  change?: string;
  /** "up" | "down" | "flat" | "new" */
  direction?: string;
  score?: number;
}

/** Tier 2: one peer rival under momentum watch. */
export interface ThreatEntry {
  brand_name: string;
  threat_score: number;
  /** "accelerating" | "steady" | "slowing" | "baseline" | "no_data" */
  momentum: string;
  scale?: string;
  headline?: string;
  signals?: ThreatSignal[];
  what_changed?: string[];
  counter_move?: string;
}

export interface ThreatWatch {
  scanned_at?: string;
  baseline_date?: string | null;
  watched: ThreatEntry[];
  alerts?: string[];
  method_note?: string;
}

/** Why one profile fact holds its value, or why it is empty. */
export interface FieldStatus {
  /** "found" | "not_stated" | "removed" | "not_searched" */
  status: string;
  source_url?: string | null;
  quote?: string | null;
  reason?: string;
  pages_checked?: number;
}

export interface CompetitorProfile {
  brand_name: string;
  product_name: string;
  pricing_model: string | null;
  core_claims: string[];
  weaknesses_mined: string[];
  /** Praise from the same review pages the complaints come from. */
  strengths_mined?: string[];
  /** Average review score on a 0-5 scale, as stated on a review page. */
  rating?: string | null;
  review_count?: number | null;
  dynamic_attributes?: Record<string, string>;
  ad_hooks?: string[];
  factual_evidence?: string[];
  sources: string[];
  relevance_score?: number;
  /** One line on why this rival matters to the merchant (LLM relevance filter). */
  relevance_reason?: string;
  /** ISO date of the newest dated evidence, or null when no source carried one. */
  as_of?: string | null;
  /** Founding year as stated on their own pages. */
  founded?: string | null;
  /** Primary office location or headquarters. */
  headquarters?: string | null;
  /** Operating regions, branch offices, service territories, or countries. */
  operating_locations?: string[];
  /** Other notable products or models in their catalog. */
  other_products?: string[];
  /** Total count or estimated count of products/models in catalog. */
  product_catalog_count?: number | null;
  /** Dated company/product events, verbatim from their pages. */
  milestones?: string[];
  /** What moved between our own scans — the one history no single page states. */
  change_history?: CompetitorChange[];
  /** Why customers praise/complain, who they are, and how to win them. Null when no reviews. */
  review_context?: CompetitorReviewContext | null;
  pricing_parsed?: PricingTier | null;
  leap_benchmark?: LeapBenchmark | null;
  /** Team size, revenue and funding exactly as a page states them; never estimated. */
  employee_count?: string | null;
  annual_revenue?: string | null;
  funding?: string | null;
  /** Per fact: where it came from, or why it is missing. */
  fact_status?: Record<string, FieldStatus>;
  /** "leapfrog" | "catching_up" | "peer" | "larger" | "incumbent" | "" */
  cohort?: string;
  /** You listed this rival; it was researched on top of the ones found independently. */
  named_by_merchant?: boolean;
}

export interface DynamicParameterTaxonomy {
  critical_jtbd_drivers: string[];
  minor_attributes: string[];
}

export interface SWOTAnalysis {
  strengths: string[];
  weaknesses: string[];
  opportunities: string[];
  threats: string[];
}

export interface MarketPositioningGap {
  quadrant: string;
  hook_angle: string;
}

export interface CompetitorRelevance {
  index: number;
  score: number;
  reason: string;
}

export interface DashboardInsights {
  executive_summary: string;
  primary_competitor_indices: number[];
  competitor_relevance?: CompetitorRelevance[];
  highlight_weaknesses: string[];
  highlight_opportunities: string[];
  priority_attributes: string[];
  recommended_actions: string[];
}

export interface SWOTReportDelta {
  competitors: CompetitorProfile[];
  swot?: SWOTAnalysis;
  swot_analysis?: SWOTAnalysis;
  positioning_gap?: MarketPositioningGap | null;
  market_positioning_gap?: MarketPositioningGap | null;
  dqs_score: number;
  assumptions_tagged: boolean;
  source_urls: string[];
  dqs_diagnostics?: string[];
  dynamic_taxonomy?: DynamicParameterTaxonomy;
  attribute_density?: number;
  validation_diagnostics?: string[];
  dashboard_insights?: DashboardInsights | null;
  /** True when the server had no API keys and returned built-in sample data. */
  sample_data?: boolean;
  suggested_ad_angles?: AdAngle[];
  wedge_scan?: WedgeScan | null;
  threat_watch?: ThreatWatch | null;
  leap_benchmarks?: LeapBenchmark[];
}
