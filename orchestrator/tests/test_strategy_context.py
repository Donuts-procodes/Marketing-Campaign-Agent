import pytest

from orchestrator.agents.campaign_strategy.context import (
    find_unknowns,
    load_personas,
    summarize_listings,
)
from orchestrator.agents.campaign_strategy.money import fmt_money, resolve_currency
from orchestrator.agents.campaign_strategy.options import generate_campaign_options
from orchestrator.agents.market_research.intelligence.profiling.listing_intel import (
    build_listing_queries,
    marketplaces_for,
    read_listing,
)
from orchestrator.schemas.research import (
    BuyingPatternIntelligence,
    ChannelListing,
    CompetitorProfile,
    CompetitorReviewContext,
    ReviewAspect,
    SWOTReportDelta,
)

AURELIUS = {
    "product_name": "Sovereign Oxford",
    "category": "Formal leather footwear",
    "target_geography": "Delhi-NCR, India",
    "budget": "10000",
    "price": 7499,
}


def _report() -> SWOTReportDelta:
    return SWOTReportDelta(competitors=[
        CompetitorProfile(
            brand_name="Bridlen", product_name="Bridlen Oxford",
            review_context=CompetitorReviewContext(
                brand_name="Bridlen",
                buyer_personas=["Corporate professionals upgrading formal shoes"],
                top_complaint_drivers=[ReviewAspect(topic="Stiff break-in")],
                unmet_customer_needs=["All-day comfort"],
            ),
            buying_patterns=BuyingPatternIntelligence(sales_channels=["myntra.com", "Brand D2C Website"]),
            channel_listings=[
                ChannelListing(competitor="Bridlen", site="myntra.com", currency="INR", mrp=8999,
                               selling_price=5399, discount_pct=40, offers=["Extra 10% off on prepaid"],
                               returns_policy="7-day exchange only", cod_available=False),
            ],
        ),
        CompetitorProfile(
            brand_name="Ruosh", product_name="Ruosh Derby",
            review_context=CompetitorReviewContext(
                brand_name="Ruosh",
                buyer_personas=["Corporate professionals upgrading formal shoes", "Wedding shoppers"],
                top_complaint_drivers=[ReviewAspect(topic="Stiff break-in"), ReviewAspect(topic="Sizing runs small")],
            ),
            channel_listings=[
                ChannelListing(competitor="Ruosh", site="myntra.com", currency="INR", selling_price=6499,
                               review_count=1200),
            ],
        ),
    ])


# ── Currency ──────────────────────────────────────────────────────────────────

def test_currency_from_market_and_explicit_code():
    assert resolve_currency(AURELIUS) == "INR"
    assert resolve_currency({"budget": "₹10,000"}) == "INR"
    assert resolve_currency({"currency": "gbp", "target_geography": "India"}) == "GBP"
    assert resolve_currency({"dossier": "Contact us for details"}) == "USD"  # "us" is not the USA
    assert fmt_money(10000, "INR") == "₹10,000"


def test_options_use_merchant_currency_and_project_nothing():
    ctx = {**AURELIUS, "currency": "INR"}
    options = generate_campaign_options(ctx, [], 10000.0)
    assert "₹" in options[0].budget_allocation_summary and "$" not in options[0].budget_allocation_summary
    assert all(o.prediction.projected_roi is None for o in options)
    assert all(c.projected_roi is None for o in options for c in o.channel_matrix)


# ── Personas ──────────────────────────────────────────────────────────────────

def test_persona_agent_output_is_used_and_mapped_from_its_own_field_names():
    state = {"persona_profiles": [
        {"id": "p1", "title": "Commuting corporate professional", "pain_points": "Sore feet by 6pm",
         "barriers": ["Unknown brand at ₹7.5k"], "channels": ["Instagram"], "confidence": 80},
        {"name": "Wedding guest"},
    ]}
    personas = load_personas(state, _report(), AURELIUS)
    assert [p.source for p in personas] == ["persona_agent", "persona_agent"]
    top = next(p for p in personas if p.persona_id == "p1")
    assert top.pains == ["Sore feet by 6pm"] and top.objections == ["Unknown brand at ₹7.5k"]
    assert top.confidence == 0.8
    assert personas[0].role == "primary" and personas[1].role == "challenger"


def test_research_derived_personas_when_persona_agent_is_absent():
    personas = load_personas({}, _report(), AURELIUS)
    assert personas and all(p.source == "research_derived" for p in personas)
    lead = next(p for p in personas if "Corporate" in p.name)
    assert "Stiff break-in" in lead.objections  # complaint voiced across rivals
    assert "myntra.com" in lead.preferred_channels
    # Mentioned by two rivals' reviewers, so it outranks the one-off persona.
    assert personas[0].name.startswith("Corporate")


def test_merchant_icp_joins_research_personas():
    personas = load_personas({}, _report(), {**AURELIUS, "target_audience": "Urban professionals 27-48"})
    assert any(p.source == "merchant_input" for p in personas)


# ── Listings summary & unknowns ───────────────────────────────────────────────

def test_listing_summary_states_price_position_and_offer_norms():
    lines = summarize_listings(_report(), AURELIUS, "INR")
    text = "\n".join(lines)
    assert "myntra.com" in text and "₹5,399" in text and "₹6,499" in text
    assert "above the median" in text            # ₹7,499 vs ₹5,949 median
    assert "40% off MRP" in text
    assert "No COD on: myntra.com" in text


