import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta


def _report():
    return SWOTReportDelta(
        competitors=[
            CompetitorProfile(
                brand_name="Praxent",
                product_name="Praxent Services",
                pricing_model="$5,000 per project",
                weaknesses_mined=["Onboarding was slow.", "Support was slow to reply on weekends."],
                sources=["https://praxent.com"],
            ),
            CompetitorProfile(brand_name="MojoTech", product_name="MojoTech", sources=["https://mojotech.com"]),
        ],
        source_urls=["https://praxent.com", "https://mojotech.com"],
    )


async def _job(client, report=None):
    from orchestrator.services.campaign_service import get_campaign_service

    resp = await client.post(
        "/api/v1/campaigns",
        json={"merchant_context": {"product_name": "DevFlow", "category": "Software agency", "primary_value_prop": "Fast"}},
    )
    job_id = resp.json()["job_id"]
    job = get_campaign_service().get_job(job_id)
    job.last_swot_report = report
    return job_id, job


@pytest.mark.asyncio
async def test_edits_apply_together_and_price_correction_is_marked_as_the_merchants():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, job = await _job(client, _report())
        resp = await client.post(
            f"/api/v1/campaigns/{job_id}/report/edits",
            json={"edits": [
                {"op": "remove_item", "competitor": "praxent", "field": "weaknesses_mined", "value": "onboarding was slow."},
                {"op": "set_price", "competitor": "Praxent", "value": "$8,000 per project"},
                {"op": "remove_competitor", "competitor": "MojoTech"},
            ]},
        )
        assert resp.status_code == 200, resp.text
        comp = job.last_swot_report.competitors[0]
        assert [c.brand_name for c in job.last_swot_report.competitors] == ["Praxent"]
        assert comp.weaknesses_mined == ["Support was slow to reply on weekends."]
        assert comp.pricing_model == "$8,000 per project"
        change = comp.change_history[-1]
        assert (change.previous, change.current, change.source) == ("$5,000 per project", "$8,000 per project", "merchant")
        assert any(d.startswith("[MERCHANT_EDIT]") for d in job.last_swot_report.validation_diagnostics)
        assert len(resp.json()["applied"]) == 3


@pytest.mark.asyncio
async def test_one_bad_edit_rejects_the_whole_batch():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, job = await _job(client, _report())
        resp = await client.post(
            f"/api/v1/campaigns/{job_id}/report/edits",
            json={"edits": [
                {"op": "remove_competitor", "competitor": "MojoTech"},
                {"op": "remove_item", "competitor": "Praxent", "field": "weaknesses_mined", "value": "slow"},
            ]},
        )
        assert resp.status_code == 422
        assert "matches several items" in resp.json()["detail"]
        assert len(job.last_swot_report.competitors) == 2, "nothing may change when any edit is invalid"

        resp = await client.post(
            f"/api/v1/campaigns/{job_id}/report/edits",
            json={"edits": [{"op": "set_price", "competitor": "Nobody Inc", "value": "$1"}]},
        )
        assert resp.status_code == 422 and "Praxent" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_edit_paths_for_missing_job_and_missing_report():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {"edits": [{"op": "remove_competitor", "competitor": "X"}]}
        assert (await client.post("/api/v1/campaigns/job-nope/report/edits", json=body)).status_code == 404
        job_id, _ = await _job(client, None)
        assert (await client.post(f"/api/v1/campaigns/{job_id}/report/edits", json=body)).status_code == 409


def _stub_research(monkeypatch):
    """No network: search returns the named rival plus an unrelated company, crawl and ads return nothing."""
    from orchestrator.agents.market_research.ingestion import ad_intelligence
    from orchestrator.agents.market_research.ingestion import page_extractor as crawler
    from orchestrator.agents.market_research.ingestion import search_client as search
    from orchestrator.agents.market_research.ingestion.search_client import TavilySearchResult

    async def _search(queries, tavily_client=None):
        return [
            TavilySearchResult(vector="pricing_scrape", title="Acme Labs pricing", url="https://acmelabs.io/pricing",
                               snippet="Acme Labs builds web apps for startups. Plans start at $99/month.", score=0.9),
            TavilySearchResult(vector="alternative_discovery", title="OtherCo Platform", url="https://otherco.com/",
                               snippet="OtherCo builds software for teams and ships it fast.", score=0.9),
        ]

    async def _pages(urls, *a, **k):
        return []

    async def _ads(competitors, *a, **k):
        return ad_intelligence.AdIntelResult()

    monkeypatch.setattr(search, "execute_tavily_search", _search)
    monkeypatch.setattr(crawler, "extract_pages", _pages)
    monkeypatch.setattr(ad_intelligence, "search_competitor_ad_hooks", _ads)


@pytest.mark.asyncio
async def test_named_research_adds_only_that_rival(monkeypatch):
    from orchestrator.services.campaign_service import get_campaign_service

    _stub_research(monkeypatch)
    monkeypatch.setattr(get_campaign_service(), "_missing_keys", lambda job: [])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, job = await _job(client, _report())
        resp = await client.post(f"/api/v1/campaigns/{job_id}/more-competitors", json={"names": ["Acme Labs"]})
        assert resp.status_code == 200, resp.text
        names = [c.brand_name for c in job.last_swot_report.competitors]
        assert names[:2] == ["Praxent", "MojoTech"]
        assert "OtherCo" not in names, "follow-up search results must not add unrelated companies"
        assert [c["brand_name"] for c in resp.json()["added_competitors"]] == ["Acme Labs"]


@pytest.mark.asyncio
async def test_promoting_from_the_bench_runs_the_follow_up_searches(monkeypatch):
    """Regression: the bench path used names defined only on the fresh-search branch."""
    from orchestrator.services.campaign_service import get_campaign_service

    _stub_research(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, job = await _job(client, _report())
        job.bench_competitors = [CompetitorProfile(brand_name="Acme Labs", product_name="Acme Labs", sources=["https://acmelabs.io"])]
        resp = await client.post(f"/api/v1/campaigns/{job_id}/more-competitors")
        assert resp.status_code == 200, resp.text
        assert "Acme Labs" in [c.brand_name for c in job.last_swot_report.competitors]
        assert job.bench_competitors == []
