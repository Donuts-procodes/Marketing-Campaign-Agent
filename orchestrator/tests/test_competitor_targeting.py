"""
Competitor-targeted deep crawl.

Deep crawl used to pick URLs by score across every host that appeared in search, so the page
budget was sprayed over listicles, forums and vendors alike and each real competitor got about
one page -- almost never their pricing page. A measured run ended with pricing on 0 of 48
profiles, which capped DQS at 0.78 against a 0.90 threshold.

The flow is now: search -> identify competitors -> rank -> crawl only the shortlist's own
domains, several pages each. These tests pin that behaviour.
"""

from __future__ import annotations

from urllib.parse import urlparse

from orchestrator.agents.market_research.ingestion.page_extractor import (
    extract_competitor_target_urls,
)
from orchestrator.agents.market_research.ingestion.search_client import TavilySearchResult
from orchestrator.agents.market_research.workflow.research_loop import (
    enrich_competitors_from_pages,
    extract_preliminary_competitors,
    merge_duplicate_competitors,
    rank_competitors,
)
from orchestrator.schemas.research import CompetitorProfile


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _vendor_results(n: int = 5, listicles: int = 15) -> list[TavilySearchResult]:
    """Vendors plus the listicle noise that dominated the real run's search output."""
    out: list[TavilySearchResult] = []
    for i in range(n):
        out.append(
            TavilySearchResult(
                "alternative_discovery", f"Vendor{i} Platform",
                f"https://vendor{i}.com/", f"Vendor{i} builds software.", 0.9 - i * 0.05,
            )
        )
        if i < 3:
            out.append(
                TavilySearchResult(
                    "pricing_scrape", f"Vendor{i} Pricing",
                    f"https://vendor{i}.com/pricing", "Plans start at $49/mo.", 0.8,
                )
            )
    # Listicles score highly but are articles about vendors, not vendors.
    for j in range(listicles):
        out.append(
            TavilySearchResult(
                "alternative_discovery", f"Top 10 best agencies {j}",
                f"https://listicle{j}.com/best", "A roundup.", 0.95,
            )
        )
    return out


def test_crawl_budget_goes_to_the_shortlist_not_every_host():
    results = _vendor_results()
    ranked = rank_competitors(extract_preliminary_competitors(results, []), results, [])
    shortlist = ranked[:5]

    urls = extract_competitor_target_urls(
        shortlist, results, pages_per_competitor=4, max_urls=24
    )

    hosts = {_host(u) for u in urls}
    assert hosts <= {f"vendor{i}.com" for i in range(5)}, "crawled a non-shortlisted host"
    assert not any("listicle" in h for h in hosts), "listicles must never be crawl targets"


def test_each_shortlisted_competitor_gets_several_pages():
    results = _vendor_results()
    ranked = rank_competitors(extract_preliminary_competitors(results, []), results, [])

    urls = extract_competitor_target_urls(
        ranked[:5], results, pages_per_competitor=4, max_urls=24
    )

    per_host: dict[str, int] = {}
    for u in urls:
        per_host[_host(u)] = per_host.get(_host(u), 0) + 1

    assert per_host, "no crawl targets produced"
    assert all(n > 1 for n in per_host.values()), (
        "one page per competitor is the old behaviour that left pricing empty"
    )


def test_pricing_pages_are_targeted_even_when_search_missed_them():
    """Vendors 3 and 4 have no pricing result; the guess fills their budget."""
    results = _vendor_results()
    ranked = rank_competitors(extract_preliminary_competitors(results, []), results, [])

    urls = extract_competitor_target_urls(
        ranked[:5], results, pages_per_competitor=4, max_urls=24
    )

    priced_hosts = {_host(u) for u in urls if "pricing" in u or "plans" in u}
    assert len(priced_hosts) >= 4, f"only {len(priced_hosts)} competitors got a pricing target"


