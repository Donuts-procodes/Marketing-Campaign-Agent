"""One archetype decision, shared by every stage that branches on business type."""

from __future__ import annotations

import pytest

from orchestrator.agents.market_research.intelligence.advisory import archetype
from orchestrator.agents.market_research.intelligence.market_mapping.taxonomy import reason_dynamic_parameters
from orchestrator.agents.market_research.ingestion.search_client import (
    build_missing_data_queries,
    build_search_queries,
)
from orchestrator.schemas.research import CompetitorProfile, DynamicParameterTaxonomy

#: Categories that previously matched one keyword list but not another.
_DIVERGENCE_CASES = [
    "Veterinary Clinic",
    "Roofing Contractor",
    "Personal Injury Law Practice",
    "Cosmetic Dental Clinic",
    "Organic Skincare eCommerce",
    "B2B SaaS Observability Platform",
    "Online Course Membership",
    "Web & Mobile App Development Agency",
]


def _competitors():
    return [CompetitorProfile(brand_name="RivalCo", product_name="RivalPro")]


class TestResolver:
    @pytest.mark.parametrize(
        "category,expected",
        [
            ("Veterinary Clinic", archetype.LOCAL),
            ("Cosmetic Dental Clinic", archetype.LOCAL),
            ("Roofing Contractor", archetype.LOCAL),
            ("Organic Skincare eCommerce", archetype.ECOMMERCE),
            ("B2B SaaS Observability Platform", archetype.SAAS),
            ("Online Course Membership", archetype.CREATOR),
            ("Web & Mobile App Development Agency", archetype.SERVICE),
        ],
    )
    def test_infers_from_category(self, category, expected):
        assert archetype.resolve({"category": category}) == expected

    def test_classified_business_model_wins_over_category_keywords(self):
        """An explicit classification beats guessing from the category string."""
        ctx = {"category": "Skincare for clinics", "business_model": "d2c_ecommerce"}
        assert archetype.resolve(ctx) == archetype.ECOMMERCE

    def test_unknown_classifier_label_falls_back_to_keywords(self):
        """The classifier may coin a label; the category still has to be read."""
        ctx = {"category": "Veterinary Clinic", "business_model": "veterinary_practice"}
        assert archetype.resolve(ctx) == archetype.LOCAL

    def test_unknown_input_is_other_not_an_error(self):
        assert archetype.resolve({"category": "Quantum Widget Foundry"}) == archetype.OTHER

    def test_empty_context_is_safe(self):
        assert archetype.resolve({}) in archetype.ARCHETYPES
        assert archetype.resolve() in archetype.ARCHETYPES

    def test_service_like_grouping(self):
        assert archetype.is_service_like(archetype.SERVICE)
        assert archetype.is_service_like(archetype.LOCAL)
        assert not archetype.is_service_like(archetype.ECOMMERCE)


class TestNoDivergenceBetweenRounds:
    """
    Regression: `build_missing_data_queries` carried a shorter keyword list than
    `build_search_queries`, so a vet clinic asked for rates in round 1 and for its MSRP in
    round 2. Both rounds must now agree for every archetype.
    """

    @pytest.mark.parametrize("category", _DIVERGENCE_CASES)
    def test_pricing_vocabulary_matches_across_rounds(self, category):
        ctx = {"product_name": "X", "category": category}
        first = next(q for q in build_search_queries(ctx) if q.vector == "pricing_scrape")
        later = next(
            q
            for q in build_missing_data_queries(ctx, _competitors(), DynamicParameterTaxonomy(), 1)
            if q.vector == "pricing_scrape"
        )
        service_first = "retainer" in first.query or "rates" in first.query
        service_later = "retainer" in later.query or "rates" in later.query
        assert service_first == service_later

    @pytest.mark.parametrize("category", _DIVERGENCE_CASES)
    def test_service_business_is_never_asked_for_msrp(self, category):
        """MSRP is a retail concept; asking a law firm for one returns nothing useful."""
        ctx = {"product_name": "X", "category": category}
        later = next(
            q
            for q in build_missing_data_queries(ctx, _competitors(), DynamicParameterTaxonomy(), 1)
            if q.vector == "pricing_scrape"
        )
        if archetype.is_service_like(archetype.resolve(ctx)):
            assert "MSRP" not in later.query

    @pytest.mark.parametrize("category", _DIVERGENCE_CASES)
    def test_complaint_venues_match_across_rounds(self, category):
        ctx = {"product_name": "X", "category": category}
        first = next(q for q in build_search_queries(ctx) if q.vector == "gripe_mining")
        later = next(
            (
                q.include_domains
                for q in build_missing_data_queries(ctx, _competitors(), DynamicParameterTaxonomy(), 1)
                if q.vector == "gripe_mining"
            ),
            None,
        )
        if later is not None:
            assert first.include_domains == later


class TestTaxonomyAgreesWithSearch:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("category", _DIVERGENCE_CASES)
    async def test_parameter_framework_matches_resolved_archetype(self, category):
        """The taxonomy must not classify the merchant differently from the query builder."""
        ctx = {"product_name": "X", "category": category, "primary_value_prop": "v"}
        taxonomy = await reason_dynamic_parameters(ctx)  # no llm -> deterministic branch
        resolved = archetype.resolve(ctx)

        service_markers = {"service_area_coverage", "pricing_and_retainer_structure"}
        is_service_taxonomy = bool(service_markers & set(taxonomy.critical_jtbd_drivers))
        assert is_service_taxonomy == archetype.is_service_like(resolved)
