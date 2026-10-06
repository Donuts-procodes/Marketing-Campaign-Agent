/**
 * Research domain types matching backend Pydantic models in orchestrator/schemas/research.py
 */

export interface CompetitorProfile {
  brand_name: string;
  product_name: string;
  pricing_model: string | null;
  core_claims: string[];
  weaknesses_mined: string[];
  dynamic_attributes?: Record<string, string>;
  ad_hooks?: string[];
  factual_evidence?: string[];
  sources: string[];
  relevance_score?: number;
  /** One line on why this rival matters to the merchant (LLM relevance filter). */
  relevance_reason?: string;
  /** ISO date of the newest dated evidence, or null when no source carried one. */
  as_of?: string | null;
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
}
