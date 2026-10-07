"""
MongoDB (finished runs) and Redis (run-creation rate limit), opened in the app lifespan.

Both are optional: with no URL configured, or when the server is unreachable, the methods
degrade to no-ops (nothing persisted, no rate limit) and the app keeps working in memory.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from orchestrator.core.config import get_settings

logger = logging.getLogger(__name__)

_RATE_WINDOW_SECONDS = 3600
_EVENTS_KEY = "run:events:{job_id}"
# Per-command ceiling: a hung (not failed) Redis must never stall the research event stream.
_REDIS_OP_TIMEOUT = 2.0


class Storage:
    def __init__(self) -> None:
        self.mongo: Any = None
        self.runs: Any = None  # campaign_runs collection
        self.redis: Any = None

    async def connect(self) -> None:
        settings = get_settings()
        if settings.mongo_url:
            try:
                from pymongo import AsyncMongoClient

                self.mongo = AsyncMongoClient(settings.mongo_url, serverSelectionTimeoutMS=3000)
                await self.mongo.admin.command("ping")
                self.runs = self.mongo[settings.mongo_db]["campaign_runs"]
                await self.runs.create_index("job_id", unique=True)
                logger.info("MongoDB connected (%s)", settings.mongo_db)
            except Exception as exc:
                logger.warning("MongoDB unavailable, runs are kept in memory only: %s", type(exc).__name__)
                await self._close_mongo()
        if settings.redis_url:
            try:
                import redis.asyncio as redis

                self.redis = redis.from_url(settings.redis_url, socket_connect_timeout=3)
                await self.redis.ping()
                logger.info("Redis connected")
            except Exception as exc:
                logger.warning("Redis unavailable, run creation is not rate limited: %s", type(exc).__name__)
                await self._close_redis()

    async def close(self) -> None:
        await self._close_mongo()
        await self._close_redis()

    async def _close_mongo(self) -> None:
        if self.mongo is not None:
            await self.mongo.close()
        self.mongo = self.runs = None

    async def _close_redis(self) -> None:
        if self.redis is not None:
            await self.redis.aclose()
        self.redis = None

    # ── MongoDB: finished runs ──────────────────────────────────────────────

    async def save_run(self, run: dict[str, Any]) -> None:
        if self.runs is None:
            return
        try:
            await self.runs.replace_one({"job_id": run["job_id"]}, run, upsert=True)
        except Exception as exc:
            logger.warning("Could not save run %s to MongoDB: %s", run.get("job_id"), type(exc).__name__)

    async def load_run(self, job_id: str) -> dict[str, Any] | None:
        if self.runs is None:
            return None
        try:
            return await self.runs.find_one({"job_id": job_id}, {"_id": 0})
        except Exception as exc:
            logger.warning("Could not load run %s from MongoDB: %s", job_id, type(exc).__name__)
            return None

    async def find_latest_run_by_product(
        self, product_name: str, category: str = ""
    ) -> dict[str, Any] | None:
        """
        Returns the most recent completed run for a given product (and optionally category),
        or None when no matching run exists. Used to seed an update run with prior findings.
        """
        if self.runs is None:
            return None
        name_lower = product_name.strip().lower()
        if not name_lower:
            return None
        try:
            cursor = self.runs.find(
                {"status": "complete"},
                {"_id": 0},
            ).sort("finished_at", -1).limit(50)
            async for doc in cursor:
                ctx = doc.get("merchant_context", {})
                stored_name = (ctx.get("product_name") or "").strip().lower()
                stored_cat = (ctx.get("category") or "").strip().lower()
                if stored_name == name_lower:
                    if not category or not stored_cat or stored_cat == category.strip().lower():
                        return doc
        except Exception as exc:
            logger.warning("Could not query prior run for %r: %s", product_name, type(exc).__name__)
        return None

    async def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Recent runs, newest first, as lightweight summaries (no events / report body)."""
        if self.runs is None:
            return []
        projection = {
            "_id": 0, "job_id": 1, "status": 1, "label": 1, "finished_at": 1,
            "merchant_context.product_name": 1, "merchant_context.category": 1,
        }
        try:
            cursor = self.runs.find({}, projection).sort("finished_at", -1).limit(limit)
            return [doc async for doc in cursor]
        except Exception as exc:
            logger.warning("Could not list runs from MongoDB: %s", type(exc).__name__)
            return []

    async def update_run(self, job_id: str, fields: dict[str, Any]) -> bool:
        """Merges `fields` into a saved run (e.g. a label). True when a run was updated."""
        if self.runs is None:
            return False
        try:
            result = await self.runs.update_one({"job_id": job_id}, {"$set": fields})
            return result.matched_count > 0
        except Exception as exc:
            logger.warning("Could not update run %s in MongoDB: %s", job_id, type(exc).__name__)
            return False

    async def delete_run(self, job_id: str) -> bool:
        """Removes a run's durable record (MongoDB) and its temp events (Redis)."""
        deleted = False
        if self.runs is not None:
            try:
                result = await self.runs.delete_one({"job_id": job_id})
                deleted = result.deleted_count > 0
            except Exception as exc:
                logger.warning("Could not delete run %s from MongoDB: %s", job_id, type(exc).__name__)
        if self.redis is not None:
            try:
                await asyncio.wait_for(
                    self.redis.delete(_EVENTS_KEY.format(job_id=job_id)), timeout=_REDIS_OP_TIMEOUT
                )
            except Exception as exc:
                logger.warning("Could not delete events for %s from Redis: %s", job_id, type(exc).__name__)
        return deleted

    # ── Redis: temp storage of live run events (TTL'd) ──────────────────────

    async def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        """Appends one live event to the run's Redis list and refreshes its TTL."""
        if self.redis is None:
            return
        key = _EVENTS_KEY.format(job_id=job_id)
        ttl = get_settings().job_ttl_seconds
        try:
            pipe = self.redis.pipeline()
            pipe.rpush(key, json.dumps(event))
            pipe.expire(key, ttl)
            await asyncio.wait_for(pipe.execute(), timeout=_REDIS_OP_TIMEOUT)
        except Exception as exc:
            logger.warning("Could not append event for %s to Redis: %s", job_id, type(exc).__name__)

    async def load_events(self, job_id: str) -> list[dict[str, Any]]:
        """Returns the live events stored for a run, or [] when Redis is off or has none."""
        if self.redis is None:
            return []
        try:
            raw = await asyncio.wait_for(
                self.redis.lrange(_EVENTS_KEY.format(job_id=job_id), 0, -1), timeout=_REDIS_OP_TIMEOUT
            )
            return [json.loads(item) for item in raw]
        except Exception as exc:
            logger.warning("Could not load events for %s from Redis: %s", job_id, type(exc).__name__)
            return []

    # ── Redis: sliding-window rate limit on run creation ────────────────────

    async def allow_job_creation(self, client_id: str) -> bool:
        """True when `client_id` created fewer than max_jobs_per_hour runs in the last hour."""
        if self.redis is None:
            return True
        key = f"ratelimit:jobs:{client_id}"
        now = time.time()
        try:
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, now - _RATE_WINDOW_SECONDS)
            pipe.zcard(key)
            _, count = await asyncio.wait_for(pipe.execute(), timeout=_REDIS_OP_TIMEOUT)
            if count >= get_settings().max_jobs_per_hour:
                return False
            pipe = self.redis.pipeline()
            pipe.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
            pipe.expire(key, _RATE_WINDOW_SECONDS)
            await asyncio.wait_for(pipe.execute(), timeout=_REDIS_OP_TIMEOUT)
            return True
        except Exception as exc:
            # ponytail: fail open — a Redis outage should not take run creation down with it.
            logger.warning("Redis rate limit check failed, allowing: %s", type(exc).__name__)
            return True


_storage = Storage()


def get_storage() -> Storage:
    return _storage
