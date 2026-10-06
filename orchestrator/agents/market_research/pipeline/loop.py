"""
Multi-Iteration Research & Convergence Loop Engine.

Coordinates the iterative discovery loop:
  1. Multi-vector search execution (Tavily)
  2. Deep page extraction (CrawlAPI, Tavily Extract fallback)
  3. Factual competitor data extraction & accumulation
  4. Dynamic parameter taxonomy refinement
  5. DQS gating & attribute density validation
  6. Targeted 'more data' query dispatch until convergence
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

from orchestrator.agents.market_research.discovery.crawler import extract_target_urls
from orchestrator.agents.market_research.progress import ProgressFn, _report
from orchestrator.agents.market_research.analysis.scoring import (
    PLACEHOLDER_PRICING,
    DQSResult,
    calculate_dqs,
)
from orchestrator.agents.market_research.discovery.search import (
    SearchQuery,
    TavilySearchResult,
    build_missing_data_queries,
    build_search_queries,
    derive_scale_signals,
    filter_out_of_scale_results,
)
from orchestrator.agents.market_research.analysis.freshness import (
    extract_publication_date,
    parse_iso_date,
)
from orchestrator.agents.market_research.analysis.taxonomy import (
    calculate_attribute_density,
    refine_parameters_from_findings,
)
from orchestrator.core.config import get_settings
from orchestrator.schemas.research import CompetitorProfile, DynamicParameterTaxonomy

if TYPE_CHECKING:
    from orchestrator.agents.market_research.pipeline.subagents import CrawlSubagent, SearchSubagent

logger = logging.getLogger(__name__)

# Review sites, forums, social networks and ad libraries: useful evidence, never competitors.
NON_COMPETITOR_DOMAINS = frozenset({
    "reddit", "g2", "capterra", "trustpilot", "yelp", "bbb", "sitejabber", "quora",
    "youtube", "facebook", "instagram", "twitter", "x", "linkedin", "tiktok", "medium",
    "wikipedia", "google", "bing", "amazon", "ebay", "producthunt", "trustradius",
    "getapp", "softwareadvice", "forbes", "techradar", "pcmag", "nytimes", "rtings",
})

_SECOND_LEVEL_SUFFIXES = frozenset({"co", "com", "org", "net", "ac", "gov", "edu"})


@dataclass
class ResearchLoopResult:
    """Consolidated findings and telemetry emitted upon research loop exit."""

    search_results: list[TavilySearchResult]
    extracted_pages: list[dict[str, Any]]
    all_source_urls: list[str]
    preliminary_competitors: list[CompetitorProfile]
    taxonomy: DynamicParameterTaxonomy
    dqs_result: DQSResult
    attribute_density: float
    retries_used: int
    assumptions_tagged: bool
    errors: list[str] = field(default_factory=list)


def _registrable_label(url: str) -> str:
    """Returns the organisation label of a URL's host, e.g. 'microsoft' for store.microsoft.co.uk."""
    host = (urlparse(url).hostname or "").lower()
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL_SUFFIXES and len(parts[-1]) == 2:
        return parts[-3]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else ""


