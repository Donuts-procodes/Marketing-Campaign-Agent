"""
Synthesis prompt budget: the research loop accumulates search results across every retry
round, so an unconverged run reached ~367 results and overflowed the model's context window,
losing the entire SWOT to the fallback path.

These tests pin the two properties that make the cap safe: it stays under budget, and it
keeps every search vector represented. The second one matters because the accumulator is
ordered by round, so a plain prefix would keep only round-0 discovery results and drop all
the pricing and complaint evidence — the exact fields that come back empty.
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.agents.market_research.analysis.synthesis import _select_within_budget


@dataclass
class _Result:
    vector: str
    title: str
    url: str
    snippet: str
    score: float = 0.0


def _corpus(counts: dict[str, int], snippet_len: int = 800) -> list[_Result]:
    """Builds results grouped by vector in order, mimicking the loop's accumulator."""
    out: list[_Result] = []
    i = 0
    for vector, n in counts.items():
        for _ in range(n):
            out.append(
                _Result(vector, f"Title {i}", f"https://example-{i}.com", "s" * snippet_len)
            )
            i += 1
    return out


def _cost(results: list[_Result]) -> int:
    return sum(len(r.title) + len(r.snippet) + 120 for r in results)


def test_selection_stays_within_budget():
    results = _corpus({"alternative_discovery": 240, "pricing_scrape": 55})
    selected, dropped = _select_within_budget(results, 60_000)

    assert _cost(selected) <= 60_000
    assert dropped == len(results) - len(selected)


def test_every_vector_survives_the_cut():
    """The regression: head-truncation kept only discovery results, so pricing stayed 0/48."""
    results = _corpus(
        {
            "alternative_discovery": 240,
            "pricing_scrape": 55,
            "gripe_mining": 50,
            "messaging_claims": 22,
        }
    )
    selected, _ = _select_within_budget(results, 160_000)

    vectors = {r.vector for r in selected}
    assert vectors == {
        "alternative_discovery",
        "pricing_scrape",
        "gripe_mining",
        "messaging_claims",
    }

    # A plain prefix of the same budget would have been discovery-only.
    naive: list[_Result] = []
    for r in results:
        if _cost(naive + [r]) > 160_000:
            break
        naive.append(r)
    assert {r.vector for r in naive} == {"alternative_discovery"}


def test_pricing_and_gripes_are_served_before_discovery():
    """Under a tight budget the DQS-critical vectors win, since those fields are the gaps."""
    results = _corpus(
        {"alternative_discovery": 200, "pricing_scrape": 20, "gripe_mining": 20}
    )
    selected, _ = _select_within_budget(results, 20_000)

    by_vector = {v: 0 for v in ("alternative_discovery", "pricing_scrape", "gripe_mining")}
    for r in selected:
        by_vector[r.vector] += 1

    assert by_vector["pricing_scrape"] > 0
    assert by_vector["gripe_mining"] > 0
    # Discovery is the most numerous input but must not crowd the others out.
    assert by_vector["alternative_discovery"] <= by_vector["pricing_scrape"] + 1


def test_duplicate_urls_are_collapsed():
    dupes = [_Result("pricing_scrape", "T", "https://same.com", "x" * 500) for _ in range(5)]
    selected, dropped = _select_within_budget(dupes, 160_000)

    assert len(selected) == 1
    assert dropped == 4


def test_everything_fits_when_the_corpus_is_small():
    results = _corpus({"pricing_scrape": 3, "gripe_mining": 2})
    selected, dropped = _select_within_budget(results, 160_000)

    assert len(selected) == 5
    assert dropped == 0


def test_empty_corpus():
    assert _select_within_budget([], 1_000) == ([], 0)


def test_unknown_vector_is_still_included():
    """A vector added later must not be silently dropped for missing from the priority list."""
    results = _corpus({"pricing_scrape": 5, "brand_new_vector": 5})
    selected, _ = _select_within_budget(results, 160_000)

    assert "brand_new_vector" in {r.vector for r in selected}


def test_higher_scored_results_win_within_a_vector():
    low = _Result("pricing_scrape", "low", "https://low.com", "s" * 500, score=0.1)
    high = _Result("pricing_scrape", "high", "https://high.com", "s" * 500, score=0.9)
    selected, _ = _select_within_budget([low, high], 800)

    assert [r.title for r in selected] == ["high"]
