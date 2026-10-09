"""
HTTP routes for Campaign Strategy Orchestration.
Handles HTTP status codes, headers, parameter extraction, and DI only.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from orchestrator.core.config import get_settings
from orchestrator.core.storage import get_storage
from orchestrator.schemas.api import (
    AgentDescriptor,
    AgentListResponse,
    AutofillResponse,
    BYOKConfig,
    CampaignCreate,
    CampaignCreateResponse,
    DossierUploadResponse,
    InterpretQueryInput,
    MoreCompetitorsInput,
    MoreCompetitorsResponse,
    PriorRunInfo,
    ReportChatInput,
    ReportEditInput,
    ReportEditResponse,
    ReResearchResponse,
    RenameSessionInput,
    ResolveInterruptInput,
    ResolveInterruptResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionSummary,
    UpdateContextInput,
    UpdateContextResponse,
    UploadedFileInfo,
)
from orchestrator.schemas.strategy import CampaignStrategyBrief
from orchestrator.services.campaign_service import (
    CampaignInterruptNotFoundError,
    CampaignJobConflictError,
    CampaignJobNotFoundError,
    CampaignService,
    DossierTooLargeError,
    ReportEditError,
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
        AgentDescriptor(
            agent_id="media_generation",
            name="Media & Creative Generation Agent",
            description="Planned. Generates multi-format ad creative variants, copy variants, and visual layouts.",
            service_endpoint="",
            port=8004,
            models=[],
            tools=[],
            capabilities=[],
            input_contract="StrategyState (campaign_brief, persona_profiles)",
            output_contract="MediaAssetDelta (ad_creatives, copy_variants, visual_layouts)",
            status="not_implemented",
        ),
        AgentDescriptor(
            agent_id="publishing",
            name="Publishing & Distribution Agent",
            description="Planned. Coordinates multi-platform scheduling, CMS dispatch, and live ad network synchronization.",
            service_endpoint="",
            port=8005,
            models=[],
            tools=[],
            capabilities=[],
            input_contract="StrategyState (media_assets, schedule)",
            output_contract="PublishingDelta (dispatch_jobs, live_urls, status)",
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
    byok_config: str | None = Form(default=None, description="JSON serialized BYOKConfig"),
) -> AutofillResponse:
    client_id = request.client.host if request.client else "unknown"
    if not await get_storage().allow_job_creation(f"autofill:{client_id}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Autofill rate limit reached.")
    uploads = await _read_uploads(files)
    
    parsed_byok: BYOKConfig | None = None
    if byok_config:
        try:
            parsed_byok = BYOKConfig.model_validate(json.loads(byok_config))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid BYOKConfig: {exc}")
            
    try:
        check_upload_limits(uploads)
        text, info = combine_documents(uploads)
        fields = await autofill_from_text(text, byok_config=parsed_byok)
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
    "/interpret",
    response_model=AutofillResponse,
    status_code=status.HTTP_200_OK,
    summary="Interpret a free-form user query into structured merchant context fields",
    description=(
        "Unlike /autofill (which reads uploaded documents), this endpoint takes raw user "
        "text — even vague goal statements — and uses an LLM to infer the most likely "
        "product_name, category, value_prop and goal. The result can be used to pre-fill "
        "the campaign brief form so the user can confirm rather than type from scratch."
    ),
)
async def interpret_user_query(
    request: Request,
    payload: InterpretQueryInput,
) -> AutofillResponse:
    client_id = request.client.host if request.client else "unknown"
    if not await get_storage().allow_job_creation(f"interpret:{client_id}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Interpret rate limit reached.")
    try:
        from orchestrator.services.query_interpreter import interpret_query
        fields = await interpret_query(payload.text)
    except AutofillUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return AutofillResponse(fields=fields, filled=filled_field_names(fields), files=[])


@router.get(
    "/prior-run",
    response_model=PriorRunInfo,
    status_code=status.HTTP_200_OK,
    summary="Check whether a completed run already exists for this product",
    description=(
        "Returns metadata about the most recent successful run for the given product_name "
        "and optional category. The frontend uses this to show an 'Update / Fresh scan' "
        "mode selector before launching a new run."
    ),
)
async def get_prior_run(
    product_name: str = Query(..., min_length=1, max_length=300),
    category: str = Query(default="", max_length=300),
) -> PriorRunInfo:
    doc = await get_storage().find_latest_run_by_product(product_name, category)
    if not doc or not doc.get("report"):
        return PriorRunInfo(found=False)
    report = doc["report"]
    finished_at = doc.get("finished_at")
    return PriorRunInfo(
        found=True,
        job_id=doc.get("job_id"),
        finished_at=str(finished_at) if finished_at else None,
        dqs_score=report.get("dqs_score"),
        competitor_count=len(report.get("competitors") or []),
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


@router.get(
    "/{job_id}",
    response_model=SessionDetailResponse,
    summary="Fetch full details, report, and events for a session",
)
async def get_session(
    job_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> SessionDetailResponse:
    try:
        job = await service.get_or_restore_job(job_id)
        storage = get_storage()
        doc = await storage.load_run(job_id)
        report = job.last_swot_report
        events = job.history_events or (doc.get("events", []) if doc else [])
        finished_at = doc.get("finished_at") if doc else None
        return SessionDetailResponse(
            job_id=job.job_id,
            status="complete" if job.is_finished else ("running" if job.is_started else "pending"),
            label=job.label,
            finished_at=finished_at.isoformat() if hasattr(finished_at, "isoformat") else (str(finished_at) if finished_at else None),
            merchant_context=job.merchant_context,
            swot_report=report,
            strategy_brief=job.strategy_brief,
            events=events,
        )
    except CampaignJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


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


@router.patch(
    "/{job_id}/context",
    response_model=UpdateContextResponse,
    status_code=status.HTTP_200_OK,
    summary="Update merchant campaign context or goal (Human-In-The-Loop)",
)
async def update_merchant_context(
    job_id: str,
    payload: UpdateContextInput,
    service: CampaignService = Depends(get_campaign_service),
) -> UpdateContextResponse:
    try:
        updated_context, applied = await service.update_merchant_context(
            job_id=job_id,
            field=payload.field,
            value=payload.value,
            reasoning=payload.reasoning,
        )
        return UpdateContextResponse(
            status="ACCEPTED",
            field=payload.field,
            value=payload.value,
            applied=applied,
            merchant_context=updated_context,
        )
    except CampaignJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc



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
    payload: MoreCompetitorsInput | None = None,
    service: CampaignService = Depends(get_campaign_service),
) -> MoreCompetitorsResponse:
    try:
        report, added = await service.find_more_competitors(job_id, payload.names if payload else None)
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


@router.post(
    "/{job_id}/report/edits",
    response_model=ReportEditResponse,
    status_code=status.HTTP_200_OK,
    summary="Apply merchant corrections to the report (remove an item, correct a price, remove a competitor)",
)
async def edit_report(
    job_id: str,
    payload: ReportEditInput,
    service: CampaignService = Depends(get_campaign_service),
) -> ReportEditResponse:
    try:
        report, applied = await service.edit_report(job_id, payload.edits)
    except CampaignJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CampaignJobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ReportEditError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ReportEditResponse(applied=applied, swot_report=report)


@router.post(
    "/{job_id}/chat",
    status_code=status.HTTP_200_OK,
    summary="Ask a question about this run's report; the answer streams as server-sent events",
    description=(
        "Answers only from this run's report and the merchant's brief. Frames are "
        '`data: {"delta": "..."}`, then `data: {"done": true}` or `data: {"error": "..."}`.'
    ),
)
async def chat_about_report(
    job_id: str,
    payload: ReportChatInput,
    request: Request,
    service: CampaignService = Depends(get_campaign_service),
) -> StreamingResponse:
    if payload.messages[-1].role != "user":
        raise HTTPException(status_code=422, detail="The last message must be the user's question.")
    client_id = request.client.host if request.client else "unknown"
    if not await get_storage().allow_job_creation(f"chat:{client_id}", limit=get_settings().max_chat_messages_per_hour):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Chat limit reached — try again in a few minutes.")
    try:
        job = await service.get_or_restore_job(job_id)
    except CampaignJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if job.last_swot_report is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The report is not ready yet.")

    from orchestrator.core.llm import LLMConfigurationError, build_chat_model
    from orchestrator.services.report_chat import stream_report_chat

    try:
        llm = build_chat_model(job.byok_config)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return StreamingResponse(
        stream_report_chat(llm, job.last_swot_report, job.merchant_context, payload.messages, job.bench_competitors),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{job_id}/strategy/approve",
    response_model=CampaignStrategyBrief,
    status_code=status.HTTP_200_OK,
    summary="Founder approval gate: approves campaign strategy brief for downstream execution",
)
async def approve_campaign_strategy(
    job_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignStrategyBrief:
    try:
        return await service.approve_strategy(job_id)
    except CampaignJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CampaignJobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