def _normalize_url(url: str) -> str:
    """Drops fragments, query strings and trailing slashes so anchors of one page merge."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", "", ""))


def is_competitor_source(url: str) -> bool:
    return _registrable_label(url) not in NON_COMPETITOR_DOMAINS


def _tokens(text: str) -> set[str]:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(w) > 2}


# Pricing counts only when an actual amount is stated ("$14/seat", "49 USD per month", "€9.99"),
# not when a page merely mentions "pricing" or "plans".
_PRICE_AMOUNT_RE = re.compile(
    r"[$\u20ac\u00a3\u00a5\u20b9]\s?\d|\b\d[\d,.]*\s?(?:usd|eur|gbp|inr|dollars?)\b|"
    r"\b\d[\d,.]*\s?(?:/|per\s)(?:mo|month|year|yr|user|seat)\b",
    re.IGNORECASE,
)


def _has_price(text: str) -> bool:
    return bool(_PRICE_AMOUNT_RE.search(text))


def _extract_price(text: str) -> str | None:
    match = _PRICE_AMOUNT_RE.search(text)
    if match:
        return match.group(0).strip()
    return None

_WEAKNESS_KEYWORDS = (
    "issue", "complaint", "wish it had", "problem", "disappointed",
    "poor", "overpriced", "expensive", "slow", "broken", "unreliable",
    "frustrating", "bad", "scam", "lacks", "hard to use", "unresponsive",
    "mushy", "heavy", "drain", "strain",
)
_COMPLAINT_RE = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in _WEAKNESS_KEYWORDS) + r")", re.IGNORECASE)


def _is_complaint(text: str) -> bool:
    """A snippet is a complaint only when it uses complaint language, whichever query found it."""
    return len(text) > 20 and bool(_COMPLAINT_RE.search(text))


_LISTICLE_RE = re.compile(
    r"\b(best|top\s+\d+|\d+\s+best|vs\.?|versus|alternatives?|compared|comparison|review(?:s|ed)?|"
    r"ranked|guide|our (?:top )?picks)\b",
    re.IGNORECASE,
)


def is_listicle(title: str, url: str = "") -> bool:
    if bool(_LISTICLE_RE.search(title or "")):
        return True
    if url:
        path = urlparse(url).path.lower()
        if any(p in path for p in ("/reviews/", "/best-", "/top-", "-vs-", "-alternatives")):
            return True
    return False


def _clean_product_name(title: str, brand: str) -> str:
    """Strips SEO suffixes (' - Home', ' | Brand Name', '| 2026 Ratings') from product title."""
    cleaned = re.sub(r"\s*[|–—•-]\s*(?:home|official|reviews?|\d{4}.*)$", "", title, flags=re.IGNORECASE).strip()
    # If the title ends with '| Brand' or '- Brand', strip the redundant brand suffix
    cleaned = re.sub(rf"\s*[|–—•-]\s*{re.escape(brand)}.*$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned[:70] if cleaned else title[:70]


def _known_competitor_profile(
    name: str, profiles: list[CompetitorProfile], search_results: list[TavilySearchResult]
) -> CompetitorProfile:
    """
    Builds the profile for a competitor the merchant named, merging any discovered profile
    for that brand and attaching the search evidence that mentions it by name.
    """
    name_lower = name.lower()
    name_key = "".join(c for c in name_lower if c.isalnum())
    matched = [
        p for p in profiles
        if "".join(c for c in p.brand_name.lower() if c.isalnum()) == name_key
    ]
    profile = CompetitorProfile(brand_name=name, product_name=name)
    for p in matched:
        profile.pricing_model = profile.pricing_model or p.pricing_model
        profile.sources.extend(u for u in p.sources if u not in profile.sources)
        profile.factual_evidence.extend(e for e in p.factual_evidence if e not in profile.factual_evidence)
        profile.weaknesses_mined.extend(w for w in p.weaknesses_mined if w not in profile.weaknesses_mined)
    for r in search_results:
        if not r.url or len(r.snippet) <= 25 or name_lower not in r.snippet.lower():
            continue
        if r.url not in profile.sources:
            profile.sources.append(r.url)
        if not profile.pricing_model and _has_price(r.snippet):
            profile.pricing_model = PLACEHOLDER_PRICING
        if _is_complaint(r.snippet) and r.snippet[:200] not in profile.weaknesses_mined:
            profile.weaknesses_mined.append(r.snippet[:200])
        evidence = f'"{r.snippet[:200].strip()}..."'
        if len(profile.factual_evidence) < 6 and evidence not in profile.factual_evidence:
            profile.factual_evidence.append(evidence)
    return profile


def extract_preliminary_competitors(
    search_results: list[TavilySearchResult],
    known_competitors: list[str] | None = None,
) -> list[CompetitorProfile]:
    """
    Extracts candidate competitor profiles from factual search snippets.

    One profile per competitor page (URL without fragment/query). Review sites, forums,
    social networks, ad libraries and listicle/comparison articles never become competitors;
    their complaints are attached to the competitor profile whose name they best match instead.
    Competitors the merchant named come first, built from the evidence that mentions them.
    """
    profiles: dict[str, CompetitorProfile] = {}
    review_results: list[TavilySearchResult] = []

    for r in search_results:
        if not r.url:
            continue
        if not is_competitor_source(r.url) or is_listicle(r.title, r.url):
            review_results.append(r)
            continue

        has_pricing = _has_price(r.snippet)
        has_weakness = _is_complaint(r.snippet)
        evidence_snippet = f'"{r.snippet[:200].strip()}..."' if len(r.snippet) > 25 else None
        extracted_claim = r.snippet[:160].strip() if len(r.snippet) > 15 else ""

        brand_name = _extract_brand_from_url(r.url)
        clean_title = _clean_product_name(r.title or "", brand_name)

        key = _normalize_url(r.url)
        existing = profiles.get(key)
        if existing is not None:
            if has_pricing and not existing.pricing_model:
                existing.pricing_model = PLACEHOLDER_PRICING
            if extracted_claim and not existing.core_claims:
                existing.core_claims.append(extracted_claim)
            if has_weakness and r.snippet[:200] not in existing.weaknesses_mined:
                existing.weaknesses_mined.append(r.snippet[:200])
            if evidence_snippet and evidence_snippet not in existing.factual_evidence:
                existing.factual_evidence.append(evidence_snippet)
            if r.url not in existing.sources:
                existing.sources.append(r.url)
            continue

        profiles[key] = CompetitorProfile(
            brand_name=brand_name,
            product_name=clean_title if clean_title else "Product",
            pricing_model=PLACEHOLDER_PRICING if has_pricing else None,
            core_claims=[extracted_claim] if extracted_claim else [],
            weaknesses_mined=[r.snippet[:200]] if has_weakness else [],
            factual_evidence=[evidence_snippet] if evidence_snippet else [],
            sources=[r.url],
        )

    # Attach review/forum complaints to the best-matching competitor the text names.
    for r in review_results:
        if not _is_complaint(r.snippet):
            continue
        text = f"{r.title} {r.snippet}"
        text_lower = text.lower()
        text_tokens = _tokens(text)
        candidates = [p for p in profiles.values() if p.brand_name.lower() in text_lower]
        if not candidates:
            continue
        best = max(candidates, key=lambda p: len(_tokens(p.product_name) & text_tokens))
        complaint = r.snippet[:200].strip()
        # Clean journalistic or review byline boilerplate: e.g. 'Written by John Doe ...'
        complaint = re.sub(r"^(?:written by|by)\s+[A-Za-z0-9 \"'.,-]+?(?:—|-|:|\.\s+)", "", complaint, flags=re.IGNORECASE).strip()
        if complaint and complaint not in best.weaknesses_mined:
            best.weaknesses_mined.append(complaint)
        if r.url not in best.sources:
            best.sources.append(r.url)

    discovered = list(profiles.values())
    if not known_competitors:
        return discovered

    known = [_known_competitor_profile(n, discovered, search_results) for n in known_competitors if n.strip()]
    known_keys = {"".join(c for c in k.brand_name.lower() if c.isalnum()) for k in known}
    rest = [p for p in discovered if "".join(c for c in p.brand_name.lower() if c.isalnum()) not in known_keys]
    return known + rest


def _extract_brand_from_url(url: str) -> str:
    """Best-effort brand name extraction from the URL's registrable domain."""
    try:
        label = _registrable_label(url)
        return label.capitalize() if label else "Unknown"
    except Exception:
        return "Unknown"


