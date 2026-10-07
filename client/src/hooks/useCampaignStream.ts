import { useCallback, useEffect, useRef, useState } from "react";
import { getCampaignStreamUrl, getSession, resolveInterrupt } from "@/lib/api-client";
import {
  AgentPhase,
  NodeCompleteEvent,
  NodeStartedEvent,
  SSEEventPayload,
  TelemetryLogItem,
} from "@/types/campaign";
import { SWOTReportDelta } from "@/types/research";

export type ConnectionStatus =
  | "IDLE"
  | "CONNECTING"
  | "STREAMING"
  | "RECONNECTING"
  | "INTERRUPTED"
  | "COMPLETED"
  | "ERROR";

export interface HitlState {
  checkpoint_id: string;
  phase: string;
  prompt: string;
  data: Record<string, unknown>;
}

export interface StreamState {
  connectionStatus: ConnectionStatus;
  activePhase: AgentPhase | null;
  completedPhases: AgentPhase[];
  telemetryLogs: TelemetryLogItem[];
  swotReport: SWOTReportDelta | null;
  hitlCheckpoint: HitlState | null;
  error: string | null;
  jobId: string | null;
}

const INITIAL_STATE: StreamState = {
  connectionStatus: "IDLE",
  activePhase: null,
  completedPhases: [],
  telemetryLogs: [],
  swotReport: null,
  hitlCheckpoint: null,
  error: null,
  jobId: null,
};

function normalizePhase(node: string): AgentPhase {
  const upper = node.toUpperCase().replace(/-/g, "_");
  if (upper.includes("RESEARCH")) return "MARKET_RESEARCH";
  if (upper.includes("PERSONA") || upper.includes("AUDIENCE")) return "AUDIENCE_PERSONA";
  if (upper.includes("STRATEGY") || upper.includes("CAMPAIGN")) return "CAMPAIGN_STRATEGY";
  if (upper.includes("MEDIA")) return "MEDIA_GENERATION";
  if (upper.includes("PUBLISH")) return "PUBLISHING";
  if (upper.includes("FEEDBACK")) return "FEEDBACK";
  return "MARKET_RESEARCH";
}

