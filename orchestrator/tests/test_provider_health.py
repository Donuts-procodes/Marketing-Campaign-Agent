"""An account error switches a crawl provider off; later pages go straight to the next one."""

import asyncio

from orchestrator.agents.market_research.ingestion import provider_health
from orchestrator.agents.market_research.ingestion.web_crawler import CrawlAccountError, CrawlAPIClient


def test_account_errors_switch_providers_off_and_pages_fall_through(monkeypatch):
    monkeypatch.setattr(provider_health, "_down", {})
    calls = []
    client = CrawlAPIClient(brightdata_api_key="b", scrapedo_api_key="s", firecrawl_api_key="f")

    async def brightdata(url, **kw):
        calls.append("brightdata")
        raise CrawlAccountError('zone "web_unlocker" not found')

    async def scrapedo(url, **kw):
        calls.append("scrapedo")
        raise CrawlAccountError("Monthly request limit exceeded")

    async def firecrawl(url, **kw):
        calls.append("firecrawl")
        return {"url": url, "status": 200, "body": "ok"}

    monkeypatch.setattr(client, "_fetch_brightdata", brightdata)
    monkeypatch.setattr(client, "_fetch_scrapedo", scrapedo)
    monkeypatch.setattr(client, "_fetch_firecrawl", firecrawl)
    asyncio.run(client.fetch("https://a.in/1"))
    asyncio.run(client.fetch("https://a.in/2"))
    assert calls == ["brightdata", "scrapedo", "firecrawl", "firecrawl"]
    assert set(provider_health.down_reasons()) == {"brightdata", "scrapedo"}


def test_account_error_detection():
    assert provider_health.is_account_error(400, 'zone "web_unlocker" not found')
    assert provider_health.is_account_error(401, "")
    assert not provider_health.is_account_error(500, "upstream timeout")
