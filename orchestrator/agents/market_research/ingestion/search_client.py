"""
Multi-vector search query generation, dynamic parameter keywords, and Tavily client integration.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar, Token
import logging
import re
from datetime import date
from dataclasses import asdict, dataclass, replace
from urllib.parse import urlparse
from typing import Any, Literal

from orchestrator.agents.market_research.intelligence.validation.scoring import PLACEHOLDER_PRICING
from orchestrator.agents.market_research.intelligence.advisory.archetype import (
    CREATOR as ARCH_CREATOR,
    ECOMMERCE as ARCH_ECOMMERCE,
    LOCAL as ARCH_LOCAL,
    OTHER as ARCH_OTHER,
    SAAS as ARCH_SAAS,
    SERVICE as ARCH_SERVICE,
    resolve as resolve_archetype,
)
from orchestrator.agents.market_research.ingestion.query_validator import validate_search_query
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


@dataclass(frozen=True)
class GeoSignals:
    """Where the merchant actually sells, used to keep discovery inside that market."""

    raw: str  # the merchant's stated target_geography, verbatim
    terms: tuple[str, ...]  # place names that mark a result as local ("delhi", "india", "ncr")
    cctlds: tuple[str, ...]  # country-code domains that mark a result as local (".in")
    strict: bool  # drop foreign results outright, rather than only demote them


#: Country-code TLDs and the place words that imply them. Only entries where a ccTLD is a
#: reliable signal of serving that market; ".co" and ".io" are generic and deliberately absent.
_GEO_TLDS: dict[str, tuple[str, ...]] = {
    "india": (".in", ".co.in"),
    "united kingdom": (".uk", ".co.uk"),
    "uk": (".uk", ".co.uk"),
    "australia": (".au", ".com.au"),
    "canada": (".ca",),
    "germany": (".de",),
    "france": (".fr",),
    "singapore": (".sg",),
    "united arab emirates": (".ae",),
    "uae": (".ae",),
    "japan": (".jp", ".co.jp"),
    "brazil": (".br", ".com.br"),
    "netherlands": (".nl",),
    "spain": (".es",),
    "italy": (".it",),
    "south africa": (".za", ".co.za"),
    "new zealand": (".nz", ".co.nz"),
}

#: Major cities mapped to the country they sit in, so "Delhi" also accepts "India" and ".in".
_CITY_COUNTRY: dict[str, str] = {
    "delhi": "india", "new delhi": "india", "noida": "india", "gurgaon": "india",
    "gurugram": "india", "mumbai": "india", "bangalore": "india", "bengaluru": "india",
    "hyderabad": "india", "chennai": "india", "pune": "india", "kolkata": "india",
    "ahmedabad": "india", "jaipur": "india",
    "london": "united kingdom", "manchester": "united kingdom", "birmingham": "united kingdom",
    "sydney": "australia", "melbourne": "australia",
    "toronto": "canada", "vancouver": "canada",
    "dubai": "united arab emirates", "abu dhabi": "united arab emirates",
    "berlin": "germany", "munich": "germany", "paris": "france",
    "singapore": "singapore", "tokyo": "japan", "amsterdam": "netherlands",
}

#: Place words that mark a result as serving somewhere else. Used only to detect a conflict,
#: never on their own: a page naming a foreign city is dropped only when it names no target one.
_FOREIGN_MARKERS: tuple[str, ...] = (
    "new york", "nyc", "san francisco", "los angeles", "chicago", "boston", "seattle",
    "austin", "miami", "denver", "atlanta", "dallas", "houston", "toronto", "vancouver",
    "london", "manchester", "dublin", "berlin", "munich", "paris", "amsterdam", "madrid",
    "barcelona", "milan", "stockholm", "zurich", "sydney", "melbourne", "auckland",
    "singapore", "dubai", "tokyo", "hong kong", "shanghai", "sao paulo",
    "delhi", "new delhi", "mumbai", "bangalore", "bengaluru", "hyderabad", "chennai",
    "pune", "kolkata", "noida", "gurgaon", "gurugram",
)


def derive_geo_signals(
    merchant_context: dict[str, Any], archetype: str | None = None
) -> GeoSignals:
    """
    Reads the merchant's target market into something discovery can filter on.

    `target_geography` was only ever pasted into the discovery query as a quoted keyword, and
    semantic search engines treat that as a hint rather than a constraint -- which is how a
    merchant selling in Delhi ends up with New York and London rivals. This produces the terms
    a deterministic post-filter can check instead.

    Strictness follows the archetype: a local trade or an agency competes inside its city, so
    a foreign result is simply wrong. Software and e-commerce routinely cross borders, so there
    the same signal only demotes a result rather than removing it.
    """
    raw = str(merchant_context.get("target_geography") or "").strip()
    if not raw:
        return GeoSignals(raw="", terms=(), cctlds=(), strict=False)

    lowered = raw.lower()
    # "Delhi NCR, India" -> each part is a usable match term.
    parts = [p.strip() for p in re.split(r"[,/|&]| and ", lowered) if p.strip()]
    terms: list[str] = []
    cctlds: list[str] = []

    for part in parts:
        if part not in terms:
            terms.append(part)
        country = _CITY_COUNTRY.get(part)
        if country:
            if country not in terms:
                terms.append(country)
            cctlds.extend(_GEO_TLDS.get(country, ()))
        cctlds.extend(_GEO_TLDS.get(part, ()))

    if archetype is None:
        archetype = resolve_archetype(merchant_context, f"{merchant_context.get('category','')}".lower())

    # Global / worldwide targets are not a location constraint at all.
    if any(t in ("global", "worldwide", "international", "anywhere") for t in terms):
        return GeoSignals(raw=raw, terms=(), cctlds=(), strict=False)

    return GeoSignals(
        raw=raw,
        terms=tuple(dict.fromkeys(terms)),
        cctlds=tuple(dict.fromkeys(cctlds)),
        # A product sold in one country competes with what is on sale there; software does not.
        strict=archetype in (ARCH_LOCAL, ARCH_SERVICE, ARCH_ECOMMERCE),
    )


# ── Search market ──────────────────────────────────────────────────────────────
# Engines rank for the searcher's country, and with no country given they default to the US:
# an India run got US shoe stores. The run's market is set once (set_search_market) and every
# engine call reads it, so no call site has to thread it through.

#: country name -> (ISO code, Tavily country name, DuckDuckGo region)
_MARKETS: dict[str, tuple[str, str, str]] = {
    "india": ("IN", "india", "in-en"),
    "united states": ("US", "united states", "us-en"),
    "usa": ("US", "united states", "us-en"),
    "united kingdom": ("GB", "united kingdom", "uk-en"),
    "uk": ("GB", "united kingdom", "uk-en"),
    "australia": ("AU", "australia", "au-en"),
    "canada": ("CA", "canada", "ca-en"),
    "germany": ("DE", "germany", "de-de"),
    "france": ("FR", "france", "fr-fr"),
    "singapore": ("SG", "singapore", "sg-en"),
    "united arab emirates": ("AE", "united arab emirates", "xa-en"),
    "uae": ("AE", "united arab emirates", "xa-en"),
    "japan": ("JP", "japan", "jp-jp"),
    "brazil": ("BR", "brazil", "br-pt"),
    "netherlands": ("NL", "netherlands", "nl-nl"),
    "spain": ("ES", "spain", "es-es"),
    "italy": ("IT", "italy", "it-it"),
    "south africa": ("ZA", "south africa", "za-en"),
    "new zealand": ("NZ", "new zealand", "nz-en"),
}
_CURRENCY_MARKET = {"INR": "india", "GBP": "united kingdom", "AED": "united arab emirates", "AUD": "australia",
                    "CAD": "canada", "SGD": "singapore", "JPY": "japan", "BRL": "brazil", "ZAR": "south africa",
                    "NZD": "new zealand"}

_search_market: ContextVar[tuple[str, str, str] | None] = ContextVar("search_market", default=None)


def market_for(merchant_context: dict[str, Any] | None) -> tuple[str, str, str] | None:
    """(ISO code, Tavily country, DDG region) for the merchant's target market; None when global/unknown."""
    ctx = merchant_context or {}
    raw = str(ctx.get("target_geography") or "").lower()
    if any(w in raw for w in ("global", "worldwide", "international")):
        return None
    parts = [p.strip() for p in re.split(r"[,/|&]| and ", raw) if p.strip()]
    for part in reversed(parts):  # "Delhi NCR, India": the country is usually last
        country = _CITY_COUNTRY.get(part, part)
        if country in _MARKETS:
            return _MARKETS[country]
    for part in parts:
        for name, market in _MARKETS.items():
            if re.search(rf"\b{re.escape(name)}\b", part):
                return market
        for city, country in _CITY_COUNTRY.items():
            if city in part:
                return _MARKETS.get(country)
    currency = str(ctx.get("currency") or "").upper()
    return _MARKETS.get(_CURRENCY_MARKET.get(currency, ""))