export function useCampaignStream(jobId: string | null | undefined) {
  const [state, setState] = useState<StreamState>(() => ({
    ...INITIAL_STATE,
    jobId: jobId ?? null,
  }));

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  // Highest event sequence number applied; reconnects resume after it so nothing is duplicated.
  const lastSeqRef = useRef<number>(-1);
  // Set once RUN_COMPLETE / RUN_FAILED arrives: the server then closes the stream on purpose.
  const finishedRef = useRef<boolean>(false);

  const clearTimers = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const closeStream = useCallback(() => {
    clearTimers();
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, [clearTimers]);

  const handleStreamPayload = useCallback((payload: SSEEventPayload) => {
    switch (payload.type) {
      case "NODE_STARTED": {
        const p = payload as NodeStartedEvent;
        const phase = normalizePhase(p.node);
        setState((s) => ({
          ...s,
          activePhase: phase,
          telemetryLogs: [
            ...s.telemetryLogs,
            {
              id: `started-${Date.now()}-${Math.random()}`,
              level: "INFO",
              message: `Started execution node: ${p.node}`,
              timestamp: p.timestamp || Date.now(),
            },
          ],
        }));
        break;
      }
      case "NODE_COMPLETE": {
        const p = payload as NodeCompleteEvent;
        const phase = normalizePhase(p.node);
        setState((s) => {
          const updatedCompleted = s.completedPhases.includes(phase)
            ? s.completedPhases
            : [...s.completedPhases, phase];

          let swotUpdate = s.swotReport;
          if (p.delta && typeof p.delta === "object") {
            const rawSwot = (p.delta as Record<string, unknown>).swot_report;
            if (rawSwot && typeof rawSwot === "object") {
              swotUpdate = rawSwot as unknown as SWOTReportDelta;
            }
          }

          return {
            ...s,
            completedPhases: updatedCompleted,
            swotReport: swotUpdate,
            telemetryLogs: [
              ...s.telemetryLogs,
              {
                id: `complete-${Date.now()}-${Math.random()}`,
                level: "INFO",
                message: `Completed execution node: ${p.node}`,
                timestamp: p.timestamp || Date.now(),
              },
            ],
          };
        });
        break;
      }
      case "TELEMETRY_LOG": {
        setState((s) => ({
          ...s,
          telemetryLogs: [
            ...s.telemetryLogs,
            {
              id: `log-${Date.now()}-${Math.random()}`,
              level: payload.level,
              message: payload.message,
              timestamp: payload.timestamp || Date.now(),
            },
          ],
        }));
        break;
      }
      case "HITL_INTERRUPT": {
        setState((s) => ({
          ...s,
          connectionStatus: "INTERRUPTED",
          hitlCheckpoint: {
            checkpoint_id: payload.checkpoint_id,
            phase: payload.phase,
            prompt: payload.prompt,
            data: payload.data,
          },
        }));
        break;
      }
      case "RUN_FAILED": {
        setState((s) => ({
          ...s,
          connectionStatus: "ERROR",
          activePhase: null,
          error: payload.message,
          telemetryLogs: [
            ...s.telemetryLogs,
            {
              id: `run-failed-${Date.now()}`,
              level: "ERROR",
              message: payload.message,
              timestamp: payload.timestamp || Date.now(),
            },
          ],
        }));
        break;
      }
      case "RUN_COMPLETE": {
        setState((s) => ({
          ...s,
          connectionStatus: "COMPLETED",
          activePhase: null,
          telemetryLogs: [
            ...s.telemetryLogs,
            {
              id: `run-complete-${Date.now()}`,
              level: "INFO",
              message: "Orchestration run completed successfully.",
              timestamp: Date.now(),
            },
          ],
        }));
        break;
      }
    }
  }, []);

  const connect = useCallback((force: boolean = false) => {
    if (!jobId) return;
    if (force) {
      finishedRef.current = false;
      reconnectAttemptsRef.current = 0;
    } else if (finishedRef.current) {
      return;
    }

    closeStream();

    setState((s) => ({
      ...s,
      connectionStatus: "CONNECTING",
      error: null,
      jobId,
    }));

    const url = getCampaignStreamUrl(jobId, lastSeqRef.current);
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => {
      reconnectAttemptsRef.current = 0;
      setState((s) => ({ ...s, connectionStatus: "STREAMING" }));
    };

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;

      // A finished run or one with an existing report closes the stream deliberately; that is not a connection failure.
      if (finishedRef.current) return;

      // If we already received completed data or terminal state, mark completed instead of looping
      setState((prev) => {
        if (prev.connectionStatus === "COMPLETED" || (prev.swotReport && prev.swotReport.competitors.length > 0)) {
          finishedRef.current = true;
          return { ...prev, connectionStatus: "COMPLETED", activePhase: null };
        }
        if (reconnectAttemptsRef.current < 4) {
          reconnectAttemptsRef.current += 1;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current - 1), 8000);
          reconnectTimeoutRef.current = window.setTimeout(connect, delay);
          return { ...prev, connectionStatus: "RECONNECTING" };
        }
        return {
          ...prev,
          connectionStatus: "ERROR",
          error: "Stream connection lost after multiple retry attempts.",
        };
      });
    };

    es.onmessage = (event) => {
      let payload: SSEEventPayload;
      try {
        payload = JSON.parse(event.data);
      } catch (err) {
        console.warn("Failed to parse SSE payload:", err, event.data);
        return;
      }
      if (typeof payload.seq === "number") {
        if (payload.seq <= lastSeqRef.current) return; // already applied
        lastSeqRef.current = payload.seq;
      }
      handleStreamPayload(payload);
      if (payload.type === "RUN_COMPLETE" || payload.type === "RUN_FAILED") {
        finishedRef.current = true;
        es.close();
        eventSourceRef.current = null;
      }
    };
  }, [jobId, closeStream, handleStreamPayload]);

  const resolveInterruptAction = useCallback(
    async (action: "APPROVED" | "REVISED", feedback?: string) => {
      if (!state.hitlCheckpoint) return;

      const checkpointId = state.hitlCheckpoint.checkpoint_id;

      // Optimistic update
      setState((s) => ({
        ...s,
        connectionStatus: "STREAMING",
        hitlCheckpoint: null,
        activePhase: action === "APPROVED" ? "AUDIENCE_PERSONA" : s.activePhase,
        telemetryLogs: [
          ...s.telemetryLogs,
          {
            id: `hitl-${Date.now()}`,
            level: "INFO",
            message: `HITL Decision: ${action}${feedback ? ` ("${feedback}")` : ""}`,
            timestamp: Date.now(),
          },
        ],
      }));

      if (jobId) {
        try {
          await resolveInterrupt(
            jobId,
            checkpointId,
            action,
            feedback
          );
        } catch (err) {
          console.error("Failed to submit HITL decision to backend:", err);
        }
      }
    },
    [state.hitlCheckpoint, jobId]
  );

  useEffect(() => {
    if (!jobId) {
      setState({ ...INITIAL_STATE, jobId: null });
      return;
    }

    // Reset state for new jobId
    lastSeqRef.current = -1;
    finishedRef.current = false;
    reconnectAttemptsRef.current = 0;
    setState({
      ...INITIAL_STATE,
      jobId,
      connectionStatus: "CONNECTING",
    });

    let isMounted = true;

    // Direct REST fetch to instantly hydrate finished/saved runs or pre-populate data
    getSession(jobId)
      .then((detail) => {
        if (!isMounted) return;
        if (detail.swot_report) {
          const logs: TelemetryLogItem[] = (detail.events || [])
            .filter((e) => e.type === "TELEMETRY_LOG" || e.type === "NODE_STARTED" || e.type === "NODE_COMPLETE")
            .map((e, idx) => ({
              id: `rest-${idx}-${Date.now()}`,
              level: (e.level as "INFO" | "WARN" | "ERROR") || "INFO",
              message: (e.message as string) || (e.node ? `${e.type}: ${e.node}` : ""),
              timestamp: (e.timestamp as number) || Date.now(),
            }));

          const completedPhases: AgentPhase[] = [];
          if (detail.swot_report) completedPhases.push("MARKET_RESEARCH");
          if (detail.status === "complete") {
            completedPhases.push("AUDIENCE_PERSONA", "CAMPAIGN_STRATEGY");
          }

          setState((s) => ({
            ...s,
            jobId,
            swotReport: detail.swot_report,
            connectionStatus: detail.status === "complete" ? "COMPLETED" : (s.connectionStatus === "CONNECTING" ? "STREAMING" : s.connectionStatus),
            completedPhases: Array.from(new Set([...s.completedPhases, ...completedPhases])),
            telemetryLogs: logs.length > 0 ? logs : s.telemetryLogs,
            activePhase: detail.status === "complete" ? null : s.activePhase,
          }));

          if (detail.status === "complete") {
            finishedRef.current = true;
            return;
          }
        }
        connect();
      })
      .catch(() => {
        if (!isMounted) return;
        connect();
      });

    return () => {
      isMounted = false;
      closeStream();
    };
  }, [jobId, connect, closeStream]);

  /** Applies a report returned directly by an API call (e.g. find-more-competitors). */
  const applyReport = useCallback((report: SWOTReportDelta) => {
    setState((s) => ({ ...s, swotReport: report }));
  }, []);

  return {
    state,
    reconnect: connect,
    resolveInterruptAction,
    applyReport,
  };
}