def test_unknowns_name_what_only_the_merchant_can_supply():
    unknowns = find_unknowns(AURELIUS, load_personas({}, _report(), AURELIUS))
    text = " ".join(unknowns)
    assert "Unit cost" in text and "Launch stage" in text and "Persona agent output" in text
    assert "Selling price" not in text  # price was given


# ── Listing extraction ────────────────────────────────────────────────────────

MYNTRA_PAGE = """
Bridlen Men Tan Leather Formal Oxford Shoes
4.2 ★ | 1,284 Ratings
₹5,399  MRP ₹8,999 (40% OFF)
inclusive of all taxes
Extra 10% off on prepaid orders above ₹3,000
Bank Offer: 10% instant discount on HDFC cards
Cash on delivery not available
Easy 7 day exchange available on this item
Get it by Thu, 16 Oct
Sold by: Bridlen Retail
"""


def test_read_listing_extracts_buy_box_values_from_page_text():
    comp = CompetitorProfile(brand_name="Bridlen", product_name="Bridlen Oxford")
    listing = read_listing("https://www.myntra.com/x/123", MYNTRA_PAGE, comp, "marketplace", "INR")
    assert listing is not None
    assert listing.site == "myntra.com"
    assert listing.selling_price == 5399 and listing.mrp == 8999 and listing.discount_pct == 40
    assert listing.rating == 4.2 and listing.review_count == 1284
    assert listing.cod_available is False  # "not available" is not read as COD offered
    assert "7 day exchange" in (listing.returns_policy or "")
    assert any("prepaid" in o.lower() for o in listing.offers)
    assert listing.seller and listing.seller.startswith("Bridlen")


def test_read_listing_drops_pages_that_are_not_this_rival_or_have_no_price():
    comp = CompetitorProfile(brand_name="Bridlen", product_name="Bridlen Oxford")
    assert read_listing("https://myntra.com/y", "Ruosh Derby ₹6,499", comp, "marketplace", "INR") is None
    assert read_listing("https://myntra.com/z", "Bridlen story and craft", comp, "marketplace", "INR") is None


def test_marketplaces_and_queries_follow_the_merchant_market():
    hosts = [h for h, _ in marketplaces_for(AURELIUS)]
    assert "myntra.com" in hosts and "amazon.in" in hosts
    assert marketplaces_for({"target_geography": "Global"}) == []
    queries = build_listing_queries(_report().competitors, hosts)
    assert len(queries) == 2 and queries[0].include_domains == tuple(hosts)
    assert queries[0].vector == "channel_listings"


@pytest.mark.asyncio
async def test_strategy_brief_carries_currency_personas_listings_and_unknowns():
    from orchestrator.agents.campaign_strategy.agent import execute_campaign_strategy

    out = await execute_campaign_strategy({"merchant_context": dict(AURELIUS), "swot_report": _report()})
    brief = out["strategy_brief"]
    assert brief.currency == "INR"
    assert brief.personas_used and brief.personas_used[0].role == "primary"
    assert brief.market_listings and brief.unknowns
    assert all("$" not in a for a in brief.budget_assumptions)


# Shape of a real amazon.in product page (Ruosh Oxford, read live): nav filter "Under ₹500",
# promo amounts, carousel prices inside links, and Amazon's "_1.4 out of 5 stars_" markup.
AMAZON_PAGE = """
All CategoriesAmazon FashionShoes & HandbagsUnder ₹500Video Games
Ruosh Mens Formal Oxford
[1.4 _1.4 out of 5 stars_](javascript:void(0))[(3)](http://www.amazon.in#averageCustomerReviewsAnchor)
₹6,990.00 ₹6,990
**EMI** starts at ₹246 per month. No Cost EMI available
Upto ₹209.00 cashback as Amazon Pay Balance when you pay with Amazon Pay ICICI Bank Credit Cards
Upto ₹3,000.00 discount on SBI Credit Cards
2. Pay on Delivery
30 days free exchange or return
1.4 out of 5 stars
3 global ratings
{"desktop_buybox_group_1":[{"displayPrice":"₹6,990.00","priceAmount":6990.00,"currencySymbol":"₹"}]}
[₹5,490.00₹5,490.00](http://www.amazon.in/Ruosh-Men-Work-Slip-on-Black/dp/B09Y94VHTR)
[_4.0 out of 5 stars_ 795](http://www.amazon.in/product-reviews/B0CDQT43TM)
[₹1,609.00₹1,609.00](http://www.amazon.in/Hush-Puppies-Aaron-Black/dp/B0CDQ7F47P)
"""


def test_read_listing_on_real_amazon_layout_ignores_nav_promo_and_carousel_amounts():
    comp = CompetitorProfile(brand_name="Ruosh", product_name="Ruosh Oxford")
    listing = read_listing("https://www.amazon.in/dp/B0CMQZD7DM", AMAZON_PAGE, comp, "marketplace", "INR")
    assert listing.selling_price == 6990          # not the "Under ₹500" nav filter or a carousel price
    assert listing.mrp is None and listing.discount_pct is None
    assert listing.rating == 1.4                  # the product's own, not a carousel item's 4.0
    assert listing.review_count == 3
    assert listing.cod_available is True
    assert "30 days" in listing.returns_policy
    assert any("₹209.00 cashback" in o for o in listing.offers)


def test_read_listing_without_any_price_is_dropped():
    comp = CompetitorProfile(brand_name="Hats Off Accessories", product_name="")
    page = "HATS OFF ACCESSORIES Genuine Leather Tan Wholecut Oxford Shoes\nCurrently unavailable.\nPrice incl. VAT (₹)"
    assert read_listing("https://www.amazon.in/dp/B07MLXD3H8", page, comp, "marketplace", "INR") is None