def set_search_market(merchant_context: dict[str, Any] | None) -> Token:
    """Pins every search in the current task (and tasks it starts) to the merchant's market."""
    return _search_market.set(market_for(merchant_context))


def reset_search_market(token: Token) -> None:
    _search_market.reset(token)


def current_search_market() -> tuple[str, str, str] | None:
    return _search_market.get()


def filter_out_of_area_results(
    results: list[TavilySearchResult],
    geo: GeoSignals,
) -> list[TavilySearchResult]:
    """
    Drops discovery results that clearly serve a different market than the merchant's.

    A result is removed only when it names a foreign place and names none of the merchant's own
    -- an explicit conflict. A page with no location signal at all is kept, because most company
    sites never state one and dropping them would gut recall to buy a little precision.

    Geography is judged on the discovery vector, since that is where a rival is proposed. Other
    vectors are then dropped only for hosts discovery rejected -- without that, a competitor
    removed as out-of-area walks straight back in through its own pricing page, because
    `extract_preliminary_competitors` reads every vector, not just discovery.
    """
    if not geo.strict or not geo.terms:
        return results

    local_pattern = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in geo.terms) + r")\b", flags=re.IGNORECASE
    )
    foreign = tuple(f for f in _FOREIGN_MARKERS if f not in geo.terms)
    if not foreign:
        return results
    foreign_pattern = re.compile(
        r"\b(" + "|".join(re.escape(f) for f in foreign) + r")\b", flags=re.IGNORECASE
    )

    def _host(url: str) -> str:
        try:
            return (urlparse(url).hostname or "").removeprefix("www.").lower()
        except Exception:
            return ""

    kept: list[TavilySearchResult] = []
    rejected_hosts: set[str] = set()

    for r in results:
        if r.vector != "alternative_discovery":
            continue

        haystack = f"{r.title} {r.snippet} {r.url}"
        host = _host(r.url)

        if geo.cctlds and host.endswith(tuple(geo.cctlds)):
            kept.append(r)  # a local ccTLD settles it
        elif local_pattern.search(haystack):
            kept.append(r)
        elif foreign_pattern.search(haystack):
            logger.debug("Geo filter dropped out-of-area result: %s", r.url)
            if host:
                rejected_hosts.add(host)
        else:
            kept.append(r)  # no location signal either way: keep

    # A host discovery accepted anywhere stays accepted: one listicle naming a foreign city
    # must not disqualify a competitor another result placed locally.
    accepted_hosts = {_host(r.url) for r in kept}
    rejected_hosts -= accepted_hosts

    for r in results:
        if r.vector == "alternative_discovery":
            continue
        if _host(r.url) in rejected_hosts:
            logger.debug("Geo filter dropped %s evidence for rejected host: %s", r.vector, r.url)
            continue
        kept.append(r)

    return kept


