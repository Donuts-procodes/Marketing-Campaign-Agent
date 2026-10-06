"""
Multi-vector search query generation, dynamic parameter keywords, and Tavily client integration.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from orchestrator.agents.market_research.analysis.scoring import PLACEHOLDER_PRICING
from orchestrator.agents.market_research.analysis.archetype import (
    CREATOR as ARCH_CREATOR,
    ECOMMERCE as ARCH_ECOMMERCE,
    LOCAL as ARCH_LOCAL,
    OTHER as ARCH_OTHER,
    SAAS as ARCH_SAAS,
    SERVICE as ARCH_SERVICE,
    resolve as resolve_archetype,
)
from orchestrator.agents.market_research.discovery.query_validator import validate_search_query
from orchestrator.core.clock import current_year as _current_year
from orchestrator.core.config import get_settings
from orchestrator.schemas.research import CompetitorProfile, DynamicParameterTaxonomy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchQuery:
    """Single search query with its taxonomy vector label and domain targeting."""

    vector: str
    query: str
    search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = "advanced"
    include_domains: tuple[str, ...] | None = None
    # Recency window passed to engines that support it ("day"/"week"/"month"/"year").
    # Facts that go stale (pricing, positioning) ask for a window; gripe mining does not,
    # since a two-year-old complaint thread is still valid evidence of a weakness.
    time_range: str | None = None


@dataclass
class TavilySearchResult:
    """Normalized result from a single Tavily search call."""

    vector: str
    title: str
    url: str
    snippet: str
    score: float = 0.0
    provider: str = "tavily"
    published_date: str | None = None


# ── Scale anchoring ────────────────────────────────────────────────────────────
# "best <category>" discovery surfaces whoever dominates that query's SEO — which for a
# 45-person studio means Accenture, IBM, Deloitte, Toptal. We derive the merchant's own
# scale tier and bias discovery toward same-sized peers instead of market incumbents.

# Category-dominating incumbents that saturate "best software/dev/consulting" listicles.
# Excluded from discovery when the merchant is sub-enterprise — a peer's own pages won't
# mention these names, so the exclusion is safe and only drops the giants.
_DEV_CONSULTING_INCUMBENTS = (
    "Accenture", "Deloitte", "IBM", "Infosys", "Cognizant", "Capgemini", "Wipro",
    "TCS", "McKinsey", "Thoughtworks", "EPAM", "Globant", "Toptal",
)

# Peer-size vocabulary keyed by (tier, archetype). Kept short (≤4 terms) so it biases
# ranking without diluting the keyword query that DuckDuckGo falls back to.
_PEER_TERMS: dict[tuple[str, str], str] = {
    ("micro", "service"): '"boutique" OR "independent" OR "freelance"',
    ("boutique", "service"): '"boutique" OR "independent" OR "small agency" OR "studio"',
    ("midmarket", "service"): '"mid-sized" OR "mid-market" OR "scale-up"',
    ("enterprise", "service"): '"leading" OR "enterprise" OR "global"',
    ("micro", "saas"): '"indie" OR "bootstrapped" OR "solo"',
    ("boutique", "saas"): '"startup" OR "indie" OR "emerging"',
    ("midmarket", "saas"): '"scale-up" OR "growth-stage" OR "mid-market"',
    ("enterprise", "saas"): '"leading" OR "enterprise"',
    ("micro", "ecommerce"): '"indie brand" OR "small brand"',
    ("boutique", "ecommerce"): '"indie brand" OR "small brand" OR "emerging brand"',
    ("midmarket", "ecommerce"): '"growing brand" OR "mid-size brand"',
    ("enterprise", "ecommerce"): '"major brand" OR "leading brand"',
    ("micro", "local"): '"independent" OR "local"',
    ("boutique", "local"): '"independent" OR "boutique" OR "local"',
    ("midmarket", "local"): '"regional" OR "multi-location"',
    ("enterprise", "local"): '"national" OR "chain"',
    ("micro", "other"): '"independent" OR "niche"',
    ("boutique", "other"): '"independent" OR "challenger"',
    ("midmarket", "other"): '"mid-market" OR "challenger"',
    ("enterprise", "other"): '"leading" OR "major"',
}

# Served-segment cues mined from the dossier, highest-focus first.
_SEGMENT_CUES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("startup", "early-stage", "early stage", "seed-stage"), '"for startups"'),
    (("small business", "smb", "small and medium", "small-and-medium"), '"for small business"'),
    (("mid-market", "mid market", "midmarket", "scale-up", "scaleup"), '"for mid-market"'),
    (("enterprise", "fortune 500", "large organization", "large enterprise"), '"for enterprises"'),
)

_TEAM_SIZE_PATTERNS = (
    r'(\d[\d,]*)\s*\+?\s*(?:employees|developers|engineers|designers|architects|'
    r'professionals|people|team members|staff|headcount|consultants|specialists|FTEs?)',
    r'team\s+of\s+(\d[\d,]*)',
)


@dataclass(frozen=True)
class ScaleSignals:
    """The merchant's own scale, used to anchor discovery to same-sized rivals."""

    tier: str  # "unknown" | "micro" | "boutique" | "midmarket" | "enterprise"
    archetype: str  # "service" | "saas" | "ecommerce" | "local" | "other"
    peer_terms: str  # OR-group of size qualifiers for the discovery query, or ""
    segment_clause: str  # served-segment anchor (OR-group), or ""
    exclude_terms: tuple[str, ...]  # incumbent names to negate in discovery


