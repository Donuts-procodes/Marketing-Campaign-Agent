export interface TargetMetric {
  name: string;
  target_value: string;
  baseline: string;
  measurement_window: string;
}

export interface ChannelAllocation {
  channel: string;
  budget_percentage: number;
  recommended_spend_usd?: number | null;
  rationale: string;
  projected_roi?: string | null;
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

export interface CampaignStrategyBrief {
  executive_summary: string;
  primary_positioning_pillar: string;
  target_metrics: TargetMetric[];
  channel_matrix: ChannelAllocation[];
  strategic_angles: StrategicAngle[];
  execution_calendar: PhaseMilestone[];
  budget_assumptions: string[];
  approval_status: "PENDING_APPROVAL" | "APPROVED_AND_DISPATCHED";
}