#: Pricing vocabulary per archetype. A services buyer searches for rates and retainers; a
#: shopper searches for discounts. Keyed by archetype so every stage agrees on which applies.
_PRICING_TERMS: dict[str, str] = {
    ARCH_SERVICE: 'pricing OR price OR rates OR fees OR retainer OR "cost"',
    ARCH_LOCAL: 'pricing OR price OR rates OR fees OR "cost" OR quote',
    ARCH_ECOMMERCE: 'price OR "MRP" OR "MSRP" OR cost OR "buy" OR "shop" OR discount OR "free shipping" OR "$"',
    ARCH_CREATOR: "pricing OR price OR cost OR enrollment OR tuition",
    ARCH_SAAS: "pricing OR price OR cost OR tiers OR plans",
    ARCH_OTHER: 'pricing OR price OR cost OR "MSRP" OR tiers OR plans OR "$"',
}

#: Where this archetype's customers actually complain.
# Listed from most-signal to least: the primary query targets the first 3; the
# category-level fallback query (used when competitor-specific search returns nothing)
# targets the full tuple so there's always somewhere to look.
_GRIPE_DOMAINS: dict[str, tuple[str, ...]] = {
    ARCH_SERVICE: ("reddit.com", "trustpilot.com", "yelp.com", "bbb.org", "sitejabber.com", "quora.com"),
    ARCH_LOCAL: ("reddit.com", "trustpilot.com", "yelp.com", "bbb.org", "sitejabber.com"),
    ARCH_ECOMMERCE: ("reddit.com", "trustpilot.com", "sitejabber.com", "quora.com", "amazon.com"),
    ARCH_CREATOR: ("reddit.com", "trustpilot.com", "quora.com", "sitejabber.com", "g2.com"),
    ARCH_SAAS: ("reddit.com", "g2.com", "capterra.com", "trustpilot.com", "trustradius.com", "getapp.com"),
    ARCH_OTHER: ("reddit.com", "g2.com", "capterra.com", "trustpilot.com", "trustradius.com"),
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


_RECENCY_HALF_LIFE_DAYS = 180
# ponytail: an undated page is scored as if ~3 months old — ranks below anything provably
# newer, above anything provably older. Upgrade path: fetch the page's own date meta.
_UNDATED_AGE_DAYS = 90


def rank_by_recency(
    results: list[TavilySearchResult],
    *,
    max_age_days: int,
    today: date | None = None,
) -> list[TavilySearchResult]:
    """
    Weights each result's score by how close its publication date is to today and returns
    them newest-weighted first. A result the search provider itself dates older than
    `max_age_days` is dropped. Dates guessed from snippet text only lower the rank, never
    drop: a snippet saying "since 2019" is not a 2019 page.
    """
    from orchestrator.agents.market_research.intelligence.validation.freshness import (
        extract_publication_date,
        parse_iso_date,
    )
    from orchestrator.core.clock import today as clock_today

    ref = today or clock_today()
    kept: list[TavilySearchResult] = []
    for r in results:
        provider_date = parse_iso_date(r.published_date)
        if provider_date and (ref - provider_date).days > max_age_days:
            logger.debug("Dropping stale result (%s): %s", provider_date, r.url)
            continue
        dated = provider_date or extract_publication_date(f"{r.title} {r.snippet}")
        age = max(0, (ref - dated).days) if dated else _UNDATED_AGE_DAYS
        r.score = round(r.score * 0.5 ** (age / _RECENCY_HALF_LIFE_DAYS), 4)
        kept.append(r)
    kept.sort(key=lambda r: r.score, reverse=True)
    return kept


_ARCHETYPE_CATEGORY_FALLBACKS: dict[str, str] = {
    ARCH_SAAS: "B2B SaaS Software",
    ARCH_SERVICE: "Professional Services Agency",
    ARCH_LOCAL: "Local Services",
    ARCH_ECOMMERCE: "E-commerce Retail",
    ARCH_CREATOR: "Creator & Online Training",
    ARCH_OTHER: "B2B Services",
}

_CONVERSATIONAL_STOPWORDS = {
    "i", "want", "to", "my", "we", "our", "me", "us", "more", "how", "help", "need",
    "and", "the", "a", "an", "for", "in", "of", "with", "so", "can", "am", "is", "are",
}


def _clean_search_category(category: str, archetype: str) -> str:
    """
    Sanitizes category token for search queries so conversational phrases
    are never quoted verbatim in search engines.
    """
    clean = (category.strip() or "").strip()
    if not clean:
        return _ARCHETYPE_CATEGORY_FALLBACKS.get(archetype, "B2B Services")
    from orchestrator.agents.market_research.intelligence.market_mapping.classification import is_conversational_statement

    if is_conversational_statement(clean):
        words = clean.split()
        filtered = [w for w in words if w.lower().strip(".,!?;:") not in _CONVERSATIONAL_STOPWORDS]
        if len(filtered) >= 2:
            return " ".join(filtered[:4])
        return _ARCHETYPE_CATEGORY_FALLBACKS.get(archetype, "Professional Services Agency")
    return clean


def _clean_search_product(product_name: str, fallback_category: str) -> str:
    """Sanitizes product name so sentences are not quoted verbatim."""
    prod = (product_name or "").strip()
    if not prod:
        return fallback_category
    from orchestrator.agents.market_research.intelligence.market_mapping.classification import is_conversational_statement

    if is_conversational_statement(prod):
        return fallback_category
    return prod


def build_search_queries(
    merchant_context: dict[str, Any],
    taxonomy: DynamicParameterTaxonomy | None = None,
    time_range_override: str | None = None,
    include_leap: bool = False,
) -> list[SearchQuery]:
    """
    Decomposes merchant context and dynamic parameters into taxonomy-scoped search queries.
    Dynamically adapts search domains, pricing terminology, and location targeting
    for any campaign archetype (B2B SaaS, D2C eCommerce, Local Services, Creators, etc.).
    """
    current_year = _current_year()
    raw_category = merchant_context.get("category", "")
    raw_product_name = merchant_context.get("product_name", "")
    known_competitors = merchant_context.get("known_competitors", [])
    business_model = merchant_context.get("business_model", "")
    target_geography = merchant_context.get("target_geography", "")
    price_model = merchant_context.get("price_model", "")

    competitor_names = " OR ".join(f'"{c}"' for c in known_competitors) if known_competitors else ""
    context_str = f"{raw_category} {business_model}".lower()
    archetype = resolve_archetype(merchant_context, context_str)

    category = _clean_search_category(raw_category, archetype)
    product_name = _clean_search_product(raw_product_name, category)

    pricing_terms = _PRICING_TERMS[archetype]
    if price_model:
        pricing_terms += f' OR "{price_model}"'

    gripe_domains = _GRIPE_DOMAINS[archetype]

    crit_keywords = ""
    if taxonomy and taxonomy.critical_jtbd_drivers:
        crit_keywords = " ".join(taxonomy.critical_jtbd_drivers[:3])

    # A quoted place name is a hint, not a constraint -- semantic engines routinely ignore it,
    # which is why filter_out_of_area_results exists. The clause still helps steer the engine,
    # so it is kept and now also applied to the gripe and claims vectors, where a local
    # merchant's rivals are discussed in local forums and local press.
    geo_clause = f' "{target_geography}"' if target_geography else ""

    scale = derive_scale_signals(merchant_context, context_str)

    discovery_query = f'"{category}" alternative OR competitor OR "best {category}" OR "top {category}"'
    discovery_query = _apply_scale_to_discovery(discovery_query, scale)
    if crit_keywords:
        discovery_query += f" {crit_keywords}"
    discovery_query += f"{geo_clause} {current_year}"

    if competitor_names:
        pricing_query = f'({competitor_names}) (inurl:pricing OR inurl:rates OR inurl:plans OR inurl:cost OR {pricing_terms})'
    else:
        pricing_query = f'"{category}" (inurl:pricing OR inurl:rates OR inurl:plans OR inurl:cost OR {pricing_terms})'

    # Build site: filter from the first 4 gripe domains so the query covers more
    # platforms without going over the engine's operator budget.
    gripe_site_filter = " OR ".join(f"site:{d}" for d in gripe_domains[:4])
    if competitor_names:
        gripe_query = (
            f'({gripe_site_filter}) '
            f'("{category}" OR ({competitor_names})) (complaint OR issue OR "wish it had" OR problem OR negative)'
        )
    else:
        gripe_query = (
            f'({gripe_site_filter}) '
            f'"{category}" (complaint OR issue OR problem OR limitation OR negative review){geo_clause}'
        )

    if competitor_names:
        claims_target = f'({competitor_names})'
    else:
        claims_target = f'"{category}"'
    claims_query = f'{claims_target} (tagline OR slogan OR "value proposition" OR "why choose"){geo_clause}'

    # Update runs override time_range to "month" so only recent changes are fetched.
    tr_discovery = time_range_override or "year"
    tr_pricing = time_range_override or "year"
    tr_claims = time_range_override or "year"

    queries = [
        # Broad discovery only needs names and URLs; "basic" is half the credits of "advanced".
        SearchQuery(
            vector="alternative_discovery",
            query=discovery_query,
            search_depth="basic",
            time_range=tr_discovery,
        ),
        SearchQuery(vector="pricing_scrape", query=pricing_query, time_range=tr_pricing),
        # A complaint about a product as it was two years ago may already be fixed.
        SearchQuery(
            vector="gripe_mining",
            query=gripe_query,
            include_domains=gripe_domains,
            time_range=time_range_override or "year",
        ),
        SearchQuery(vector="messaging_claims", query=claims_query, time_range=tr_claims),
    ]

    # For e-commerce and physical product companies, search where they are selling, at what cost,
    # sales velocity, and observable buying patterns (Amazon/D2C channels, best-sellers, return policies).
    if archetype == ARCH_ECOMMERCE:
        channel_target = f'({competitor_names})' if competitor_names else f'"{category}"'
        pattern_query = (
            f'{channel_target} ("best seller" OR "Amazon" OR "store" OR "free shipping" OR '
            f'"discount" OR "return policy" OR "bought in past month" OR "customer reviews" OR '
            f'"warranty" OR "sizing"){geo_clause}'
        )
        queries.append(
            SearchQuery(
                vector="buying_patterns_channels",
                query=pattern_query,
                time_range=time_range_override or "year",
            )
        )
    if include_leap:
        leap_terms = '("successful" OR "market leader" OR "case studies" OR "enterprise clients" OR "portfolio" OR "trusted by" OR "client roster")'
        queries.append(
            SearchQuery(
                vector="leap_discovery",
                query=f'"{category}" {leap_terms}{geo_clause}',
                search_depth="basic",
                time_range=time_range_override or "year",
            )
        )
        if competitor_names:
            queries.append(
                SearchQuery(
                    vector="leap_history",
                    query=f'({competitor_names}) ("founded" OR "milestones" OR "growth" OR "funding" OR "timeline" OR "revenue")',
                    time_range=time_range_override or "year",
                )
            )
    return queries


def _web_name(brand: str) -> str:
    """The name a rival is written as on the web: "Table XI (TXI)" searches as "Table XI"."""
    from orchestrator.agents.market_research.ingestion.source_types import search_names

    names = search_names(brand)
    return names[0] if names else brand


def build_missing_data_queries(
    merchant_context: dict[str, Any],
    competitors: list[CompetitorProfile],
    taxonomy: DynamicParameterTaxonomy | None,
    iteration: int,
) -> list[SearchQuery]:
    """
    Formulates targeted 'more data' search queries for missing competitor attributes,
    pricing models, or unverified claims across any business category.
    """
    current_year = _current_year()
    raw_category = merchant_context.get("category", "")
    business_model = merchant_context.get("business_model", "")
    context_str = f"{raw_category} {business_model}".lower()

    # Same resolver as the first round. These used to be a separate, shorter keyword list,
    # so a vet clinic asked for rates in round 1 and for its MSRP in round 2.
    archetype = resolve_archetype(merchant_context, context_str)
    category = _clean_search_category(raw_category, archetype)
    price_keywords = _PRICING_TERMS[archetype]
    review_domains = _GRIPE_DOMAINS[archetype]

    queries: list[SearchQuery] = []

    # 1. Target rivals missing pricing model using deterministic operator tiering
    unpriced_comps = [c for c in competitors if not c.pricing_model or c.pricing_model == PLACEHOLDER_PRICING]
    all_gripe_site_filter = " OR ".join(f"site:{d}" for d in review_domains)

    for comp in unpriced_comps[:4]:
        w_brand = _web_name(comp.brand_name)
        prod = comp.product_name if comp.product_name and comp.product_name != "Product" else comp.brand_name

        if iteration <= 1:
            # Round 1: Direct official inurl operator targeting and canonical price keywords
            queries.append(
                SearchQuery(
                    vector="pricing_scrape",
                    query=f'"{w_brand}" (inurl:pricing OR inurl:rates OR inurl:plans OR inurl:cost OR inurl:fees)',
                    time_range="year",
                )
            )
            queries.append(
                SearchQuery(
                    vector="pricing_scrape",
                    query=f'"{w_brand}" "{prod}" ({price_keywords})',
                    time_range="year",
                )
            )
        elif iteration == 2:
            # Round 2: Secondary community triangulation & forum pricing leaks (Reddit, G2, Trustpilot)
            queries.append(
                SearchQuery(
                    vector="pricing_scrape",
                    query=f'({all_gripe_site_filter}) "{w_brand}" ("pricing" OR "cost" OR "quote" OR "quoted" OR "per month" OR "$")',
                    include_domains=review_domains,
                    time_range="year",
                )
            )
            queries.append(
                SearchQuery(
                    vector="pricing_scrape",
                    query=f'({all_gripe_site_filter}) "{w_brand}" ("how much" OR "expensive" OR "worth the money" OR "renewal")',
                    include_domains=review_domains,
                    time_range="year",
                )
            )
        else:
            # Round 3+: Head-to-head comparison and peer triangulation displacement queries
            queries.append(
                SearchQuery(
                    vector="pricing_scrape",
                    query=f'"{w_brand}" vs ("cost" OR "pricing" OR "rates" OR "quote" OR "cheaper alternative")',
                    time_range="year",
                )
            )
            queries.append(
                SearchQuery(
                    vector="pricing_scrape",
                    query=f'"{w_brand}" ("rate card" OR "project estimate" OR "pricing breakdown" OR "average cost")',
                    time_range="year",
                )
            )

    # 2. Target rivals missing real user complaints/weaknesses with progressive depth
    missing_gripes = [c for c in competitors if not c.weaknesses_mined]
    for comp in missing_gripes[:3]:
        w_brand = _web_name(comp.brand_name)
        prod = comp.product_name if comp.product_name and comp.product_name != "Product" else comp.brand_name
        if iteration <= 1:
            queries.append(
                SearchQuery(
                    vector="gripe_mining",
                    query=f'({all_gripe_site_filter}) "{w_brand}" "{prod}" (complaint OR issue OR downside OR problem OR "not worth" OR "bad experience" OR negative)',
                    include_domains=review_domains,
                )
            )
        else:
            queries.append(
                SearchQuery(
                    vector="gripe_mining",
                    query=f'({all_gripe_site_filter}) "{w_brand}" ("switched from" OR "cancelled" OR "regret" OR "frustrated" OR "poor support" OR "hidden fee")',
                    include_domains=review_domains,
                )
            )

    # Category-level fallback: when brand has no reviews at all, look for what
    # customers dislike about the category in general — still useful signal.
    if missing_gripes:
        queries.append(
            SearchQuery(
                vector="gripe_mining",
                query=f'({all_gripe_site_filter}) "{category}" (worst OR limitation OR problem OR "switching from" OR "alternative to")',
                include_domains=review_domains,
            )
        )

    # 3. Target rivals missing core claims, specs or evidence
    missing_specs = [c for c in competitors if not c.core_claims or not c.factual_evidence]
    for comp in missing_specs[:3]:
        w_brand = _web_name(comp.brand_name)
        prod = comp.product_name if comp.product_name and comp.product_name != "Product" else comp.brand_name
        queries.append(
            SearchQuery(
                vector="messaging_claims",
                query=f'"{w_brand}" (inurl:features OR inurl:capabilities OR inurl:about OR inurl:overview OR "why choose")',
                time_range="year",
            )
        )
        queries.append(
            SearchQuery(
                vector="messaging_claims",
                query=f'"{w_brand}" "{prod}" (features OR specifications OR specs OR capabilities OR "what is")',
                time_range="year",
            )
        )

    # 4. If under 5 competitors, discover additional market alternatives — kept peer-scoped
    #    so a thin result set isn't backfilled with out-of-scale incumbents.
    if len(competitors) < 5:
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

    # 5. Target rivals missing growth trajectory, milestones, founding, or scale history
    missing_growth = [c for c in competitors if not c.leap_benchmark and (not c.milestones or not c.founded)]
    for comp in missing_growth[:3]:
        w_brand = _web_name(comp.brand_name)
        queries.append(
            SearchQuery(
                vector="leap_history",
                query=f'"{w_brand}" ("founded" OR "history" OR "milestones" OR "growth" OR "revenue" OR "funding" OR "team size" OR "clients")',
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
    raw_category = merchant_context.get("category", "")
    raw_product_name = merchant_context.get("product_name", "")
    known_competitors = merchant_context.get("known_competitors", [])

    context_str = f"{raw_category} {merchant_context.get('business_model', '')}".lower()
    archetype = resolve_archetype(merchant_context, context_str)
    category = _clean_search_category(raw_category, archetype)
    product_name = _clean_search_product(raw_product_name, category)

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


class SearchCircuitBreaker:
    """
    Circuit breaker for external search APIs.

    Tracks failure counts per search provider ('tavily', 'you', 'duckduckgo').
    If a provider fails twice (max_failures=2 by default), it is marked as tripped/disabled.
    Further queries bypass that provider and are distributed among remaining working providers.
    """

    def __init__(self, max_failures: int | None = None) -> None:
        if max_failures is None:
            try:
                max_failures = get_settings().search_circuit_breaker_max_failures
            except Exception:
                max_failures = 2
        self.max_failures = max_failures
        self._failures: dict[str, int] = {}
        self._tripped: set[str] = set()

    def record_failure(self, provider: str, exc: Exception | None = None) -> int:
        count = self._failures.get(provider, 0) + 1
        self._failures[provider] = count
        if count >= self.max_failures:
            if provider not in self._tripped:
                self._tripped.add(provider)
                logger.warning(
                    "[CIRCUIT_BREAKER] Search API '%s' failed %d times (reason: %s); "
                    "tripping circuit breaker and redistributing queries to working providers.",
                    provider,
                    count,
                    exc or "unknown error",
                )
        else:
            logger.warning(
                "[CIRCUIT_BREAKER] Search API '%s' failure %d/%d (reason: %s)",
                provider,
                count,
                self.max_failures,
                exc or "unknown error",
            )
        return count

    def record_success(self, provider: str) -> None:
        if provider not in self._tripped:
            self._failures[provider] = 0

    def is_available(self, provider: str) -> bool:
        return provider not in self._tripped

    def get_failures(self, provider: str) -> int:
        return self._failures.get(provider, 0)

    def is_tripped(self, provider: str) -> bool:
        return provider in self._tripped

    def get_tripped_providers(self) -> set[str]:
        return set(self._tripped)

    def reset(self) -> None:
        self._failures.clear()
        self._tripped.clear()


_SEARCH_CIRCUIT_BREAKER = SearchCircuitBreaker()


def get_search_circuit_breaker() -> SearchCircuitBreaker:
    return _SEARCH_CIRCUIT_BREAKER


_KEY_NOISE = re.compile(r'["()]')
# Vectors whose answers move week to week; never reused across runs.
_VOLATILE_VECTORS = {"pricing_scrape", "buying_patterns_channels", "channel_listings"}


def query_key(query: SearchQuery) -> str:
    """
    Normalized identity of a search: case, quotes, parentheses and term order are ignored, so
    near-duplicates ("A OR B" vs "b or a") from retry and gap rounds share one engine call.
    """
    terms = sorted(set(_KEY_NOISE.sub(" ", query.query.lower()).split()))
    domains = ",".join(sorted(query.include_domains or ()))
    market = current_search_market()
    return f"{' '.join(terms)}|{query.time_range or ''}|{domains}|{query.search_depth}|{market[0] if market else ''}"


def _as_vector(results: list[TavilySearchResult], vector: str) -> list[TavilySearchResult]:
    return [r if r.vector == vector else replace(r, vector=vector) for r in results]


def _cacheable_across_runs(query: SearchQuery) -> bool:
    return query.time_range not in ("day", "week", "month") and query.vector not in _VOLATILE_VECTORS


class SearchSessionCache:
    """
    Session-level in-memory cache for search queries across parallel subagents.
    Prevents redundant external search API calls for identical query and time_range.
    """

    def __init__(self, max_size: int = 500) -> None:
        self.max_size = max_size
        self._cache: dict[str, list[TavilySearchResult]] = {}

    def get(self, query: SearchQuery) -> list[TavilySearchResult] | None:
        results = self._cache.get(query_key(query))
        if results is not None:
            return [replace(r, vector=query.vector) for r in results]
        return None

    def set(self, query: SearchQuery, results: list[TavilySearchResult]) -> None:
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache), None)
            if oldest_key:
                self._cache.pop(oldest_key, None)
        self._cache[query_key(query)] = list(results)

    def clear(self) -> None:
        self._cache.clear()


_SEARCH_CACHE = SearchSessionCache()


def get_search_session_cache() -> SearchSessionCache:
    return _SEARCH_CACHE


_engine_semaphores: dict[tuple[str, int], asyncio.Semaphore] = {}


def _engine_semaphore(engine: str, limit: int) -> asyncio.Semaphore:
    """Per-loop cap on in-flight requests to one paid engine."""
    key = (engine, id(asyncio.get_running_loop()))
    sem = _engine_semaphores.get(key)
    if sem is None:
        sem = _engine_semaphores[key] = asyncio.Semaphore(max(limit, 1))
    return sem


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
                params={"query": query, "count": count, **({"country": m[0]} if (m := current_search_market()) else {})},
                headers={"X-API-Key": self.api_key},
            )
        response.raise_for_status()
        return response.json()