#: Pricing vocabulary per archetype. A services buyer searches for rates and retainers; a
#: shopper searches for discounts. Keyed by archetype so every stage agrees on which applies.
_PRICING_TERMS: dict[str, str] = {
    ARCH_SERVICE: 'pricing OR price OR rates OR fees OR retainer OR "cost"',
    ARCH_LOCAL: 'pricing OR price OR rates OR fees OR "cost" OR quote',
    ARCH_ECOMMERCE: "pricing OR price OR cost OR tiers OR discount",
    ARCH_CREATOR: "pricing OR price OR cost OR enrollment OR tuition",
    ARCH_SAAS: "pricing OR price OR cost OR tiers OR plans",
    ARCH_OTHER: "pricing OR price OR cost OR tiers OR plans",
}

#: Where this archetype's customers actually complain.
_GRIPE_DOMAINS: dict[str, tuple[str, ...]] = {
    ARCH_SERVICE: ("reddit.com", "trustpilot.com", "yelp.com", "bbb.org"),
    ARCH_LOCAL: ("reddit.com", "trustpilot.com", "yelp.com", "bbb.org"),
    ARCH_ECOMMERCE: ("reddit.com", "trustpilot.com", "sitejabber.com"),
    ARCH_CREATOR: ("reddit.com", "trustpilot.com", "quora.com"),
    ARCH_SAAS: ("reddit.com", "g2.com", "capterra.com"),
    ARCH_OTHER: ("reddit.com", "g2.com", "capterra.com"),
}


def _extract_team_size(dossier: str) -> int | None:
    best: int | None = None
    for pattern in _TEAM_SIZE_PATTERNS:
        for m in re.finditer(pattern, dossier, flags=re.IGNORECASE):
            n = int(m.group(1).replace(",", ""))
            best = n if best is None else max(best, n)
    return best


def _tier_from_team(team: int) -> str:
    if team < 15:
        return "micro"
    if team < 150:
        return "boutique"
    if team < 1500:
        return "midmarket"
    return "enterprise"


def _tier_from_service_price(price_usd: float) -> str:
    if price_usd < 100_000:
        return "boutique"
    if price_usd < 1_000_000:
        return "midmarket"
    return "enterprise"


