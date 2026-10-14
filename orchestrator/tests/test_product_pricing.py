"""Per-product competitor pricing: product-aware queries, search-excerpt fallback, cited AI search."""

import asyncio
from types import SimpleNamespace

from orchestrator.agents.market_research.ingestion.search_client import TavilySearchResult
from orchestrator.agents.market_research.intelligence.profiling.listing_intel import (
    build_listing_queries,
    collect_channel_listings,
    listing_price_summary,
)
from orchestrator.agents.market_research.intelligence.profiling.price_search import parse_listings
from orchestrator.agents.market_research.intelligence.profiling.profile_completer import build_queries
from orchestrator.schemas.research import ChannelListing, CompetitorProfile, SWOTReportDelta

IN = {"target_geography": "India", "currency": "INR"}


def _rival() -> CompetitorProfile:
    return CompetitorProfile(brand_name="Red Tape", product_name="Red Tape")


def _report() -> SWOTReportDelta:
    return SWOTReportDelta.model_construct(competitors=[_rival()])


def test_product_sellers_are_not_asked_for_hourly_rates():
    product = " ".join(q.query for q in build_queries(_rival(), ["pricing_model"], 1, service_like=False))
    service = " ".join(q.query for q in build_queries(_rival(), ["pricing_model"], 1, service_like=True))
    assert "MRP" in product and "minimum project" not in product
    assert "minimum project" in service
    second = " ".join(q.query for q in build_queries(_rival(), ["pricing_model"], 2, service_like=False))
    assert "hourly" not in second


def test_listing_queries_use_the_merchant_product_category():
    q = build_listing_queries([_rival()], ["amazon.in"], {"name": "Derby", "category": "formal leather shoes"})
    assert '"Red Tape" formal leather shoes' in q[0].query


def test_each_merchant_product_gets_its_own_listings_and_excerpts_fill_blocked_pages():
    ctx = {**IN, "category": "formal shoes", "products": [{"name": "Oxford", "category": "formal shoes"}, {"name": "Runner", "category": "sneakers"}]}
    calls = []

    async def search(queries):
        calls.append(queries[0].query)
        if "sneakers" in queries[0].query:
            return [TavilySearchResult(vector="channel_listings", title="Red Tape Sneakers for Men",
                                       url="https://www.amazon.in/red-tape-sneaker/dp/B1",
                                       snippet="Red Tape Sneakers M.R.P: ₹4,999 ₹1,499 (70% off)")]
        return [TavilySearchResult(vector="channel_listings", title="Red Tape Oxford Formal Shoes",
                                   url="https://www.myntra.com/red-tape-oxford/123", snippet="")]

    async def crawl(urls):
        return [{"url": u, "markdown": "Red Tape Oxford Formal Shoes ₹2,499 ₹2,499 MRP ₹6,999"}
                for u in urls if "myntra" in u]  # amazon page is blocked

    report, notes = asyncio.run(collect_channel_listings(_report(), ctx, [], search, crawl))
    listings = report.competitors[0].channel_listings
    assert len(calls) == 2
    by_product = {l.matched_product: l for l in listings}
    assert by_product["Oxford"].selling_price == 2499 and by_product["Oxford"].source == "page"
    assert by_product["Runner"].selling_price == 1499 and by_product["Runner"].source == "search_snippet"
    assert "1 from search excerpts" in notes[-1]
    assert "on myntra.com" in report.competitors[0].pricing_model


def test_ai_search_only_runs_for_unpriced_products():
    seen = []

    async def search(queries):
        return []

    async def crawl(urls):
        return []

    async def ai(comp, product, currency, hosts):
        seen.append((comp.brand_name, product, currency))
        return [ChannelListing(competitor=comp.brand_name, product="Red Tape Derby", site="redtape.com",
                               url="https://redtape.com/derby", currency="INR", selling_price=2999,
                               source="ai_search")]

    report, notes = asyncio.run(collect_channel_listings(_report(), IN, [], search, crawl, ai_search_fn=ai))
    assert seen == [("Red Tape", None, "INR")]
    assert report.competitors[0].channel_listings[0].source == "ai_search"
    assert report.competitors[0].pricing_model == "Red Tape Derby: ₹2,999 on redtape.com"


