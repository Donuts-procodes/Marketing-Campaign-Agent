from datetime import date

from orchestrator.agents.market_research.discovery.search import (
    TavilySearchResult,
    build_search_queries,
    rank_by_recency,
)

TODAY = date(2026, 10, 7)


def _r(url, score=0.8, published=None, snippet="pricing plans"):
    return TavilySearchResult(
        vector="gripe_mining", title="t", url=url, snippet=snippet, score=score, published_date=published
    )


def test_provider_dated_stale_result_is_dropped():
    out = rank_by_recency([_r("https://quora.com/old", published="2025-01-10")], max_age_days=548, today=TODAY)
    assert out == []


def test_newer_outranks_older_despite_lower_relevance():
    old = _r("https://a.com", score=0.9, published="2026-01-01")
    new = _r("https://b.com", score=0.7, published="2026-10-01")
    out = rank_by_recency([old, new], max_age_days=548, today=TODAY)
    assert [r.url for r in out] == ["https://b.com", "https://a.com"]


def test_snippet_date_lowers_rank_but_never_drops():
    r = _r("https://c.com", snippet="Trusted by teams since 2019")
    out = rank_by_recency([r], max_age_days=548, today=TODAY)
    assert len(out) == 1 and out[0].score < 0.8


def test_undated_kept_below_fresh_dated():
    fresh = _r("https://fresh.com", published="2026-10-05")
    undated = _r("https://undated.com")
    out = rank_by_recency([undated, fresh], max_age_days=548, today=TODAY)
    assert [r.url for r in out] == ["https://fresh.com", "https://undated.com"]


def test_every_search_vector_requests_recent_results():
    queries = build_search_queries({"product_name": "X", "category": "CRM software"})
    assert all(q.time_range for q in queries)
