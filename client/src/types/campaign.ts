/**
 * Campaign lifecycle, agent phases, and SSE stream frames.
 */

export type AgentPhase =
  | "MARKET_RESEARCH"
  | "AUDIENCE_PERSONA"
  | "CAMPAIGN_STRATEGY"
  | "MEDIA_GENERATION"
  | "PUBLISHING"
  | "FEEDBACK";

export type PhaseStatus =
  | "IDLE"
  | "RUNNING"
  | "WAITING_APPROVAL"
  | "COMPLETED"
  | "FAILED";

export interface TelemetryLogItem {
  id: string;
  level: "INFO" | "WARN" | "ERROR";
  message: string;
  timestamp: number;
}

export interface NodeStartedEvent {
  type: "NODE_STARTED";
  node: string;
  timestamp: number;
}

export interface NodeCompleteEvent {
  type: "NODE_COMPLETE";
  node: string;
  delta: Record<string, unknown>;
  timestamp: number;
}

export interface TelemetryLogEvent {
  type: "TELEMETRY_LOG";
  level: "INFO" | "WARN" | "ERROR";
  message: string;
  timestamp: number;
}

export interface HitlInterruptEvent {
  type: "HITL_INTERRUPT";
  checkpoint_id: string;
  phase: string;
  prompt: string;
  data: Record<string, unknown>;
}

export interface RunCompleteEvent {
  type: "RUN_COMPLETE";
  job_id: string;
  summary: Record<string, unknown>;
}

export interface RunFailedEvent {
  type: "RUN_FAILED";
  message: string;
  timestamp: number;
}

/** Every server frame carries a monotonically increasing sequence number for resume. */
export type SSEEventPayload = (
  | NodeStartedEvent
  | NodeCompleteEvent
  | TelemetryLogEvent
  | HitlInterruptEvent
  | RunCompleteEvent
  | RunFailedEvent
) & { seq?: number };