def test_duplicate_profiles_for_one_company_are_merged():
    """Profiles are keyed per URL, so one vendor's home/pricing/blog arrive as three entries."""
    results = [
        TavilySearchResult("alternative_discovery", "Vendor0 Platform",
                           "https://vendor0.com/", "Vendor0 builds software.", 0.9),
        TavilySearchResult("pricing_scrape", "Vendor0 Pricing",
                           "https://vendor0.com/pricing", "Plans start at $49/mo.", 0.8),
        TavilySearchResult("gripe_mining", "Vendor0 Platform",
                           "https://vendor0.com/blog", "Users complain support is slow.", 0.6),
    ]
    raw = extract_preliminary_competitors(results, [])
    assert len(raw) > 1, "fixture should produce the duplicate profiles being tested"

    merged = merge_duplicate_competitors(raw)
    assert len(merged) == 1
    # The merged profile keeps what each duplicate knew.
    assert len(merged[0].sources) >= 2


def test_shortlist_contains_distinct_companies():
    results = _vendor_results()
    ranked = rank_competitors(extract_preliminary_competitors(results, []), results, [])
    top = ranked[:5]

    hosts = [_host(c.sources[0]) for c in top if c.sources]
    assert len(set(hosts)) == len(hosts), "one company occupied several shortlist slots"


def test_merchant_named_competitors_rank_first():
    results = _vendor_results()
    raw = extract_preliminary_competitors(results, ["Vendor4"])
    ranked = rank_competitors(raw, results, ["Vendor4"])

    assert ranked[0].brand_name.lower().startswith("vendor4"), (
        "a competitor the merchant named must outrank organically discovered ones"
    )


def test_crawled_pricing_page_upgrades_the_profile():
    """The placeholder does not count toward DQS; a real amount from the crawl does."""
    comp = CompetitorProfile(
        brand_name="Vendor0", product_name="Vendor0",
        pricing_model="detected", sources=["https://vendor0.com/"],
    )
    pages = [{"url": "https://vendor0.com/pricing", "markdown": "Pro plan is $49/month per seat."}]

    enrich_competitors_from_pages([comp], pages)

    assert comp.pricing_model != "detected"
    assert "49" in comp.pricing_model


def test_enrichment_only_matches_pages_from_the_competitors_own_domain():
    comp = CompetitorProfile(
        brand_name="Vendor0", product_name="Vendor0", sources=["https://vendor0.com/"],
    )
    pages = [{"url": "https://unrelated.com/pricing", "markdown": "Plans from $999/month."}]

    enrich_competitors_from_pages([comp], pages)

    assert not comp.pricing_model, "a foreign domain must not set a competitor's price"


def test_extracted_price_keeps_the_whole_amount():
    """The detector regex stops after one digit; extraction must not reuse it ($49 -> $4)."""
    from orchestrator.agents.market_research.workflow.research_loop import _extract_price

    assert _extract_price("Pro plan is $49/month per seat.") == "$49/month"
    assert _extract_price("Plans start at $1,299 per year.") == "$1,299 per year"
    assert _extract_price("Costs 49 USD per month") == "49 USD per month"
    assert _extract_price("$12,000/year") == "$12,000/year"


def test_no_price_is_reported_when_the_page_states_none():
    from orchestrator.agents.market_research.workflow.research_loop import _extract_price

    assert _extract_price("Pricing available on request") is None
    assert _extract_price("Contact us for plans") is None


def test_targeting_handles_competitors_without_sources():
    comp = CompetitorProfile(brand_name="Ghost", product_name="Ghost", sources=[])
    assert extract_competitor_target_urls([comp], [], pages_per_competitor=4) == []


def test_max_urls_is_respected():
    results = _vendor_results(n=10, listicles=0)
    ranked = rank_competitors(extract_preliminary_competitors(results, []), results, [])

    urls = extract_competitor_target_urls(
        ranked, results, pages_per_competitor=4, max_urls=12
    )
    assert len(urls) <= 12


def test_enrichment_extracts_logo_and_product_image():
    comp = CompetitorProfile(
        brand_name="Aurelius", product_name="Oxford", sources=["https://aureliusfootwear.com/"]
    )
    pages = [{
        "url": "https://aureliusfootwear.com/products/oxford",
        "markdown": "# Sovereign Oxford\n\n![Sovereign Oxford Handcrafted Leather Shoe](https://cdn.aureliusfootwear.com/oxford_hero.webp)\n\nPrice: ₹ 7,499. Handcrafted buff calf leather.",
    }]

    enrich_competitors_from_pages([comp], pages)

    assert comp.logo_url == "https://www.google.com/s2/favicons?domain=aureliusfootwear.com&sz=128"
    assert comp.product_image_url == "https://cdn.aureliusfootwear.com/oxford_hero.webp"
