"""
Deterministic Data Quality Score (DQS) engine.

Evaluates research completeness across 5 weighted dimensions:
  C_comp    (0.30) — competitor coverage (only competitors backed by quoted evidence)
  P_pricing (0.22) — pricing intelligence density
  V_vuln    (0.18) — vulnerability/weakness mining depth
  S_sources (0.15) — source diversity (distinct websites, not URLs)
  R_recency (0.15) — how current the dated evidence is

Returns a float [0.00, 1.00] with diagnostic feedback when score < threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlparse

from orchestrator.agents.market_research.intelligence.validation.freshness import score_recency
from orchestrator.schemas.research import CompetitorProfile


# ── Weight Constants ──────────────────────────────────────────────────────────

W_COMPETITORS = 0.30
W_PRICING = 0.22
W_VULNERABILITIES = 0.18
W_SOURCES = 0.15
W_RECENCY = 0.15

# Evidence older than this is counted as stale by R_recency.
DEFAULT_MAX_AGE_DAYS = 548  # ~18 months

#: Sentinel written by the search-stage extractor for "a snippet looked price-shaped".
#: Shared so the scorer and the retry-query builder cannot drift apart on its meaning.
PLACEHOLDER_PRICING = "detected"

# ── Thresholds for full credit within each dimension ──────────────────────────

MIN_COMPETITORS_FULL = 5
MIN_PRICING_FULL = 4
MIN_WEAKNESSES_FULL = 6
MIN_SOURCES_FULL = 6


@dataclass
class DQSResult:
    """Structured output from the DQS evaluation gate."""

    score: float
    c_comp: float
    p_pricing: float
    v_vuln: float
    s_sources: float
    r_recency: float = 1.0
    diagnostics: list[str] = field(default_factory=list)
    passed: bool = False


def calculate_dqs(
    competitors: list[CompetitorProfile],
    source_urls: list[str],
    threshold: float = 0.80,
    evidence_dates: list[date] | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> DQSResult:
    """
    Compute the weighted Data Quality Score.

    DQS = (0.30 × C_comp) + (0.22 × P_pricing) + (0.18 × V_vuln)
        + (0.15 × S_sources) + (0.15 × R_recency)

    Each sub-score is a ratio clamped to [0.0, 1.0]:
      C_comp    = min(num_competitors / MIN_COMPETITORS_FULL, 1.0)
      P_pricing = min(competitors_with_pricing / MIN_PRICING_FULL, 1.0)
      V_vuln    = min(total_weaknesses_mined / MIN_WEAKNESSES_FULL, 1.0)
      S_sources = min(unique_source_urls / MIN_SOURCES_FULL, 1.0)
      R_recency = share of dated evidence newer than `max_age_days`; full credit when
                  evidence exists but carries no dates (absence is not staleness)
    """
    diagnostics: list[str] = []

    # Volume is not quality: a competitor counts only when real evidence backs it.
    num_competitors = sum(1 for c in competitors if c.factual_evidence or c.sources and c.weaknesses_mined)
    c_comp = min(num_competitors / MIN_COMPETITORS_FULL, 1.0) if MIN_COMPETITORS_FULL > 0 else 0.0

    if num_competitors < MIN_COMPETITORS_FULL:
        diagnostics.append(
            f"C_comp: found {num_competitors}/{MIN_COMPETITORS_FULL} evidence-backed competitors "
            f"(−{round((1.0 - c_comp) * W_COMPETITORS, 3)} weighted points)"
        )

    # "detected" is the placeholder `extract_preliminary_competitors` sets when a snippet
    # merely looked price-shaped -- it is not an actual price. Counting it let the loop
    # believe pricing was covered, converge, and skip the targeted pricing retry; synthesis
    # then dropped it and the delivered report scored lower than the gate that passed it.
    # `build_missing_data_queries` already treats it as unpriced; this agrees with it.
    competitors_with_pricing = sum(
        1 for c in competitors if c.pricing_model and c.pricing_model != PLACEHOLDER_PRICING
    )
    p_pricing = min(competitors_with_pricing / MIN_PRICING_FULL, 1.0) if MIN_PRICING_FULL > 0 else 0.0

    if competitors_with_pricing < MIN_PRICING_FULL:
        diagnostics.append(
            f"P_pricing: only {competitors_with_pricing}/{MIN_PRICING_FULL} competitors have pricing data "
            f"(−{round((1.0 - p_pricing) * W_PRICING, 3)} weighted points)"
        )

    total_weaknesses = sum(len(c.weaknesses_mined) for c in competitors)
    v_vuln = min(total_weaknesses / MIN_WEAKNESSES_FULL, 1.0) if MIN_WEAKNESSES_FULL > 0 else 0.0

    if total_weaknesses < MIN_WEAKNESSES_FULL:
        diagnostics.append(
            f"V_vuln: mined {total_weaknesses}/{MIN_WEAKNESSES_FULL} weakness entries "
            f"(−{round((1.0 - v_vuln) * W_VULNERABILITIES, 3)} weighted points)"
        )

    unique_sources = len({(urlparse(u).hostname or u).removeprefix("www.") for u in source_urls})
    s_sources = min(unique_sources / MIN_SOURCES_FULL, 1.0) if MIN_SOURCES_FULL > 0 else 0.0

    if unique_sources < MIN_SOURCES_FULL:
        diagnostics.append(
            f"S_sources: {unique_sources}/{MIN_SOURCES_FULL} distinct source websites "
            f"(−{round((1.0 - s_sources) * W_SOURCES, 3)} weighted points)"
        )

    r_recency, recency_diagnostics = score_recency(
        evidence_dates or [],
        has_evidence=bool(source_urls),
        max_age_days=max_age_days,
    )
    diagnostics.extend(recency_diagnostics)

    score = round(
        (W_COMPETITORS * c_comp)
        + (W_PRICING * p_pricing)
        + (W_VULNERABILITIES * v_vuln)
        + (W_SOURCES * s_sources)
        + (W_RECENCY * r_recency),
        4,
    )

    return DQSResult(
        score=score,
        c_comp=round(c_comp, 4),
        p_pricing=round(p_pricing, 4),
        v_vuln=round(v_vuln, 4),
        s_sources=round(s_sources, 4),
        r_recency=round(r_recency, 4),
        diagnostics=diagnostics,
        passed=score >= threshold,
    )