def _response(text, urls):
    anns = [SimpleNamespace(type="url_citation", url=u) for u in urls]
    return SimpleNamespace(output_text=text, output=[SimpleNamespace(content=[SimpleNamespace(annotations=anns)])])


def test_ai_listings_need_a_citation_and_the_price_in_the_answer():
    text = ('{"listings": ['
            '{"product": "Red Tape Oxford", "selling_price": 2499, "mrp": 6999, "currency": "INR", '
            '"url": "https://www.amazon.in/dp/B1"},'
            '{"product": "Invented", "selling_price": 1999, "currency": "INR", "url": "https://made-up.example/x"},'
            '{"product": "US store", "selling_price": 49, "currency": "USD", "url": "https://www.amazon.in/dp/B2"}'
            ']}')
    out = parse_listings(_response(text, ["https://www.amazon.in/dp/B1"]), _rival(), "INR", {"amazon.in": "marketplace"})
    assert [(l.product, l.selling_price, l.mrp, l.site) for l in out] == [("Red Tape Oxford", 2499, 6999, "amazon.in")]
    assert out[0].discount_pct == 64.3
    assert parse_listings(_response("no json here", []), _rival(), "INR", {}) == []


def test_price_summary_prefers_page_reads_and_names_the_product():
    listings = [
        ChannelListing(competitor="X", product="Loafer", site="a.com", currency="INR", selling_price=999, source="ai_search"),
        ChannelListing(competitor="X", product="Loafer", site="b.com", currency="INR", selling_price=1099, mrp=1999),
    ]
    assert listing_price_summary(listings) == "Loafer: ₹1,099 (MRP ₹1,999) on b.com"
    assert listing_price_summary([]) is None


def test_listing_image_prefers_structured_data_and_skips_banners():
    from orchestrator.agents.market_research.intelligence.profiling.listing_intel import listing_image

    names = ["Red Tape"]
    assert listing_image('{"@type":"Product","image":"https://cdn.x/shoe.jpg"}', names) == "https://cdn.x/shoe.jpg"
    md = "![Sale banner](https://cdn.x/banner.jpg)\n![Red Tape Oxford](https://cdn.x/oxford.jpg)"
    assert listing_image(md, names) == "https://cdn.x/oxford.jpg"
    assert listing_image("![Another brand](https://cdn.x/a.jpg)", names) is None


def test_simple_research_caps_effort_and_deep_keeps_configured_values(monkeypatch):
    from orchestrator.core.config import get_settings, research_limit

    s = get_settings()
    monkeypatch.setattr(s, "dqs_max_retries", 3)
    monkeypatch.setattr(s, "research_depth", "simple")
    assert research_limit(s, "dqs_max_retries") == 1
    monkeypatch.setattr(s, "research_depth", "deep")
    assert research_limit(s, "dqs_max_retries") == 3


def test_marketplaces_follow_category_and_marketplace_pages_render_in_market(monkeypatch):
    from orchestrator.agents.market_research.ingestion import page_extractor
    from orchestrator.agents.market_research.ingestion.search_client import reset_search_market, set_search_market
    from orchestrator.agents.market_research.intelligence.profiling.listing_intel import marketplaces_for

    hosts = lambda c: [h for h, _ in marketplaces_for({"target_geography": "India", "category": c})]
    assert "croma.com" in hosts("wireless earbuds") and "myntra.com" not in hosts("wireless earbuds")
    assert "blinkit.com" in hosts("green tea") and hosts("yoga mat")[:2] == ["amazon.in", "flipkart.com"]

    calls = []

    class Client:
        provider = "scrapedo"

        async def fetch(self, url, **kw):
            calls.append((url, kw))
            return {"body": "word " * 200}

    token = set_search_market({"target_geography": "India"})
    try:
        asyncio.run(page_extractor.extract_pages(
            ["https://www.amazon.in/dp/B1", "https://redtape.com/about"], crawl_client=Client()))
    finally:
        reset_search_market(token)
    opts = dict(calls)
    assert opts["https://www.amazon.in/dp/B1"] == {"output_format": "md", "javascript": True, "country": "in"}
    assert opts["https://redtape.com/about"] == {"output_format": "md", "country": "in"}