def collect_evidence_dates(
    search_results: list[TavilySearchResult],
    extracted_pages: list[dict[str, Any]],
) -> list[date]:
    """
    One publication date per piece of evidence: the provider-supplied date when a search
    engine gave one, otherwise a date parsed out of the fetched page. Evidence with no
    discoverable date contributes nothing (it is not counted as stale).
    """
    dates: list[date] = []

    for r in search_results:
        parsed = parse_iso_date(r.published_date)
        if parsed:
            dates.append(parsed)

    for page in extracted_pages:
        markdown = page.get("markdown") or ""
        parsed = extract_publication_date(markdown)
        if parsed:
            dates.append(parsed)

    return dates


def is_research_converged(
    dqs_result: DQSResult,
    density: float,
    competitors_count: int,
    min_density: float = 0.0,
    min_competitors: int = 2,
    min_recency: float = 0.0,
) -> bool:
    """
    Evaluates whether accumulated research data is sufficient, verified and current:
      - DQS meets or exceeds threshold (e.g. >= 0.80)
      - Spec Matrix Attribute Density >= min_density (settings.research_min_density)
      - At least min_competitors distinct verified competitors discovered (default 4)
      - R_recency >= min_recency, so verifiably stale evidence re-triggers research instead
        of converging (undated evidence scores 1.0 and therefore never blocks convergence)
    """
    return (
        dqs_result.passed
        and density >= min_density
        and competitors_count >= min_competitors
        and dqs_result.r_recency >= min_recency
    )