def derive_scale_signals(merchant_context: dict[str, Any], context_str: str | None = None) -> ScaleSignals:
    """
    Infers the merchant's scale tier from the dossier's team size (most reliable) or,
    for service businesses, the entry price, then returns peer-size qualifiers, a
    served-segment anchor, and incumbent exclusions to keep discovery peer-scoped.
    Returns an inert ScaleSignals (tier="unknown", empty terms) when no scale signal is
    available, so query generation is unchanged for contexts we can't size.
    `context_str` is derived from category + business_model when not supplied.
    """
    if context_str is None:
        context_str = f"{merchant_context.get('category', '')} {merchant_context.get('business_model', '')}".lower()
    archetype = resolve_archetype(merchant_context, context_str)
    dossier = (merchant_context.get("dossier") or "")
    price_usd = merchant_context.get("price_usd")

    team = _extract_team_size(dossier) if dossier else None
    if team is not None:
        tier = _tier_from_team(team)
    elif isinstance(price_usd, (int, float)) and archetype == ARCH_SERVICE:
        tier = _tier_from_service_price(float(price_usd))
    else:
        tier = "unknown"

    if tier == "unknown":
        return ScaleSignals("unknown", archetype, "", "", ())

    peer_terms = _PEER_TERMS.get((tier, archetype), "")

    segment_matches: list[str] = []
    dossier_low = dossier.lower()
    for cues, clause in _SEGMENT_CUES:
        if any(cue in dossier_low for cue in cues):
            segment_matches.append(clause)
    segment_matches = segment_matches[:2]
    segment_clause = (
        f"({' OR '.join(segment_matches)})" if len(segment_matches) > 1
        else (segment_matches[0] if segment_matches else "")
    )

    exclude_terms: tuple[str, ...] = ()
    # Not an archetype question: a narrower check for whether the software/consulting
    # incumbent list is the right one to exclude for this merchant.
    is_dev_consulting = archetype in (ARCH_SERVICE, ARCH_SAAS) and any(
        kw in context_str for kw in ("software", "develop", "web", "app", "digital", "it ", "tech", "consult", "agency")
    )
    if tier != "enterprise" and is_dev_consulting:
        exclude_terms = _DEV_CONSULTING_INCUMBENTS

    return ScaleSignals(tier, archetype, peer_terms, segment_clause, exclude_terms)


def _apply_scale_to_discovery(query: str, scale: ScaleSignals) -> str:
    """Appends peer-size qualifiers, segment anchor, and incumbent exclusions to a discovery query."""
    if scale.peer_terms:
        query += f" {scale.peer_terms}"
    if scale.segment_clause:
        query += f" {scale.segment_clause}"
    for term in scale.exclude_terms:
        query += f' -"{term}"'
    return query


# Home domains of the excludable incumbents, for the deterministic post-search guard.
# Tavily is semantic and You.com/DuckDuckGo mangle long boolean queries, so the '-"name"'
# operators in the query are a soft hint at best — this list is the hard guarantee.
_INCUMBENT_DOMAINS = (
    "accenture.com", "deloitte.com", "ibm.com", "infosys.com", "cognizant.com",
    "capgemini.com", "wipro.com", "tcs.com", "mckinsey.com", "thoughtworks.com",
    "epam.com", "globant.com", "toptal.com",
)


def filter_out_of_scale_results(
    results: list[TavilySearchResult],
    scale: ScaleSignals,
) -> list[TavilySearchResult]:
    """
    Deterministically drops discovery results that point at mega-incumbents a sub-enterprise
    merchant does not compete with — by home domain, or by brand name appearing as a whole
    word in the title or URL (e.g. a 'clutch.co/profile/accenture' listing). Only the
    alternative_discovery vector is filtered: pricing/gripe/claims results for a named
    known_competitor are kept even if that competitor happens to be large.
    """
    if scale.tier in ("unknown", "enterprise") or not scale.exclude_terms:
        return results

    name_pattern = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in scale.exclude_terms) + r")\b",
        flags=re.IGNORECASE,
    )

    kept: list[TavilySearchResult] = []
    for r in results:
        if r.vector != "alternative_discovery":
            kept.append(r)
            continue
        url_low = (r.url or "").lower()
        if any(dom in url_low for dom in _INCUMBENT_DOMAINS):
            logger.debug("Dropping out-of-scale incumbent result: %s", r.url)
            continue
        if name_pattern.search(r.title or "") or name_pattern.search(url_low):
            logger.debug("Dropping out-of-scale incumbent result: %s", r.url)
            continue
        kept.append(r)
    return kept