async def execute_you_search(
    queries: list[SearchQuery],
    you_client: Any,
    circuit_breaker: SearchCircuitBreaker | None = None,
) -> list[TavilySearchResult]:
    """Executes search queries against You.com in parallel, normalized to search results."""
    cb = circuit_breaker or get_search_circuit_breaker()
    if not cb.is_available("you"):
        logger.info("[CIRCUIT_BREAKER] You.com search API is disabled; skipping search.")
        return []

    settings = get_settings()

    async def _search_one(query: SearchQuery) -> list[TavilySearchResult]:
        if not cb.is_available("you"):
            return []
        try:
            async with _engine_semaphore("you", settings.you_max_concurrent):
                response = await you_client.search(_ddg_queries(query.query)[0], count=min(settings.tavily_max_results, 20))
            cb.record_success("you")
        except Exception as exc:
            cb.record_failure("you", exc)
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
                    published_date=hit.get("page_age"),
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

    async def search(
        self, query: str, max_results: int = 10, timelimit: str | None = None
    ) -> list[dict[str, Any]]:
        loop_id = id(asyncio.get_running_loop())
        semaphore = self._semaphores.get(loop_id)
        if semaphore is None:
            self._semaphores.clear()
            semaphore = self._semaphores[loop_id] = asyncio.Semaphore(self._MAX_CONCURRENT)
        ddgs_cls = self._ddgs_class()
        market = current_search_market()
        region = market[2] if market else self.region
        async with semaphore:
            return await asyncio.to_thread(
                lambda: list(
                    ddgs_cls().text(
                        query, region=region, max_results=max_results, timelimit=timelimit
                    )
                    or []
                )
            )


