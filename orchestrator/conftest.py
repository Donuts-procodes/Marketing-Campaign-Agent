import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_API_KEY_FIELDS = (
    "openai_api_key",
    "tavily_api_key",
    "you_api_key",
    "firecrawl_api_key",
    "crawlapi_token",
    "crawlapi_js_token",
    "meta_access_token",
    "api_access_key",
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
    # No MongoDB / Redis in unit tests: storage degrades to in-memory no-ops.
    monkeypatch.setattr(settings, "mongo_url", "")
    monkeypatch.setattr(settings, "redis_url", "")
