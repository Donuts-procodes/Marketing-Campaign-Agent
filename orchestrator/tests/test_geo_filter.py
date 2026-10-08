"""
Geographic scoping of competitor discovery.

`target_geography` was only ever pasted into the discovery query as a quoted keyword, which
semantic search engines treat as a hint. A merchant selling in Delhi therefore got New York and
London rivals. These tests pin the deterministic post-filter that enforces it instead.

The filter is deliberately asymmetric: a local trade competes inside its city, so a foreign
result is simply wrong, while software crosses borders and must not be filtered at all.
"""

from __future__ import annotations

from orchestrator.agents.market_research.discovery.search import (
    TavilySearchResult,
    derive_geo_signals,
    filter_out_of_area_results,
)

LOCAL_CTX = {"target_geography": "Delhi", "category": "interior design services"}
SAAS_CTX = {"target_geography": "Delhi", "category": "B2B SaaS platform"}


def _r(vector: str, title: str, url: str, snippet: str = "") -> TavilySearchResult:
    return TavilySearchResult(vector=vector, title=title, url=url, snippet=snippet, score=0.8)


def test_geography_is_parsed_into_matchable_terms():
    geo = derive_geo_signals(LOCAL_CTX)
    assert "delhi" in geo.terms
    assert "india" in geo.terms, "a city should imply its country"
    assert ".in" in geo.cctlds


def test_local_business_is_strict_and_software_is_not():
    assert derive_geo_signals(LOCAL_CTX).strict is True
    assert derive_geo_signals(SAAS_CTX).strict is False, (
        "software competes across borders; filtering it by city would be wrong"
    )


def test_foreign_competitors_are_dropped_for_a_local_merchant():
    geo = derive_geo_signals(LOCAL_CTX)
    results = [
        _r("alternative_discovery", "Best designers in New York", "https://nycdesign.com/", "Manhattan."),
        _r("alternative_discovery", "Delhi NCR designers", "https://delhidecor.in/", "Gurgaon."),
    ]
    kept = filter_out_of_area_results(results, geo)
    urls = {r.url for r in kept}

    assert "https://delhidecor.in/" in urls
    assert "https://nycdesign.com/" not in urls


def test_results_with_no_location_signal_are_kept():
    """Most company sites never state a city; dropping them would gut recall."""
    geo = derive_geo_signals(LOCAL_CTX)
    results = [_r("alternative_discovery", "Elegant Interiors", "https://elegant.com/", "Award-winning.")]

    assert len(filter_out_of_area_results(results, geo)) == 1


def test_evidence_from_a_rejected_host_is_dropped_too():
    """Otherwise an out-of-area rival walks back in through its own pricing page."""
    geo = derive_geo_signals(LOCAL_CTX)
    results = [
        _r("alternative_discovery", "NY designers", "https://nycdesign.com/", "New York."),
        _r("pricing_scrape", "Pricing", "https://nycdesign.com/pricing", "From $5000."),
    ]
    kept = filter_out_of_area_results(results, geo)

    assert kept == [] or all("nycdesign.com" not in r.url for r in kept)


def test_a_host_accepted_anywhere_keeps_its_evidence():
    """One listicle naming a foreign city must not disqualify a locally-confirmed competitor."""
    geo = derive_geo_signals(LOCAL_CTX)
    results = [
        _r("alternative_discovery", "Studio X in New York magazine", "https://studiox.in/", "New York feature."),
        _r("alternative_discovery", "Studio X Delhi", "https://studiox.in/about", "Delhi based."),
        _r("pricing_scrape", "Studio X pricing", "https://studiox.in/pricing", "Packages."),
    ]
    kept = filter_out_of_area_results(results, geo)

    assert any(r.url.endswith("/pricing") for r in kept), "locally-confirmed host lost its evidence"


def test_software_merchant_keeps_foreign_competitors():
    geo = derive_geo_signals(SAAS_CTX)
    results = [
        _r("alternative_discovery", "Best CRM in New York", "https://nycsaas.com/", "New York."),
        _r("alternative_discovery", "London CRM", "https://londoncrm.co.uk/", "London."),
    ]

    assert len(filter_out_of_area_results(results, geo)) == 2


def test_no_geography_means_no_filtering():
    geo = derive_geo_signals({"category": "interior design services"})
    results = [_r("alternative_discovery", "NY designers", "https://nycdesign.com/", "New York.")]

    assert len(filter_out_of_area_results(results, geo)) == 1


def test_global_target_is_not_a_location_constraint():
    geo = derive_geo_signals({"target_geography": "Global", "category": "interior design services"})
    assert geo.terms == ()

    results = [_r("alternative_discovery", "NY designers", "https://nycdesign.com/", "New York.")]
    assert len(filter_out_of_area_results(results, geo)) == 1


def test_local_cctld_overrides_a_foreign_word_in_the_text():
    geo = derive_geo_signals(LOCAL_CTX)
    results = [
        _r("alternative_discovery", "Design studio", "https://studio.co.in/", "Inspired by New York style.")
    ]

    assert len(filter_out_of_area_results(results, geo)) == 1, (
        "an .in domain should settle the question regardless of stylistic references"
    )


def test_multi_part_geography_is_split():
    geo = derive_geo_signals(
        {"target_geography": "Delhi NCR, India", "category": "interior design services"}
    )
    assert "india" in geo.terms