# Tavily time_range -> DuckDuckGo timelimit.
_DDG_TIMELIMIT = {"day": "d", "week": "w", "month": "m", "year": "y"}


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
    circuit_breaker: SearchCircuitBreaker | None = None,
) -> list[TavilySearchResult]:
    """Executes search queries against DuckDuckGo, normalized to search results."""
    cb = circuit_breaker or get_search_circuit_breaker()
    if not cb.is_available("duckduckgo"):
        logger.info("[CIRCUIT_BREAKER] DuckDuckGo search API is disabled; skipping search.")
        return []

    settings = get_settings()

    async def _search_one(query: SearchQuery) -> list[TavilySearchResult]:
        if not cb.is_available("duckduckgo"):
            return []
        hits: list[dict[str, Any]] = []
        attempts = _ddg_queries(query.query)
        if query.include_domains and attempts:
            attempts = [f"{attempts[-1]} site:{query.include_domains[0]}"] + attempts
        timelimit = _DDG_TIMELIMIT.get(query.time_range or "")
        had_exception = False
        last_exc: Exception | None = None
        for attempt in attempts:
            try:
                if timelimit:
                    try:
                        hits = await ddg_client.search(
                            attempt, max_results=settings.duckduckgo_max_results, timelimit=timelimit
                        )
                    except TypeError:
                        # A stub client without timelimit: the recency re-rank still applies.
                        hits = await ddg_client.search(attempt, max_results=settings.duckduckgo_max_results)
                else:
                    hits = await ddg_client.search(attempt, max_results=settings.duckduckgo_max_results)
            except Exception as exc:
                had_exception = True
                last_exc = exc
                logger.info("DuckDuckGo search returned nothing for vector=%s (%r): %s", query.vector, attempt, exc)
                hits = []
            if hits:
                break
        if had_exception and not hits:
            cb.record_failure("duckduckgo", last_exc)
        elif hits:
            cb.record_success("duckduckgo")

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


