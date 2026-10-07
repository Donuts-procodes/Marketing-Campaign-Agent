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

from orchestrator.core.config import get_settings
from orchestrator.core.llm import has_llm_credentials
from orchestrator.core.storage import get_storage
from orchestrator.schemas.api import BYOKConfig, CampaignCreate
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta
from orchestrator.schemas.state import StrategyState
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
        self.task: asyncio.Task[None] | None = None
        self.report_lock: asyncio.Lock = asyncio.Lock()
        self.created_at: float = time.monotonic()
        self.finished_at: float | None = None
        self.bench_competitors: list[CompetitorProfile] = []


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
        restored.bench_competitors = [
            CompetitorProfile(**c) for c in doc.get("bench_competitors") or []
        ]
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
        try:
            await self._emit_event(
                job, {"type": "NODE_STARTED", "node": "market_research", "timestamp": _now_ms()}
            )

            missing = self._missing_keys(job)
            if missing:
                raise ResearchKeysMissingError(
                    f"Live research needs {' and '.join(missing)}; no sample data is substituted."
                )
            settings = get_settings()
            if not (settings.firecrawl_api_key or settings.crawlapi_token or settings.crawlapi_js_token):
                await self._log(
                    job,
                    "[DEEP_SEARCH] No crawl API key (FIRECRAWL_API_KEY or CRAWLAPI_TOKEN) — deep search "
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

            # Downstream agents are not implemented yet; report them as skipped pass-throughs.
            for node in ("audience_persona", "campaign_strategy"):
                await self._emit_event(job, {"type": "NODE_STARTED", "node": node, "timestamp": _now_ms()})
                await self._log(job, f"[{node.upper()}] Agent not implemented yet — skipped.")
                await self._emit_event(
                    job, {"type": "NODE_COMPLETE", "node": node, "delta": {}, "timestamp": _now_ms()}
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
        last = job.history_events[-1]["type"] if job.history_events else None
        return {
            "job_id": job.job_id,
            "finished_at": datetime.now(timezone.utc),
            "status": "complete" if last == "RUN_COMPLETE" else "failed",
            "label": job.label,
            "merchant_context": context,
            "dossier_chars": len(job.dossier_text or ""),
            "report": job.last_swot_report.model_dump() if job.last_swot_report else None,
            # Kept so "find more competitors" can still serve the next in line after a restart.
            "bench_competitors": [c.model_dump() for c in job.bench_competitors],
            "events": job.history_events,
        }

    # ── Session management: list / rename / delete past runs ─────────────────

    def _summary(self, job: CampaignJob) -> dict:
        status = "running" if (job.is_started and not job.is_finished) else (
            "pending" if not job.is_started else (
                "complete" if job.history_events and job.history_events[-1]["type"] == "RUN_COMPLETE" else "failed"
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

        state: StrategyState = {
            "merchant_context": job.merchant_context,
            "swot_report": None,
            "dqs_retries": 0,
            "errors": [],
            "run_mode": run_mode,
            "prior_report": prior_report,
            "prior_run_at": prior_run_at,
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

    # ── On-demand competitor discovery ───────────────────────────────────────

    async def find_more_competitors(
        self, job_id: str
    ) -> tuple[SWOTReportDelta, list[CompetitorProfile]]:
        job = await self.get_or_restore_job(job_id)

        if not job.last_swot_report:
            raise CampaignJobConflictError(f"Job {job_id} does not have a research report yet.")

        # Serialize concurrent requests: each one reads and extends the same report.
        async with job.report_lock:
            return await self._find_more_competitors_locked(job)

    async def _find_more_competitors_locked(
        self, job: CampaignJob
    ) -> tuple[SWOTReportDelta, list[CompetitorProfile]]:
        current_report = job.last_swot_report
        assert current_report is not None
        existing_names = [c.brand_name for c in current_report.competitors]
        existing_keys = {_norm(c.brand_name) for c in current_report.competitors} | {
            _norm(f"{c.brand_name} {c.product_name}") for c in current_report.competitors
        } | {_norm(c.product_name) for c in current_report.competitors}

        category = job.merchant_context.get("category", "General")

        from orchestrator.agents.market_research.ads.ad_intelligence import search_competitor_ad_hooks

        # The research loop already discovered more competitors than the top-N cut-off let
        # through. Serve the next in line from that bench before paying for a new search.
        bench_ready = [
            c for c in job.bench_competitors if _norm(c.brand_name) not in existing_keys
        ]
        new_competitors: list[CompetitorProfile] = bench_ready[:2]

        if new_competitors:
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

            from orchestrator.agents.market_research.pipeline.loop import extract_preliminary_competitors
            from orchestrator.agents.market_research.discovery.search import (
                SearchQuery,
                build_search_queries,
                derive_scale_signals,
                execute_tavily_search,
                filter_out_of_scale_results,
            )

            # Reuse the real generator so this path gets the same peer-scale anchoring, recency
            # window and incumbent exclusions as the research loop — then additionally exclude the
            # competitors already on the board.
            scale = derive_scale_signals(job.merchant_context)
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
            from orchestrator.agents.market_research.discovery.crawler import (
                extract_competitor_target_urls,
                extract_pages,
            )
            from orchestrator.agents.market_research.pipeline.loop import (
                enrich_competitors_from_pages,
            )

            settings = get_settings()
            crawl_urls = extract_competitor_target_urls(
                new_competitors,
                [],
                pages_per_competitor=settings.research_pages_per_competitor,
                max_urls=settings.research_pages_per_competitor * len(new_competitors),
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
        from orchestrator.agents.market_research.analysis.taxonomy import calculate_attribute_density

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


# Global singleton instance for Dependency Injection
_campaign_service = CampaignService()


def get_campaign_service() -> CampaignService:
    return _campaign_service
