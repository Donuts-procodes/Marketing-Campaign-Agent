"""Loop 2 Verification: DQS scoring engine and query generation tests."""

from __future__ import annotations

import pytest

from orchestrator.agents.market_research.analysis.scoring import (
    DQSResult,
    W_COMPETITORS,
    W_PRICING,
    W_RECENCY,
    W_SOURCES,
    W_VULNERABILITIES,
    calculate_dqs,
)
from orchestrator.agents.market_research.discovery.crawler import extract_target_urls
from orchestrator.agents.market_research.discovery.search import (
    SearchQuery,
    TavilySearchResult,
    build_search_queries,
    derive_scale_signals,
    filter_out_of_scale_results,
    refine_queries_for_retry,
)
from orchestrator.schemas.research import CompetitorProfile


# ── DQS Scoring Tests ────────────────────────────────────────────────────────

class TestDQSFormula:
    def test_perfect_score(self):
        """All dimensions at full credit → DQS = 1.0."""
        competitors = [
            CompetitorProfile(
                brand_name=f"Brand{i}",
                product_name=f"Product{i}",
                pricing_model=f"${i}9/mo",
                weaknesses_mined=["issue_a", "issue_b"],
                sources=[f"https://example.com/{i}"],
            )
            for i in range(5)
        ]
        sources = [f"https://source{i}.com" for i in range(6)]

        result = calculate_dqs(competitors, sources)

        assert result.score == 1.0
        assert result.c_comp == 1.0
        assert result.p_pricing == 1.0
        assert result.v_vuln == 1.0
        assert result.s_sources == 1.0
        assert result.passed is True
        assert result.diagnostics == []

    def test_zero_score(self):
        """No data at all → DQS = 0.0."""
        result = calculate_dqs([], [])

        assert result.score == 0.0
        assert result.passed is False
        # One diagnostic per dimension, recency included (no sources to date-check).
        assert len(result.diagnostics) == 5

    def test_missing_pricing_docks_points(self):
        """5 competitors but none with pricing → P_pricing = 0.0."""
        competitors = [
            CompetitorProfile(
                brand_name=f"B{i}",
                product_name=f"P{i}",
                weaknesses_mined=["gripe_1", "gripe_2"],
                sources=[f"https://s{i}.com"],
            )
            for i in range(5)
        ]
        sources = [f"https://src{i}.com" for i in range(6)]

        result = calculate_dqs(competitors, sources)

        assert result.c_comp == 1.0
        assert result.p_pricing == 0.0
        assert result.v_vuln == 1.0
        assert result.s_sources == 1.0
        # Undated evidence takes full recency credit, so only pricing is docked.
        expected = (
            (W_COMPETITORS * 1.0) + (W_PRICING * 0.0) + (W_VULNERABILITIES * 1.0)
            + (W_SOURCES * 1.0) + (W_RECENCY * 1.0)
        )
        assert result.score == round(expected, 4)
        assert result.passed is False
        assert any("P_pricing" in d for d in result.diagnostics)

    def test_low_competitor_count_reduces_c_comp(self):
        """1 competitor out of 5 required → C_comp = 0.2."""
        competitors = [
            CompetitorProfile(
                brand_name="Solo",
                product_name="OnlyOne",
                pricing_model="$50",
                weaknesses_mined=["a", "b", "c", "d", "e", "f"],
                sources=["https://a.com"],
            )
        ]
        sources = [f"https://s{i}.com" for i in range(6)]

        result = calculate_dqs(competitors, sources)

        assert result.c_comp == 0.2
        assert result.p_pricing == 0.25
        assert result.v_vuln == 1.0
        assert result.s_sources == 1.0
        assert any("C_comp" in d for d in result.diagnostics)

    def test_low_sources_reduces_s_sources(self):
        """Only 3 unique sources out of 6 required → S_sources = 0.5."""
        competitors = [
            CompetitorProfile(
                brand_name=f"B{i}",
                product_name=f"P{i}",
                pricing_model=f"${i}0",
                weaknesses_mined=["x"],
            )
            for i in range(5)
        ]
        sources = ["https://a.com", "https://b.com", "https://c.com"]

        result = calculate_dqs(competitors, sources)

        assert result.s_sources == 0.5
        assert any("S_sources" in d for d in result.diagnostics)

    def test_duplicate_sources_counted_once(self):
        """Duplicate URLs should only count as one unique source."""
        competitors = [
            CompetitorProfile(
                brand_name=f"B{i}",
                product_name=f"P{i}",
                pricing_model=f"${i}0",
                weaknesses_mined=["x"],
            )
            for i in range(5)
        ]
        sources = ["https://a.com", "https://a.com", "https://a.com"]

        result = calculate_dqs(competitors, sources)

        assert result.s_sources == round(1 / 6, 4)

    def test_over_threshold_passes(self):
        """Score above threshold → passed = True."""
        competitors = [
            CompetitorProfile(
                brand_name=f"B{i}",
                product_name=f"P{i}",
                pricing_model=f"${i}0",
                weaknesses_mined=["w1", "w2"],
                sources=[f"https://s{i}.com"],
            )
            for i in range(4)
        ]
        sources = [f"https://s{i}.com" for i in range(6)]

        result = calculate_dqs(competitors, sources, threshold=0.80)

        assert result.score >= 0.80
        assert result.passed is True

    def test_weights_sum_to_one(self):
        assert W_COMPETITORS + W_PRICING + W_VULNERABILITIES + W_SOURCES + W_RECENCY == pytest.approx(1.0)

    def test_custom_threshold(self):
        """Lower threshold makes partial data pass."""
        competitors = [
            CompetitorProfile(brand_name="B1", product_name="P1", factual_evidence=['"B1 ships in 2 days"'])
        ]
        result_strict = calculate_dqs(competitors, [], threshold=0.80)
        result_lenient = calculate_dqs(competitors, [], threshold=0.05)

        assert result_strict.passed is False
        assert result_lenient.passed is True
        assert result_strict.score == result_lenient.score


