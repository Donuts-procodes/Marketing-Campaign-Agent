"""
HTTP routes for Campaign Strategy Orchestration.
Handles HTTP status codes, headers, parameter extraction, and DI only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from orchestrator.core.config import get_settings
from orchestrator.core.storage import get_storage
from orchestrator.schemas.api import (
    AgentDescriptor,
    AgentListResponse,
    AutofillResponse,
    CampaignCreate,
    CampaignCreateResponse,
    DossierUploadResponse,
    MoreCompetitorsResponse,
    ReResearchResponse,
    RenameSessionInput,
    ResolveInterruptInput,
    ResolveInterruptResponse,
    SessionListResponse,
    SessionSummary,
    UploadedFileInfo,
)
from orchestrator.services.campaign_service import (
    CampaignInterruptNotFoundError,
    CampaignJobConflictError,
    CampaignJobNotFoundError,
    CampaignService,
    DossierTooLargeError,
    ResearchKeysMissingError,
    check_upload_limits,
    get_campaign_service,
)
from orchestrator.services.autofill import AutofillUnavailableError, autofill_from_text, filled_field_names
from orchestrator.services.dossier import DossierFormatError, combine_documents

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get(
    "/agents",
    response_model=AgentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all registered agent microservices, their models, tools, and contracts",
)
async def list_agents() -> AgentListResponse:
    agents = [
        AgentDescriptor(
            agent_id="market_research",
            name="Market & Competitor Research Agent",
            description="Autonomous competitive intelligence agent executing multi-vector discovery, dynamic taxonomy reasoning, and factual grounding.",
            service_endpoint="http://agent_market_research:8001",
            port=8001,
            models=["gpt-4o", "gpt-4o-mini"],
            tools=[
                "Tavily Async Multi-Vector Client",
                "You.com Web Search",
                "DuckDuckGo Search (fallback)",
                "Firecrawl / Crawlbase Deep Search (Tavily Extract fallback)",
                "Ad Library Search (Meta, LinkedIn, Google)",
                "Dynamic Parameter Taxonomy Reasoner",
                "DQS Weighted Scoring Engine (4-dimension)",
                "Factual Grounding & Anti-Hallucination Gate",
            ],
            capabilities=[
                "dynamic_parameter_taxonomy",
                "tavily_multi_vector_search",
                "crawlapi_deep_search",
                "iterative_dqs_convergence",
                "competitor_ad_intelligence",
                "factual_grounding_validation",
                "swot_synthesis",
            ],
            input_contract="StrategyState (merchant_context, dqs_retries)",
            output_contract="SWOTReportDelta (competitors, swot, positioning_gap, dynamic_taxonomy)",
            status="operational",
        ),
        AgentDescriptor(
            agent_id="audience_persona",
            name="Audience & Persona Research Agent",
            description="Planned. Not implemented yet: the pipeline passes through it without producing data.",
            service_endpoint="",
            port=8002,
            models=[],
            tools=[],
            capabilities=[],
            input_contract="StrategyState (merchant_context, swot_report)",
            output_contract="PersonaReportDelta (persona_profiles, objections)",
            status="not_implemented",
        ),
        AgentDescriptor(
            agent_id="campaign_strategy",
            name="Campaign Strategy & Budgeting Agent",
            description="Planned. Not implemented yet: the pipeline passes through it without producing data.",
            service_endpoint="",
            port=8003,
            models=[],
            tools=[],
            capabilities=[],
            input_contract="StrategyState (swot_report, persona_profiles)",
            output_contract="CampaignBriefDelta (channel_budgets, kpis, schedule)",
            status="not_implemented",
        ),
    ]
    return AgentListResponse(agents=agents)


@router.post(
    "",
    response_model=CampaignCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new autonomous campaign strategy run",
)
async def create_campaign(
    payload: CampaignCreate,
    request: Request,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignCreateResponse:
    # ponytail: keyed by client IP; behind the dev proxy every browser shares one IP, so this is a global cap.
    client_id = request.client.host if request.client else "unknown"
    if not await get_storage().allow_job_creation(client_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit: at most {get_settings().max_jobs_per_hour} research runs per hour.",
        )
    job_id = service.create_campaign_job(payload)
    return CampaignCreateResponse(job_id=job_id, status="PENDING")


async def _read_uploads(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    """Reads at most max_upload_files + 1 files and one byte past the total limit, so oversized
    uploads are rejected by check_upload_limits without buffering them whole."""
    settings = get_settings()
    out: list[tuple[str, bytes]] = []
    total = 0
    for upload in files[: settings.max_upload_files + 1]:
        content = await upload.read(settings.max_dossier_bytes + 1 - total)
        total += len(content)
        out.append((upload.filename or "dossier.txt", content))
        if total > settings.max_dossier_bytes:
            break
    return out


@router.post(
    "/autofill",
    response_model=AutofillResponse,
    status_code=status.HTTP_200_OK,
    summary="Read the campaign form fields out of one or more uploaded documents",
)
async def autofill_campaign_form(
    request: Request,
    files: list[UploadFile] = File(...),
) -> AutofillResponse:
    client_id = request.client.host if request.client else "unknown"
    if not await get_storage().allow_job_creation(f"autofill:{client_id}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Autofill rate limit reached.")
    uploads = await _read_uploads(files)
    try:
        check_upload_limits(uploads)
        text, info = combine_documents(uploads)
        fields = await autofill_from_text(text)
    except DossierTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except DossierFormatError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    except AutofillUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return AutofillResponse(
        fields=fields,
        filled=filled_field_names(fields),
        files=[UploadedFileInfo(filename=n, characters=c) for n, c in info],
    )


@router.post(
    "/{job_id}/dossier",
    response_model=DossierUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload one or more merchant dossiers / pitch decks to a campaign job",
)
async def upload_dossier(
    job_id: str,
    files: list[UploadFile] | None = File(default=None),
    file: UploadFile | None = File(default=None),  # single-file field, kept for older clients
    service: CampaignService = Depends(get_campaign_service),
) -> DossierUploadResponse:
    uploads = await _read_uploads((files or []) + ([file] if file else []))
    try:
        info = service.attach_dossiers(job_id, uploads)
    except CampaignJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CampaignJobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DossierTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except DossierFormatError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    return DossierUploadResponse(
        status="ATTACHED",
        characters=sum(c for _, c in info),
        filename=", ".join(n for n, _ in info),
        files=[UploadedFileInfo(filename=n, characters=c) for n, c in info],
    )


@router.get(
    "/{job_id}/stream",
    response_class=StreamingResponse,
    summary="Server-Sent Events (SSE) telemetry and deltas stream",
)
async def stream_campaign_progress(
    job_id: str,
    after: int = Query(default=-1, description="Replay only events with seq greater than this"),
    last_event_id: str | None = Header(default=None),
    service: CampaignService = Depends(get_campaign_service),
) -> StreamingResponse:
    after_seq = after
    if last_event_id is not None and last_event_id.isdigit():
        after_seq = max(after_seq, int(last_event_id))

    generator = service.stream_job_events(job_id, after_seq=after_seq)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{job_id}/resolve-interrupt",
    response_model=ResolveInterruptResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Human-In-The-Loop review approval or revision guidance",
)
async def resolve_interrupt(
    job_id: str,
    payload: ResolveInterruptInput,
    service: CampaignService = Depends(get_campaign_service),
) -> ResolveInterruptResponse:
    try:
        service.resolve_interrupt(
            job_id=job_id,
            checkpoint_id=payload.checkpoint_id,
            action=payload.action,
            feedback=payload.feedback,
        )
        return ResolveInterruptResponse(status="ACCEPTED")
    except CampaignJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except CampaignInterruptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List recent campaign sessions (in-memory and saved), newest first",
)
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    service: CampaignService = Depends(get_campaign_service),
) -> SessionListResponse:
    rows = await service.list_sessions(limit=limit)
    return SessionListResponse(sessions=[SessionSummary(**r) for r in rows])


@router.patch(
    "/{job_id}",
    response_model=SessionSummary,
    summary="Rename a session",
)
async def rename_session(
    job_id: str,
    payload: RenameSessionInput,
    service: CampaignService = Depends(get_campaign_service),
) -> SessionSummary:
    try:
        await service.update_session(job_id, payload.label)
    except CampaignJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    rows = await service.list_sessions(limit=200)
    row = next((r for r in rows if r["job_id"] == job_id), None)
    return SessionSummary(**row) if row else SessionSummary(job_id=job_id, status="unknown", label=payload.label)


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session from memory and storage",
)
async def delete_session(
    job_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> None:
    try:
        await service.delete_session(job_id)
    except CampaignJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{job_id}/more-competitors",
    response_model=MoreCompetitorsResponse,
    status_code=status.HTTP_200_OK,
    summary="On-demand discovery of additional competitors from web",
)
async def find_more_competitors(
    job_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> MoreCompetitorsResponse:
    try:
        report, added = await service.find_more_competitors(job_id)
    except CampaignJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CampaignJobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ResearchKeysMissingError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return MoreCompetitorsResponse(
        status="SUCCESS",
        added_competitors=added,
        total_competitors=len(report.competitors),
        swot_report=report,
    )


@router.post(
    "/{job_id}/re-research",
    response_model=ReResearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Re-execute the entire market research agent and discovery loop for this campaign",
)
async def rerun_research(
    job_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> ReResearchResponse:
    try:
        report = await service.rerun_market_research(job_id)
    except CampaignJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ResearchKeysMissingError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return ReResearchResponse(
        status="SUCCESS",
        swot_report=report,
    )