async def execute_research_loop(
    merchant_context: dict[str, Any],
    initial_taxonomy: DynamicParameterTaxonomy,
    *,
    initial_retries: int = 0,
    tavily_client: Any = None,
    crawl_client: Any = None,
    on_progress: ProgressFn | None = None,
    search_agent: SearchSubagent | None = None,
    crawl_agent: CrawlSubagent | None = None,
) -> ResearchLoopResult:
    """
    Executes the multi-iteration research loop with dynamic parameter refinement,
    data accumulation, and DQS/density convergence gating.

    Searching and scraping are delegated to the Search and Crawl tool subagents.
    """
    from orchestrator.agents.market_research.pipeline.subagents import CrawlSubagent, SearchSubagent

    settings = get_settings()
    search_agent = search_agent or SearchSubagent(tavily_client, on_progress)
    crawl_agent = crawl_agent or CrawlSubagent(crawl_client, on_progress, tavily_client=tavily_client)

    queries: list[SearchQuery] = build_search_queries(merchant_context, taxonomy=initial_taxonomy)
    taxonomy = initial_taxonomy

    # Scale guard: giants slip past the query's soft "-name" exclusions (semantic engines
    # ignore them), so discovery results are filtered deterministically before they accumulate.
    scale_signals = derive_scale_signals(merchant_context)

    accumulated_search_results: list[TavilySearchResult] = []
    accumulated_extracted_pages: list[dict[str, Any]] = []
    accumulated_source_urls: list[str] = []
    preliminary_competitors: list[CompetitorProfile] = []
    dqs_result: DQSResult | None = None
    density: float = 0.0
    converged = False

    current_retries = initial_retries

    while True:
        # Step A: Search subagent executes the query batch (incumbents filtered out by scale)
        round_results = await search_agent.run(queries, round_number=current_retries)
        accumulated_search_results.extend(filter_out_of_scale_results(round_results, scale_signals))

        # Step B: Crawl subagent extracts high-signal pages it has not scraped yet
        target_urls = extract_target_urls(accumulated_search_results, max_urls=settings.deep_search_max_pages)
        accumulated_source_urls = list({r.url for r in accumulated_search_results} | set(target_urls))
        accumulated_extracted_pages.extend(await crawl_agent.run(target_urls))

        # Step C: Extract and aggregate preliminary competitor profiles
        preliminary_competitors = extract_preliminary_competitors(
            accumulated_search_results, merchant_context.get("known_competitors") or []
        )

        # Step D: Dynamically update parameter taxonomy from crawled text
        raw_corpus = [r.snippet for r in accumulated_search_results] + [
            p["markdown"] for p in accumulated_extracted_pages if p.get("markdown")
        ]
        taxonomy = refine_parameters_from_findings(taxonomy, raw_corpus)

        # Step E: Evaluate Data Quality Score (DQS), recency and Attribute Density
        evidence_dates = collect_evidence_dates(
            accumulated_search_results, accumulated_extracted_pages
        )
        dqs_result = calculate_dqs(
            competitors=preliminary_competitors,
            source_urls=accumulated_source_urls,
            threshold=settings.dqs_threshold,
            evidence_dates=evidence_dates,
            max_age_days=settings.recency_max_age_days,
        )
        density = calculate_attribute_density(preliminary_competitors, taxonomy)

        logger.info(
            "Research loop iteration %d: DQS=%.4f (passed=%s), Density=%.2f, Competitors=%d",
            current_retries,
            dqs_result.score,
            dqs_result.passed,
            density,
            len(preliminary_competitors),
        )

        # Step F: Convergence check
        converged = is_research_converged(
            dqs_result,
            density,
            len(preliminary_competitors),
            min_density=settings.research_min_density,
            min_competitors=settings.research_min_competitors,
            min_recency=settings.research_min_recency,
        )
        await _report(
            on_progress,
            f"[DQS_EVAL] Round {current_retries}: DQS {dqs_result.score:.2f} "
            f"(threshold {settings.dqs_threshold:.2f}), {len(preliminary_competitors)} competitors, "
            f"density {density * 100:.0f}%, recency {dqs_result.r_recency * 100:.0f}% "
            f"- {'converged' if converged else 'not converged'}",
        )
        if converged:
            logger.info("Research loop converged successfully at cycle %d", current_retries)
            break

        if current_retries >= settings.dqs_max_retries:
            logger.warning(
                "Research loop hit maximum retry limit (%d) — proceeding with tagged assumptions",
                current_retries,
            )
            break

        # Step G: Formulate targeted 'more data' search queries for next cycle
        current_retries += 1
        queries = build_missing_data_queries(
            merchant_context,
            preliminary_competitors,
            taxonomy,
            iteration=current_retries,
        )
        logger.info(
            "Dispatching 'more data' iteration %d with %d targeted queries",
            current_retries,
            len(queries),
        )

    assumptions_tagged = not converged

    return ResearchLoopResult(
        search_results=accumulated_search_results,
        extracted_pages=accumulated_extracted_pages,
        all_source_urls=accumulated_source_urls,
        preliminary_competitors=preliminary_competitors,
        taxonomy=taxonomy,
        dqs_result=dqs_result or calculate_dqs([], accumulated_source_urls, settings.dqs_threshold),
        attribute_density=density,
        retries_used=current_retries,
        assumptions_tagged=assumptions_tagged,
        errors=search_agent.errors + crawl_agent.errors,
    )
