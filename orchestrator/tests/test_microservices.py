"""
Tests for Agent Microservice Architecture.

Verifies:
- Autonomous microservice factory (/health, /info, /execute endpoints)
- RemoteAgentNode HTTP client adapter & automatic fallback
- End-to-end integration between microservice and LangGraph Strategy SubGraph
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from orchestrator.agents.microservice import create_agent_microservice
from orchestrator.agents.remote import RemoteAgentNode
from orchestrator.schemas.research import (
    CompetitorProfile,
    MarketPositioningGap,
    SWOTAnalysis,
    SWOTReportDelta,
)
from orchestrator.schemas.state import StrategyState


# ── Fixtures & Mocks ─────────────────────────────────────────────────────────

def _sample_strategy_state() -> StrategyState:
    return {
        "merchant_context": {
            "product_name": "TestErgoMouse",
            "category": "Peripherals",
            "known_competitors": ["BrandX"],
        },
        "swot_report": None,
        "dqs_retries": 0,
        "errors": [],
    }


def _sample_swot_delta() -> SWOTReportDelta:
    return SWOTReportDelta(
        competitors=[
            CompetitorProfile(
                brand_name="BrandX",
                product_name="ProductX",
                pricing_model="$50/mo",
                core_claims=["Best in class"],
                weaknesses_mined=["Poor battery"],
                sources=["https://brandx.com"],
            )
        ],
        swot=SWOTAnalysis(
            strengths=["Ergonomic"],
            weaknesses=["Unknown"],
            opportunities=["Enterprise"],
            threats=["BrandX"],
        ),
        positioning_gap=MarketPositioningGap(quadrant="Premium", hook_angle="Ergonomic coders"),
        dqs_score=0.88,
        assumptions_tagged=False,
        source_urls=["https://brandx.com"],
    )


async def _dummy_agent_executor(state: StrategyState) -> dict:
    return {
        "swot_report": _sample_swot_delta(),
        "dqs_retries": 1,
        "errors": [],
    }


async def _failing_agent_executor(state: StrategyState) -> dict:
    raise RuntimeError("Simulated external API crash")


# ── Microservice Factory Tests ───────────────────────────────────────────────

class TestAgentMicroserviceEndpoints:
    @pytest.fixture
    def test_app(self):
        return create_agent_microservice(
            agent_name="market_research",
            execute_fn=_dummy_agent_executor,
            description="Autonomous market research microservice",
            version="1.0.0",
            capabilities=["tavily_search", "firecrawl_scrape", "swot_synthesis"],
        )

    def test_health_endpoint(self, test_app):
        client = TestClient(test_app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["agent"] == "market_research"
        assert data["version"] == "1.0.0"

    def test_info_endpoint(self, test_app):
        client = TestClient(test_app)
        resp = client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"] == "market_research"
        assert "tavily_search" in data["capabilities"]

    def test_execute_endpoint_success(self, test_app):
        client = TestClient(test_app)
        resp = client.post("/execute", json=_sample_strategy_state())
        assert resp.status_code == 200
        data = resp.json()
        assert "swot_report" in data
        assert data["dqs_retries"] == 1
        assert len(data["swot_report"]["competitors"]) == 1
        assert data["swot_report"]["competitors"][0]["brand_name"] == "BrandX"

    def test_execute_endpoint_failure_returns_500(self):
        failing_app = create_agent_microservice(
            agent_name="broken_agent",
            execute_fn=_failing_agent_executor,
        )
        client = TestClient(failing_app)
        resp = client.post("/execute", json=_sample_strategy_state())
        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert "RuntimeError" in detail
        # Internal exception text must not leak to callers
        assert "Simulated external API crash" not in detail

    def test_execute_requires_token_when_configured(self, monkeypatch):
        from orchestrator.core.config import get_settings

        monkeypatch.setattr(get_settings(), "agent_service_token", "s3cret")
        app = create_agent_microservice(agent_name="secured", execute_fn=_dummy_agent_executor)
        client = TestClient(app)
        assert client.post("/execute", json=_sample_strategy_state()).status_code == 401
        ok = client.post(
            "/execute", json=_sample_strategy_state(), headers={"X-Agent-Token": "s3cret"}
        )
        assert ok.status_code == 200


# ── RemoteAgentNode Client Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
class TestRemoteAgentNodeClient:
    async def test_in_process_fallback_when_url_empty(self):
        called = False

        async def fallback(state: StrategyState) -> dict:
            nonlocal called
            called = True
            return {"swot_report": None, "dqs_retries": 0, "errors": []}

        node = RemoteAgentNode(
            agent_name="market_research",
            service_url="",
            fallback_fn=fallback,
        )

        res = await node(_sample_strategy_state())
        assert called is True
        assert res["dqs_retries"] == 0

    async def test_raises_when_no_url_and_no_fallback(self):
        node = RemoteAgentNode(agent_name="market_research", service_url="")
        with pytest.raises(ValueError, match="no configured service URL and no local fallback"):
            await node(_sample_strategy_state())

    async def test_remote_http_invocation_via_asgi_transport(self):
        app = create_agent_microservice(
            agent_name="market_research",
            execute_fn=_dummy_agent_executor,
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testservice") as client:
            node = RemoteAgentNode(
                agent_name="market_research",
                service_url="http://testservice",
                http_client=client,
            )

            state = _sample_strategy_state()
            result_delta = await node(state)

            assert "swot_report" in result_delta
            assert isinstance(result_delta["swot_report"], SWOTReportDelta)
            assert result_delta["swot_report"].dqs_score == 0.88
            assert result_delta["swot_report"].competitors[0].brand_name == "BrandX"

    async def test_fallback_engaged_when_remote_service_fails(self):
        failing_app = create_agent_microservice(
            agent_name="market_research",
            execute_fn=_failing_agent_executor,
        )

        fallback_called = False

        async def local_fallback(state: StrategyState) -> dict:
            nonlocal fallback_called
            fallback_called = True
            return {"swot_report": None, "dqs_retries": 99, "errors": ["Fallback used"]}

        transport = httpx.ASGITransport(app=failing_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://failingservice") as client:
            node = RemoteAgentNode(
                agent_name="market_research",
                service_url="http://failingservice",
                fallback_fn=local_fallback,
                http_client=client,
            )

            result_delta = await node(_sample_strategy_state())
            assert fallback_called is True
            assert result_delta["dqs_retries"] == 99
