/**
 * HTTP Client communicating with FastAPI Gateway.
 */

import {
  AutofillResponse,
  BYOKConfig,
  CampaignInitPayload,
  CreateJobResponse,
  MoreCompetitorsResponse,
  PriorRunInfo,
  ReResearchResponse,
  ResolveInterruptPayload,
  ResolveInterruptResponse,
  SessionDetailResponse,
  SessionListResponse,
  SessionSummary,
  UploadDossierResponse,
} from "@/types/api";
import type { SWOTReportDelta } from "@/types/research";
import type { CampaignStrategyBrief, StrategyCustomizeRequest } from "@/types/strategy";
import type { ChannelKey, ContentAsset, ContentPack } from "@/types/content";

const API_BASE_URL =
  import.meta.env.VITE_API_URL?.replace(/\/$/, "") || "";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorDetails: unknown;
    try {
      errorDetails = await response.json();
    } catch {
      errorDetails = await response.text();
    }
    // FastAPI sends a string detail for HTTPException and a list for validation errors.
    const rawDetail =
      errorDetails && typeof errorDetails === "object" && "detail" in errorDetails
        ? (errorDetails as { detail: unknown }).detail
        : null;
    const detail =
      typeof rawDetail === "string"
        ? rawDetail
        : Array.isArray(rawDetail)
          ? rawDetail
              .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d)))
              .join("; ")
          : null;
    throw new ApiError(
      detail ?? `API Request failed with status ${response.status}`,
      response.status,
      errorDetails
    );
  }
  return response.json();
}

/**
 * Dispatches a new campaign execution job to the FastAPI Gateway.
 */
export async function createCampaignJob(
  payload: CampaignInitPayload
): Promise<CreateJobResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/campaigns`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleResponse<CreateJobResponse>(response);
}

/**
 * Checks whether a completed run already exists for the given product and category.
 * Used to show the Update / Fresh scan mode selector before launching.
 */
export async function checkPriorRun(
  productName: string,
  category: string = ""
): Promise<PriorRunInfo> {
  const params = new URLSearchParams({ product_name: productName });
  if (category) params.set("category", category);
  const response = await fetch(
    `${API_BASE_URL}/api/v1/campaigns/prior-run?${params.toString()}`
  );
  return handleResponse<PriorRunInfo>(response);
}

/**
 * Interprets free-form user text (even vague goal statements) into structured merchant
 * context fields. Unlike autofillFromFiles, this actively infers missing context via LLM.
 */
export async function interpretQuery(text: string): Promise<AutofillResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/campaigns/interpret`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return handleResponse<AutofillResponse>(response);
}

/**
 * Reads the campaign form fields out of one or more documents (PDF, DOCX, TXT, MD, JSON).
 */
export async function autofillFromFiles(files: File[], byokConfig?: BYOKConfig): Promise<AutofillResponse> {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  if (byokConfig) {
    formData.append("byok_config", JSON.stringify(byokConfig));
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/campaigns/autofill`, {
    method: "POST",
    body: formData,
  });

  return handleResponse<AutofillResponse>(response);
}

/**
 * Uploads one or more merchant dossiers (PDF, DOCX, TXT, MD, JSON) to a campaign job.
 */
export async function uploadDossiers(
  jobId: string,
  files: File[]
): Promise<UploadDossierResponse> {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));

  const response = await fetch(
    `${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/dossier`,
    {
      method: "POST",
      body: formData,
    }
  );

  return handleResponse<UploadDossierResponse>(response);
}

/**
 * Resolves a Human-in-the-Loop (HITL) interrupt checkpoint on a paused LangGraph thread.
 */
export async function resolveInterrupt(
  jobId: string,
  checkpointId: string,
  action: "APPROVED" | "REVISED",
  feedback?: string
): Promise<ResolveInterruptResponse> {
  const payload: ResolveInterruptPayload = {
    checkpoint_id: checkpointId,
    action,
    feedback,
  };

  const response = await fetch(
    `${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/resolve-interrupt`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );

  return handleResponse<ResolveInterruptResponse>(response);
}

/**
 * Lists recent campaign sessions (in-memory and saved), newest first.
 */
export async function listSessions(limit = 50): Promise<SessionListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/campaigns/sessions?limit=${limit}`);
  return handleResponse<SessionListResponse>(response);
}

/**
 * Fetches full details, report, and events for a session.
 */
export async function getSession(jobId: string): Promise<SessionDetailResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}`);
  return handleResponse<SessionDetailResponse>(response);
}

/**
 * Renames a session.
 */
export async function renameSession(jobId: string, label: string): Promise<SessionSummary> {
  const response = await fetch(`${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  return handleResponse<SessionSummary>(response);
}

/**
 * Deletes a session from memory and storage.
 */
export async function deleteSession(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 204) {
    await handleResponse<unknown>(response);
  }
}