def build_search_queries(
    merchant_context: dict[str, Any],
    taxonomy: DynamicParameterTaxonomy | None = None,
) -> list[SearchQuery]:
    """
    Decomposes merchant context and dynamic parameters into taxonomy-scoped search queries.
    Dynamically adapts search domains, pricing terminology, and location targeting
    for any campaign archetype (B2B SaaS, D2C eCommerce, Local Services, Creators, etc.).
    """
    current_year = _current_year()
    category = merchant_context.get("category", "")
    product_name = merchant_context.get("product_name", "")
    known_competitors = merchant_context.get("known_competitors", [])
    business_model = merchant_context.get("business_model", "")
    target_geography = merchant_context.get("target_geography", "")
    price_model = merchant_context.get("price_model", "")

    competitor_names = " OR ".join(f'"{c}"' for c in known_competitors) if known_competitors else ""
    context_str = f"{category} {business_model}".lower()
    archetype = resolve_archetype(merchant_context, context_str)

    pricing_terms = _PRICING_TERMS[archetype]
    if price_model:
        pricing_terms += f' OR "{price_model}"'

    gripe_domains = _GRIPE_DOMAINS[archetype]

    crit_keywords = ""
    if taxonomy and taxonomy.critical_jtbd_drivers:
        crit_keywords = " ".join(taxonomy.critical_jtbd_drivers[:3])

    geo_clause = f' "{target_geography}"' if target_geography else ""

    scale = derive_scale_signals(merchant_context, context_str)

    discovery_query = f'"{category}" alternative OR competitor OR "best {category}" OR "top {category}"'
    discovery_query = _apply_scale_to_discovery(discovery_query, scale)
    if crit_keywords:
        discovery_query += f" {crit_keywords}"
    discovery_query += f"{geo_clause} {current_year}"

    if competitor_names:
        pricing_query = f'"{product_name}" OR ({competitor_names}) {pricing_terms}'
    else:
        pricing_query = f'"{product_name}" {pricing_terms} "{category}"'

    if competitor_names:
        gripe_query = (
            f'site:reddit.com OR site:g2.com OR site:capterra.com '
            f'("{category}" OR ({competitor_names})) (complaint OR issue OR "wish it had" OR problem)'
        )
    else:
        gripe_query = (
            f'site:reddit.com OR site:g2.com OR site:capterra.com '
            f'"{category}" (complaint OR issue OR problem OR limitation)'
        )

    if competitor_names:
        claims_target = f'({competitor_names})'
    else:
        claims_target = f'"{product_name}"'
    claims_query = f'{claims_target} "{category}" (tagline OR slogan OR "value proposition" OR "why choose")'

    queries = [
        # Broadened discovery vector capturing alternatives, rivals, and top category picks
        SearchQuery(vector="alternative_discovery", query=discovery_query, time_range="year"),
        SearchQuery(vector="pricing_scrape", query=pricing_query, time_range="year"),
        # Complaints age well — an older thread is still valid evidence of a weakness.
        SearchQuery(
            vector="gripe_mining",
            query=gripe_query,
            include_domains=gripe_domains,
        ),
        SearchQuery(vector="messaging_claims", query=claims_query, time_range="year"),
    ]
    return queries


def build_missing_data_queries(
    merchant_context: dict[str, Any],
    competitors: list[CompetitorProfile],
    taxonomy: DynamicParameterTaxonomy,
    iteration: int,
) -> list[SearchQuery]:
    """
    Formulates targeted 'more data' search queries for missing competitor attributes,
    pricing models, or unverified claims across any business category.
    """
    current_year = _current_year()
    category = merchant_context.get("category", "")
    business_model = merchant_context.get("business_model", "")
    context_str = f"{category} {business_model}".lower()

    # Same resolver as the first round. These used to be a separate, shorter keyword list,
    # so a vet clinic asked for rates in round 1 and for its MSRP in round 2.
    archetype = resolve_archetype(merchant_context, context_str)
    price_keywords = _PRICING_TERMS[archetype]
    review_domains = _GRIPE_DOMAINS[archetype]

    queries: list[SearchQuery] = []

    # 1. Target rivals missing pricing model
    unpriced = [c.brand_name for c in competitors if not c.pricing_model or c.pricing_model == PLACEHOLDER_PRICING]
    if unpriced:
        brand_terms = " OR ".join(f'"{b}"' for b in unpriced[:3])
        queries.append(
            SearchQuery(
                vector="pricing_scrape",
                query=f'({brand_terms}) ({price_keywords}) "{category}"',
                time_range="year",
            )
        )

    # 2. Target rivals missing real user complaints/weaknesses
    missing_gripes = [c.brand_name for c in competitors if not c.weaknesses_mined]
    if missing_gripes:
        brand_terms = " OR ".join(f'"{b}"' for b in missing_gripes[:3])
        queries.append(
            SearchQuery(
                vector="gripe_mining",
                query=f'site:reddit.com OR site:g2.com ({brand_terms}) (complaint OR issue OR downside OR problem)',
                include_domains=review_domains,
            )
        )

    # 3. If under 4 competitors, discover additional market alternatives — kept peer-scoped
    #    so a thin result set isn't backfilled with out-of-scale incumbents.
    if len(competitors) < 4:
        scale = derive_scale_signals(merchant_context, context_str)
        discovery = _apply_scale_to_discovery(
            f'"best {category}" alternatives OR competitors comparison', scale
        )
        queries.append(
            SearchQuery(
                vector="alternative_discovery",
                query=f"{discovery} {current_year}",
                time_range="year",
            )
        )

    if not queries:
        return refine_queries_for_retry([], merchant_context, iteration)
    return queries


