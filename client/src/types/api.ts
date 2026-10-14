/**
 * Ingress payloads, endpoint contracts, and Bring-Your-Own-Key (BYOK) specifications.
 */

export type BYOKProvider = "openai" | "anthropic" | "gemini";

export interface ModelDescriptor {
  id: string;
  name: string;
  provider: BYOKProvider;
  recommended?: boolean;
}

/**
 * Model IDs sent as-is to the provider's API. Only list IDs the provider actually serves;
 * an unknown ID fails the run with "model not found".
 */
export const AVAILABLE_MODELS: Record<BYOKProvider, ModelDescriptor[]> = {
  openai: [
    { id: "gpt-4o", name: "GPT-4o", provider: "openai", recommended: true },
    { id: "gpt-4o-mini", name: "GPT-4o mini", provider: "openai" },
    { id: "o3-mini", name: "o3-mini", provider: "openai" },
  ],
  anthropic: [
    { id: "claude-opus-5-5", name: "Claude Opus 5.5", provider: "anthropic", recommended: true },
    { id: "claude-sonnet-5-5", name: "Claude Sonnet 5.5", provider: "anthropic" },
    { id: "claude-haiku-4-5-20251001", name: "Claude Haiku 4.5", provider: "anthropic" },
  ],
  gemini: [
    { id: "gemini-2.5-pro", name: "Gemini 2.5 Pro", provider: "gemini", recommended: true },
    { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash", provider: "gemini" },
    { id: "gemini-2.0-flash", name: "Gemini 2.0 Flash", provider: "gemini" },
  ],
};

export interface BYOKConfig {
  provider: BYOKProvider;
  model: string;
  api_key: string;
  custom_endpoint?: string;
}

import type { CompetitorProfile, SWOTReportDelta } from "./research";
import type { CampaignStrategyBrief } from "./strategy";

/** One product in the merchant's line; competitor prices are compared per product. */
export interface MerchantProduct {
  name: string;
  category?: string;
  price?: number;
  mrp?: number;
}

export interface MerchantContext {
  product_name: string;
  category: string;
  primary_value_prop: string;
  goal?: string;
  price_usd?: number;
  products?: MerchantProduct[];
  known_competitors?: string[];
  existing_customer_profiles?: string[];
  target_geography?: string;
}

export interface CampaignInitPayload {
  merchant_context: MerchantContext;
  byok_config?: BYOKConfig;
  run_mode?: "fresh" | "update";
}

export interface PriorRunInfo {
  found: boolean;
  job_id: string | null;
  finished_at: string | null;
  dqs_score: number | null;
  competitor_count: number | null;
}

export interface CreateJobResponse {
  job_id: string;
  status: string;
}

export interface UploadedFileInfo {
  filename: string;
  characters: number;
}

export interface UploadDossierResponse {
  status: string;
  characters: number;
  filename: string;
  files: UploadedFileInfo[];
}

/** Form fields read from uploaded documents; null / empty when the documents do not state them. */
export interface AutofillFields {
  product_name: string | null;
  category: string | null;
  primary_value_prop: string | null;
  goal: string | null;
  price_usd: number | null;
  known_competitors: string[];
  existing_customer_profiles: string[];
  target_geography?: string | null;
}

export interface AutofillResponse {
  fields: AutofillFields;
  filled: string[];
  files: UploadedFileInfo[];
}

export interface ResolveInterruptPayload {
  checkpoint_id: string;
  action: "APPROVED" | "REVISED";
  feedback?: string;
}

export interface SessionSummary {
  job_id: string;
  status: string;
  label: string | null;
  finished_at: string | null;
  product_name: string | null;
  category: string | null;
}

export interface SessionListResponse {
  sessions: SessionSummary[];
}

export interface SessionDetailResponse {
  job_id: string;
  status: string;
  label: string | null;
  finished_at: string | null;
  merchant_context: Record<string, unknown>;
  swot_report: SWOTReportDelta | null;
  strategy_brief?: CampaignStrategyBrief | null;
  events: Array<Record<string, unknown>>;
}

export interface ResolveInterruptResponse {
  status: string;
}

export interface MoreCompetitorsResponse {
  status: string;
  added_competitors: CompetitorProfile[];
  total_competitors: number;
  swot_report: SWOTReportDelta;
}

export interface ReResearchResponse {
  status: string;
  swot_report: SWOTReportDelta;
}
