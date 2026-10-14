export interface TargetMetric {
  name: string;
  target_value: string;
  baseline?: string | null;
  measurement_window?: string;
  is_sub_goal?: boolean;
}

export interface ChannelAllocation {
  channel: string;
  budget_percentage: number;
  recommended_spend_usd?: number | null;
  rationale: string;
  projected_roi?: string | null;
  promotion_tactics?: string[];
  payee_platform?: string;
  purchased_inventory?: string;
  spend_type?: "ad_spend" | "data_tooling" | "asset_production";
}

export interface StrategicAngle {
  angle_title: string;
  target_wedge: string;
  competitor_weakness: string;
  hook: string;
  messaging_pillar: string;
}

export interface PhaseMilestone {
  phase_name: string;
  weeks: string;
  focus: string;
  deliverables: string[];
}

export interface StrategyPrediction {
  // Null unless computed from the merchant's own sales data / unit economics; `basis` says why.
  projected_cac?: string | null;
  projected_roi?: string | null;
  conversion_velocity?: string | null;
  risk_level: "Low" | "Medium" | "High";
  break_even_timeline?: string | null;
  basis?: string;
}

/** Shared with the Audience/Persona Agent (orchestrator/schemas/persona.py). */
export interface PersonaInput {
  persona_id: string;
  name: string;
  description?: string;
  demographics?: Record<string, string>;
  pains?: string[];
  motivations?: string[];
  objections?: string[];
  preferred_channels?: string[];
  buying_triggers?: string[];
  evidence?: string[];
  source: "persona_agent" | "research_derived" | "merchant_input";
  confidence?: number | null;
  fit_score?: number | null;
  role?: "primary" | "challenger" | "later" | null;
}

export interface CompetitorCampaignIntel {
  competitor_name: string;
  campaign_themes: string[];
  detected_channels: string[];
  active_offers_and_hooks: string[];
  blindspots: string[];
  sample_evidence?: string[];
  estimated_monthly_ad_spend?: string | null;
  platform_cost_benchmarks?: Record<string, string>;
  competitor_flagship_clients?: string[];
  competitor_consumer_feedback?: string[];
  competitor_icp?: string | null;
  merchant_icp?: string | null;
}

export interface CampaignStrategyOption {
  option_id: string;
  title: string;
  theme: string;
  tagline: string;
  recommended: boolean;
  budget_allocation_summary: string;
  channel_matrix: ChannelAllocation[];
  advantages: string[];
  disadvantages: string[];
  constraints: string[];
  opportunities: string[];
  suggested_channels?: string[];
  promotion_means?: string[];
  prediction: StrategyPrediction;
}

export interface SubagentDeployment {
  agent_id: string;
  name: string;
  role: string;
  status: "idle" | "ready" | "running" | "completed";
  target_channels: string[];
  deliverables: string[];
  estimated_hours_saved: string;
}

export interface TacticalOutreachBlueprint {
  playbook_id: string;
  channel_name: string;
  who_target_profile: string;
  where_platform: string;
  how_mechanism: string;
  budget_allocation_usd: number;
  budget_share_pct: number;
  duration_and_cadence: string;
  expected_cpa: string;
  assigned_subagent: string;
}

export interface CampaignStrategyBrief {
  executive_summary: string;
  primary_positioning_pillar: string;
  target_metrics: TargetMetric[];
  channel_matrix: ChannelAllocation[];
  suggested_channels?: string[];
  promotion_means?: string[];
  strategic_angles: StrategicAngle[];
  execution_calendar: PhaseMilestone[];
  budget_assumptions: string[];
  user_budget?: number | null;
  /** ISO code every amount in the brief is in (legacy *_usd field names included). */
  currency?: string;
  personas_used?: PersonaInput[];
  market_listings?: string[];
  unknowns?: string[];
  mode?: PlanMode | null;
  plan?: CampaignPlan | null;
  economics?: UnitEconomics | null;
  competitor_campaign_intel?: CompetitorCampaignIntel[];
  campaign_options?: CampaignStrategyOption[];
  selected_option_id?: string | null;
  subagents_roster?: SubagentDeployment[];
  outreach_blueprint?: TacticalOutreachBlueprint[];
  approval_status: "PENDING_APPROVAL" | "APPROVED" | "APPROVED_AND_DISPATCHED";
  campaign_days?: number;
  sub_goals?: string[];
  core_goal?: string | null;
  campaign_type?: string | null;
  messaging?: MessagingStrategy | null;
  budget_given?: boolean;
}

export interface StrategyCustomizeRequest {
  budget?: number;
  selected_option_id?: string;
  custom_goal?: string;
  campaign_days?: number;
  sub_goals?: string[];
  campaign_type?: string;
  custom_option?: CampaignStrategyOption;
}



export type PlanMode = "validate" | "traction" | "scale";

export interface PlanChannel {
  channel: string;
  persona_id: string;
  budget: number;
  spend_type: "ad_spend" | "creator" | "content" | "tools" | "research" | "organic";
  purpose: string;
  tactics: string[];
  evidence: string[];
}

export interface MessageTest {
  test_id: string;
  persona_id: string;
  angle: string;
  hook: string;
  cta: string;
  role: "champion" | "challenger";
  proof_needed: string;
  evidence: string[];
}

export interface PlanPhase {
  name: string;
  days: string;
  budget_ceiling: number;
  objective: string;
  actions: string[];
  decision_gate: string;
}

export interface ReadinessItem {
  item: string;
  reason: string;
  blocking: boolean;
}

export interface CampaignPlan {
  primary_persona_id: string;
  challenger_persona_id?: string | null;
  rationale: string;
  channels: PlanChannel[];
  reserve: number;
  message_tests: MessageTest[];
  phases: PlanPhase[];
  readiness: ReadinessItem[];
  success_metrics: string[];
  questions_for_merchant: string[];
  generated_by: "llm" | "rules";
  validation_notes: string[];
}

export interface UnitEconomics {
  price?: number | null;
  unit_cost?: number | null;
  variable_cost_pct: number;
  contribution_per_unit?: number | null;
  orders_to_break_even?: number | null;
  max_affordable_cac?: number | null;
  note: string;
}

export interface MessagingPillar {
  title: string;
  message: string;
  proof: string;
  needs_proof: boolean;
}

export interface MessagingStrategy {
  positioning: string;
  core_message: string;
  pillars: MessagingPillar[];
}
