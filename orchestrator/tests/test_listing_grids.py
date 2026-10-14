"""Real marketplace pages (captured 2026-10-13): grid pages are read card by card, never as one price."""

import pathlib

import pytest

from orchestrator.agents.market_research.intelligence.profiling.listing_intel import _PRICE, read_listing
from orchestrator.schemas.research import CompetitorProfile

FIX = pathlib.Path(__file__).parent / "fixtures" / "listings"
RIVAL = CompetitorProfile(brand_name="Red Tape", product_name="Red Tape")


@pytest.mark.parametrize("name,url,count,lo,hi", [
    ("flipkart.md", "https://www.flipkart.com/mens-footwear/mens-formal-shoes/red-tape~brand/pr?sid=osp", 40, 700, 1600),
    ("ajio.md", "https://www.ajio.com/find/Red-Tape-Formal-Shoes", 31, 800, 1700),
    ("myntra.md", "https://www.myntra.com/red-tape-formal-shoes", 38, 900, 2000),
    ("amazon.in.md", "https://www.amazon.in/stores/RedTape/page/E313", 3, 2000, 2500),
])
def test_grid_pages_give_the_rivals_own_products_with_their_prices(name, url, count, lo, hi):
    listing = read_listing(url, (FIX / name).read_text(encoding="utf-8"), RIVAL, "marketplace", "INR")
    assert listing is not None and listing.page_kind == "grid"
    assert listing.product_count == count
    assert lo <= listing.price_from <= listing.selling_price <= hi  # cheapest and median, rupees
    for item in listing.items:
        assert "red tape" in f"{item.name} {item.url.replace('-', ' ')}".lower()  # no ads for other brands
        assert item.mrp is None or item.mrp > item.selling_price


def test_rupee_words_need_their_own_word():
    assert _PRICE.findall("4.4 out of 5 stars. 28 customer reviews") == []
    assert _PRICE.findall("Rs. 944 Rs. 6299") == ["944", "6299"]


def test_a_store_page_without_readable_cards_gives_no_price():
    text = "Red Tape store\n* [Dresses Under ₹599](https://www.myntra.com/fwd)\nRed Tape shoes ₹944"
    assert read_listing("https://www.myntra.com/search?q=red-tape", text, RIVAL, "marketplace", "INR") is None
