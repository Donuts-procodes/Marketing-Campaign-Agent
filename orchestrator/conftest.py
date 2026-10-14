import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_API_KEY_FIELDS = (
    "openai_api_key",
    "tavily_api_key",
    "you_api_key",
    "scrapedo_api_key",
    "brightdata_api_key",
    "firecrawl_api_key",
    "crawlapi_token",
    "crawlapi_js_token",
    "meta_access_token",
    "api_access_key",
    "serpapi_api_key",
    "keepa_api_key",
    "dataforseo_login",
    "dataforseo_password",
)


@pytest.fixture(autouse=True)
def _no_live_api_keys(monkeypatch):
    """Unit tests never reach live APIs, even when real keys are present in .env."""
    from orchestrator.core.config import get_settings

    settings = get_settings()
    for name in _API_KEY_FIELDS:
        monkeypatch.setattr(settings, name, "")
    # DuckDuckGo needs no key, so switch it off explicitly.
    monkeypatch.setattr(settings, "duckduckgo_mode", "off")
    # Google Trends needs no key either.
    monkeypatch.setattr(settings, "demand_trends_enabled", False)
    monkeypatch.setattr(settings, "fx_conversion_enabled", False)
    monkeypatch.setattr(settings, "provider_health_check", False)
    # No MongoDB / Redis in unit tests: storage degrades to in-memory no-ops.
    monkeypatch.setattr(settings, "mongo_url", "")
    monkeypatch.setattr(settings, "redis_url", "")


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """Resets the search circuit breaker before each test."""
    from orchestrator.agents.market_research.ingestion.search_client import get_search_circuit_breaker

    cb = get_search_circuit_breaker()
    cb.reset()
    yield
    cb.reset()



@pytest.fixture(autouse=True)
def _reset_crawl_client_pool():
    """Tests patch httpx.AsyncClient; drop the pooled crawl client so each test builds its own."""
    from orchestrator.agents.market_research.ingestion import web_crawler as crawlapi

    crawlapi._shared_clients.clear()
    yield
    crawlapi._shared_clients.clear()
