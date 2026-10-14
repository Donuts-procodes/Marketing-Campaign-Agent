import pytest
from orchestrator.agents.market_research.ingestion.search_client import (
    build_search_queries,
    build_missing_data_queries,
    SearchQuery,
)
from orchestrator.agents.market_research.intelligence.profiling.leap_analyzer import (
    qualifies,
    _factual_benchmark,
)
from orchestrator.schemas.research import CompetitorProfile, DynamicParameterTaxonomy


def test_build_search_queries_emits_leap_queries():
    ctx = {
        "category": "CRM Software",
        "product_name": "SalesPro",
        "known_competitors": ["HubSpot", "Pipedrive"],
    }
    queries = build_search_queries(ctx, include_leap=True)
    vectors = [q.vector for q in queries]
    assert "leap_discovery" in vectors
    assert "leap_history" in vectors

    history_q = next(q for q in queries if q.vector == "leap_history")
    assert "HubSpot" in history_q.query
    assert "Pipedrive" in history_q.query
    assert "milestones" in history_q.query


def test_build_missing_data_queries_targets_missing_growth():
    ctx = {
        "category": "Email Marketing",
        "business_model": "SaaS",
    }
    comp = CompetitorProfile(
        brand_name="MailFast",
        product_name="MailFast App",
        relevance_score=0.85,
        sources=["https://mailfast.com"],
        pricing_model="$29/month",
        milestones=[],
        founded=None,
    )
    taxonomy = DynamicParameterTaxonomy(archetype="saas")
    queries = build_missing_data_queries(ctx, [comp], taxonomy, iteration=1)
    leap_queries = [q for q in queries if q.vector == "leap_history"]
    assert len(leap_queries) >= 1
    assert "MailFast" in leap_queries[0].query
    assert "founded" in leap_queries[0].query


def test_qualifies_and_factual_benchmark_with_pricing_and_milestones():
    comp = CompetitorProfile(
        brand_name="AcmeAnalytics",
        product_name="Acme Platform",
        relevance_score=0.75,
        sources=["https://acme.com"],
        pricing_model="Tiered ($99 - $499/mo)",
        employee_count="50-100",
        milestones=["2022: Launched AI Engine", "2024: Expanded to EU"],
    )
    ok, why = qualifies(comp)
    assert ok is True
    assert why == ""

    bench = _factual_benchmark(comp)
    assert bench.brand_name == "AcmeAnalytics"
    assert "50-100 employees" in bench.current_scale
    assert "2022" in bench.origin_story
