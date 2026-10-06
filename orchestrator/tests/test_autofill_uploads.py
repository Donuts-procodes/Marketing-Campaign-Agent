"""
Multi-file dossier uploads and document autofill.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app
from orchestrator.schemas.api import AutofillFields
from orchestrator.services import autofill

MERCHANT = {"merchant_context": {"product_name": "P", "category": "C", "primary_value_prop": "V"}}
BRIEF = b"DealFlow CRM is a pipeline CRM for small sales teams. Price: $29 per seat. We compete with Pipedrive."
DECK = b"Goal: win 500 agencies in 2027. Customers: agency owners, sales managers."


@pytest.mark.asyncio
async def test_multiple_dossier_files_are_combined():
    from orchestrator.services.campaign_service import get_campaign_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = (await client.post("/api/v1/campaigns", json=MERCHANT)).json()["job_id"]
        resp = await client.post(
            f"/api/v1/campaigns/{job_id}/dossier",
            files=[("files", ("brief.txt", BRIEF, "text/plain")), ("files", ("deck.md", DECK, "text/markdown"))],
        )
    assert resp.status_code == 200
    body = resp.json()
    assert [f["filename"] for f in body["files"]] == ["brief.txt", "deck.md"]
    text = get_campaign_service().get_job(job_id).dossier_text
    assert "### brief.txt" in text and "### deck.md" in text and "agency owners" in text


@pytest.mark.asyncio
async def test_too_many_files_rejected(monkeypatch):
    from orchestrator.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_files", 2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = (await client.post("/api/v1/campaigns", json=MERCHANT)).json()["job_id"]
        files = [("files", (f"f{i}.txt", b"some text", "text/plain")) for i in range(3)]
        resp = await client.post(f"/api/v1/campaigns/{job_id}/dossier", files=files)
    assert resp.status_code == 413


def _llm_returning(fields: AutofillFields):
    llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=fields)
    llm.with_structured_output = MagicMock(return_value=structured)
    return llm


@pytest.mark.asyncio
async def test_autofill_keeps_only_what_the_documents_state():
    text = (BRIEF + b"\n" + DECK).decode()
    llm = _llm_returning(AutofillFields(
        product_name="DealFlow CRM",
        category="Sales CRM",
        price_usd=29,
        known_competitors=["Pipedrive", "Salesforce"],  # Salesforce is not in the documents
        existing_customer_profiles=["agency owners", "sales managers"],
    ))

    fields = await autofill.autofill_from_text(text, llm=llm)

    assert fields.product_name == "DealFlow CRM"
    assert fields.price_usd == 29
    assert fields.known_competitors == ["Pipedrive"]
    assert autofill.filled_field_names(fields) == [
        "product_name", "category", "price_usd", "known_competitors", "existing_customer_profiles",
    ]


@pytest.mark.asyncio
async def test_autofill_drops_invented_name_and_price():
    llm = _llm_returning(AutofillFields(product_name="SuperCRM Pro", price_usd=49.99))
    fields = await autofill.autofill_from_text(BRIEF.decode(), llm=llm)
    assert fields.product_name is None and fields.price_usd is None


@pytest.mark.asyncio
async def test_autofill_endpoint_reads_multiple_files(monkeypatch):
    seen = {}

    async def fake_autofill(text, llm=None):
        seen["text"] = text
        return AutofillFields(product_name="DealFlow CRM", goal="win 500 agencies in 2027")

    monkeypatch.setattr("orchestrator.api.endpoints.campaigns.autofill_from_text", fake_autofill)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/campaigns/autofill",
            files=[("files", ("brief.txt", BRIEF, "text/plain")), ("files", ("deck.md", DECK, "text/markdown"))],
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filled"] == ["product_name", "goal"]
    assert [f["filename"] for f in body["files"]] == ["brief.txt", "deck.md"]
    assert "### brief.txt" in seen["text"] and "### deck.md" in seen["text"]


@pytest.mark.asyncio
async def test_autofill_without_llm_returns_503():
    # conftest blanks OPENAI_API_KEY, so no model can be built.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/campaigns/autofill", files=[("files", ("brief.txt", BRIEF, "text/plain"))])
    assert resp.status_code == 503
