"""
Tests for live-data sourcing: CrawlAPI client, ad-library parsing, and the guarantee that
nothing generated (invented hooks, claims or sample data) reaches the report.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from orchestrator.agents.market_research.ingestion import ad_intelligence
from orchestrator.agents.market_research.ingestion.ad_intelligence import parse_ad_cards, search_competitor_ad_hooks
from orchestrator.agents.market_research.ingestion.web_crawler import CrawlAPIClient, CrawlAPIError
from orchestrator.agents.market_research.intelligence.validation.grounding import validate_information_grounding
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta

META_PAGE = """
Active
Library ID: 123456
Started running on Sep 1, 2026
See ad details
**HubSpot**
Sponsored
Grow better with HubSpot's AI-powered customer platform.
Start free today.
Learn more
Active
Library ID: 999
See ad details
Some Reseller
Sponsored
Cheap HubSpot templates for sale right now, limited offer
"""

LINKEDIN_PAGE = """
HubSpot
Promoted
Your CRM should work as hard as you do. See what's new in Breeze AI agents.
View details
"""


def test_parse_ad_cards_keeps_only_the_brand_advertisers_copy():
    copies = parse_ad_cards(META_PAGE, "Sponsored", "HubSpot")
    assert copies == ["Grow better with HubSpot's AI-powered customer platform. Start free today."]


def test_parse_linkedin_promoted_cards():
    copies = parse_ad_cards(LINKEDIN_PAGE, "Promoted", "hubspot")
    assert copies == ["Your CRM should work as hard as you do. See what's new in Breeze AI agents."]


def test_grounding_drops_hooks_claims_and_complaints_not_in_sources():
    report = SWOTReportDelta(
        competitors=[
            CompetitorProfile(
                brand_name="HubSpot",
                product_name="HubSpot CRM",
                core_claims=["Grow better with HubSpot", "The number one CRM on Mars"],
                weaknesses_mined=["Pricing jumps sharply at the Professional tier", "Crashes every Tuesday"],
                ad_hooks=[
                    'Meta Ad Library: "Grow better with HubSpot\'s AI-powered customer platform. Start free today."',
                    'Campaign Hook: "Say goodbye to spreadsheets forever with our robots"',
                ],
                sources=["https://hubspot.com"],
            )
        ]
    )
    corpus = [
        META_PAGE,
        "Reddit: pricing jumps sharply at the Professional tier, which hurt our small team.",
    ]

    report, diagnostics = validate_information_grounding(report, corpus, {"https://hubspot.com"})
    comp = report.competitors[0]

    assert comp.core_claims == ["Grow better with HubSpot"]
    assert comp.weaknesses_mined == ["Pricing jumps sharply at the Professional tier"]
    assert comp.ad_hooks == [
        'Meta Ad Library: "Grow better with HubSpot\'s AI-powered customer platform. Start free today."'
    ]
    assert any("ad hook" in d for d in diagnostics)


@pytest.mark.asyncio
async def test_ad_intel_never_fills_hooks_when_nothing_is_found(monkeypatch):
    settings = ad_intelligence.get_settings()
    monkeypatch.setattr(settings, "meta_access_token", "")
    crawl_client = MagicMock(configured=False, can_render_js=False)
    tavily = AsyncMock()
    tavily.search = AsyncMock(return_value={"results": []})
    comp = CompetitorProfile(
        brand_name="Acme", product_name="Acme Pro", core_claims=["Best widgets ever"], sources=["https://acme.com"]
    )

    result = await search_competitor_ad_hooks([comp], "widgets", tavily_client=tavily, crawl_client=crawl_client)

    assert result.hooks_by_competitor == {"Acme Pro": []}
    assert result.documents == []
    assert len(result.skipped) == 3  # meta, linkedin, google need credentials


@pytest.mark.asyncio
async def test_ad_intel_reads_meta_and_linkedin_libraries_via_crawlapi(monkeypatch):
    settings = ad_intelligence.get_settings()
    monkeypatch.setattr(settings, "meta_access_token", "")
    monkeypatch.setattr(settings, "ad_library_platforms", "meta,linkedin")

    async def _fetch(url, **kwargs):
        if "facebook.com/ads/library" in url:
            assert kwargs.get("javascript") is True
            return {"body": META_PAGE}
        if "linkedin.com/ad-library" in url:
            return {"body": LINKEDIN_PAGE}
        raise AssertionError(url)

    crawl_client = MagicMock(configured=True, can_render_js=True)
    crawl_client.fetch = _fetch
    tavily = AsyncMock()
    tavily.search = AsyncMock(return_value={"results": []})
    comp = CompetitorProfile(brand_name="HubSpot", product_name="HubSpot CRM", sources=["https://www.hubspot.com"])

    result = await search_competitor_ad_hooks([comp], "CRM", tavily_client=tavily, crawl_client=crawl_client)

    hooks = result.hooks_by_competitor["HubSpot CRM"]
    assert any(h.startswith("Meta Ad Library:") and "Grow better" in h for h in hooks)
    assert any(h.startswith("LinkedIn Ad Library:") and "Breeze AI" in h for h in hooks)
    assert not any("Cheap HubSpot templates" in h for h in hooks)  # another advertiser's ad
    assert len(result.documents) == 2


@pytest.mark.asyncio
async def test_crawlapi_client_sends_token_and_rejects_blocked_pages(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        if "blocked" in seen["url"]:
            return httpx.Response(200, text="denied", headers={"cb_status": "200", "original_status": "403"})
        return httpx.Response(200, text="# Pricing\n$49 per month", headers={"cb_status": "200", "original_status": "200"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "orchestrator.agents.market_research.ingestion.web_crawler.httpx.AsyncClient",
        lambda **kw: real_client(transport=transport, **kw),
    )
    client = CrawlAPIClient(token="normal", js_token="js")

    page = await client.fetch("https://acme.com/pricing", javascript=True, page_wait_ms=3000)
    assert page["body"].startswith("# Pricing")
    assert seen["token"] == "js" and seen["format"] == "md" and seen["page_wait"] == "3000"

    with pytest.raises(CrawlAPIError):
        await client.fetch("https://blocked.example")

    with pytest.raises(CrawlAPIError):
        await CrawlAPIClient(token="", js_token="").fetch("https://acme.com")


@pytest.mark.asyncio
async def test_crawlapi_client_uses_firecrawl_when_key_set(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen["auth"] = request.headers["Authorization"]
        seen["body"] = _json.loads(request.content)
        if "blocked" in seen["body"]["url"]:
            return httpx.Response(200, json={"success": True, "data": {"markdown": "x", "metadata": {"statusCode": 403}}})
        return httpx.Response(
            200,
            json={"success": True, "data": {"markdown": "# Ads\nreal copy", "metadata": {"statusCode": 200, "sourceURL": seen["body"]["url"]}}},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "orchestrator.agents.market_research.ingestion.web_crawler.httpx.AsyncClient",
        lambda **kw: real_client(transport=transport, **kw),
    )
    client = CrawlAPIClient(firecrawl_api_key="fc-test", token="", js_token="")
    assert client.provider == "firecrawl" and client.can_render_js

    page = await client.fetch("https://www.facebook.com/ads/library/?q=x", javascript=True, page_wait_ms=4000, scroll=True)
    assert page["body"] == "# Ads\nreal copy"
    assert seen["auth"] == "Bearer fc-test"
    assert seen["body"]["onlyMainContent"] is False and seen["body"]["waitFor"] == 4000
    assert seen["body"]["actions"][0]["type"] == "scroll"

    with pytest.raises(CrawlAPIError):
        await client.fetch("https://blocked.example")


@pytest.mark.asyncio
async def test_crawlapi_client_uses_brightdata_when_key_set(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = _json.loads(request.content)
        if "blocked" in seen["body"]["url"]:
            return httpx.Response(200, text="denied", headers={"x-response-code": "403"})
        return httpx.Response(200, text="# Pricing\n$99/month", headers={"x-response-code": "200"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "orchestrator.agents.market_research.ingestion.web_crawler.httpx.AsyncClient",
        lambda **kw: real_client(transport=transport, **kw),
    )
    client = CrawlAPIClient(
        brightdata_api_key="bd-test",
        brightdata_zone="test_zone",
        scrapedo_api_key="",
        firecrawl_api_key="",
        token="",
        js_token="",
    )
    assert client.provider == "brightdata" and client.can_render_js

    page = await client.fetch("https://acme.com/pricing", country="us")
    assert page["body"] == "# Pricing\n$99/month"
    assert seen["auth"] == "Bearer bd-test"
    assert seen["body"]["zone"] == "test_zone"
    assert seen["body"]["url"] == "https://acme.com/pricing"
    assert seen["body"]["country"] == "us"

    with pytest.raises(CrawlAPIError):
        await client.fetch("https://blocked.example")


@pytest.mark.asyncio
async def test_crawlapi_client_brightdata_falls_back_to_scrapedo(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "brightdata.com" in str(request.url):
            seen.append("brightdata")
            return httpx.Response(400, text="Bad Request: zone not found")
        if "scrape.do" in str(request.url):
            seen.append("scrapedo")
            return httpx.Response(200, text="# Fallback Content", headers={"scrape.do-initial-status-code": "200"})
        return httpx.Response(500, text="Unknown")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "orchestrator.agents.market_research.ingestion.web_crawler.httpx.AsyncClient",
        lambda **kw: real_client(transport=transport, **kw),
    )
    client = CrawlAPIClient(
        brightdata_api_key="bd-test",
        scrapedo_api_key="sd-test",
        firecrawl_api_key="",
        token="",
        js_token="",
    )
    page = await client.fetch("https://acme.com")
    assert page["body"] == "# Fallback Content"
    assert seen == ["brightdata", "scrapedo"]



@pytest.mark.asyncio
async def test_search_merges_tavily_and_you_results_without_duplicates():
    from orchestrator.agents.market_research.ingestion.search_client import SearchQuery, execute_tavily_search

    tavily = AsyncMock()
    tavily.search = AsyncMock(
        return_value={"results": [{"title": "A", "url": "https://a.com", "content": "tavily a", "score": 0.9}]}
    )
    you = AsyncMock()
    you.search = AsyncMock(
        return_value={
            "results": {
                "web": [
                    {"title": "A", "url": "https://a.com", "snippets": ["you a"]},
                    {"title": "B", "url": "https://b.com", "description": "you b"},
                ]
            }
        }
    )

    results = await execute_tavily_search(
        [SearchQuery(vector="alternative_discovery", query='site:reddit.com "crm" OR "sales"')],
        tavily_client=tavily,
        you_client=you,
    )

    assert [r.url for r in results] == ["https://a.com", "https://b.com"]
    assert results[0].snippet == "tavily a" and results[1].snippet == "you b"
    sent = you.search.await_args.args[0]
    assert "site:" not in sent and " OR " not in sent


def test_parse_google_activity_reports_real_advertiser_and_ad_count():
    from orchestrator.agents.market_research.ingestion.ad_intelligence import parse_google_activity

    page = "Ads In United States\npipedrive.com\n~2K ads\n_chevron_\n![](x)\nPipedrive Inc.\nVerified\nPipedrive Inc.\nVerified\n"
    assert parse_google_activity(page, "Pipedrive", "US") == "Pipedrive Inc. (Verified) — ~2K ads in US"
    assert parse_google_activity("no ads here", "Pipedrive", "US") is None


def test_listicles_are_evidence_and_known_competitors_come_first():
    from orchestrator.agents.market_research.workflow.research_loop import extract_preliminary_competitors
    from orchestrator.agents.market_research.ingestion.search_client import TavilySearchResult as R

    results = [
        R("alternative_discovery", "Best CRM for Small Business in 2026: Our Top Picks", "https://blog.example.com/best-crm",
          "Pipedrive starts at $14 per user per month and suits small sales teams.", 0.9),
        R("pricing_scrape", "Pipedrive Pricing", "https://www.pipedrive.com/en/pricing",
          "Plans start at $14 per seat per month billed annually.", 0.8),
        R("alternative_discovery", "Close CRM", "https://close.com", "Close is the inside sales CRM built for calling.", 0.7),
    ]

    comps = extract_preliminary_competitors(results, ["Pipedrive", "HubSpot"])

    names = [c.brand_name for c in comps]
    assert names[:2] == ["Pipedrive", "HubSpot"]
    assert "Blog" not in names  # the listicle is not a competitor
    assert "Close" in names
    pipedrive = comps[0]
    assert "https://www.pipedrive.com/en/pricing" in pipedrive.sources
    assert pipedrive.pricing_model == "detected"


def test_parse_ad_cards_strips_images_and_links():
    page = "HubSpot\nSponsored\nLevel-up your digital marketing skills today. ![](https://scontent.fbcdn.net/x.jpg)\n[Learn more](https://x)\n"
    assert parse_ad_cards(page, "Sponsored", "HubSpot") == ["Level-up your digital marketing skills today."]


def _ddg_client(hits):
    client = AsyncMock()
    client.search = AsyncMock(return_value=hits)
    return client


def _tavily_returning(n):
    tavily = AsyncMock()
    tavily.search = AsyncMock(
        return_value={"results": [{"title": f"T{i}", "url": f"https://t{i}.com", "content": "c", "score": 0.9} for i in range(n)]}
    )
    return tavily


@pytest.mark.asyncio
async def test_duckduckgo_fills_in_when_primary_engines_are_thin(monkeypatch):
    from orchestrator.agents.market_research.ingestion.search_client import SearchQuery, execute_tavily_search, get_settings

    monkeypatch.setattr(get_settings(), "duckduckgo_mode", "fallback")
    ddg = _ddg_client([{"title": "D", "href": "https://ddg.com", "body": "duck result"}, {"title": "T0", "href": "https://t0.com", "body": "dup"}])

    results = await execute_tavily_search(
        [SearchQuery(vector="pricing_scrape", query="q")], tavily_client=_tavily_returning(1), ddg_client=ddg
    )

    assert [(r.url, r.provider) for r in results] == [("https://t0.com", "tavily"), ("https://ddg.com", "duckduckgo")]
    ddg.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_duckduckgo_skipped_when_primary_engines_have_enough(monkeypatch):
    from orchestrator.agents.market_research.ingestion.search_client import SearchQuery, execute_tavily_search, get_settings

    monkeypatch.setattr(get_settings(), "duckduckgo_mode", "fallback")
    ddg = _ddg_client([{"title": "D", "href": "https://ddg.com", "body": "x"}])

    results = await execute_tavily_search(
        [SearchQuery(vector="v", query="q")], tavily_client=_tavily_returning(6), ddg_client=ddg
    )

    assert len(results) == 6 and all(r.provider == "tavily" for r in results)
    ddg.search.assert_not_awaited()


@pytest.mark.asyncio
async def test_duckduckgo_takes_over_when_primary_engines_fail(monkeypatch):
    from orchestrator.agents.market_research.ingestion.search_client import SearchQuery, execute_tavily_search, get_settings

    monkeypatch.setattr(get_settings(), "duckduckgo_mode", "fallback")
    broken = AsyncMock()
    broken.search = AsyncMock(side_effect=ConnectionError("tavily down"))
    ddg = _ddg_client([{"title": "D", "href": "https://reddit.com/r/crm", "body": "x"}, {"title": "E", "href": "https://e.com", "body": "y"}])

    results = await execute_tavily_search(
        [SearchQuery(vector="gripe_mining", query='site:reddit.com "crm" OR complaint', include_domains=("reddit.com",))],
        tavily_client=broken,
        ddg_client=ddg,
    )

    assert [r.url for r in results] == ["https://reddit.com/r/crm"]  # domain filter still applies
    # A domain-restricted query gets one plain keyword query with a single site: filter.
    assert ddg.search.await_args.args[0] == "crm complaint site:reddit.com"


@pytest.mark.asyncio
async def test_duckduckgo_always_and_off_modes(monkeypatch):
    from orchestrator.agents.market_research.ingestion.search_client import SearchQuery, execute_tavily_search, get_settings

    settings = get_settings()
    ddg = _ddg_client([{"title": "D", "href": "https://ddg.com", "body": "x"}])
    query = [SearchQuery(vector="v", query="q")]

    monkeypatch.setattr(settings, "duckduckgo_mode", "always")
    results = await execute_tavily_search(query, tavily_client=_tavily_returning(6), ddg_client=ddg)
    assert any(r.provider == "duckduckgo" for r in results)

    monkeypatch.setattr(settings, "duckduckgo_mode", "off")
    ddg.search.reset_mock()
    await execute_tavily_search(query, tavily_client=_tavily_returning(0), ddg_client=ddg)
    ddg.search.assert_not_awaited()


def test_ddg_queries_are_plain_keywords_with_shorter_retry():
    from orchestrator.agents.market_research.ingestion.search_client import _ddg_queries

    full, short = _ddg_queries('"DealFlow CRM" OR ("Pipedrive" OR "HubSpot") pricing OR price OR cost OR tiers OR plans OR pricing')
    assert full == "DealFlow CRM Pipedrive HubSpot pricing price cost tiers plans"
    assert short == "DealFlow CRM Pipedrive HubSpot pricing price"


@pytest.mark.asyncio
async def test_duckduckgo_drops_ad_click_urls(monkeypatch):
    from orchestrator.agents.market_research.ingestion.search_client import SearchQuery, execute_duckduckgo_search

    ddg = _ddg_client([
        {"title": "Ad", "href": "https://www.bing.com/aclick?ld=abc", "body": "sponsored"},
        {"title": "Real", "href": "https://capterra.com/crm", "body": "real"},
    ])
    results = await execute_duckduckgo_search([SearchQuery(vector="v", query="crm")], ddg)
    assert [r.url for r in results] == ["https://capterra.com/crm"]


def test_grounding_rejects_negated_or_reworded_claims():
    from orchestrator.agents.market_research.intelligence.validation.grounding import _document, _is_supported

    page = ("Pipedrive pricing for small teams. Plans start at $14 per seat. Customer support is available by email. "
            "Reporting tools help managers. Many teams switch from spreadsheets.") * 3
    docs = [_document(page)]

    assert _is_supported("Customer support is available by email", docs)
    assert _is_supported('Web ad mention: "Reporting tools help managers. Many teams switch from spreadsheets..."', docs)
    assert not _is_supported("Pipedrive customer support is not available for small teams", docs)
    assert not _is_supported("Pipedrive reporting tools do not help managers of small teams", docs)
