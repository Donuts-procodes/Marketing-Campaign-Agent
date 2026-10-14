"""
Business logic and execution service for Campaign Strategy Orchestration.
Pure service layer: zero imports of FastAPI Request, Response, or status codes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from orchestrator.agents.campaign_strategy.money import fmt_money
from orchestrator.core.config import get_settings, research_limit
from orchestrator.core.llm import has_llm_credentials
from orchestrator.core.storage import get_storage
from orchestrator.schemas.api import BYOKConfig, CampaignCreate, ReportEdit
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta
from orchestrator.services.report_edits import ReportEditError, apply_report_edits
from orchestrator.schemas.state import StrategyState
from orchestrator.schemas.strategy import CampaignStrategyBrief, CampaignStrategyOption
from orchestrator.schemas.content import ContentAsset, ContentPack
from orchestrator.agents.market_research.ingestion.search_client import reset_search_market, set_search_market
from orchestrator.services.dossier import combine_documents

logger = logging.getLogger(__name__)


class CampaignJobNotFoundError(Exception):
    """Raised when the requested campaign job is not found."""


class CampaignInterruptNotFoundError(Exception):
    """Raised when an interrupt checkpoint does not match the active gate."""


class CampaignJobConflictError(Exception):
    """Raised when an operation is not valid for the job's current lifecycle state."""


class DossierTooLargeError(Exception):
    """Raised when an uploaded dossier exceeds the configured size limit."""


def check_upload_limits(files: list[tuple[str, bytes]]) -> None:
    """Shared by dossier and autofill uploads: file count and total size."""
    settings = get_settings()
    if not files:
        raise DossierTooLargeError("No files were uploaded.")
    if len(files) > settings.max_upload_files:
        raise DossierTooLargeError(f"At most {settings.max_upload_files} files per upload.")
    if sum(len(content) for _, content in files) > settings.max_dossier_bytes:
        raise DossierTooLargeError("Uploaded files exceed the maximum total size.")


class ResearchKeysMissingError(Exception):
    """Raised when live research is impossible; the service never substitutes sample data."""


# Events after which a run is over; anything else as the last event means it was still going.
_TERMINAL_EVENTS = frozenset({"RUN_COMPLETE", "RUN_FAILED"})
# How long a run held by no process may stay silent before it is declared interrupted. Longer
# than the slowest single pipeline step without a log line (a crawl batch, ~80s), so a run
# alive in another worker is never cut off.
_ORPHAN_QUIET_SECONDS = 120


def _now_ms() -> int:
    return int(time.time() * 1000)


def _norm(name: str) -> str:
    return " ".join(name.lower().split())


class CampaignJob:
    def __init__(
        self,
        job_id: str,
        merchant_context: dict,
        byok_config: BYOKConfig | None = None,
    ):
        self.job_id = job_id
        self.merchant_context = merchant_context
        self.byok_config = byok_config
        self.dossier_text: str | None = None
        self.history_events: list[dict] = []
        self.subscribers: list[asyncio.Queue[dict | None]] = []
        self.interrupt_event: asyncio.Event = asyncio.Event()
        self.active_checkpoint_id: str | None = None
        self.resolution: dict | None = None
        self.label: str | None = None
        self.is_started: bool = False
        self.is_finished: bool = False
        self.last_swot_report: SWOTReportDelta | None = None
        self.strategy_brief: CampaignStrategyBrief | None = None
        # Audience/Persona Agent output for this run. Empty until that agent is wired in; the
        # strategy agent then derives provisional personas from the research instead.
        self.persona_profiles: list = []
        self.task: asyncio.Task[None] | None = None
        self.report_lock: asyncio.Lock = asyncio.Lock()
        self.created_at: float = time.monotonic()
        self.finished_at: float | None = None
        self.bench_competitors: list[CompetitorProfile] = []
        self.content_pack: ContentPack | None = None
        self.content_task: asyncio.Task[None] | None = None


