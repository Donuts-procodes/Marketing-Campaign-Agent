/**
 * HTTP Client communicating with FastAPI Gateway.
 */

import {
  AutofillResponse,
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
export async function autofillFromFiles(files: File[]): Promise<AutofillResponse> {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));

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
  jobId: string
): Promise<MoreCompetitorsResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/campaigns/${encodeURIComponent(jobId)}/more-competitors`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
  return handleResponse<MoreCompetitorsResponse>(response);
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
