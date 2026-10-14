"""Listing currency is read from the page; foreign prices are converted, keeping the original and rate."""

import asyncio

from orchestrator.agents.market_research.intelligence.profiling.listing_intel import convert_listings, page_currency
from orchestrator.core import fx
from orchestrator.schemas.research import ChannelListing, CompetitorProfile


def test_page_currency_reads_symbols_and_resolves_dollar_by_market():
    assert page_currency("Price $49.99, was $79.99", "INR") == "USD"
    assert page_currency("A$ 49", "AUD") == "AUD"
    assert page_currency("Rs. 944 Rs. 6299 £3", "USD") == "INR"
    assert page_currency("no prices here", "INR") == "INR"


def test_foreign_listings_convert_and_pegged_currencies_go_through_usd(monkeypatch):
    async def rates_from(base, timeout=10.0):
        return {"USD": {"INR": 84.0, "USD": 1.0}, "EUR": {"INR": 90.0}}.get(base)

    monkeypatch.setattr(fx, "rates_from", rates_from)
    monkeypatch.setattr("orchestrator.core.config.get_settings", lambda: type("S", (), {"fx_conversion_enabled": True})())
    comp = CompetitorProfile(brand_name="X", product_name="X", channel_listings=[
        ChannelListing(competitor="X", site="amazon.com", currency="USD", selling_price=50),
        ChannelListing(competitor="X", site="noon.com", currency="AED", selling_price=367.25),
        ChannelListing(competitor="X", site="amazon.in", currency="INR", selling_price=2000),
        ChannelListing(competitor="X", site="odd.shop", currency="XYZ", selling_price=10),
    ])
    notes = asyncio.run(convert_listings([comp], "INR"))
    usd, aed, inr, odd = comp.channel_listings
    assert (usd.price_in_merchant_currency, usd.fx_rate, usd.selling_price) == (4200.0, 84.0, 50)
    assert aed.price_in_merchant_currency == 8400.0  # 367.25 AED = 100 USD at the peg
    assert inr.price_in_merchant_currency is None and odd.price_in_merchant_currency is None
    assert "Converted 2" in notes[0] and "1 left" in notes[0]