def refine_queries_for_retry(
    queries: list[SearchQuery],
    merchant_context: dict[str, Any],
    retry_number: int,
) -> list[SearchQuery]:
    """
    Broadens/adjusts search operators on DQS retry to improve data coverage.
    """
    current_year = _current_year()
    category = merchant_context.get("category", "")
    product_name = merchant_context.get("product_name", "")
    known_competitors = merchant_context.get("known_competitors", [])

    refined: list[SearchQuery] = []

    for q in queries:
        if retry_number >= 1 and q.vector == "gripe_mining":
            refined.append(
                SearchQuery(
                    vector="gripe_mining",
                    query=f'"{category}" OR "{product_name}" review OR complaint OR problem OR frustration',
                    include_domains=None,
                )
            )
        elif retry_number >= 2 and q.vector == "alternative_discovery":
            broader_category = category.split()[-1] if category else product_name
            # Broaden the category but keep the incumbent exclusions, so a wider net still
            # avoids re-surfacing the giants a boutique isn't competing with.
            context_str = f"{category} {merchant_context.get('business_model', '')}".lower()
            scale = derive_scale_signals(merchant_context, context_str)
            broadened = f'"best {broader_category}" OR "{broader_category} comparison" OR "{broader_category} vs"'
            for term in scale.exclude_terms:
                broadened += f' -"{term}"'
            refined.append(
                SearchQuery(
                    vector="alternative_discovery",
                    query=f"{broadened} {current_year}",
                )
            )
        elif retry_number >= 3 and q.vector == "pricing_scrape":
            comp_vs = " vs ".join(f'"{c}"' for c in known_competitors[:2]) if len(known_competitors) >= 2 else f'"{product_name}"'
            refined.append(
                SearchQuery(
                    vector="pricing_scrape",
                    query=f'{comp_vs} (price OR cost OR "how much" OR "pricing")',
                )
            )
        else:
            refined.append(q)

    return refined


YOU_SEARCH_ENDPOINT = "https://ydc-index.io/v1/search"


