"""Pre-flight search query validation: reject garbage, repair the salvageable, never corrupt."""

from __future__ import annotations

import pytest

from orchestrator.agents.market_research.ingestion.query_validator import (
    MAX_EXCLUSIONS,
    MAX_QUERY_CHARS,
    validate_search_query,
)
from orchestrator.agents.market_research.ingestion.search_client import build_search_queries


class TestRejectsUnusableQueries:
    @pytest.mark.parametrize("query", ["", "   ", "\n\t "])
    def test_empty_query(self, query):
        assert validate_search_query(query).ok is False

    def test_operators_and_exclusions_only(self):
        """Nothing to match on — the engine would bill the call and return noise."""
        result = validate_search_query('OR AND -"Accenture" -"IBM"')
        assert result.ok is False
        assert "substantive" in result.summary

    def test_blank_merchant_fields_leave_an_unsearchable_query(self):
        """A blank category renders as `""` and the template searches for nothing."""
        result = validate_search_query('"" alternative OR competitor OR "best " 2026')
        assert result.ok is False
        assert "placeholder" in result.summary

    def test_unfilled_template_variable(self):
        assert validate_search_query("{category} pricing OR cost").ok is False

    def test_single_subject_is_valid(self):
        """One real term (a brand name) is a legitimate search."""
        assert validate_search_query("Toptal").ok is True


class TestRepairsSalvageableQueries:
    def test_trims_exclusions_over_budget(self):
        excl = " ".join(f'-"Brand{i}"' for i in range(13))
        result = validate_search_query(f'"Web Agency" alternative {excl} 2026')
        assert result.ok is True
        assert result.repaired is True
        assert result.query.count("-\"") == MAX_EXCLUSIONS

    def test_closes_unbalanced_quote(self):
        result = validate_search_query('"Web Agency alternative OR competitor')
        assert result.ok is True
        assert result.query.count('"') % 2 == 0

    def test_balances_parentheses(self):
        result = validate_search_query('"Vet Clinic" ("for startups" OR "for smb" pricing')
        assert result.ok is True
        assert result.query.count("(") == result.query.count(")")

    def test_long_query_is_brought_within_budget(self):
        long_q = '"Some Long Category Name Here" ' + " ".join(
            f'"filler phrase number {i}"' for i in range(40)
        )
        result = validate_search_query(long_q)
        assert len(result.query) <= MAX_QUERY_CHARS


class TestNeverCorruptsValidQueries:
    def test_adjacent_quoted_phrases_are_not_merged(self):
        """Regression: a naive `"\\s+"` placeholder pattern welded two phrases into one."""
        result = validate_search_query('"alpha co" "beta co" pricing')
        assert result.ok is True
        assert '"alpha co"' in result.query
        assert '"beta co"' in result.query
        assert '"alpha co beta co"' not in result.query

    def test_healthy_query_passes_through_untouched(self):
        query = '"Veterinary Clinic" alternative OR competitor "Austin, TX" 2026'
        result = validate_search_query(query)
        assert result.ok is True
        assert result.repaired is False
        assert result.query == query

    def test_site_filters_are_preserved(self):
        query = 'site:reddit.com "Vet Clinic" (complaint OR issue)'
        result = validate_search_query(query)
        assert result.ok is True
        assert "site:reddit.com" in result.query


class TestRealGeneratedQueries:
    """The generator stacks peer terms, a segment anchor, geography, a year and exclusions."""

    CTX = {
        "category": "Web & Mobile App Development Agency",
        "business_model": "professional_services",
        "target_geography": "United States",
        "dossier": "Team Size: 45+ developers. Serving startups to mid-market.",
    }

    def test_scale_anchored_query_is_valid_after_repair(self):
        query = next(
            q for q in build_search_queries(self.CTX) if q.vector == "alternative_discovery"
        )
        result = validate_search_query(query.query)
        assert result.ok is True
        assert len(result.query) <= MAX_QUERY_CHARS
        # The subject must survive whatever was trimmed.
        assert self.CTX["category"] in result.query

    def test_every_generated_vector_is_searchable(self):
        for query in build_search_queries(self.CTX):
            result = validate_search_query(query.query)
            assert result.ok is True, f"{query.vector}: {result.summary}"

    def test_conversational_category_is_sanitized_in_generated_queries(self):
        conv_ctx = {
            "category": "i want to increase my connections to attract more customers",
            "product_name": "i want to increase my connections to attract more customers",
            "business_model": "professional_services",
        }
        queries = build_search_queries(conv_ctx)
        assert len(queries) >= 4
        for q in queries:
            result = validate_search_query(q.query)
            assert result.ok is True, f"{q.vector}: {result.summary}"
            assert '"i want to increase my connections to attract more customers"' not in q.query

    def test_unquotes_conversational_sentence_directly(self):
        query = '"i want to increase my connections to attract more customers" alternative 2026'
        result = validate_search_query(query)
        assert result.ok is True
        assert result.repaired is True
        assert '"i want to increase my connections to attract more customers"' not in result.query