# ── Query Generation Tests ────────────────────────────────────────────────────

class TestQueryGeneration:
    MOCK_CONTEXT = {
        "product_name": "ErgoMouse V2",
        "category": "B2B Ergonomic Computer Peripherals",
        "primary_value_prop": "Patented 57-degree neutral wrist angle",
        "price_usd": 129.00,
        "known_competitors": ["Logitech Lift", "Logitech MX Master 3S"],
    }

    def test_generates_four_vectors(self):
        queries = build_search_queries(self.MOCK_CONTEXT)
        assert len(queries) == 4
        vectors = {q.vector for q in queries}
        assert vectors == {"alternative_discovery", "pricing_scrape", "gripe_mining", "messaging_claims"}

    def test_queries_contain_category(self):
        queries = build_search_queries(self.MOCK_CONTEXT)
        category = self.MOCK_CONTEXT["category"]
        alt_q = next(q for q in queries if q.vector == "alternative_discovery")
        assert category in alt_q.query

    def test_queries_contain_competitor_names(self):
        queries = build_search_queries(self.MOCK_CONTEXT)
        pricing_q = next(q for q in queries if q.vector == "pricing_scrape")
        assert "Logitech Lift" in pricing_q.query or "Logitech MX Master 3S" in pricing_q.query

    def test_no_competitors_still_generates_queries(self):
        ctx = {**self.MOCK_CONTEXT, "known_competitors": []}
        queries = build_search_queries(ctx)
        assert len(queries) == 4
        pricing_q = next(q for q in queries if q.vector == "pricing_scrape")
        assert self.MOCK_CONTEXT["product_name"] in pricing_q.query

    def test_all_queries_use_advanced_depth(self):
        queries = build_search_queries(self.MOCK_CONTEXT)
        assert all(q.search_depth == "advanced" for q in queries)


class TestQueryRefinement:
    MOCK_CONTEXT = {
        "product_name": "ErgoMouse V2",
        "category": "B2B Ergonomic Computer Peripherals",
        "known_competitors": ["Logitech Lift", "Logitech MX Master 3S"],
    }

    def test_retry_1_broadens_gripe_mining(self):
        original = build_search_queries(self.MOCK_CONTEXT)
        refined = refine_queries_for_retry(original, self.MOCK_CONTEXT, retry_number=1)
        gripe_q = next(q for q in refined if q.vector == "gripe_mining")
        assert "site:reddit.com" not in gripe_q.query

    def test_retry_2_broadens_discovery(self):
        original = build_search_queries(self.MOCK_CONTEXT)
        refined = refine_queries_for_retry(original, self.MOCK_CONTEXT, retry_number=2)
        alt_q = next(q for q in refined if q.vector == "alternative_discovery")
        assert "comparison" in alt_q.query or "vs" in alt_q.query

    def test_retry_preserves_unchanged_vectors(self):
        original = build_search_queries(self.MOCK_CONTEXT)
        refined = refine_queries_for_retry(original, self.MOCK_CONTEXT, retry_number=1)
        orig_pricing = next(q for q in original if q.vector == "pricing_scrape")
        ref_pricing = next(q for q in refined if q.vector == "pricing_scrape")
        assert orig_pricing.query == ref_pricing.query