class YouSearchClient:
    """You.com Search API client (GET ydc-index.io/v1/search, X-API-Key header)."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.api_key = api_key if api_key is not None else get_settings().you_api_key
        self.timeout = timeout

    async def search(self, query: str, count: int = 10) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                YOU_SEARCH_ENDPOINT,
                params={"query": query, "count": count},
                headers={"X-API-Key": self.api_key},
            )
        response.raise_for_status()
        return response.json()


async def execute_you_search(
    queries: list[SearchQuery],
    you_client: Any,
) -> list[TavilySearchResult]:
    """Executes search queries against You.com in parallel, normalized to search results."""
    settings = get_settings()

    async def _search_one(query: SearchQuery) -> list[TavilySearchResult]:
        try:
            response = await you_client.search(_ddg_queries(query.query)[0], count=min(settings.tavily_max_results, 20))
        except Exception as exc:
            logger.warning("You.com search failed for vector=%s: %s", query.vector, exc)
            return []
        hits = (response.get("results") or {}).get("web") or []
        results = []
        for rank, hit in enumerate(hits):
            url = hit.get("url", "")
            if query.include_domains and not any(d in url for d in query.include_domains):
                continue
            snippet = " ".join(hit.get("snippets") or []) or hit.get("description", "")
            results.append(
                TavilySearchResult(
                    vector=query.vector,
                    title=hit.get("title", ""),
                    url=url,
                    snippet=snippet,
                    # You.com returns ranked results without a score; derive one from rank.
                    score=round(max(0.3, 0.75 - rank * 0.03), 3),
                    provider="you",
                )
            )
        return results

    batches = await asyncio.gather(*[_search_one(q) for q in queries])
    return [result for batch in batches for result in batch]


class DuckDuckGoSearchClient:
    """DuckDuckGo web search via the `ddgs` package (no API key). The library is sync, so calls run in a thread."""

    # DuckDuckGo rate limits bursts; keep only a couple of requests in flight.
    _MAX_CONCURRENT = 2

    # Shared by every client in the process (per event loop), so parallel subagents cannot burst.
    _semaphores: dict[int, asyncio.Semaphore] = {}

    def __init__(self, region: str | None = None) -> None:
        self.region = region or get_settings().duckduckgo_region

    @staticmethod
    def _ddgs_class() -> Any:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # older package name
        return DDGS

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        loop_id = id(asyncio.get_running_loop())
        semaphore = self._semaphores.get(loop_id)
        if semaphore is None:
            self._semaphores.clear()
            semaphore = self._semaphores[loop_id] = asyncio.Semaphore(self._MAX_CONCURRENT)
        ddgs_cls = self._ddgs_class()
        async with semaphore:
            return await asyncio.to_thread(
                lambda: list(ddgs_cls().text(query, region=self.region, max_results=max_results) or [])
            )


_DDG_OPERATORS = {"or", "and", "not"}
# Sponsored/tracking redirects some DuckDuckGo backends return; they are ads, not results.
_TRACKING_URL_MARKERS = ("bing.com/aclick", "duckduckgo.com/y.js", "googleadservices.com", "doubleclick.net")


def _ddg_queries(query: str) -> list[str]:
    """
    DuckDuckGo returns nothing for long boolean queries, so it gets plain keywords: no site:,
    OR/AND, quotes or parentheses, duplicates removed. A shorter variant is the retry.
    """
    words: list[str] = []
    for tok in re.sub(r'[()"]', " ", query).split():
        low = tok.lower()
        if low.startswith("site:") or low in _DDG_OPERATORS or low in {w.lower() for w in words}:
            continue
        words.append(tok)
    full = " ".join(words[:12])
    short = " ".join(words[:6])
    return [q for q in dict.fromkeys([full, short]) if q]


async def execute_duckduckgo_search(
    queries: list[SearchQuery],
    ddg_client: Any,
) -> list[TavilySearchResult]:
    """Executes search queries against DuckDuckGo, normalized to search results."""
    settings = get_settings()

    async def _search_one(query: SearchQuery) -> list[TavilySearchResult]:
        hits: list[dict[str, Any]] = []
        attempts = _ddg_queries(query.query)
        if query.include_domains and attempts:
            attempts = [f"{attempts[-1]} site:{query.include_domains[0]}"] + attempts
        for attempt in attempts:
            try:
                hits = await ddg_client.search(attempt, max_results=settings.duckduckgo_max_results)
            except Exception as exc:
                logger.info("DuckDuckGo search returned nothing for vector=%s (%r): %s", query.vector, attempt, exc)
                hits = []
            if hits:
                break
        if not hits:
            logger.warning("DuckDuckGo found no results for vector=%s", query.vector)
        results = []
        for rank, hit in enumerate(hits):
            url = hit.get("href") or hit.get("url") or ""
            if any(marker in url for marker in _TRACKING_URL_MARKERS):
                continue
            if query.include_domains and not any(d in url for d in query.include_domains):
                continue
            results.append(
                TavilySearchResult(
                    vector=query.vector,
                    title=hit.get("title", ""),
                    url=url,
                    snippet=hit.get("body", ""),
                    # DuckDuckGo results are ranked without a score; rank them below paid engines.
                    score=round(max(0.25, 0.6 - rank * 0.03), 3),
                    provider="duckduckgo",
                )
            )
        return results

    batches = await asyncio.gather(*[_search_one(q) for q in queries])
    return [result for batch in batches for result in batch]


def _merge(*result_lists: list[TavilySearchResult]) -> list[TavilySearchResult]:
    """Deduplicates per vector and URL, keeping the first (highest-priority engine) result."""
    merged: list[TavilySearchResult] = []
    seen: set[tuple[str, str]] = set()
    for results in result_lists:
        for r in results:
            key = (r.vector, r.url)
            if r.url and key not in seen:
                seen.add(key)
                merged.append(r)
    return merged


def _validated_queries(queries: list[SearchQuery]) -> list[SearchQuery]:
    """Repairs each query pre-flight and drops any that cannot be made searchable."""
    checked: list[SearchQuery] = []
    for q in queries:
        verdict = validate_search_query(q.query)
        if not verdict.ok:
            logger.warning(
                "Skipping unusable %s query (%s): %r", q.vector, verdict.summary, q.query
            )
            continue
        if verdict.repaired:
            logger.info("Repaired %s query (%s)", q.vector, verdict.summary)
            q = replace(q, query=verdict.query)
        checked.append(q)
    return checked


async def execute_tavily_search(
    queries: list[SearchQuery],
    tavily_client: Any = None,
    you_client: Any = None,
    ddg_client: Any = None,
) -> list[TavilySearchResult]:
    """
    Executes each query against Tavily and You.com in parallel, then DuckDuckGo as support:
    for queries where those engines fail or return fewer than `duckduckgo_min_results`
    (mode "fallback"), or for every query (mode "always"). Results are merged and
    deduplicated per vector and URL. Live clients are built only when none is injected.

    Every query is validated and repaired first, and one that cannot be made searchable is
    dropped rather than sent — a malformed query still costs a request and returns noise.
    """
    settings = get_settings()
    ddg_mode = settings.duckduckgo_mode.lower()

    queries = _validated_queries(queries)
    if not queries:
        return []

    if tavily_client is None:
        if you_client is None and settings.you_api_key:
            you_client = YouSearchClient()
        if ddg_client is None and ddg_mode != "off":
            ddg_client = DuckDuckGoSearchClient()
        if settings.tavily_api_key:
            try:
                from tavily import AsyncTavilyClient

                tavily_client = AsyncTavilyClient(api_key=settings.tavily_api_key)
            except ImportError:
                logger.error("tavily-python not installed — Tavily search unavailable")

    async def _one(query: SearchQuery) -> list[TavilySearchResult]:
        tavily_task = _execute_tavily_only([query], tavily_client) if tavily_client is not None else _empty()
        you_task = execute_you_search([query], you_client) if you_client is not None else _empty()
        primary = _merge(*(await asyncio.gather(tavily_task, you_task)))
        if ddg_client is None or ddg_mode == "off":
            return primary
        if ddg_mode == "always" or len(primary) < settings.duckduckgo_min_results:
            return _merge(primary, await execute_duckduckgo_search([query], ddg_client))
        return primary

    batches = await asyncio.gather(*[_one(q) for q in queries])
    return _merge(*batches)


async def _empty() -> list[TavilySearchResult]:
    return []


async def _execute_tavily_only(
    queries: list[SearchQuery],
    tavily_client: Any,
) -> list[TavilySearchResult]:
    """Executes search queries against Tavily in parallel."""
    settings = get_settings()

    async def _search_one(query: SearchQuery) -> list[TavilySearchResult]:
        try:
            search_kwargs: dict[str, Any] = {
                "query": query.query,
                "search_depth": query.search_depth,
                "max_results": settings.tavily_max_results,
            }
            if query.include_domains:
                search_kwargs["include_domains"] = list(query.include_domains)
            if query.time_range:
                search_kwargs["time_range"] = query.time_range

            try:
                response = await tavily_client.search(**search_kwargs)
            except TypeError:
                # Older tavily-python (or a stub client) may not accept time_range —
                # drop the recency hint rather than lose the whole query.
                search_kwargs.pop("time_range", None)
                response = await tavily_client.search(**search_kwargs)
            results = response.get("results", [])
            return [
                TavilySearchResult(
                    vector=query.vector,
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                    score=r.get("score", 0.0),
                    published_date=r.get("published_date"),
                )
                for r in results
            ]
        except Exception as exc:
            logger.warning("Tavily search failed for vector=%s: %s", query.vector, exc)
            return []

    batches = await asyncio.gather(*[_search_one(q) for q in queries])
    return [result for batch in batches for result in batch]
