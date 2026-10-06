"""
Session management: list recent runs, rename, and delete (memory + storage).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.core import storage as storage_mod
from orchestrator.core.storage import Storage
from orchestrator.main import app

MERCHANT = {"merchant_context": {"product_name": "DealFlow CRM", "category": "Sales CRM", "primary_value_prop": "V"}}


class MemStorage(Storage):
    """In-memory stand-in for Mongo+Redis so session CRUD is testable without servers."""

    def __init__(self):
        super().__init__()
        self.docs: dict[str, dict] = {}
        self.events: dict[str, list] = {}

    async def append_event(self, job_id, event):
        self.events.setdefault(job_id, []).append(event)

    async def load_events(self, job_id):
        return list(self.events.get(job_id, []))

    async def save_run(self, run):
        self.docs[run["job_id"]] = run

    async def load_run(self, job_id):
        return self.docs.get(job_id)

    async def list_runs(self, limit=50):
        return sorted(self.docs.values(), key=lambda d: d.get("finished_at") or "", reverse=True)[:limit]

    async def update_run(self, job_id, fields):
        if job_id in self.docs:
            self.docs[job_id].update(fields)
            return True
        return False

    async def delete_run(self, job_id):
        self.events.pop(job_id, None)
        return self.docs.pop(job_id, None) is not None

    async def allow_job_creation(self, client_id):
        return True


@pytest.fixture
def mem(monkeypatch):
    s = MemStorage()
    monkeypatch.setattr(storage_mod, "_storage", s)
    monkeypatch.setattr("orchestrator.services.campaign_service.get_storage", lambda: s)
    # fresh service so no jobs leak between tests
    from orchestrator.services import campaign_service as cs
    monkeypatch.setattr(cs, "_campaign_service", cs.CampaignService())
    return s


async def _finish_one(client) -> str:
    """Create + stream a run to completion (fails fast: no API keys), leaving a saved doc."""
    job_id = (await client.post("/api/v1/campaigns", json=MERCHANT)).json()["job_id"]
    await client.get(f"/api/v1/campaigns/{job_id}/stream")
    return job_id


@pytest.mark.asyncio
async def test_list_rename_delete_roundtrip(mem):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = await _finish_one(client)

        listed = (await client.get("/api/v1/campaigns/sessions")).json()["sessions"]
        assert any(s["job_id"] == job_id and s["product_name"] == "DealFlow CRM" for s in listed)

        renamed = await client.patch(f"/api/v1/campaigns/{job_id}", json={"label": "Q1 launch"})
        assert renamed.status_code == 200 and renamed.json()["label"] == "Q1 launch"
        assert mem.docs[job_id]["label"] == "Q1 launch"

        deleted = await client.delete(f"/api/v1/campaigns/{job_id}")
        assert deleted.status_code == 204
        assert job_id not in mem.docs
        after = (await client.get("/api/v1/campaigns/sessions")).json()["sessions"]
        assert all(s["job_id"] != job_id for s in after)


@pytest.mark.asyncio
async def test_delete_and_rename_unknown_session_404(mem):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.delete("/api/v1/campaigns/job-nope")).status_code == 404
        assert (await client.patch("/api/v1/campaigns/job-nope", json={"label": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_deleted_session_stops_being_replayable(mem):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = await _finish_one(client)
        assert mem.events.get(job_id)  # events were mirrored
        await client.delete(f"/api/v1/campaigns/{job_id}")
        # A fresh stream now finds neither temp events nor a saved run.
        resp = await client.get(f"/api/v1/campaigns/{job_id}/stream")
        assert "was not found" in resp.text