# ── Scale Anchoring Tests ─────────────────────────────────────────────────────

class TestScaleAnchoring:
    BOUTIQUE_CONTEXT = {
        "product_name": "DevFlow Studio",
        "category": "Web & Mobile App Development Agency",
        "primary_value_prop": "Custom SaaS and apps for startups to mid-market",
        "business_model": "professional_services",
        "price_usd": 25000,
        "target_geography": "United States",
        "dossier": (
            "DevFlow Studio. Team Size: 45+ professional developers, designers, and "
            "architects. Serving startups to mid-market enterprises."
        ),
    }

    def test_boutique_tier_detected_from_team_size(self):
        scale = derive_scale_signals(self.BOUTIQUE_CONTEXT, "web & mobile app development agency professional_services")
        assert scale.tier == "boutique"
        assert scale.archetype == "service"

    def test_boutique_discovery_excludes_mega_incumbents(self):
        alt_q = next(q for q in build_search_queries(self.BOUTIQUE_CONTEXT) if q.vector == "alternative_discovery")
        # The exact giants that polluted the original DevFlow output must be negated.
        for incumbent in ("Accenture", "IBM", "Deloitte", "Toptal", "Thoughtworks"):
            assert f'-"{incumbent}"' in alt_q.query

    def test_boutique_discovery_adds_peer_and_segment_terms(self):
        alt_q = next(q for q in build_search_queries(self.BOUTIQUE_CONTEXT) if q.vector == "alternative_discovery")
        assert "boutique" in alt_q.query or "small agency" in alt_q.query
        assert "for startups" in alt_q.query or "for mid-market" in alt_q.query

    def test_enterprise_merchant_keeps_no_exclusions(self):
        ctx = {**self.BOUTIQUE_CONTEXT, "dossier": "Global firm of 12,000 employees serving Fortune 500 enterprises."}
        scale = derive_scale_signals(ctx, "web & mobile app development agency professional_services")
        assert scale.tier == "enterprise"
        assert scale.exclude_terms == ()

    def test_no_scale_signal_is_inert(self):
        """Contexts we can't size (no dossier/price) must not alter the query — protects other archetypes."""
        ctx = {"product_name": "X", "category": "B2B Ergonomic Computer Peripherals", "price_usd": 129}
        scale = derive_scale_signals(ctx, "b2b ergonomic computer peripherals ")
        assert scale.tier == "unknown"
        assert scale.peer_terms == "" and scale.exclude_terms == ()

    def test_retry_broadening_preserves_incumbent_exclusions(self):
        original = build_search_queries(self.BOUTIQUE_CONTEXT)
        refined = refine_queries_for_retry(original, self.BOUTIQUE_CONTEXT, retry_number=2)
        alt_q = next(q for q in refined if q.vector == "alternative_discovery")
        assert '-"Accenture"' in alt_q.query

    def test_filter_drops_incumbent_by_domain_and_name(self):
        """Semantic engines ignore '-name'; the deterministic filter is the hard guarantee."""
        scale = derive_scale_signals(self.BOUTIQUE_CONTEXT)
        results = [
            TavilySearchResult(vector="alternative_discovery", title="Accenture | Consulting", url="https://www.accenture.com/us", snippet="", score=0.9),
            TavilySearchResult(vector="alternative_discovery", title="Top 10 agencies: Deloitte Digital leads", url="https://listicle.com/top", snippet="", score=0.8),
            TavilySearchResult(vector="alternative_discovery", title="MojoTech — product studio", url="https://www.mojotech.com", snippet="", score=0.7),
            TavilySearchResult(vector="alternative_discovery", title="Clutch profile", url="https://clutch.co/profile/ibm", snippet="", score=0.6),
        ]
        kept = filter_out_of_scale_results(results, scale)
        kept_urls = {r.url for r in kept}
        assert "https://www.mojotech.com" in kept_urls
        assert "https://www.accenture.com/us" not in kept_urls   # domain match
        assert "https://listicle.com/top" not in kept_urls        # name-in-title match
        assert "https://clutch.co/profile/ibm" not in kept_urls    # name-in-url match

    def test_filter_keeps_named_competitor_pricing_results(self):
        """A large firm the merchant explicitly named must survive on non-discovery vectors."""
        scale = derive_scale_signals(self.BOUTIQUE_CONTEXT)
        results = [
            TavilySearchResult(vector="pricing_scrape", title="Accenture pricing", url="https://www.accenture.com/pricing", snippet="", score=0.9),
        ]
        assert filter_out_of_scale_results(results, scale) == results

    def test_filter_inert_for_enterprise_and_unknown(self):
        incumbent = [TavilySearchResult(vector="alternative_discovery", title="IBM", url="https://ibm.com", snippet="", score=0.9)]
        ent = derive_scale_signals({**self.BOUTIQUE_CONTEXT, "dossier": "Global firm of 20,000 employees."})
        unknown = derive_scale_signals({"category": "Mouse", "price_usd": 99})
        assert filter_out_of_scale_results(incumbent, ent) == incumbent
        assert filter_out_of_scale_results(incumbent, unknown) == incumbent


