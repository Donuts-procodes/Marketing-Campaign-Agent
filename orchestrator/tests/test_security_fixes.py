"""
Regression checks for the audit fixes: API key gate, running-job cap, upload and field limits.
"""

import io
import json
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.core.config import get_settings
from orchestrator.main import app
from orchestrator.services import dossier
from orchestrator.services.dossier import DossierFormatError, extract_dossier_text

MERCHANT = {"merchant_context": {"product_name": "P", "category": "C", "primary_value_prop": "V"}}


@pytest.mark.asyncio
async def test_api_key_required_when_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "api_access_key", "s3cret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/v1/campaigns", json=MERCHANT)).status_code == 401
        wrong = await client.post("/api/v1/campaigns", json=MERCHANT, headers={"X-API-Key": "nope"})
        assert wrong.status_code == 401
        ok = await client.post("/api/v1/campaigns", json=MERCHANT, headers={"X-API-Key": "s3cret"})
        assert ok.status_code == 201
        assert (await client.get("/healthz")).status_code == 200  # health stays open


@pytest.mark.asyncio
async def test_running_job_cap_refuses_to_start_more_runs(monkeypatch):
    from orchestrator.services.campaign_service import get_campaign_service

    service = get_campaign_service()
    monkeypatch.setattr(get_settings(), "max_running_jobs", 0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = (await client.post("/api/v1/campaigns", json=MERCHANT)).json()["job_id"]
        resp = await client.get(f"/api/v1/campaigns/{job_id}/stream")
    events = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    assert events[-1]["type"] == "RUN_FAILED" and "busy" in events[-1]["message"].lower()
    assert service.get_job(job_id).is_started is False  # can be retried later


def test_docx_that_expands_too_far_is_rejected(monkeypatch):
    monkeypatch.setattr(dossier, "MAX_DOCX_XML_BYTES", 1000)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", "<a>" + "x" * 50_000 + "</a>")  # compresses to well under 1 KB
    assert len(buf.getvalue()) < 1000
    with pytest.raises(DossierFormatError, match="too large"):
        extract_dossier_text("bomb.docx", buf.getvalue())


def test_parse_errors_do_not_echo_parser_internals():
    with pytest.raises(DossierFormatError) as err:
        extract_dossier_text("broken.docx", b"not a zip")
    assert str(err.value) == "Could not read the DOCX file."


@pytest.mark.asyncio
async def test_oversized_request_fields_are_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        too_long = {"merchant_context": {**MERCHANT["merchant_context"], "product_name": "x" * 301}}
        too_many = {"merchant_context": {**MERCHANT["merchant_context"], "known_competitors": ["a"] * 21}}
        assert (await client.post("/api/v1/campaigns", json=too_long)).status_code == 422
        assert (await client.post("/api/v1/campaigns", json=too_many)).status_code == 422


def test_meta_api_errors_never_contain_the_token(monkeypatch):
    import asyncio

    import httpx

    from orchestrator.agents.market_research.ads import ad_intelligence

    monkeypatch.setattr(get_settings(), "meta_access_token", "TOKEN_ABC")
    transport = httpx.MockTransport(lambda r: httpx.Response(400, json={"error": {"message": "bad request"}}))
    real_client = httpx.AsyncClient
    monkeypatch.setattr(ad_intelligence.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw))

    with pytest.raises(RuntimeError) as err:
        asyncio.run(ad_intelligence._meta_graph_api("Acme"))
    assert "TOKEN_ABC" not in str(err.value) and "400" in str(err.value)


def test_saved_run_excludes_byok_key_and_dossier_text():
    from orchestrator.schemas.api import BYOKConfig
    from orchestrator.services.campaign_service import CampaignJob, CampaignService

    job = CampaignJob(
        "job-x",
        {"product_name": "P", "dossier": "secret plan " * 100},
        BYOKConfig(provider="openai", model="gpt-4o", api_key="sk-user-secret"),
    )
    job.dossier_text = "secret plan " * 100
    job.history_events = [{"seq": 0, "type": "RUN_COMPLETE"}]

    doc = CampaignService._run_document(job)

    assert doc["status"] == "complete" and doc["dossier_chars"] == 1200
    assert "dossier" not in doc["merchant_context"]
    assert "sk-user-secret" not in repr(doc)


@pytest.mark.asyncio
async def test_storage_is_a_noop_without_urls():
    from orchestrator.core.storage import Storage

    storage = Storage()
    await storage.connect()  # conftest blanks MONGO_URL / REDIS_URL
    assert await storage.allow_job_creation("1.2.3.4") is True
    assert await storage.load_run("job-x") is None
    await storage.save_run({"job_id": "job-x"})
