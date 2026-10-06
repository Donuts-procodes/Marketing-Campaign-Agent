"""
Redis temp storage: live events are mirrored on emit and replayed for a run not in memory,
before falling back to the durable MongoDB run. Redis slowness never stalls the stream.
"""

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.core import storage as storage_mod
from orchestrator.core.storage import Storage
from orchestrator.main import app

MERCHANT = {"merchant_context": {"product_name": "P", "category": "C", "primary_value_prop": "V"}}


class FakeRedisStorage(Storage):
    """In-memory stand-in: records appended events, serves them back, and counts calls."""

    def __init__(self):
        super().__init__()
        self.events: dict[str, list] = {}
        self.runs_saved: list[str] = []

    async def append_event(self, job_id, event):
        self.events.setdefault(job_id, []).append(event)

    async def load_events(self, job_id):
        return list(self.events.get(job_id, []))

    async def load_run(self, job_id):
        return None

    async def save_run(self, run):
        self.runs_saved.append(run["job_id"])

    async def allow_job_creation(self, client_id):
        return True


@pytest.fixture
def fake_storage(monkeypatch):
    fake = FakeRedisStorage()
    monkeypatch.setattr(storage_mod, "_storage", fake)
    return fake


@pytest.mark.asyncio
async def test_events_are_mirrored_and_replayed_from_temp_storage(fake_storage, monkeypatch):
    # No keys → the run fails fast but still emits NODE_STARTED + RUN_FAILED, which must be mirrored.
    monkeypatch.setattr("orchestrator.services.campaign_service.get_storage", lambda: fake_storage)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = (await client.post("/api/v1/campaigns", json=MERCHANT)).json()["job_id"]
        first = await client.get(f"/api/v1/campaigns/{job_id}/stream")
    live = [json.loads(l[6:]) for l in first.text.splitlines() if l.startswith("data: ")]

    # The same events were written to temp storage...
    assert fake_storage.events[job_id] == [e for e in live if "seq" in e]
    assert live[-1]["type"] == "RUN_FAILED"

    # ...and a brand-new service (as if another worker / after a restart) replays them from temp storage.
    from orchestrator.services.campaign_service import CampaignService

    fresh = CampaignService()
    frames = [frame async for frame in fresh.stream_job_events(job_id, after_seq=-1)]
    replayed = [json.loads(f.split("data: ", 1)[1]) for f in frames]
    assert [e["type"] for e in replayed] == [e["type"] for e in live if "seq" in e]

    # after_seq replays only newer events.
    tail = [f async for f in fresh.stream_job_events(job_id, after_seq=live[-1]["seq"] - 1)]
    assert len(tail) == 1


@pytest.mark.asyncio
async def test_slow_redis_append_does_not_block(monkeypatch):
    storage = Storage()

    class HangingRedis:
        def pipeline(self):
            return self

        def rpush(self, *a): ...
        def expire(self, *a): ...

        async def execute(self):
            await asyncio.sleep(30)  # hung, not failed

    storage.redis = HangingRedis()
    monkeypatch.setattr(storage_mod, "_REDIS_OP_TIMEOUT", 0.05)

    # Returns promptly despite the 30s hang, because of the per-command timeout.
    await asyncio.wait_for(storage.append_event("job-x", {"seq": 0, "type": "X"}), timeout=2.0)