_NON_PRODUCT_EXTENSIONS_OR_PATHS = re.compile(
    r"(?:\.(?:pdf|docx?|xlsx?|pptx?|zip|gz|tar)(?:[?#]|$)|/(?:dam|downloads?|stocks?|sec-filings?|investor-relations|ir)/)",
    re.IGNORECASE,
)

_TAVILY_EXCLUDE_NOISE_DOMAINS = (
    "wikipedia.org", "visa.com", "crunchbase.com", "dealroom.co", "hal.science",
    "arxiv.org", "drugs.com", "marketbeat.com", "robinhood.com", "bloomberg.com",
    "reuters.com", "yahoo.com", "msn.com", "sec.gov", "investing.com",
)


def _merge(*result_lists: list[TavilySearchResult]) -> list[TavilySearchResult]:
    """
    Deduplicates per vector and URL, keeping the first (highest-priority engine) result.
    Plain-HTTP URLs are upgraded to HTTPS at this point so every downstream consumer
    (crawler, grounding, synthesis) only ever sees secure URLs.
    """
    from orchestrator.agents.market_research.ingestion.url_guard import enforce_https

    merged: list[TavilySearchResult] = []
    seen: set[tuple[str, str]] = set()
    for results in result_lists:
        for r in results:
            if not r.url:
                continue
            secure = enforce_https(r.url)
            if secure is None:
                logger.debug("_merge: dropped non-HTTPS result: %s", r.url)
                continue
            if _NON_PRODUCT_EXTENSIONS_OR_PATHS.search(secure):
                logger.debug("_merge: dropped non-product document/path: %s", secure)
                continue
            key = (r.vector, secure)
            if key not in seen:
                seen.add(key)
                merged.append(r if secure == r.url else TavilySearchResult(
                    vector=r.vector,
                    title=r.title,
                    url=secure,
                    snippet=r.snippet,
                    score=r.score,
                    provider=r.provider,
                    published_date=r.published_date,
                ))
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
    circuit_breaker: SearchCircuitBreaker | None = None,
    session_cache: SearchSessionCache | None = None,
) -> list[TavilySearchResult]:
    """
    Executes search queries with circuit-breaker protection and automatic failure redistribution:
    if any search API fails twice (configurable via search_circuit_breaker_max_failures),
    it is tripped and excluded from subsequent queries. The workload is distributed into
    the remaining active providers (Tavily, You.com, DuckDuckGo).
    """
    settings = get_settings()
    ddg_mode = settings.duckduckgo_mode.lower()
    cb = circuit_breaker or get_search_circuit_breaker()

    queries = _validated_queries(queries)
    if not queries:
        return []

    # Build live clients only when none injected and key/mode allows and breaker not tripped
    if tavily_client is None and settings.tavily_api_key and cb.is_available("tavily"):
        try:
            from tavily import AsyncTavilyClient

            tavily_client = AsyncTavilyClient(api_key=settings.tavily_api_key)
        except ImportError:
            logger.error("tavily-python not installed — Tavily search unavailable")

    if you_client is None and settings.you_api_key and cb.is_available("you"):
        you_client = YouSearchClient()

    if ddg_client is None and ddg_mode != "off" and cb.is_available("duckduckgo"):
        ddg_client = DuckDuckGoSearchClient()

    free_first = {v.strip() for v in settings.search_free_first_vectors.split(",") if v.strip()}

    async def _one(query: SearchQuery) -> list[TavilySearchResult]:
        if session_cache is not None:
            cached = session_cache.get(query)
            if cached is not None:
                return cached
        persist = settings.search_cache_ttl_hours > 0 and _cacheable_across_runs(query)
        if persist:
            from orchestrator.core.storage import get_storage

            stored = await get_storage().get_cached_search(query_key(query))
            if stored:
                results = [
                    TavilySearchResult(**{**r, "vector": query.vector, "score": float(r.get("score") or 0.0)})
                    for r in stored
                ]
                if session_cache is not None:
                    session_cache.set(query, results)
                return results

        results = await _run_engines(query)
        if results:
            if session_cache is not None:
                session_cache.set(query, results)
            if persist:
                from orchestrator.core.storage import get_storage

                await get_storage().set_cached_search(query_key(query), [asdict(r) for r in results])
        return results

    async def _run_engines(query: SearchQuery) -> list[TavilySearchResult]:
        can_use_tavily = tavily_client is not None and cb.is_available("tavily")
        can_use_you = you_client is not None and cb.is_available("you")
        can_use_ddg = ddg_client is not None and cb.is_available("duckduckgo") and ddg_mode != "off"

        # Broad discovery is answered well by the free engine; paid ones only top up a thin result.
        if query.vector in free_first and can_use_ddg and not settings.search_paid_fanout:
            free = await execute_duckduckgo_search([query], ddg_client, circuit_breaker=cb)
            if len(free) >= settings.duckduckgo_min_results:
                return _merge(free)
            return _merge(await _run_paid(query, can_use_tavily, can_use_you), free)

        primary = await _run_paid(query, can_use_tavily, can_use_you)

        # If primary engines failed or are disabled/tripped, or primary results are thin:
        # distribute query into working support engine (DuckDuckGo).
        tavily_disabled = (tavily_client is not None and not cb.is_available("tavily"))
        you_disabled = (you_client is not None and not cb.is_available("you"))
        primary_disabled_or_empty = (tavily_disabled or you_disabled or (not can_use_tavily and not can_use_you))

        if not can_use_ddg:
            return primary

        needs_ddg = (
            ddg_mode == "always"
            or (primary_disabled_or_empty and not primary)
            or len(primary) < settings.duckduckgo_min_results
        )
        if needs_ddg:
            return _merge(primary, await execute_duckduckgo_search([query], ddg_client, circuit_breaker=cb))
        return primary

    async def _run_paid(query: SearchQuery, can_use_tavily: bool, can_use_you: bool) -> list[TavilySearchResult]:
        if settings.search_paid_fanout:
            primary_tasks = []
            if can_use_tavily:
                primary_tasks.append(_execute_tavily_only([query], tavily_client, circuit_breaker=cb))
            if can_use_you:
                primary_tasks.append(execute_you_search([query], you_client, circuit_breaker=cb))
            return _merge(*(await asyncio.gather(*primary_tasks))) if primary_tasks else []
        # Cascade: one paid call per query; the second engine only tops up a thin or failed first.
        primary = (
            await _execute_tavily_only([query], tavily_client, circuit_breaker=cb)
            if can_use_tavily else []
        )
        if (
            len(primary) < settings.duckduckgo_min_results
            and you_client is not None
            and cb.is_available("you")
        ):
            primary = _merge(primary, await execute_you_search([query], you_client, circuit_breaker=cb))
        return primary

    # Near-duplicate queries (same terms, any order or vector) hit the engines once; each
    # vector still gets its own copy of the results.
    unique: dict[str, SearchQuery] = {}
    for q in queries:
        unique.setdefault(query_key(q), q)
    by_key = dict(zip(unique, await asyncio.gather(*[_one(q) for q in unique.values()])))
    return _merge(*[_as_vector(by_key[query_key(q)], q.vector) for q in queries])


