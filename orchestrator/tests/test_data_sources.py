"""Google Shopping offers, Keepa history and Google Ads volumes join the research when keys are set."""

import asyncio

from orchestrator.agents.market_research.ingestion import data_sources
from orchestrator.agents.market_research.intelligence.market_mapping import demand as demand_mod
from orchestrator.agents.market_research.intelligence.profiling import listing_intel
from orchestrator.schemas.research import ChannelListing, CompetitorProfile, ListingItem, MarketDemand


class _S:
    serpapi_api_key = "k"
    keepa_api_key = "k"
    dataforseo_login = "l"
    dataforseo_password = "p"


def _settings(monkeypatch):
    monkeypatch.setattr("orchestrator.core.config.get_settings", lambda: _S())


def test_shopping_offers_add_unread_stores_only(monkeypatch):
    _settings(monkeypatch)

    async def shopping(query, iso):
        assert iso == "IN"
        return [
            {"title": "Red Tape Oxford", "store": "Flipkart", "price": 1200.0, "old_price": 9000.0, "rating": 4.1,
             "reviews": 10, "link": "https://f/1", "image": None, "price_text": "₹1,200"},
            {"title": "Red Tape Derby", "store": "Tata CLiQ", "price": 1500.0, "old_price": None, "rating": None,
             "reviews": None, "link": "https://t/1", "image": None, "price_text": "₹1,500"},
            {"title": "Bata Oxford", "store": "Tata CLiQ", "price": 999.0, "old_price": None, "rating": None,
             "reviews": None, "link": "https://t/2", "image": None, "price_text": "₹999"},
        ]

    monkeypatch.setattr(data_sources, "google_shopping", shopping)
    comp = CompetitorProfile(brand_name="Red Tape", product_name="x", channel_listings=[
        ChannelListing(competitor="Red Tape", site="flipkart.com", selling_price=1400)])
    notes = asyncio.run(listing_intel.add_shopping_offers([comp], [], {"target_geography": "India"}, "INR"))
    added = [l for l in comp.channel_listings if l.source == "shopping_api"]
    assert [(l.site, l.selling_price, l.currency) for l in added] == [("Tata CLiQ", 1500.0, "INR")]  # Flipkart already read; Bata dropped
    assert "1 store listing" in notes[0]


def test_keepa_history_attaches_to_amazon_products(monkeypatch):
    _settings(monkeypatch)

    async def history(asins, host):
        assert host == "amazon.in" and asins == ["B0D41DKK5X"]
        return {"B0D41DKK5X": {"current": 2309.0, "avg_90d": 2499.0, "min_90d": 1999.0, "max_90d": 2999.0,
                               "sales_rank": 1520, "sales_rank_drops_30d": 41}}

    monkeypatch.setattr(data_sources, "keepa_history", history)
    item = ListingItem(name="Red Tape Oxford", url="https://www.amazon.in/x/dp/B0D41DKK5X?th=1", selling_price=2309)
    comp = CompetitorProfile(brand_name="Red Tape", product_name="x", channel_listings=[
        ChannelListing(competitor="Red Tape", site="amazon.in", url="https://www.amazon.in/stores/x", items=[item])])
    asyncio.run(listing_intel.add_amazon_history([comp]))
    assert (item.avg_90d, item.min_90d, item.sales_rank) == (2499.0, 1999.0, 1520)
    assert data_sources.asin_of("https://www.amazon.in/gp/product/B0CY2CTZR3") == "B0CY2CTZR3"


def test_google_ads_volumes_fill_demand(monkeypatch):
    _settings(monkeypatch)

    async def volume(words, location):
        assert location == "India" and words[0] == "formal shoes"
        return [{"keyword": "formal shoes", "search_volume": 74000, "cpc": 0.12, "competition": "HIGH",
                 "monthly": [("2026-08", 60500), ("2026-09", 74000)]},
                {"keyword": "derby shoes", "search_volume": 9900, "cpc": 0.08, "competition": "MEDIUM", "monthly": []}]

    monkeypatch.setattr(data_sources, "search_volume", volume)
    d = MarketDemand(keyword="formal shoes", rising_searches=[{"query": "derby shoes", "growth": "+50%"}])
    asyncio.run(demand_mod.add_search_volume(d, ("IN", "india", "in-en")))
    assert (d.monthly_volume, d.competition) == (74000, "HIGH")
    assert [k["keyword"] for k in d.keyword_volumes] == ["formal shoes", "derby shoes"]
    assert d.volume_series[-1].value == 74000