/**
 * Constructs the SSE streaming URL for a specific campaign execution.
 */
export function getCampaignStreamUrl(jobId: string, afterSeq = -1): string {
  const base = `${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/stream`;
  return afterSeq >= 0 ? `${base}?after=${afterSeq}` : base;
}

/**
 * Triggers an on-demand web search for additional competitors.
 */
export async function fetchMoreCompetitors(
  jobId: string,
  names: string[] = []
): Promise<MoreCompetitorsResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/more-competitors`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ names }),
    }
  );
  return handleResponse<MoreCompetitorsResponse>(response);
}

export interface ReportEdit {
  op: "remove_item" | "set_price" | "set_rating" | "remove_competitor";
  competitor: string;
  field?: string | null;
  value?: string | null;
}

/** Applies merchant corrections to the report; all edits apply together or none do. */
export async function applyReportEdits(
  jobId: string,
  edits: ReportEdit[]
): Promise<{ applied: string[]; swot_report: SWOTReportDelta }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/report/edits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edits }),
  });
  return handleResponse(response);
}

/**
 * Triggers a complete re-research run for the active campaign.
 */
export async function reResearchCampaign(
  jobId: string
): Promise<ReResearchResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/re-research`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  return handleResponse<ReResearchResponse>(response);
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

/** A change the assistant proposed; it only runs when the merchant confirms it. */
export interface ChatAction {
  id: string;
  kind:
    | "refresh"
    | "research"
    | "edit"
    | "update_context"
    | "customize_strategy"
    | "rewrite_asset"
    | "channel_approval"
    | "reschedule"
    | "regenerate_content";
  title: string;
  detail: string;
  payload: {
    names?: string[];
    edits?: ReportEdit[];
    field?: string;
    value?: unknown;
    reasoning?: string;
    budget?: number;
    campaign_days?: number;
    sub_goals?: string[];
    add_sub_goal?: string;
    campaign_type?: string;
    selected_option_id?: string;
    custom_goal?: string;
    asset_id?: string;
    instruction?: string;
    channel?: string;
    approved?: boolean;
    shift_days?: number;
    time_of_day?: string;
    asset_ids?: string[];
    reason?: string;
  };
}

/** Updates initial merchant brief context or campaign goal (HITL). */
export async function updateMerchantContext(
  jobId: string,
  field: string,
  value: unknown
): Promise<{ status: string; applied: string; merchant_context: Record<string, unknown> }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/context`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
  return handleResponse(response);
}

/** Result of re-fetching a competitor's sources to check one statement. */
export interface SourceCheck {
  competitor: string;
  statement: string;
  verdict: "confirmed" | "not_found" | "unreachable" | "no_sources";
  url: string | null;
  pages_checked: number;
}

export interface ChatStreamHandlers {
  onDelta: (text: string) => void;
  onAction?: (action: ChatAction) => void;
  onCheck?: (check: SourceCheck) => void;
  onStatus?: (status: string) => void;
}

export interface ChatOpeningResponse {
  step: string;
  message: string;
  suggestions: string[];
}

/** Fetches the zero-latency opening message and suggested chips for a step. */
export async function fetchChatOpening(
  jobId: string,
  step: string
): Promise<ChatOpeningResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/chat/opening?step=${encodeURIComponent(step)}`
  );
  return handleResponse<ChatOpeningResponse>(response);
}