# ── URL Extraction Tests ──────────────────────────────────────────────────────

class TestURLExtraction:
    def test_deduplicates_and_caps(self):
        results = [
            TavilySearchResult(vector="pricing_scrape", title="A", url="https://a.com", snippet="", score=0.9),
            TavilySearchResult(vector="pricing_scrape", title="B", url="https://a.com", snippet="", score=0.8),
            TavilySearchResult(vector="alternative_discovery", title="C", url="https://b.com", snippet="", score=0.7),
        ]
        urls = extract_target_urls(results, max_urls=5)
        assert len(urls) == 2
        assert urls[0] == "https://a.com"

    def test_respects_max_urls(self):
        results = [
            TavilySearchResult(vector="pricing_scrape", title=f"T{i}", url=f"https://{i}.com", snippet="", score=0.5)
            for i in range(20)
        ]
        urls = extract_target_urls(results, max_urls=3)
        assert len(urls) == 3

    def test_priority_ordering(self):
        """pricing_scrape has higher vector priority — its bonus should outweigh a small raw score deficit."""
        results = [
            TavilySearchResult(vector="messaging_claims", title="Low", url="https://low.com", snippet="", score=0.70),
            TavilySearchResult(vector="pricing_scrape", title="High", url="https://high.com", snippet="", score=0.50),
        ]
        urls = extract_target_urls(results, max_urls=5)
        assert urls[0] == "https://high.com"

    def test_empty_results(self):
        urls = extract_target_urls([], max_urls=10)
        assert urls == []


# ── Dynamic Campaign Archetype Tests ──────────────────────────────────────────

class TestDynamicCampaignArchetypes:
    @pytest.mark.asyncio
    async def test_local_services_campaign_adapts_domains_and_pricing(self):
        ctx = {
            "product_name": "Apex Dental Studio",
            "category": "Cosmetic Dental Clinic",
            "primary_value_prop": "Painless porcelain veneers and same-day implants",
            "campaign_type": "lead_gen",
            "business_model": "local_service",
            "target_geography": "Austin, TX",
            "price_model": "hourly_rate",
        }
        queries = build_search_queries(ctx)
        alt_q = next(q for q in queries if q.vector == "alternative_discovery")
        pricing_q = next(q for q in queries if q.vector == "pricing_scrape")
        gripe_q = next(q for q in queries if q.vector == "gripe_mining")

        assert "Austin, TX" in alt_q.query
        assert "rates" in pricing_q.query or "fees" in pricing_q.query or "retainer" in pricing_q.query
        assert gripe_q.include_domains is not None
        assert "yelp.com" in gripe_q.include_domains or "trustpilot.com" in gripe_q.include_domains

    @pytest.mark.asyncio
    async def test_ecommerce_d2c_campaign_adapts_domains_and_pricing(self):
        ctx = {
            "product_name": "GlowBerry Serum",
            "category": "Organic Skincare eCommerce",
            "primary_value_prop": "Cold-pressed antioxidant vitamin C serum",
            "campaign_type": "ecommerce_sales",
            "business_model": "d2c_ecommerce",
        }
        queries = build_search_queries(ctx)
        gripe_q = next(q for q in queries if q.vector == "gripe_mining")

        assert gripe_q.include_domains is not None
        assert "sitejabber.com" in gripe_q.include_domains or "trustpilot.com" in gripe_q.include_domains

    @pytest.mark.asyncio
    async def test_saas_campaign_adapts_domains_and_pricing(self):
        ctx = {
            "product_name": "CloudMetrics IO",
            "category": "B2B SaaS Observability",
            "primary_value_prop": "Real-time distributed tracing with zero-overhead eBPF",
            "campaign_type": "competitor_takeover",
            "business_model": "b2b_saas",
        }
        queries = build_search_queries(ctx)
        gripe_q = next(q for q in queries if q.vector == "gripe_mining")

        assert gripe_q.include_domains is not None
        assert "g2.com" in gripe_q.include_domains and "capterra.com" in gripe_q.include_domains