class CampaignService:
    def __init__(self):
        self._jobs: dict[str, CampaignJob] = {}

    # ── Job lifecycle ────────────────────────────────────────────────────────

    def _evict_expired_jobs(self) -> None:
        settings = get_settings()
        now = time.monotonic()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if not job.subscribers
            and not (job.is_started and not job.is_finished)
            and (
                # Finished runs expire a TTL after completion...
                (job.finished_at is not None and now - job.finished_at > settings.job_ttl_seconds)
                # ...and runs that were created but never streamed expire a TTL after creation.
                or (not job.is_started and now - job.created_at > settings.job_ttl_seconds)
            )
        ]
        for job_id in expired:
            del self._jobs[job_id]

        # Hard cap: drop the oldest finished jobs first.
        overflow = len(self._jobs) - settings.max_jobs + 1
        if overflow > 0:
            finished = sorted(
                (j for j in self._jobs.values() if j.is_finished and not j.subscribers),
                key=lambda j: j.created_at,
            )
            for job in finished[:overflow]:
                del self._jobs[job.job_id]

    def create_campaign_job(self, payload: CampaignCreate) -> str:
        self._evict_expired_jobs()

        # Full 128-bit id: the job id is the only thing guarding access to a run.
        job_id = f"job-{uuid.uuid4().hex}"
        merchant_ctx = payload.merchant_context.model_dump()
        # Carry run_mode into merchant_context so _run_market_research_node can read it
        merchant_ctx["run_mode"] = payload.run_mode or "fresh"

        job = CampaignJob(
            job_id=job_id,
            merchant_context=merchant_ctx,
            byok_config=payload.byok_config,
        )
        self._jobs[job_id] = job
        return job_id

    def get_job(self, job_id: str) -> CampaignJob:
        job = self._jobs.get(job_id)
        if not job:
            raise CampaignJobNotFoundError(f"Job {job_id} not found")
        return job

    async def get_or_restore_job(self, job_id: str) -> CampaignJob:
        job = self._jobs.get(job_id)
        if job:
            return job

        doc = await get_storage().load_run(job_id)
        if not doc:
            raise CampaignJobNotFoundError(f"Job {job_id} not found")

        merchant_ctx = doc.get("merchant_context", {})
        restored = CampaignJob(job_id=job_id, merchant_context=merchant_ctx)
        restored.label = doc.get("label")
        restored.is_started = True
        restored.is_finished = True
        raw_report = doc.get("report")
        if raw_report:
            restored.last_swot_report = SWOTReportDelta(**raw_report)
        raw_brief = doc.get("strategy_brief")
        if raw_brief:
            restored.strategy_brief = CampaignStrategyBrief(**raw_brief)
        restored.bench_competitors = [
            CompetitorProfile(**c) for c in doc.get("bench_competitors") or []
        ]
        if doc.get("content_pack"):
            restored.content_pack = ContentPack(**doc["content_pack"])
        restored.history_events = list(doc.get("events", []))
        self._jobs[job_id] = restored
        return restored

    def attach_dossiers(self, job_id: str, files: list[tuple[str, bytes]]) -> list[tuple[str, int]]:
        """Attaches one or more dossier files (replacing earlier ones); returns (filename, characters) per file."""
        job = self.get_job(job_id)
        if job.is_started:
            raise CampaignJobConflictError(
                f"Job {job_id} has already started; dossiers must be attached before streaming."
            )
        check_upload_limits(files)

        text, info = combine_documents(files)
        job.dossier_text = text
        job.merchant_context["dossier"] = text
        return info

    def resolve_interrupt(
        self,
        job_id: str,
        checkpoint_id: str,
        action: str,
        feedback: str | None = None,
    ) -> None:
        job = self.get_job(job_id)

        if job.active_checkpoint_id != checkpoint_id:
            raise CampaignInterruptNotFoundError(
                f"Checkpoint {checkpoint_id} is not the active interrupt for job {job_id}"
            )

        job.resolution = {"action": action, "feedback": feedback}
        job.active_checkpoint_id = None
        job.interrupt_event.set()

    def _missing_keys(self, job: CampaignJob) -> list[str]:
        """Live research needs a search engine (Tavily, You.com or DuckDuckGo) plus an LLM key."""
        settings = get_settings()
        missing = []
        ddg_on = settings.duckduckgo_mode.lower() != "off"
        if not (settings.tavily_api_key or settings.you_api_key or ddg_on):
            missing.append("TAVILY_API_KEY or YOU_API_KEY (or enable DUCKDUCKGO_MODE)")
        if not has_llm_credentials(job.byok_config):
            missing.append("an LLM API key")
        return missing

    def _is_live(self, job: CampaignJob) -> bool:
        return not self._missing_keys(job)

    # ── Event streaming ──────────────────────────────────────────────────────

    async def stream_job_events(self, job_id: str, after_seq: int = -1) -> AsyncIterator[str]:
        job = self._jobs.get(job_id)
        if not job:
            # Not in this worker's memory. Replay recent live events from Redis (temp storage),
            # then fall back to the durable finished run in MongoDB.
            storage = get_storage()
            events = await storage.load_events(job_id)
            if not events:
                saved = await storage.load_run(job_id)
                events = saved.get("events", []) if saved else []
            if events:
                for evt in events:
                    if evt["seq"] > after_seq:
                        yield self._format_frame(evt)
                # A run that is not in this process's memory, never reached a final event, and
                # has gone quiet was killed by a restart (a code reload or a crash): the pipeline
                # runs in-process and does not resume. Without a final event the page waited on
                # it forever, re-polling the same position every two seconds.
                last = events[-1]
                stamp = last.get("timestamp")
                # No timestamp means no way to tell how long it has been quiet: never declare it.
                quiet_s = (_now_ms() - int(stamp)) / 1000 if stamp else 0
                # Approval and content events come after RUN_COMPLETE, so "finished" means any
                # terminal event, not the last one; otherwise a restart marked approved runs as failed.
                finished = any(e.get("type") in _TERMINAL_EVENTS for e in events)
                if not finished and quiet_s >= _ORPHAN_QUIET_SECONDS:
                    failed = {
                        "type": "RUN_FAILED",
                        "seq": int(last.get("seq", len(events) - 1)) + 1,
                        "message": (
                            "This run was interrupted: the server restarted while it was in progress, "
                            "so it could not finish. Start the research again."
                        ),
                        "timestamp": _now_ms(),
                    }
                    # Stored so every later reconnect sees the same final answer.
                    await storage.append_event(job_id, failed)
                    logger.warning("Job %s was orphaned by a restart; marked as interrupted", job_id)
                    if failed["seq"] > after_seq:
                        yield self._format_frame(failed)
                return
            err_frame = {
                "type": "RUN_FAILED",
                "message": f"Job {job_id} was not found.",
                "timestamp": _now_ms(),
            }
            yield f"data: {json.dumps(err_frame)}\n\n"
            return

        sub_queue: asyncio.Queue[dict | None] = asyncio.Queue()
        job.subscribers.append(sub_queue)

        try:
            # Replay only events the client has not seen yet.
            for evt in list(job.history_events):
                if evt["seq"] > after_seq:
                    yield self._format_frame(evt)

            if job.is_finished:
                return

            if not job.is_started:
                running = sum(1 for j in self._jobs.values() if j.is_started and not j.is_finished)
                if running >= get_settings().max_running_jobs:
                    busy = {
                        "type": "RUN_FAILED",
                        "message": f"Server busy: {running} research runs in progress. Try again shortly.",
                        "timestamp": _now_ms(),
                    }
                    yield f"data: {json.dumps(busy)}\n\n"
                    return
                job.is_started = True
                # Keep a reference: the event loop only holds weak references to tasks.
                job.task = asyncio.create_task(self._execute_pipeline(job))

            while True:
                evt = await sub_queue.get()
                if evt is None:
                    break
                yield self._format_frame(evt)
        finally:
            if sub_queue in job.subscribers:
                job.subscribers.remove(sub_queue)

    @staticmethod
    def _format_frame(evt: dict) -> str:
        return f"id: {evt['seq']}\ndata: {json.dumps(evt)}\n\n"

    async def _emit_event(self, job: CampaignJob, event: dict) -> None:
        event = {**event, "seq": len(job.history_events)}
        job.history_events.append(event)
        # Temp storage: mirror into Redis so an in-flight run survives a restart / other worker.
        await get_storage().append_event(job.job_id, event)
        for sub_queue in list(job.subscribers):
            await sub_queue.put(event)

    async def _log(self, job: CampaignJob, message: str, level: str = "INFO") -> None:
        # Mirror pipeline telemetry to the server console (colorized by core.log_format).
        py_level = {"WARN": logging.WARNING, "ERROR": logging.ERROR}.get(level, logging.INFO)
        logger.log(py_level, "%s %s", job.job_id[:12], message)
        await self._emit_event(
            job,
            {"type": "TELEMETRY_LOG", "level": level, "message": message, "timestamp": _now_ms()},
        )

    # ── Pipeline ─────────────────────────────────────────────────────────────

    async def _execute_pipeline(self, job: CampaignJob) -> None:
        # Runs in its own task, so the market pinned here covers this job's searches only.
        set_search_market(job.merchant_context)
        try:
            await self._log_provider_health(job)
            await self._emit_event(
                job, {"type": "NODE_STARTED", "node": "market_research", "timestamp": _now_ms()}
            )

            missing = self._missing_keys(job)
            if missing:
                raise ResearchKeysMissingError(
                    f"Live research needs {' and '.join(missing)}; no sample data is substituted."
                )
            settings = get_settings()
            if not (settings.scrapedo_api_key or settings.firecrawl_api_key or settings.crawlapi_token or settings.crawlapi_js_token):
                await self._log(
                    job,
                    "[DEEP_SEARCH] No crawl API key (SCRAPEDO_API_KEY, FIRECRAWL_API_KEY or CRAWLAPI_TOKEN) — deep search "
                    "uses Tavily Extract only; LinkedIn/Google ad libraries are skipped.",
                    level="WARN",
                )
            providers = [
                name
                for name, key in (
                    ("Tavily", settings.tavily_api_key),
                    ("You.com", settings.you_api_key),
                    (
                        f"DuckDuckGo ({settings.duckduckgo_mode})",
                        settings.duckduckgo_mode.lower() != "off",
                    ),
                    ("Scrape.do", settings.scrapedo_api_key),
                    ("Firecrawl", settings.firecrawl_api_key),
                    ("Crawlbase", settings.crawlapi_token or settings.crawlapi_js_token),
                    ("Meta Ad Library API", settings.meta_access_token),
                )
                if key
            ]
            await self._log(job, f"[CONFIG] Live data sources: {', '.join(providers)}")

            report_delta = await self._run_market_research_node(job)
            job.last_swot_report = report_delta

            await self._emit_event(
                job,
                {
                    "type": "NODE_COMPLETE",
                    "node": "market_research",
                    "delta": {"swot_report": report_delta.model_dump()},
                    "timestamp": _now_ms(),
                },
            )

            # Stage 2: Audience Persona — personas built from the research's grounded audience read
            await self._emit_event(job, {"type": "NODE_STARTED", "node": "audience_persona", "timestamp": _now_ms()})
            job.persona_profiles = await self._run_audience_persona_node(job, report_delta)
            await self._emit_event(
                job,
                {"type": "NODE_COMPLETE", "node": "audience_persona",
                 "delta": {"persona_profiles": job.persona_profiles}, "timestamp": _now_ms()},
            )

            # Stage 3: Campaign Strategy & Budget Decomposition (Loops 1-3)
            await self._emit_event(job, {"type": "NODE_STARTED", "node": "campaign_strategy", "timestamp": _now_ms()})
            try:
                strategy_brief = await self._run_campaign_strategy_node(job, report_delta)
                job.strategy_brief = strategy_brief
                await self._emit_event(
                    job,
                    {
                        "type": "NODE_COMPLETE",
                        "node": "campaign_strategy",
                        "delta": {"strategy_brief": strategy_brief.model_dump()},
                        "timestamp": _now_ms(),
                    },
                )
            except Exception as exc:
                logger.warning("Campaign strategy node error for job %s: %s", job.job_id, exc)
                await self._log(job, f"[STRATEGY] Non-fatal strategy generation error: {exc}", level="WARN")
                await self._emit_event(
                    job, {"type": "NODE_COMPLETE", "node": "campaign_strategy", "delta": {}, "timestamp": _now_ms()}
                )

            await self._emit_event(
                job,
                {
                    "type": "RUN_COMPLETE",
                    "job_id": job.job_id,
                    "summary": {
                        "dqs_score": report_delta.dqs_score,
                        "attribute_density": report_delta.attribute_density,
                        "competitors": len(report_delta.competitors),
                        "mode": "live",
                    },
                    "timestamp": _now_ms(),
                },
            )

        except ResearchKeysMissingError as exc:
            await self._log(job, f"[CONFIG] {exc}", level="ERROR")
            await self._emit_event(
                job, {"type": "RUN_FAILED", "message": str(exc), "timestamp": _now_ms()}
            )
        except Exception as exc:
            logger.exception("Pipeline failed for job %s", job.job_id)
            # Do not leak internal exception text (may include URLs, keys or stack details).
            await self._emit_event(
                job,
                {
                    "type": "RUN_FAILED",
                    "message": f"Research pipeline failed ({type(exc).__name__}). See server logs.",
                    "timestamp": _now_ms(),
                },
            )
        finally:
            job.is_finished = True
            job.finished_at = time.monotonic()
            for sub_queue in list(job.subscribers):
                await sub_queue.put(None)
            await get_storage().save_run(self._run_document(job))

    @staticmethod
    def _run_document(job: CampaignJob) -> dict:
        """The persisted run: no BYOK key, and the dossier text stays out (it can approach Mongo's 16 MB cap)."""
        context = {k: v for k, v in job.merchant_context.items() if k != "dossier"}
        # Approval and content events follow RUN_COMPLETE, so "complete" means it ever completed.
        completed = any(e.get("type") == "RUN_COMPLETE" for e in job.history_events)
        return {
            "job_id": job.job_id,
            "finished_at": datetime.now(timezone.utc),
            "status": "complete" if completed else "failed",
            "label": job.label,
            "merchant_context": context,
            "dossier_chars": len(job.dossier_text or ""),
            "report": job.last_swot_report.model_dump() if job.last_swot_report else None,
            "strategy_brief": job.strategy_brief.model_dump() if job.strategy_brief else None,
            # Kept so "find more competitors" can still serve the next in line after a restart.
            "bench_competitors": [c.model_dump() for c in job.bench_competitors],
            "content_pack": job.content_pack.model_dump() if job.content_pack else None,
            "events": job.history_events,
        }

    # ── Session management: list / rename / delete past runs ─────────────────

    def _summary(self, job: CampaignJob) -> dict:
        status = "running" if (job.is_started and not job.is_finished) else (
            "pending" if not job.is_started else (
                "complete" if any(e.get("type") == "RUN_COMPLETE" for e in job.history_events) else "failed"
            )
        )
        ctx = job.merchant_context
        return {
            "job_id": job.job_id,
            "status": status,
            "label": job.label,
            "finished_at": None,
            "product_name": ctx.get("product_name"),
            "category": ctx.get("category"),
        }

    async def list_sessions(self, limit: int = 50) -> list[dict]:
        """In-memory jobs (live/pending) plus durable finished runs from MongoDB, newest first, deduped."""
        sessions: dict[str, dict] = {}
        for doc in await get_storage().list_runs(limit):
            ts = doc.get("finished_at")
            sessions[doc["job_id"]] = {
                "job_id": doc["job_id"],
                "status": doc.get("status", "complete"),
                "label": doc.get("label"),
                "finished_at": ts.isoformat() if hasattr(ts, "isoformat") else ts,
                "product_name": (doc.get("merchant_context") or {}).get("product_name"),
                "category": (doc.get("merchant_context") or {}).get("category"),
            }
        for job in self._jobs.values():
            sessions[job.job_id] = self._summary(job)  # in-memory wins: it is the most current
        ordered = sorted(sessions.values(), key=lambda s: (s["finished_at"] or "9999"), reverse=True)
        return ordered[:limit]

    async def update_session(self, job_id: str, label: str) -> None:
        """Renames a session. Works for an in-memory job, a saved run, or both."""
        in_memory = job_id in self._jobs
        if in_memory:
            self._jobs[job_id].label = label
        saved = await get_storage().update_run(job_id, {"label": label})
        if not in_memory and not saved:
            raise CampaignJobNotFoundError(f"Job {job_id} not found")

    async def delete_session(self, job_id: str) -> None:
        """Deletes a session from memory and from durable + temp storage, stopping it if it is still running."""
        job = self._jobs.pop(job_id, None)
        if job is not None:
            # Cancel the running pipeline so its finally-block cannot re-save the run after deletion.
            if job.task is not None and not job.task.done():
                job.task.cancel()
            for sub_queue in list(job.subscribers):
                await sub_queue.put(None)  # close any open streams
        deleted = await get_storage().delete_run(job_id)
        if job is None and not deleted:
            raise CampaignJobNotFoundError(f"Job {job_id} not found")

    async def _load_baseline(self, job: CampaignJob) -> tuple[SWOTReportDelta | None, str | None]:
        """The last finished run for this product, as the reading momentum is measured from."""
        product_name = job.merchant_context.get("product_name", "")
        category = job.merchant_context.get("category", "")
        try:
            doc = await get_storage().find_latest_run_by_product(product_name, category)
            if doc and doc.get("report"):
                return SWOTReportDelta(**doc["report"]), str(doc.get("finished_at", "")) or None
        except Exception as exc:
            # A missing baseline only costs momentum on this run; never fail research over it.
            logger.warning("Could not load baseline run for %r: %s", product_name, exc)
        return None, None

    async def _run_market_research_node(self, job: CampaignJob) -> SWOTReportDelta:
        """Runs the market research agent in-process, forwarding its progress to the stream."""
        from orchestrator.agents.market_research.agent import execute_market_research

        # Cross-run memory: for update runs, load the prior report for the same product
        # so the agent can seed known competitors, use time-bounded queries, and merge.
        prior_report = None
        prior_run_at = None
        run_mode = job.merchant_context.get("run_mode") or "fresh"
        if run_mode == "update":
            product_name = job.merchant_context.get("product_name", "")
            category = job.merchant_context.get("category", "")
            prior_doc = await get_storage().find_latest_run_by_product(product_name, category)
            if prior_doc and prior_doc.get("report"):
                try:
                    prior_report = SWOTReportDelta(**prior_doc["report"])
                    prior_run_at = str(prior_doc.get("finished_at", ""))
                    await self._log(
                        job,
                        f"[NODE] Prior run found ({prior_run_at[:10] if prior_run_at else 'unknown date'}) "
                        f"— running incremental update with {len(prior_report.competitors)} baseline competitors",
                    )
                except Exception as exc:
                    await self._log(
                        job,
                        f"[NODE] Could not load prior run report ({exc}); running as fresh scan",
                        level="WARN",
                    )
                    run_mode = "fresh"
            else:
                await self._log(
                    job,
                    "[NODE] No prior run found for this product — running as fresh scan",
                )
                run_mode = "fresh"

        # Momentum needs two readings. Load the last finished run on every run, not only on
        # updates, so the threat watch can measure movement even on a fresh scan. It goes in its
        # own state key: a fresh run must never merge old findings into the new report.
        baseline_report, baseline_run_at = prior_report, prior_run_at
        if baseline_report is None:
            baseline_report, baseline_run_at = await self._load_baseline(job)

        state: StrategyState = {
            "merchant_context": job.merchant_context,
            "swot_report": None,
            "dqs_retries": 0,
            "errors": [],
            "run_mode": run_mode,
            "prior_report": prior_report,
            "prior_run_at": prior_run_at,
            "baseline_report": baseline_report,
            "baseline_run_at": baseline_run_at,
        }

        async def on_progress(message: str, level: str = "INFO") -> None:
            await self._log(job, message, level=level)

        delta = await execute_market_research(
            state, llm_config=job.byok_config, on_progress=on_progress
        )

        report = delta.get("swot_report")
        if not isinstance(report, SWOTReportDelta):
            raise RuntimeError("Market research agent returned no report")
        report.sample_data = False

        # Competitors discovered but not promoted into the report. "Find more" serves these
        # before spending a search call.
        job.bench_competitors = [
            c for c in delta.get("bench_competitors", []) if isinstance(c, CompetitorProfile)
        ]

        for err in delta.get("errors", []):
            logger.warning("Job %s research error: %s", job.job_id, err)
        if delta.get("errors"):
            await self._log(
                job,
                f"[RESEARCH] Completed with {len(delta['errors'])} non-fatal error(s); see report diagnostics.",
                level="WARN",
            )
        return report

    async def _log_provider_health(self, job: CampaignJob) -> None:
        """Says up front when a scraping account is broken, instead of failing page by page."""
        from orchestrator.agents.market_research.ingestion.provider_health import check_providers

        if not get_settings().provider_health_check:
            return
        try:
            for p in await check_providers():
                if p["configured"] and not p["ok"]:
                    await self._log(job, f"[PROVIDERS] {p['provider']}: {p['detail']}", "WARNING")
        except Exception as exc:  # a status check must never block a run
            logger.info("Provider health check skipped: %s", exc)

    async def _run_audience_persona_node(self, job: CampaignJob, report_delta: SWOTReportDelta) -> list:
        from orchestrator.agents.audience_persona.agent import execute_audience_persona

        async def on_progress(message: str, level: str = "INFO") -> None:
            await self._log(job, message, level=level)

        try:
            delta = await execute_audience_persona(
                {"merchant_context": job.merchant_context, "swot_report": report_delta, "errors": []},
                llm_config=job.byok_config, on_progress=on_progress,
            )
            return list(delta.get("persona_profiles") or [])
        except Exception as exc:
            # Strategy derives personas from the research itself when this step has none.
            logger.warning("Audience persona node failed: %s", exc)
            await self._log(job, f"[AUDIENCE_PERSONA] Failed ({type(exc).__name__}); strategy will derive personas.", "WARNING")
            return []

    async def _run_campaign_strategy_node(
        self, job: CampaignJob, report_delta: SWOTReportDelta
    ) -> CampaignStrategyBrief:
        """Runs the Campaign Strategy agent in-process, forwarding its progress to the stream."""
        from orchestrator.agents.campaign_strategy.agent import execute_campaign_strategy

        state: StrategyState = {
            "merchant_context": job.merchant_context,
            "swot_report": report_delta,
            "persona_profiles": job.persona_profiles,
            "errors": [],
        }

        async def on_progress(message: str, level: str = "INFO") -> None:
            await self._log(job, message, level=level)

        delta = await execute_campaign_strategy(
            state, llm_config=job.byok_config, on_progress=on_progress
        )

        brief = delta.get("strategy_brief")
        if isinstance(brief, CampaignStrategyBrief):
            return brief
        if isinstance(delta.get("campaign_brief"), dict):
            return CampaignStrategyBrief(**delta["campaign_brief"])
        raise RuntimeError("Campaign strategy agent returned no strategy brief")

    async def customize_strategy(
        self,
        job_id: str,
        budget: float | None = None,
        selected_option_id: str | None = None,
        custom_goal: str | None = None,
        campaign_days: int | None = None,
        sub_goals: list[str] | None = None,
        campaign_type: str | None = None,
        custom_option: CampaignStrategyOption | None = None,
    ) -> CampaignStrategyBrief:
        """
        Re-scales strategy options and channel spend based on custom user budget,
        duration in days, sub-goals, campaign type, and optional custom strategy option.
        """
        job = await self.get_or_restore_job(job_id)
        if not job.last_swot_report:
            raise CampaignJobConflictError(f"Job {job_id} does not have a research report yet.")

        if budget is not None:
            job.merchant_context["budget"] = str(budget)
        if custom_goal is not None:
            job.merchant_context["goal"] = custom_goal
        if campaign_days is not None:
            job.merchant_context["campaign_days"] = campaign_days
        if sub_goals is not None:
            job.merchant_context["sub_goals"] = sub_goals
        if campaign_type is not None:
            job.merchant_context["campaign_type"] = campaign_type

        # Re-run strategy node with the updated parameters
        job.strategy_brief = await self._run_campaign_strategy_node(job, job.last_swot_report)

        if custom_option is not None:
            existing_idx = next(
                (i for i, opt in enumerate(job.strategy_brief.campaign_options) if opt.option_id == custom_option.option_id),
                None,
            )
            if existing_idx is not None:
                job.strategy_brief.campaign_options[existing_idx] = custom_option
            else:
                job.strategy_brief.campaign_options.insert(0, custom_option)
            job.strategy_brief.selected_option_id = custom_option.option_id
            if custom_option.channel_matrix:
                job.strategy_brief.channel_matrix = custom_option.channel_matrix
        elif selected_option_id:
            job.strategy_brief.selected_option_id = selected_option_id
            for opt in job.strategy_brief.campaign_options:
                if opt.option_id == selected_option_id:
                    job.strategy_brief.channel_matrix = opt.channel_matrix
                    break


        await self._log(
            job,
            f"[STRATEGY_CUSTOMIZED] User updated budget to {fmt_money(job.strategy_brief.user_budget or 0, job.strategy_brief.currency)}, duration to {job.strategy_brief.campaign_days} days, and selected option '{job.strategy_brief.selected_option_id}'.",
        )
        await self._emit_event(
            job,
            {
                "type": "STRATEGY_UPDATED",
                "brief": job.strategy_brief.model_dump(),
                "timestamp": _now_ms(),
            },
        )
        await get_storage().save_run(self._run_document(job))
        return job.strategy_brief

    async def approve_strategy(
        self,
        job_id: str,
        budget: float | None = None,
        selected_option_id: str | None = None,
        campaign_days: int | None = None,
        sub_goals: list[str] | None = None,
        campaign_type: str | None = None,
    ) -> CampaignStrategyBrief:
        """Confirms founder approval on the strategy brief, preparing downstream execution."""
        job = await self.get_or_restore_job(job_id)
        if not job.strategy_brief:
            if not job.last_swot_report:
                raise CampaignJobConflictError(f"Job {job_id} does not have a research report yet.")
            job.strategy_brief = await self._run_campaign_strategy_node(job, job.last_swot_report)

        if budget is not None:
            job.merchant_context["budget"] = str(budget)
            job.strategy_brief.user_budget = budget
        if campaign_days is not None:
            job.merchant_context["campaign_days"] = campaign_days
            job.strategy_brief.campaign_days = campaign_days
        if sub_goals is not None:
            job.merchant_context["sub_goals"] = sub_goals
            job.strategy_brief.sub_goals = sub_goals
        if campaign_type is not None:
            job.merchant_context["campaign_type"] = campaign_type
            job.strategy_brief.campaign_type = campaign_type
        if selected_option_id:
            job.strategy_brief.selected_option_id = selected_option_id
            for opt in job.strategy_brief.campaign_options:
                if opt.option_id == selected_option_id:
                    job.strategy_brief.channel_matrix = opt.channel_matrix
                    break

        job.strategy_brief.approval_status = "APPROVED_AND_DISPATCHED"
        await self._log(
            job,
            f"[STRATEGY_APPROVED] Founder approval confirmed (Option: '{job.strategy_brief.selected_option_id}'). Handing off to downstream execution engines.",
        )
        await self._emit_event(
            job,
            {
                "type": "STRATEGY_APPROVED",
                "brief": job.strategy_brief.model_dump(),
                "timestamp": _now_ms(),
            },
        )
        await get_storage().save_run(self._run_document(job))
        # Content is written from the approved strategy, in the background: approval returns now.
        if job.content_pack is None and (job.content_task is None or job.content_task.done()):
            job.content_task = asyncio.create_task(self._generate_content(job))
        return job.strategy_brief

    # ── Campaign content: written from the approved strategy, approved per channel ───────

    def _content_llm(self, job: CampaignJob) -> Any:
        from orchestrator.core.llm import build_chat_model

        return build_chat_model(byok=job.byok_config) if has_llm_credentials(job.byok_config) else None

    async def _generate_content(self, job: CampaignJob) -> None:
        from orchestrator.agents.content.writer import write_content

        await self._emit_event(job, {"type": "CONTENT_STARTED", "timestamp": _now_ms()})
        try:
            await self._log(job, "[CONTENT_WRITER] Writing assets for each channel in the approved plan")
            pack = await write_content(
                job.strategy_brief, job.last_swot_report, job.merchant_context, self._content_llm(job)
            )
            await self._log(job, f"[CONTENT_WRITER] {len(pack.assets)} asset(s) across {len(pack.channels())} channel(s)")
            self._qa_and_schedule(job, pack)
            flagged = sum(bool(a.qa_issues) for a in pack.assets)
            await self._log(job, f"[CONTENT_QA] {flagged} of {len(pack.assets)} asset(s) have something to check")
            planned = sum(bool(a.scheduled_for) for a in pack.assets)
            await self._log(job, f"[SCHEDULER] {planned} asset(s) given a planned date")
        except Exception as exc:
            logger.exception("Content generation failed for %s", job.job_id)
            pack = ContentPack(notes=[f"Content generation failed ({type(exc).__name__})."])
        job.content_pack = pack
        await self._emit_event(job, {"type": "CONTENT_READY", "content": pack.model_dump(), "timestamp": _now_ms()})
        await get_storage().save_run(self._run_document(job))

    def _qa_and_schedule(self, job: CampaignJob, pack: ContentPack) -> None:
        from orchestrator.agents.content.qa import review_pack
        from orchestrator.agents.content.scheduler import plan_schedule

        rivals = [c.brand_name for c in (job.last_swot_report.competitors if job.last_swot_report else [])]
        review_pack(pack, job.merchant_context, rivals)
        if job.strategy_brief:
            plan_schedule(pack, job.strategy_brief, job.merchant_context)

    async def get_content(self, job_id: str) -> ContentPack | None:
        job = await self.get_or_restore_job(job_id)
        return job.content_pack

    async def generate_content(self, job_id: str) -> None:
        """(Re)writes the whole pack; only allowed once the strategy is approved."""
        job = await self.get_or_restore_job(job_id)
        if not job.strategy_brief or job.strategy_brief.approval_status == "PENDING_APPROVAL":
            raise CampaignJobConflictError("Approve the strategy before writing content.")
        if job.content_task is not None and not job.content_task.done():
            raise CampaignJobConflictError("Content is already being written.")
        job.content_pack = None
        job.content_task = asyncio.create_task(self._generate_content(job))

    def _asset(self, job: CampaignJob, asset_id: str) -> ContentAsset:
        if not job.content_pack:
            raise CampaignJobConflictError("No content has been written for this campaign yet.")
        asset = next((a for a in job.content_pack.assets if a.asset_id == asset_id), None)
        if asset is None:
            raise CampaignJobNotFoundError(f"Asset {asset_id} not found")
        return asset

    async def edit_asset(self, job_id: str, asset_id: str, fields: dict[str, Any]) -> ContentAsset:
        """Merchant edits; an edit to an approved channel sends that channel back to review."""
        job = await self.get_or_restore_job(job_id)
        asset = self._asset(job, asset_id)
        if asset.status in ("scheduled", "published"):
            raise CampaignJobConflictError("This asset is already scheduled or published; unschedule it first.")
        editable = {"name", "subject", "preview_text", "body", "headlines", "descriptions", "cta", "scheduled_for",
                    "landing_url", "creative_brief", "hashtags"}
        updated = asset.model_copy(update={k: v for k, v in fields.items() if k in editable})
        updated = ContentAsset.model_validate(updated.model_dump() | {"status": "draft"})
        updated.qa_issues = self._qa(job, updated)
        self._replace_asset(job, updated)
        await get_storage().save_run(self._run_document(job))
        return updated

    async def regenerate_asset(self, job_id: str, asset_id: str, instruction: str | None = None) -> ContentAsset:
        from orchestrator.agents.content.writer import rewrite_asset

        job = await self.get_or_restore_job(job_id)
        asset = self._asset(job, asset_id)
        llm = self._content_llm(job)
        if llm is None:
            raise CampaignJobConflictError("Rewriting needs a language model; none is configured.")
        new = await rewrite_asset(asset, job.strategy_brief, job.last_swot_report, job.merchant_context, llm, instruction)
        new.scheduled_for = asset.scheduled_for
        new.qa_issues = self._qa(job, new)
        self._replace_asset(job, new)
        await get_storage().save_run(self._run_document(job))
        return new

    def _qa(self, job: CampaignJob, asset: ContentAsset) -> list[str]:
        from orchestrator.agents.content.qa import check_asset

        rivals = [c.brand_name for c in (job.last_swot_report.competitors if job.last_swot_report else [])]
        return check_asset(asset, job.merchant_context, rivals)

    async def reschedule_assets(
        self,
        job_id: str,
        shift_days: int = 0,
        time_of_day: str | None = None,
        channel: str | None = None,
        asset_ids: list[str] | None = None,
    ) -> ContentPack:
        """Moves planned dates/times; published or already-booked assets are left alone."""
        from datetime import datetime, timedelta

        job = await self.get_or_restore_job(job_id)
        pack = job.content_pack
        if not pack:
            raise CampaignJobConflictError("No content has been written for this campaign yet.")
        hh, mm = (int(x) for x in time_of_day.split(":")) if time_of_day else (None, None)
        moved = 0
        for a in pack.assets:
            if a.status in ("scheduled", "published") or not a.scheduled_for:
                continue
            if channel and a.channel != channel or asset_ids and a.asset_id not in asset_ids:
                continue
            when = datetime.fromisoformat(a.scheduled_for) + timedelta(days=shift_days)
            if hh is not None:
                when = when.replace(hour=hh, minute=mm)
            a.scheduled_for = when.isoformat()
            moved += 1
        if not moved:
            raise CampaignJobConflictError("No planned asset matched; nothing was moved.")
        await self._emit_event(job, {"type": "SCHEDULE_CHANGED", "moved": moved, "timestamp": _now_ms()})
        await get_storage().save_run(self._run_document(job))
        return pack

    def _replace_asset(self, job: CampaignJob, asset: ContentAsset) -> None:
        pack = job.content_pack
        assert pack is not None
        pack.assets = [asset if a.asset_id == asset.asset_id else a for a in pack.assets]
        if asset.status == "draft" and asset.channel in pack.approved_channels:
            pack.approved_channels = [c for c in pack.approved_channels if c != asset.channel]

    async def set_channel_approval(self, job_id: str, channel: str, approved: bool) -> ContentPack:
        job = await self.get_or_restore_job(job_id)
        pack = job.content_pack
        if not pack or channel not in pack.channels():
            raise CampaignJobNotFoundError(f"No content for channel {channel}")
        for a in pack.assets:
            if a.channel == channel and a.status in ("draft", "approved"):
                a.status = "approved" if approved else "draft"
        others = [c for c in pack.approved_channels if c != channel]
        pack.approved_channels = others + ([channel] if approved else [])  # type: ignore[list-item]
        await self._emit_event(job, {"type": "CONTENT_APPROVAL", "channel": channel, "approved": approved,
                                     "timestamp": _now_ms()})
        await get_storage().save_run(self._run_document(job))
        return pack

    # ── On-demand competitor discovery ───────────────────────────────────────

    async def find_more_competitors(
        self, job_id: str, names: list[str] | None = None
    ) -> tuple[SWOTReportDelta, list[CompetitorProfile]]:
        job = await self.get_or_restore_job(job_id)

        if not job.last_swot_report:
            raise CampaignJobConflictError(f"Job {job_id} does not have a research report yet.")

        # Serialize concurrent requests: each one reads and extends the same report.
        async with job.report_lock:
            return await self._find_more_competitors_locked(job, [n.strip() for n in names or [] if n.strip()])

    async def _find_more_competitors_locked(
        self, job: CampaignJob, names: list[str] | None = None
    ) -> tuple[SWOTReportDelta, list[CompetitorProfile]]:
        current_report = job.last_swot_report
        assert current_report is not None
        token = set_search_market(job.merchant_context)
        try:
            return await self._find_more_competitors_in_market(job, current_report, names)
        finally:
            reset_search_market(token)

    async def _find_more_competitors_in_market(
        self, job: CampaignJob, current_report: SWOTReportDelta, names: list[str] | None
    ) -> tuple[SWOTReportDelta, list[CompetitorProfile]]:
        existing_names = [c.brand_name for c in current_report.competitors]
        existing_keys = {_norm(c.brand_name) for c in current_report.competitors} | {
            _norm(f"{c.brand_name} {c.product_name}") for c in current_report.competitors
        } | {_norm(c.product_name) for c in current_report.competitors}

        category = job.merchant_context.get("category", "General")

        from orchestrator.agents.market_research.ingestion.ad_intelligence import search_competitor_ad_hooks
        from orchestrator.agents.market_research.ingestion.search_client import (
            SearchQuery,
            build_missing_data_queries,
            build_search_queries,
            derive_scale_signals,
            execute_tavily_search,
            filter_out_of_scale_results,
        )
        from orchestrator.agents.market_research.workflow.research_loop import extract_preliminary_competitors

        # Every branch below feeds the same follow-up searches, which need these; they used to
        # be defined only on the fresh-search branch, so promoting from the bench crashed.
        scale = derive_scale_signals(job.merchant_context)

        # The research loop already discovered more competitors than the top-N cut-off let
        # through. Serve the next in line from that bench before paying for a new search.
        bench_ready = [
            c for c in job.bench_competitors if _norm(c.brand_name) not in existing_keys
        ]
        new_competitors: list[CompetitorProfile] = bench_ready[:2]

        if names:
            # The merchant named who to research: use the bench's profile when it has one,
            # otherwise start from the name alone and let the targeted searches below fill it.
            missing = self._missing_keys(job)
            if missing:
                raise ResearchKeysMissingError(
                    f"Researching competitors needs {' and '.join(missing)}; no sample data is substituted."
                )
            requested = [n for n in dict.fromkeys(names) if _norm(n) not in existing_keys]
            bench_by_name = {_norm(c.brand_name): c for c in job.bench_competitors}
            new_competitors = [
                bench_by_name.get(_norm(n)) or CompetitorProfile(brand_name=n, product_name=n) for n in requested
            ]
            for c in new_competitors:
                c.named_by_merchant = True
            job.bench_competitors = [c for c in job.bench_competitors if _norm(c.brand_name) not in {_norm(n) for n in requested}]
            await self._log(
                job,
                f"[FIND_MORE_COMPETITORS] Researching named competitor(s): {', '.join(requested)}"
                if requested
                else "[FIND_MORE_COMPETITORS] Every named competitor is already in the report.",
            )
        elif new_competitors:
            served = {_norm(c.brand_name) for c in new_competitors}
            job.bench_competitors = [
                c for c in job.bench_competitors if _norm(c.brand_name) not in served
            ]
            await self._log(
                job,
                f"[FIND_MORE_COMPETITORS] Promoting {len(new_competitors)} from the discovery "
                f"bench ({len(job.bench_competitors)} still in reserve) — no new search needed: "
                f"{', '.join(c.brand_name for c in new_competitors)}",
            )
        else:
            await self._log(
                job,
                f"[FIND_MORE_COMPETITORS] Discovery bench empty — searching for competitors "
                f"beyond: {', '.join(existing_names[:4])}",
            )

            missing = self._missing_keys(job)
            if missing:
                raise ResearchKeysMissingError(
                    f"Finding competitors needs {' and '.join(missing)}; no sample data is substituted."
                )

            # Reuse the real generator so this path gets the same peer-scale anchoring, recency
            # window and incumbent exclusions as the research loop — then additionally exclude the
            # competitors already on the board.
            base_discovery = next(
                (
                    q for q in build_search_queries(job.merchant_context)
                    if q.vector == "alternative_discovery"
                ),
                None,
            )
            already_found = " ".join(f'-"{b}"' for b in existing_names[:5])
            query = SearchQuery(
                vector="alternative_discovery",
                query=f"{base_discovery.query} {already_found}".strip()
                if base_discovery
                else f'"best {category}" alternatives OR competitors {already_found}',
                time_range=base_discovery.time_range if base_discovery else "year",
            )
            batch_results = filter_out_of_scale_results(await execute_tavily_search([query]), scale)
            extracted = extract_preliminary_competitors(batch_results)
            fresh = [c for c in extracted if _norm(c.brand_name) not in existing_keys]
            new_competitors = fresh[:2]
            # Anything the search turned up beyond this batch refills the bench for next time.
            job.bench_competitors.extend(fresh[2:])

        # Bench competitors were discovered but never deep-crawled -- that budget went to the
        # shortlist. Now that the merchant has asked for them, crawl their own pages so they
        # arrive with the same pricing and evidence depth as the originals.
        if new_competitors:
            from orchestrator.agents.market_research.ingestion.page_extractor import (
                extract_competitor_target_urls,
                extract_pages,
            )
            from orchestrator.agents.market_research.workflow.research_loop import (
                enrich_competitors_from_pages,
                merge_duplicate_competitors,
            )

            # Start a mini-loop for just the new data to ensure it meets quality standards
            for iteration in range(1, 3):
                missing_queries = build_missing_data_queries(
                    job.merchant_context, new_competitors, current_report.dynamic_taxonomy, iteration=iteration
                )
                if not missing_queries:
                    break
                await self._log(job, f"[MORE_COMPETITORS] Iteration {iteration}: Fetching missing data for new competitors...")
                batch_results = filter_out_of_scale_results(await execute_tavily_search(missing_queries), scale)
                enriched_fresh = extract_preliminary_competitors(batch_results, [c.brand_name for c in new_competitors])
                
                # Keys taken before merging: computed after, they matched every profile the
                # follow-up searches turned up and let unrelated companies onto the report.
                target_keys = {_norm(c.brand_name) for c in new_competitors}
                new_competitors = merge_duplicate_competitors(new_competitors + enriched_fresh)
                new_competitors = [c for c in new_competitors if _norm(c.brand_name) in target_keys]
                # A competitor added by name starts without a website, so its seed and the profile
                # the search found are keyed apart; keep the one that has sources.
                by_name: dict[str, CompetitorProfile] = {}
                for c in new_competitors:
                    kept = by_name.get(_norm(c.brand_name))
                    if kept is None or (not kept.sources and c.sources):
                        by_name[_norm(c.brand_name)] = c
                new_competitors = list(by_name.values())

            settings = get_settings()
            crawl_urls = extract_competitor_target_urls(
                new_competitors,
                [],
                pages_per_competitor=research_limit(settings, "research_pages_per_competitor"),
                max_urls=research_limit(settings, "research_pages_per_competitor") * len(new_competitors),
            )
            if crawl_urls:
                await self._log(
                    job,
                    f"[DEEP_SEARCH] Deep-crawling {len(crawl_urls)} page(s) for "
                    f"{len(new_competitors)} promoted competitor(s)",
                )
                try:
                    pages = await extract_pages(crawl_urls)
                    enrich_competitors_from_pages(
                        new_competitors,
                        [{"url": p.url, "markdown": p.markdown} for p in pages],
                    )
                except Exception as exc:
                    await self._log(
                        job,
                        f"[DEEP_SEARCH] Crawl failed for promoted competitors ({type(exc).__name__}); "
                        f"they are returned with search-stage data only.",
                        level="WARN",
                    )

        ad_intel = await search_competitor_ad_hooks(
            new_competitors, category, target_geography=job.merchant_context.get("target_geography")
        )
        for c in new_competitors:
            c.ad_hooks = ad_intel.hooks_by_competitor.get(c.product_name, [])

        new_sources = [u for c in new_competitors for u in c.sources] + [d["url"] for d in ad_intel.documents]
        current_report.competitors.extend(new_competitors)
        current_report.source_urls = list(dict.fromkeys(current_report.source_urls + new_sources))
        from orchestrator.agents.market_research.intelligence.market_mapping.taxonomy import calculate_attribute_density

        current_report.attribute_density = calculate_attribute_density(
            current_report.competitors, current_report.dynamic_taxonomy
        )

        if new_competitors:
            await self._log(
                job,
                f"[MORE_COMPETITORS_FOUND] Added {len(new_competitors)} competitor(s): "
                f"{', '.join(c.brand_name for c in new_competitors)}",
            )
        else:
            await self._log(job, "[MORE_COMPETITORS_FOUND] No new competitors found.", level="WARN")

        await self._emit_event(
            job,
            {
                "type": "NODE_COMPLETE",
                "node": "market_research",
                "delta": {"swot_report": current_report.model_dump()},
                "timestamp": _now_ms(),
            },
        )

        # Persist the extended report and the drained bench; otherwise a restart would
        # re-serve competitors that are already on the board.
        await get_storage().save_run(self._run_document(job))

        return current_report, new_competitors

    async def edit_report(self, job_id: str, edits: list[ReportEdit]) -> tuple[SWOTReportDelta, list[str]]:
        """
        Applies merchant corrections to the report: remove a quote, correct or clear a price,
        remove a competitor. All edits are checked first and applied together, or none are.
        A corrected price is recorded in the competitor's change history as the merchant's,
        so the report never presents it as something the research found.
        """
        job = await self.get_or_restore_job(job_id)
        if not job.last_swot_report:
            raise CampaignJobConflictError(f"Job {job_id} does not have a research report yet.")

        async with job.report_lock:
            report, applied = apply_report_edits(job.last_swot_report.model_copy(deep=True), edits)

            from orchestrator.agents.market_research.intelligence.validation.scoring import calculate_dqs
            from orchestrator.agents.market_research.intelligence.market_mapping.taxonomy import calculate_attribute_density

            settings = get_settings()
            report.dqs_score = calculate_dqs(
                competitors=report.competitors, source_urls=report.source_urls, threshold=settings.dqs_threshold
            ).score
            report.attribute_density = calculate_attribute_density(report.competitors, report.dynamic_taxonomy)
            report.validation_diagnostics = report.validation_diagnostics + [f"[MERCHANT_EDIT] {a}" for a in applied]
            job.last_swot_report = report

            for a in applied:
                await self._log(job, f"[MERCHANT_EDIT] {a}")
            await self._emit_event(
                job,
                {
                    "type": "NODE_COMPLETE",
                    "node": "market_research",
                    "delta": {"swot_report": report.model_dump()},
                    "timestamp": _now_ms(),
                },
            )
            await get_storage().save_run(self._run_document(job))
            return report, applied

    async def rerun_market_research(self, job_id: str) -> SWOTReportDelta:
        job = await self.get_or_restore_job(job_id)
        missing = self._missing_keys(job)
        if missing:
            raise ResearchKeysMissingError(
                f"Re-research needs {' and '.join(missing)}; no sample data is substituted."
            )

        async with job.report_lock:
            await self._log(job, "[RE_RESEARCH] Initiating full re-research cycle with updated discovery rules...")
            report_delta = await self._run_market_research_node(job)
            job.last_swot_report = report_delta

            await self._emit_event(
                job,
                {
                    "type": "NODE_COMPLETE",
                    "node": "market_research",
                    "delta": {"swot_report": report_delta.model_dump()},
                    "timestamp": _now_ms(),
                },
            )

            await self._emit_event(
                job,
                {
                    "type": "RUN_COMPLETE",
                    "job_id": job.job_id,
                    "summary": {
                        "dqs_score": report_delta.dqs_score,
                        "attribute_density": report_delta.attribute_density,
                        "competitors": len(report_delta.competitors),
                        "mode": "live",
                    },
                    "timestamp": _now_ms(),
                },
            )

            await get_storage().save_run(self._run_document(job))
            return report_delta

    async def update_merchant_context(
        self, job_id: str, field: str, value: Any, reasoning: str | None = None
    ) -> tuple[dict[str, Any], str]:
        """
        Updates initial merchant brief parameters or campaign goal (Human-In-The-Loop).
        Can update goal, category, target audience, price, value prop, or product name.
        """
        job = await self.get_or_restore_job(job_id)
        old_val = job.merchant_context.get(field)
        job.merchant_context[field] = value

        msg = f"Updated merchant context '{field}' to '{value}'"
        if reasoning:
            msg += f" (Reasoning: {reasoning})"
        await self._log(job, f"[HITL] {msg}")

        await self._emit_event(
            job,
            {
                "type": "TELEMETRY_LOG",
                "level": "INFO",
                "message": f"[HITL] {msg}",
                "timestamp": _now_ms(),
            },
        )

        await get_storage().save_run(self._run_document(job))
        return job.merchant_context, f"Updated {field.replace('_', ' ')} from '{old_val}' to '{value}'"



# Global singleton instance for Dependency Injection
_campaign_service = CampaignService()


def get_campaign_service() -> CampaignService:
    return _campaign_service