/**
 * Asks a question about a run's report. The answer streams as server-sent events over the
 * POST response: text pieces, tool status lines, live source checks, and proposed actions.
 * Resolves when done, with `offTopic` set when the question was outside the report's scope.
 */
export async function streamReportChat(
  jobId: string,
  messages: ChatTurn[],
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
  step?: string,
  focusAssetId?: string
): Promise<{ offTopic: boolean }> {
  const body: Record<string, unknown> = { messages };
  if (step) body.step = step;
  if (focusAssetId) body.focus_asset_id = focusAssetId;

  const response = await fetch(`${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    await handleResponse<never>(response);
    throw new ApiError("The assistant returned no answer.", response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Frames end with a blank line; keep any partial frame for the next read.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6)) as {
        delta?: string;
        done?: boolean;
        error?: string;
        off_topic?: boolean;
        status?: string;
        action?: ChatAction;
        check?: SourceCheck;
      };
      if (payload.error) throw new ApiError(payload.error, 502);
      if (payload.delta) handlers.onDelta(payload.delta);
      if (payload.status) handlers.onStatus?.(payload.status);
      if (payload.action) handlers.onAction?.(payload.action);
      if (payload.check) handlers.onCheck?.(payload.check);
      if (payload.done) return { offTopic: !!payload.off_topic };
    }
  }
  return { offTopic: false };
}

/**
 * Customizes budget allocations, days, sub-goals, and selected strategy option for Campaign Strategy Brief.
 */
export async function customizeCampaignStrategy(
  jobId: string,
  payload: StrategyCustomizeRequest
): Promise<CampaignStrategyBrief> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/strategy/customize`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return handleResponse<CampaignStrategyBrief>(response);
}

/**
 * Founder approval gate for Campaign Strategy Brief.
 */
export async function approveCampaignStrategy(
  jobId: string,
  payload?: StrategyCustomizeRequest
): Promise<CampaignStrategyBrief> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/strategy/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload ? JSON.stringify(payload) : undefined,
    }
  );
  return handleResponse<CampaignStrategyBrief>(response);
}

// ── Campaign content ────────────────────────────────────────────────────────

const contentUrl = (jobId: string, path = "") =>
  `${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/content${path}`;

export async function getCampaignContent(jobId: string): Promise<ContentPack | null> {
  return handleResponse<ContentPack | null>(await fetch(contentUrl(jobId)));
}

export async function generateCampaignContent(jobId: string): Promise<void> {
  await handleResponse<unknown>(await fetch(contentUrl(jobId, "/generate"), { method: "POST" }));
}

export async function editCampaignAsset(
  jobId: string,
  assetId: string,
  fields: Partial<Pick<ContentAsset, "name" | "subject" | "preview_text" | "body" | "headlines" | "descriptions" | "cta" | "landing_url" | "creative_brief" | "hashtags">>
): Promise<ContentAsset> {
  return handleResponse<ContentAsset>(
    await fetch(contentUrl(jobId, `/${encodeURIComponent(assetId)}`), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    })
  );
}

export async function regenerateCampaignAsset(jobId: string, assetId: string, instruction?: string): Promise<ContentAsset> {
  return handleResponse<ContentAsset>(
    await fetch(contentUrl(jobId, `/${encodeURIComponent(assetId)}/regenerate`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction: instruction || null }),
    })
  );
}

export async function setChannelApproval(jobId: string, channel: ChannelKey, approved: boolean): Promise<ContentPack> {
  return handleResponse<ContentPack>(
    await fetch(contentUrl(jobId, "/approval"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel, approved }),
    })
  );
}

export async function rescheduleCampaignContent(
  jobId: string,
  payload: { shift_days?: number; time_of_day?: string; channel?: string; asset_ids?: string[] }
): Promise<ContentPack> {
  return handleResponse<ContentPack>(
    await fetch(contentUrl(jobId, "/reschedule"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}
