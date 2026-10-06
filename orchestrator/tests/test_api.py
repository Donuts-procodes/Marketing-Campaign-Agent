"""
Tests for FastAPI endpoints and campaign orchestration API.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "app": "marketing-orchestrator"}


@pytest.mark.asyncio
async def test_create_campaign():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "merchant_context": {
                "product_name": "ErgoMouse V2",
                "category": "B2B Peripherals",
                "primary_value_prop": "57-degree neutral wrist angle",
                "price_usd": 129.0,
                "known_competitors": ["Logitech Lift"],
            },
            "byok_config": None,
        }
        response = await client.post("/api/v1/campaigns", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "job_id" in data
        assert data["job_id"].startswith("job-")
        assert data["status"] == "PENDING"


@pytest.mark.asyncio
async def test_upload_dossier():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/api/v1/campaigns",
            json={
                "merchant_context": {
                    "product_name": "TestProduct",
                    "category": "Tech",
                    "primary_value_prop": "Fast",
                }
            },
        )
        job_id = create_resp.json()["job_id"]

        files = {"file": ("deck.txt", b"Product specification and pricing info.", "text/plain")}
        upload_resp = await client.post(
            f"/api/v1/campaigns/{job_id}/dossier",
            files=files,
        )
        assert upload_resp.status_code == 200
        data = upload_resp.json()
        assert data["status"] == "ATTACHED"
        assert data["characters"] > 0
        assert data["filename"] == "deck.txt"


@pytest.mark.asyncio
async def test_resolve_interrupt_unknown_job():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/campaigns/non-existent-job/resolve-interrupt",
            json={
                "checkpoint_id": "chk-fake",
                "action": "APPROVED",
            },
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_find_more_competitors_unknown_job():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/campaigns/job-fake-999/more-competitors")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_find_more_competitors_without_keys_never_invents_one(monkeypatch):
    from orchestrator.services.campaign_service import get_campaign_service
    from orchestrator.schemas.research import SWOTReportDelta, CompetitorProfile

    service = get_campaign_service()
    monkeypatch.setattr(service, "_missing_keys", lambda job: ["TAVILY_API_KEY"])
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/api/v1/campaigns",
            json={
                "merchant_context": {
                    "product_name": "ErgoMouse V2",
                    "category": "B2B Peripherals",
                    "primary_value_prop": "57-degree neutral wrist angle",
                    "known_competitors": ["Logitech", "Evoluent VerticalMouse"],
                }
            },
        )
        job_id = create_resp.json()["job_id"]
        job = service.get_job(job_id)
        job.last_swot_report = SWOTReportDelta(
            competitors=[
                CompetitorProfile(brand_name="Logitech", product_name="Lift", sources=["https://logitech.com"])
            ],
            source_urls=["https://logitech.com"],
        )

        response = await client.post(f"/api/v1/campaigns/{job_id}/more-competitors")
        assert response.status_code == 503
        assert "no sample data" in response.json()["detail"]
        assert len(job.last_swot_report.competitors) == 1

        re_res = await client.post(f"/api/v1/campaigns/{job_id}/re-research")
        assert re_res.status_code == 503
        assert "no sample data" in re_res.json()["detail"]



@pytest.mark.asyncio
async def test_upload_unsupported_dossier_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/v1/campaigns",
            json={"merchant_context": {"product_name": "P", "category": "C", "primary_value_prop": "V"}},
        )
        job_id = create_resp.json()["job_id"]
        resp = await client.post(
            f"/api/v1/campaigns/{job_id}/dossier",
            files={"file": ("deck.exe", b"MZ binary payload", "application/octet-stream")},
        )
        assert resp.status_code == 415


@pytest.mark.asyncio
async def test_upload_docx_dossier_extracts_text():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Launch plan for ErgoMouse</w:t></w:r></w:p></w:body></w:document>",
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/v1/campaigns",
            json={"merchant_context": {"product_name": "P", "category": "C", "primary_value_prop": "V"}},
        )
        job_id = create_resp.json()["job_id"]
        resp = await client.post(
            f"/api/v1/campaigns/{job_id}/dossier",
            files={"file": ("plan.docx", buf.getvalue(), "application/octet-stream")},
        )
        assert resp.status_code == 200
        from orchestrator.services.campaign_service import get_campaign_service

        job = get_campaign_service().get_job(job_id)
        assert job.dossier_text == "### plan.docx\nLaunch plan for ErgoMouse"


@pytest.mark.asyncio
async def test_upload_xlsx_dossier_extracts_text():
    import io
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ConsumerProfiles"
    ws.append(["Segment", "ICP", "PainPoint"])
    ws.append(["Enterprise", "VP Marketing", "High CAC"])
    buf = io.BytesIO()
    wb.save(buf)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/v1/campaigns",
            json={"merchant_context": {"product_name": "P", "category": "C", "primary_value_prop": "V"}},
        )
        job_id = create_resp.json()["job_id"]
        resp = await client.post(
            f"/api/v1/campaigns/{job_id}/dossier",
            files={"file": ("Consumer_Profile_Database.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        from orchestrator.services.campaign_service import get_campaign_service

        job = get_campaign_service().get_job(job_id)
        assert "Segment | ICP | PainPoint" in job.dossier_text
        assert "Enterprise | VP Marketing | High CAC" in job.dossier_text


@pytest.mark.asyncio
async def test_upload_csv_dossier_extracts_text():
    csv_bytes = b"Competitor,Price,Claim\nAcme,$99,Fastest\nBeta,$149,Reliable"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/v1/campaigns",
            json={"merchant_context": {"product_name": "P", "category": "C", "primary_value_prop": "V"}},
        )
        job_id = create_resp.json()["job_id"]
        resp = await client.post(
            f"/api/v1/campaigns/{job_id}/dossier",
            files={"file": ("competitors.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        from orchestrator.services.campaign_service import get_campaign_service

        job = get_campaign_service().get_job(job_id)
        assert "Competitor | Price | Claim" in job.dossier_text
        assert "Acme | $99 | Fastest" in job.dossier_text


@pytest.mark.asyncio
async def test_stream_without_keys_fails_and_replays_only_unseen_events(monkeypatch):
    import json

    from orchestrator.services.campaign_service import get_campaign_service

    service = get_campaign_service()
    monkeypatch.setattr(service, "_missing_keys", lambda job: ["TAVILY_API_KEY"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/v1/campaigns",
            json={"merchant_context": {"product_name": "P", "category": "Peripherals", "primary_value_prop": "V"}},
        )
        job_id = create_resp.json()["job_id"]

        first = await client.get(f"/api/v1/campaigns/{job_id}/stream")
        events = [json.loads(line[6:]) for line in first.text.splitlines() if line.startswith("data: ")]
        # Without keys the run fails loudly instead of showing sample data.
        assert events[-1]["type"] == "RUN_FAILED"
        assert "no sample data" in events[-1]["message"]
        assert [e["seq"] for e in events] == list(range(len(events)))
        assert not any(e["type"] == "NODE_COMPLETE" for e in events)

        # Resuming after the last seen event replays nothing.
        resumed = await client.get(f"/api/v1/campaigns/{job_id}/stream", params={"after": events[-1]["seq"]})
        assert "data: " not in resumed.text

        # Dossiers cannot be attached once the run has started.
        late = await client.post(
            f"/api/v1/campaigns/{job_id}/dossier",
            files={"file": ("deck.txt", b"late notes", "text/plain")},
        )
        assert late.status_code == 409


@pytest.mark.asyncio
async def test_re_research_rehydrates_from_storage(monkeypatch):
    from orchestrator.core.storage import get_storage
    from orchestrator.schemas.research import SWOTReportDelta
    from orchestrator.services.campaign_service import get_campaign_service

    service = get_campaign_service()
    storage = get_storage()

    job_id = "job-rehydrate-test-123"
    fake_doc = {
        "job_id": job_id,
        "merchant_context": {
            "product_name": "Antigravity Cloud",
            "category": "Cloud Computing",
            "primary_value_prop": "Fast and cheap",
        },
        "report": {
            "competitors": [],
            "source_urls": [],
            "dqs_score": 0.8,
            "attribute_density": 0.5,
        },
        "events": [],
    }
    # Ensure not in in-memory dict
    service._jobs.pop(job_id, None)

    # Mock storage load_run and save_run
    async def mock_load_run(jid):
        return fake_doc if jid == job_id else None

    async def mock_save_run(run):
        return None

    monkeypatch.setattr(storage, "load_run", mock_load_run)
    monkeypatch.setattr(storage, "save_run", mock_save_run)
    monkeypatch.setattr(service, "_missing_keys", lambda job: [])

    # Mock _run_market_research_node
    async def mock_run_node(job):
        return SWOTReportDelta(
            competitors=[],
            source_urls=["https://example.com"],
            dqs_score=0.9,
            attribute_density=0.6,
        )

    monkeypatch.setattr(service, "_run_market_research_node", mock_run_node)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/api/v1/campaigns/{job_id}/re-research")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["swot_report"]["dqs_score"] == 0.9
        assert data["swot_report"]["source_urls"] == ["https://example.com"]