async def _empty() -> list[TavilySearchResult]:
    return []


async def _execute_tavily_only(
    queries: list[SearchQuery],
    tavily_client: Any,
    circuit_breaker: SearchCircuitBreaker | None = None,
) -> list[TavilySearchResult]:
    """Executes search queries against Tavily in parallel with circuit breaker tracking."""
    cb = circuit_breaker or get_search_circuit_breaker()
    if not cb.is_available("tavily"):
        logger.info("[CIRCUIT_BREAKER] Tavily search API is disabled; skipping search.")
        return []

    settings = get_settings()

    async def _search_one(query: SearchQuery) -> list[TavilySearchResult]:
        if not cb.is_available("tavily"):
            return []
        try:
            search_kwargs: dict[str, Any] = {
                "query": query.query,
                "search_depth": query.search_depth,
                "max_results": settings.tavily_max_results,
            }
            if query.include_domains:
                search_kwargs["include_domains"] = list(query.include_domains)
            else:
                search_kwargs["exclude_domains"] = list(_TAVILY_EXCLUDE_NOISE_DOMAINS)
            if query.time_range:
                search_kwargs["time_range"] = query.time_range
            if market := current_search_market():
                search_kwargs["country"] = market[1]  # boosts results from that country

            async with _engine_semaphore("tavily", settings.tavily_max_concurrent):
                try:
                    response = await tavily_client.search(**search_kwargs)
                except TypeError:
                    # Older tavily-python (or a stub client) may not accept time_range or exclude_domains —
                    # drop the extra hints rather than lose the whole query.
                    search_kwargs.pop("time_range", None)
                    search_kwargs.pop("exclude_domains", None)
                    search_kwargs.pop("country", None)
                    response = await tavily_client.search(**search_kwargs)
            results = response.get("results", [])
            cb.record_success("tavily")
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
            cb.record_failure("tavily", exc)
            logger.warning("Tavily search failed for vector=%s: %s", query.vector, exc)
            return []

    batches = await asyncio.gather(*[_search_one(q) for q in queries])
    return [result for batch in batches for result in batch]
