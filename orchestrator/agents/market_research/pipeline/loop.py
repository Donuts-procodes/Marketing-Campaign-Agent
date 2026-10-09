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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

from orchestrator.agents.market_research.discovery.crawler import (
    extract_competitor_target_urls,
    extract_target_urls,
)
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
    derive_geo_signals,
    derive_scale_signals,
    filter_out_of_area_results,
    filter_out_of_scale_results,
    rank_by_recency,
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

# A DQS move smaller than this is noise, not progress.
_PLATEAU_DQS_EPSILON = 0.005

# Density below this once pages are in hand means the framework names parameters the market
# does not use, so nothing can be scored against it. Worth one LLM call to rewrite.
_TAXONOMY_REVISION_DENSITY_FLOOR = 0.10


def _time_range_since(prior_run_at: str | None) -> str:
    """
    Returns the Tavily time_range string that covers everything since prior_run_at.
    Tavily supports: "day", "week", "month", "year".
    Falls back to "month" when the date cannot be parsed.
    """
    if not prior_run_at:
        return "month"
    try:
        from datetime import datetime, timezone as tz
        prior_dt = datetime.fromisoformat(prior_run_at.replace("Z", "+00:00"))
        days_ago = (datetime.now(tz.utc) - prior_dt).days
        if days_ago <= 1:
            return "day"
        if days_ago <= 7:
            return "week"
        if days_ago <= 31:
            return "month"
        return "year"
    except (ValueError, TypeError):
        return "month"

# Review sites, forums, social networks, ad libraries, aggregators and payment/infra rails:
# useful evidence, never competitors.
NON_COMPETITOR_DOMAINS = frozenset({
    "reddit", "g2", "capterra", "trustpilot", "yelp", "bbb", "sitejabber", "quora",
    "youtube", "facebook", "instagram", "twitter", "x", "linkedin", "tiktok", "medium",
    "wikipedia", "google", "bing", "amazon", "ebay", "producthunt", "trustradius",
    "getapp", "softwareadvice", "forbes", "techradar", "pcmag", "nytimes", "rtings",
    "crunchbase", "dealroom", "pitchbook", "rocketreach", "zoominfo", "cbinsights", "tracxn",
    "owler", "signalhire", "comparably", "glassdoor", "indeed", "builtin",
    "marketbeat", "robinhood", "msn", "yahoo", "bloomberg", "reuters", "cnbc", "marketwatch",
    "nasdaq", "nyse", "investing", "seekingalpha", "businesswire", "prnewswire", "globenewswire",
    "einpresswire", "drugs", "webmd", "hal", "arxiv", "researchgate", "springer", "sciencedirect",
    "academia", "scribd", "slideshare", "vendr", "superbcompanies", "clutch", "goodfirms",
    "designrush", "sortlist", "themanifest", "upwork", "fiverr", "toptal", "github", "gitlab",
    "stackoverflow", "visa", "mastercard", "paypal", "stripe", "apple", "microsoft", "aws",
    "amazonaws", "wordpress", "blogspot", "substack", "wix",
    "webflow", "vercel", "netlify", "squarespace", "carrd", "framer", "shopify", "myshopify",
    "render", "fly", "heroku",
})

_NON_BRAND_PATH = re.compile(
    r"(?:\.pdf$|/(?:stocks?|news|blog|press|article|articles|research|document|documents|download|"
    r"dam|organizations?|companies|profile|price-guide|marketplace|frontend|history|collections)/)",
    re.I,
)

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
    from orchestrator.agents.market_research.discovery.source_types import MULTI_TENANT_DOMAINS

    host = (urlparse(url).hostname or "").lower()
    for mtd in MULTI_TENANT_DOMAINS:
        if host == mtd:
            return mtd.split(".")[0]
        if host.endswith("." + mtd):
            sub = host[: -len(mtd) - 1]
            sub_parts = sub.split(".")
            return sub_parts[-1] if sub_parts else mtd.split(".")[0]

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
    if not url:
        return False
    if _NON_BRAND_PATH.search(urlparse(url).path or ""):
        return False
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


# _PRICE_AMOUNT_RE only has to prove an amount is present, so its symbol branch stops after a
# single digit. Reusing it to read the amount truncated "$49/month" to "$4" -- a wrong price
# reads as a finding, which is worse than no price at all. Extraction takes the whole figure
# and any rate suffix.
# Longest alternatives first, so "/month" is not captured as the shorter "/mo".
_PRICE_UNIT = r"(?:\s?(?:/|per\s)\s?(?:month|mo|year|yr|user|seat|licence|license))?"
_PRICE_EXTRACT_RE = re.compile(
    r"[$€£¥₹]\s?\d[\d,.]*" + _PRICE_UNIT
    + r"|\b\d[\d,.]*\s?(?:usd|eur|gbp|inr|dollars?)" + _PRICE_UNIT
    + r"|\b\d[\d,.]*\s?(?:/|per\s)(?:month|mo|year|yr|user|seat)\b",
    re.IGNORECASE,
)


_NON_PRICING_CONTEXT = re.compile(
    r"\b(?:penalt(?:y|ies)|liabilit(?:y|ies)|bond|insurance|processing volume|transaction volume|"
    r"volume of|turnover|valuation|raised|funding|fine|fines|damages|settlement)\b",
    re.IGNORECASE,
)


def _has_price(text: str) -> bool:
    if _NON_PRICING_CONTEXT.search(text):
        return False
    return bool(_PRICE_AMOUNT_RE.search(text))


def _extract_price(text: str) -> str | None:
    if _NON_PRICING_CONTEXT.search(text):
        return None
    match = _PRICE_EXTRACT_RE.search(text)
    if not match:
        return None
    price = match.group(0).strip().rstrip(".,;:")
    p_num = re.search(r"\d[\d,.]*", price)
    if p_num:
        try:
            val = float(p_num.group(0).replace(",", ""))
            if "/mo" in price.lower() and val > 50_000:
                return None
        except ValueError:
            pass
    return price or None

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


# The review and forum pages mined for complaints carry praise in the same breath -- the
# thread that says support is slow also says the dashboard is excellent. Only the complaint
# half was ever kept, so every competitor profile recorded what was wrong with a rival and
# nothing about what actually wins them customers.
_STRENGTH_KEYWORDS = (
    "love", "excellent", "outstanding", "best in", "great", "fantastic", "reliable",
    "intuitive", "easy to use", "fast", "responsive", "worth it", "recommend",
    "impressed", "seamless", "lifesaver", "solid", "powerful", "flexible",
    "helpful", "affordable", "value for money", "well worth", "professional",
)
_PRAISE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in _STRENGTH_KEYWORDS) + r")",
    re.IGNORECASE,
)

#: Praise phrased as a let-down ("not great", "hardly reliable") is a complaint. Checked
#: before the praise test so a negated positive never lands in the strengths column.
_NEGATED_PRAISE_RE = re.compile(
    r"\b(?:not|never|hardly|barely|isn't|isnt|wasn't|wasnt|far from|less than)\s+\w{0,10}\s*(?:"
    + "|".join(re.escape(k) for k in _STRENGTH_KEYWORDS)
    + r")",
    re.IGNORECASE,
)


def _clean_mined_snippet(snippet: str) -> str:
    """Strips scraper and byline boilerplate that would otherwise be quoted as user opinion."""
    out = snippet[:200].strip()
    out = re.sub(r"^Title:\s*[^|]+\|\s*", "", out, flags=re.IGNORECASE).strip()
    out = re.sub(
        r"^(?:written by|by)\s+[A-Za-z0-9 \"'.,-]+?(?:\u2014|-|:|\.\s+)", "", out, flags=re.IGNORECASE
    ).strip()
    out = re.sub(r"#{1,6}\s*", "", out).strip()
    out = re.sub(r"\*{2,}", "", out).strip()
    return out


def _is_praise(text: str) -> bool:
    """A snippet counts as a strength only when it praises and does not also complain."""
    if len(text) <= 20 or _NEGATED_PRAISE_RE.search(text):
        return False
    return bool(_PRAISE_RE.search(text)) and not _COMPLAINT_RE.search(text)


# "4.6 out of 5", "4.6/5", "4.6/5.0", "Rated 4.6", "Rating: 4.6", "4.6★", JSON-LD ratingValue.
# Bounded to a 0-5 scale so a price or a year cannot be read as a rating.
_RATING_RE = re.compile(
    r"(?:"
    r"\b([0-5](?:\.\d{1,2})?)\s*(?:/\s*5(?:\.0)?\b|out of\s+5(?:\.0)?\b|stars?\b|★)"
    r"|(?:rating|rated|score)[\s:]+([0-5](?:\.\d{1,2})?)(?:\s*(?:/\s*5(?:\.0)?|stars?|★))?"
    r'|"ratingValue"\s*:\s*"?([0-5](?:\.\d{1,2})?)"?'
    r")",
    re.IGNORECASE,
)

# "1,240 reviews", "based on 312 ratings", schema.org reviewCount
_REVIEW_COUNT_RE = re.compile(
    r"(?:"
    r"\b(\d{1,3}(?:,\d{3})*|\d+)\s+(?:customer\s+|verified\s+|user\s+)?(?:reviews?|ratings?)\b"
    r'|"reviewCount"\s*:\s*"?(\d+)"?'
    r")",
    re.IGNORECASE,
)


_ARTICLE_RATING_RE = re.compile(
    r"\b(?:rate this (?:article|post|page)|article rating|post rating|editorial rating|author rating)\b",
    re.IGNORECASE,
)


def _extract_rating(text: str) -> str | None:
    if not text or _ARTICLE_RATING_RE.search(text):
        return None
    for match in _RATING_RE.finditer(text):
        for group in match.groups():
            if group is not None:
                try:
                    val = float(group)
                    if 1.0 <= val <= 5.0:
                        return f"{val:.1f}" if "." in group else str(int(val))
                except ValueError:
                    continue
    return None


def _extract_review_count(text: str) -> int | None:
    if not text:
        return None
    for match in _REVIEW_COUNT_RE.finditer(text):
        for group in match.groups():
            if group is not None:
                try:
                    value = int(group.replace(",", ""))
                    if 3 <= value <= 10_000_000:
                        return value
                except ValueError:
                    continue
    return None


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
        profile.rating = profile.rating or p.rating
        profile.review_count = profile.review_count or p.review_count
        profile.founded = profile.founded or p.founded
        profile.headquarters = profile.headquarters or p.headquarters
        profile.operating_locations.extend(l for l in p.operating_locations if l not in profile.operating_locations)
        profile.other_products.extend(op for op in p.other_products if op not in profile.other_products)
        profile.product_catalog_count = profile.product_catalog_count or p.product_catalog_count
        profile.sources.extend(u for u in p.sources if u not in profile.sources)
        profile.factual_evidence.extend(e for e in p.factual_evidence if e not in profile.factual_evidence)
        profile.weaknesses_mined.extend(w for w in p.weaknesses_mined if w not in profile.weaknesses_mined)
        profile.strengths_mined.extend(s for s in p.strengths_mined if s not in profile.strengths_mined)
        profile.core_claims.extend(c for c in p.core_claims if c not in profile.core_claims)
        for k, v in (p.dynamic_attributes or {}).items():
            profile.dynamic_attributes.setdefault(k, v)
        for m in p.milestones:
            if m not in profile.milestones:
                profile.milestones.append(m)

    for r in search_results:
        if not r.url or len(r.snippet) <= 25 or name_lower not in r.snippet.lower():
            continue
        if r.url not in profile.sources:
            profile.sources.append(r.url)
        if not profile.pricing_model and _has_price(r.snippet):
            profile.pricing_model = PLACEHOLDER_PRICING
        combined = f"{r.title} {r.snippet}"
        if not profile.rating:
            profile.rating = _extract_rating(combined)
        if not profile.review_count:
            profile.review_count = _extract_review_count(combined)
        if _is_complaint(r.snippet) and r.snippet[:200] not in profile.weaknesses_mined:
            profile.weaknesses_mined.append(r.snippet[:200])
        if _is_praise(r.snippet) and r.snippet[:200] not in profile.strengths_mined:
            profile.strengths_mined.append(r.snippet[:200])
        evidence = f'"{r.snippet[:200].strip()}..."'
        if len(profile.factual_evidence) < 6 and evidence not in profile.factual_evidence:
            profile.factual_evidence.append(evidence)
    return profile


def extract_preliminary_competitors(
    search_results: list[TavilySearchResult],
    known_competitors: list[str] | None = None,
    merchant_context: dict[str, Any] | None = None,
) -> list[CompetitorProfile]:
    """
    Extracts candidate competitor profiles from factual search snippets.

    One profile per competitor page (URL without fragment/query). Review sites, forums,
    social networks, ad libraries and listicle/comparison articles never become competitors;
    their complaints are attached to the competitor profile whose name they best match instead.
    Competitors the merchant named come first, built from the evidence that mentions them.
    The merchant's own business name and website domain are always excluded.
    """
    from orchestrator.agents.market_research.discovery.source_types import (
        is_merchant_identity,
        merchant_identifiers,
    )

    merchant_name_keys, merchant_hosts = merchant_identifiers(merchant_context)
    profiles: dict[str, CompetitorProfile] = {}
    review_results: list[TavilySearchResult] = []

    for r in search_results:
        if not r.url:
            continue
        if is_merchant_identity("", [r.url], merchant_name_keys, merchant_hosts):
            continue
        if not is_competitor_source(r.url) or is_listicle(r.title, r.url):
            review_results.append(r)
            continue

        has_pricing = _has_price(r.snippet)
        has_weakness = _is_complaint(r.snippet)
        has_strength = _is_praise(r.snippet)
        evidence_snippet = f'"{r.snippet[:200].strip()}..."' if len(r.snippet) > 25 else None
        extracted_claim = r.snippet[:160].strip() if len(r.snippet) > 15 else ""

        brand_name = _extract_brand_from_url(r.url)
        clean_title = _clean_product_name(r.title or "", brand_name)

        if is_merchant_identity(brand_name, [r.url], merchant_name_keys, merchant_hosts):
            continue
        if is_merchant_identity(clean_title, [r.url], merchant_name_keys, merchant_hosts):
            continue

        key = _normalize_url(r.url)
        existing = profiles.get(key)
        if existing is not None:
            if has_pricing and not existing.pricing_model:
                existing.pricing_model = PLACEHOLDER_PRICING
            if extracted_claim and not existing.core_claims:
                existing.core_claims.append(extracted_claim)
            if has_weakness and r.snippet[:200] not in existing.weaknesses_mined:
                existing.weaknesses_mined.append(r.snippet[:200])
            if has_strength and r.snippet[:200] not in existing.strengths_mined:
                existing.strengths_mined.append(r.snippet[:200])
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
            strengths_mined=[r.snippet[:200]] if has_strength else [],
            factual_evidence=[evidence_snippet] if evidence_snippet else [],
            sources=[r.url],
        )

    # Review pages also carry the rating and the review count, which is the social proof a
    # merchant judges a rival on long before they read any individual complaint.
    for r in review_results:
        combined = f"{r.title} {r.snippet}"
        text_lower = combined.lower()
        named = [p for p in profiles.values() if p.brand_name.lower() in text_lower]
        if len(named) != 1:
            continue  # ambiguous page: a rating here could belong to any rival it lists
        profile = named[0]
        rating = _extract_rating(combined)
        count = _extract_review_count(combined)
        if count and profile.review_count is None:
            profile.review_count = count
        if rating and profile.rating is None:
            effective_count = count or profile.review_count
            if effective_count is not None and effective_count >= 3:
                profile.rating = rating
            elif effective_count is None:
                try:
                    if float(rating) not in (1.0, 5.0):
                        profile.rating = rating
                except ValueError:
                    pass

    # Attach review/forum praise to the best-matching competitor the text names.
    for r in review_results:
        if not _is_praise(r.snippet):
            continue
        text = f"{r.title} {r.snippet}"
        text_lower = text.lower()
        text_tokens = _tokens(text)
        candidates = [p for p in profiles.values() if p.brand_name.lower() in text_lower]
        if not candidates:
            continue
        best = max(candidates, key=lambda p: len(_tokens(p.product_name) & text_tokens))
        praise = _clean_mined_snippet(r.snippet)
        if praise and praise not in best.strengths_mined:
            best.strengths_mined.append(praise)
        if r.url not in best.sources:
            best.sources.append(r.url)

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
        complaint = re.sub(r"^Title:\s*[^|]+\|\s*", "", complaint, flags=re.IGNORECASE).strip()
        complaint = re.sub(r"^(?:written by|by)\s+[A-Za-z0-9 \"'.,-]+?(?:—|-|:|\.\s+)", "", complaint, flags=re.IGNORECASE).strip()
        complaint = re.sub(r"#{1,6}\s*", "", complaint).strip()
        complaint = re.sub(r"\*{2,}", "", complaint).strip()
        complaint = re.sub(r"##\s*Post details\.?\s*##\s*Content\.?\s*##\s*Top Comments\.?", "", complaint, flags=re.IGNORECASE).strip()
        if len(complaint) > 15 and complaint not in best.weaknesses_mined:
            best.weaknesses_mined.append(complaint)
        if r.url not in best.sources:
            best.sources.append(r.url)

    discovered = [
        p for p in profiles.values()
        if not is_merchant_identity(p.brand_name, p.sources, merchant_name_keys, merchant_hosts)
        and not is_merchant_identity(p.product_name, p.sources, merchant_name_keys, merchant_hosts)
    ]
    if not known_competitors:
        return discovered

    known = [_known_competitor_profile(n, discovered, search_results) for n in known_competitors if n.strip()]
    known = [
        k for k in known
        if not is_merchant_identity(k.brand_name, k.sources, merchant_name_keys, merchant_hosts)
    ]
    known_keys = {"".join(c for c in k.brand_name.lower() if c.isalnum()) for k in known}
    rest = [p for p in discovered if "".join(c for c in p.brand_name.lower() if c.isalnum()) not in known_keys]
    return known + rest


def split_named(
    competitors: list[CompetitorProfile],
    named: list[str] | None,
    cap: int,
) -> tuple[list[CompetitorProfile], list[CompetitorProfile], list[CompetitorProfile]]:
    """
    (named within cap, named past cap, discovered), each in input order.

    The merchant's own list and the agent's discoveries are two separate quotas. Cutting one
    ranked list at N let named rivals (always ranked first) take every slot: name five and the
    agent researched none of its own.
    """
    keys = {_norm_key(n) for n in (named or []) if n and n.strip()}
    picked, overflow, discovered = [], [], []
    for c in competitors:
        brand = _norm_key(c.brand_name)
        if keys and (brand in keys or _norm_key(c.product_name) in keys):
            (picked if len(picked) < cap else overflow).append(c)
        elif len(brand) >= 4 and any(k.startswith(brand) for k in keys):
            # The parent company of a named product ("Logitech" when "Logitech Lift" was
            # named) is already covered; it must not use up one of the discovery slots.
            continue
        else:
            discovered.append(c)
    return picked, overflow, discovered


def rank_competitors(
    competitors: list[CompetitorProfile],
    search_results: list[TavilySearchResult],
    known_competitors: list[str] | None = None,
    merchant_context: dict[str, Any] | None = None,
) -> list[CompetitorProfile]:
    """
    Orders discovered competitors strongest-first so deep crawl can spend its page budget on
    the few that matter instead of one page each across every host that appeared in search.

    Purely heuristic, so it costs nothing and is deterministic. The signals, in order of
    weight: the merchant naming someone outranks everything; appearing under several search
    vectors means the brand surfaced as a rival, as a priced product and as a source of
    complaints rather than in one lucky result; search relevance and corroborating source
    count break the remaining ties.
    """
    from orchestrator.agents.market_research.discovery.source_types import (
        is_never_a_brand,
        is_merchant_identity,
        merchant_identifiers,
    )

    merchant_name_keys, merchant_hosts = merchant_identifiers(merchant_context)
    competitors = merge_duplicate_competitors(competitors)
    known_keys = {_norm_key(n) for n in (known_competitors or []) if n.strip()}
    # Directories, data aggregators and code hosts are never rivals. Ranked by mentions they
    # top the list (every rival has a Clutch and a GitHub page), and the deep crawl then spent
    # its page budget on them: one run crawled GitHub, Clutch and Crunchbase while three real
    # rivals' own sites went unread. A rival the merchant named is always kept.
    # The merchant itself is always excluded.
    competitors = [
        c for c in competitors
        if not is_merchant_identity(c.brand_name, c.sources, merchant_name_keys, merchant_hosts)
        and not is_merchant_identity(c.product_name, c.sources, merchant_name_keys, merchant_hosts)
        and (
            _norm_key(c.brand_name) in known_keys
            or not (is_never_a_brand(c.brand_name) or (c.sources and is_never_a_brand(c.sources[0])))
        )
    ]

    vectors_by_host: dict[str, set[str]] = {}
    best_score_by_host: dict[str, float] = {}
    for r in search_results:
        if not r.url:
            continue
        host = _host_of(r.url)
        if not host:
            continue
        vectors_by_host.setdefault(host, set()).add(r.vector)
        best_score_by_host[host] = max(best_score_by_host.get(host, 0.0), r.score)

    def _score(c: CompetitorProfile) -> tuple[int, float]:
        if _norm_key(c.brand_name) in known_keys:
            return (1, 999.0)

        host = _host_of(c.sources[0]) if c.sources else ""
        vectors = vectors_by_host.get(host, set())

        score = 0.0
        # Surfacing under several vectors is the strongest organic signal of a real rival.
        score += len(vectors) * 2.0
        # Evidence we already hold on them: these fields are what the report is graded on.
        score += 1.5 if c.pricing_model else 0.0
        score += min(len(c.weaknesses_mined), 3) * 0.75
        score += min(len(c.sources), 4) * 0.5
        score += best_score_by_host.get(host, 0.0)
        return (0, score)

    return sorted(competitors, key=_score, reverse=True)


# "Founded in 1998", "Est. 2015", "since 2007". Bounded to plausible years so a price or a
# street number cannot masquerade as a founding date.
_FOUNDED_RE = re.compile(
    r"\b(?:founded|established|est\.?|incorporated|started|launched|serving\s+\w+\s+since|since)"
    r"[^\d]{0,20}((?:19[5-9]\d|20[0-2]\d))\b",
    re.IGNORECASE,
)

# A dated sentence: "In 2021 we opened our Berlin office." Milestones are only useful when
# they carry a date, so an undated achievement line is deliberately not matched.
_MILESTONE_RE = re.compile(
    r"(?:^|[.\n])\s*((?:in\s+)?(?:19[5-9]\d|20[0-2]\d)[^.\n]{15,160})",
    re.IGNORECASE,
)

_MILESTONE_KEYWORDS = (
    "launch", "found", "establish", "acquir", "merge", "expand", "open", "raise", "fund",
    "partner", "award", "certif", "release", "introduc", "reach", "grew", "grow", "million",
    "office", "headquarter", "rebrand", "ipo", "series",
)


def _extract_founded(text: str) -> str | None:
    match = _FOUNDED_RE.search(text)
    return match.group(1) if match else None


def _extract_milestones(text: str) -> list[str]:
    """Dated company events, kept verbatim so the UI never presents a paraphrase as a fact."""
    out: list[str] = []
    for match in _MILESTONE_RE.finditer(text):
        sentence = " ".join(match.group(1).split()).strip()
        if len(sentence) < 20:
            continue
        if not any(k in sentence.lower() for k in _MILESTONE_KEYWORDS):
            continue
        if sentence not in out:
            out.append(sentence)
        if len(out) >= 6:
            break
    return out


_HQ_RE = re.compile(
    r"\b(?:headquartered\s+(?:in|at)|headquarters(?:\s+in|:|\s+located\s+in)?|based\s+in|main\s+office\s+in)\s+([A-Z][A-Za-z0-9\s,.-]{2,40}?)(?=[.;\n]|and\b|\band\s+operat|\bwith|\bserve|\bemploy)",
    re.IGNORECASE,
)

_LOC_RE = re.compile(
    r"\b(?:operating\s+in|active\s+in|branches\s+in|presence\s+in|serving|available\s+in|locations\s+in|offices\s+in)\s+([A-Za-z0-9\s,.-]{3,60}?)(?=[.;\n]|\bwith\b|\band\s+has\b)",
    re.IGNORECASE,
)

_CATALOG_COUNT_RE = re.compile(
    r"\b(\d+)\s+(?:different\s+)?(?:products|models|systems|appliances|skus|product\s+lines|variants)\b",
    re.IGNORECASE,
)


def _extract_headquarters(text: str) -> str | None:
    match = _HQ_RE.search(text)
    if not match:
        return None
    val = match.group(1).strip().rstrip(".,;:")
    return val if len(val) >= 3 else None


def _extract_operating_locations(text: str) -> list[str]:
    out: list[str] = []
    for match in _LOC_RE.finditer(text):
        item = match.group(1).strip().rstrip(".,;:")
        if len(item) >= 3 and item not in out:
            out.append(item)
        if len(out) >= 4:
            break
    return out


def _extract_catalog_count(text: str) -> int | None:
    match = _CATALOG_COUNT_RE.search(text)
    if match:
        try:
            val = int(match.group(1))
            if 1 <= val <= 5000:
                return val
        except ValueError:
            pass
    return None


def merge_duplicate_competitors(
    competitors: list[CompetitorProfile],
) -> list[CompetitorProfile]:
    """
    Collapses profiles that describe the same company into one.

    `extract_preliminary_competitors` keys profiles by normalised URL, so a vendor whose home
    page, pricing page and blog all appear in search becomes three entries. That inflates the
    competitor count, lets one company occupy several shortlist slots, and understates the
    evidence held on each. Grouping by registrable host (brand name when a host is missing)
    unions what each duplicate knew, preferring a real price over the placeholder.
    """
    merged: dict[str, CompetitorProfile] = {}

    for c in competitors:
        host = next((h for h in (_host_of(s) for s in c.sources) if h), "")
        key = host or _norm_key(c.brand_name)
        if not key:
            continue

        primary = merged.get(key)
        if primary is None:
            merged[key] = c
            continue

        if not primary.pricing_model or primary.pricing_model == PLACEHOLDER_PRICING:
            if c.pricing_model and c.pricing_model != PLACEHOLDER_PRICING:
                primary.pricing_model = c.pricing_model
            elif not primary.pricing_model:
                primary.pricing_model = c.pricing_model

        if not primary.rating and c.rating:
            primary.rating = c.rating
        if not primary.review_count and c.review_count:
            primary.review_count = c.review_count
        if not primary.founded and c.founded:
            primary.founded = c.founded
        if not primary.headquarters and c.headquarters:
            primary.headquarters = c.headquarters
        for loc in c.operating_locations:
            if loc and loc not in primary.operating_locations:
                primary.operating_locations.append(loc)
        for prod in c.other_products:
            if prod and prod not in primary.other_products:
                primary.other_products.append(prod)
        if not primary.product_catalog_count and c.product_catalog_count:
            primary.product_catalog_count = c.product_catalog_count

        for claim in c.core_claims:
            if claim and claim not in primary.core_claims:
                primary.core_claims.append(claim)
        for weakness in c.weaknesses_mined:
            if weakness and weakness not in primary.weaknesses_mined:
                primary.weaknesses_mined.append(weakness)
        for evidence in c.factual_evidence:
            if evidence and evidence not in primary.factual_evidence:
                primary.factual_evidence.append(evidence)
        for source in c.sources:
            if source and source not in primary.sources:
                primary.sources.append(source)
        for hook in c.ad_hooks:
            if hook and hook not in primary.ad_hooks:
                primary.ad_hooks.append(hook)
        for attr_key, attr_value in (c.dynamic_attributes or {}).items():
            primary.dynamic_attributes.setdefault(attr_key, attr_value)

        # The home page usually carries the cleanest product name; "Product" is the fallback
        # the extractor uses when a title yielded nothing.
        if primary.product_name in ("", "Product") and c.product_name not in ("", "Product"):
            primary.product_name = c.product_name

    return list(merged.values())


def enrich_competitors_from_pages(
    competitors: list[CompetitorProfile],
    extracted_pages: list[dict[str, Any]],
) -> list[CompetitorProfile]:
    """
    Folds deep-crawled page text back into the competitor profiles it belongs to.

    Search snippets rarely state a price, so profiles built from them alone carry at most the
    "detected" placeholder -- which `calculate_dqs` deliberately refuses to count. The crawled
    pricing page usually does state one, and attaching it here is what moves P_pricing off
    zero. Pages are matched to a competitor by host, so a page can only ever enrich the rival
    whose own domain served it.
    """
    if not extracted_pages:
        return competitors

    by_host: dict[str, CompetitorProfile] = {}
    for c in competitors:
        for s in c.sources:
            host = _host_of(s)
            if host:
                by_host.setdefault(host, c)
                break

    for page in extracted_pages:
        markdown = page.get("markdown") or ""
        url = page.get("url") or ""
        if not markdown or not url:
            continue
        comp = by_host.get(_host_of(url))
        if comp is None:
            continue

        # A real amount replaces the placeholder; an existing real price is left alone.
        if not comp.pricing_model or comp.pricing_model == PLACEHOLDER_PRICING:
            price = _extract_price(markdown)
            if price:
                comp.pricing_model = price

        if url not in comp.sources:
            comp.sources.append(url)

        # Background history: when a competitor was founded and what they date as milestones.
        # Stated on about/company pages, which the shortlist crawl now reaches.
        if not comp.founded:
            founded = _extract_founded(markdown)
            if founded:
                comp.founded = founded
        if not comp.headquarters:
            hq = _extract_headquarters(markdown)
            if hq:
                comp.headquarters = hq
        if not comp.operating_locations:
            locs = _extract_operating_locations(markdown)
            if locs:
                comp.operating_locations = locs
        if not comp.product_catalog_count:
            cat_count = _extract_catalog_count(markdown)
            if cat_count:
                comp.product_catalog_count = cat_count
        if len(comp.milestones) < 6:
            for event in _extract_milestones(markdown):
                if event not in comp.milestones:
                    comp.milestones.append(event)
                if len(comp.milestones) >= 6:
                    break

        if comp.rating is None:
            rating = _extract_rating(markdown)
            if rating:
                comp.rating = rating
        if comp.review_count is None:
            count = _extract_review_count(markdown)
            if count:
                comp.review_count = count

        if len(comp.factual_evidence) < 4:
            excerpt = " ".join(markdown[:400].split()).strip()
            if excerpt:
                quoted = f'"{excerpt[:200]}..."'
                if quoted not in comp.factual_evidence:
                    comp.factual_evidence.append(quoted)

    return competitors


def _norm_key(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").removeprefix("www.").lower()
    except Exception:
        return ""


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
    is_update: bool = False,
    prior_run_at: str | None = None,
    on_first_competitors: Callable[[list[CompetitorProfile]], Awaitable[None]] | None = None,
    revise_taxonomy: Callable[
        [DynamicParameterTaxonomy, list[str]], Awaitable[DynamicParameterTaxonomy]
    ]
    | None = None,
    judge_category_fit: Callable[[list[CompetitorProfile]], Awaitable[list[CompetitorProfile]]]
    | None = None,
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

    # Update runs use a time window anchored to the prior run's finish date so we only
    # fetch what has changed since then. Tavily supports: "day", "week", "month", "year".
    update_time_range: str | None = None
    if is_update:
        update_time_range = _time_range_since(prior_run_at)

    queries: list[SearchQuery] = build_search_queries(
        merchant_context,
        taxonomy=initial_taxonomy,
        time_range_override=update_time_range,
        include_leap=True,
    )
    taxonomy = initial_taxonomy

    # Scale guard: giants slip past the query's soft "-name" exclusions (semantic engines
    # ignore them), so discovery results are filtered deterministically before they accumulate.
    scale_signals = derive_scale_signals(merchant_context)
    # Where the merchant actually sells. For a geographically bound business a rival in another
    # city is not a rival at all, and the quoted place name in the query does not enforce that.
    geo_signals = derive_geo_signals(merchant_context)

    accumulated_search_results: list[TavilySearchResult] = []
    accumulated_extracted_pages: list[dict[str, Any]] = []
    accumulated_source_urls: list[str] = []
    preliminary_competitors: list[CompetitorProfile] = []
    dqs_result: DQSResult | None = None
    density: float = 0.0
    converged = False

    current_retries = initial_retries
    # Previous round's yield, for the plateau check below.
    last_competitor_count = -1
    last_dqs_score = -1.0
    locked_names: list[str] | None = None
    fit_verdicts: dict[str, tuple[float, str]] = {}

    async def _filtered(round_results: list[Any]) -> list[Any]:
        in_scale = filter_out_of_scale_results(round_results, scale_signals)
        in_area = filter_out_of_area_results(in_scale, geo_signals)
        if len(in_area) < len(in_scale):
            await _report(
                on_progress,
                f"[GEO_FILTER] Dropped {len(in_scale) - len(in_area)} result(s) serving a market "
                f"other than {geo_signals.raw}",
            )
        current = rank_by_recency(in_area, max_age_days=get_settings().recency_max_age_days)
        if len(current) < len(in_area):
            await _report(
                on_progress,
                f"[RECENCY] Dropped {len(in_area) - len(current)} result(s) published more than "
                f"{get_settings().recency_max_age_days} days ago",
            )
        return current

    while True:
        # Step A: Search subagent executes the query batch (incumbents filtered out by scale)
        round_results = await search_agent.run(queries, round_number=current_retries)
        accumulated_search_results.extend(await _filtered(round_results))

        # Step B: Identify who the competitors are. This precedes the crawl so the page budget
        # can be aimed at the shortlist; selecting crawl targets from raw search results spread
        # it across every host that appeared and left each real rival with a single page.
        preliminary_competitors = extract_preliminary_competitors(
            accumulated_search_results,
            merchant_context.get("known_competitors") or [],
            merchant_context=merchant_context,
        )
        preliminary_competitors = rank_competitors(
            preliminary_competitors,
            accumulated_search_results,
            merchant_context.get("known_competitors") or [],
            merchant_context=merchant_context,
        )

        # The list is settled once, from the first search, before any deep work starts. Later
        # rounds only deepen these rivals; anyone they newly surface joins the bench. Letting
        # the shortlist re-rank each round swapped rivals mid-run, so crawl and ad lookups
        # were spent on companies that then fell off the report.
        if locked_names is None:
            # One category query cannot surface every serious rival, so before locking, ask who
            # competes with the strongest names found. A rival missed by the first query but
            # known as an alternative to the leaders gets ranked before the list is settled
            # rather than landing on the bench after deep work has started.
            # Repeats while it keeps surfacing new strong names; stops once an iteration adds
            # nothing to the top 10, or after research_discovery_iterations.
            expanded: set[str] = set()
            for iteration in range(1, settings.research_discovery_iterations + 1):
                leaders = [
                    c.product_name for c in preliminary_competitors[:10] if c.product_name not in expanded
                ][:3]
                if not leaders:
                    break
                expanded.update(leaders)
                top_before = {c.product_name for c in preliminary_competitors[:10]}
                expansion = [
                    SearchQuery(
                        vector="alternative_discovery",
                        query=f'"{name}" (alternatives OR competitors OR "similar companies")',
                        time_range="year",
                    )
                    for name in leaders
                ]
                accumulated_search_results.extend(
                    await _filtered(await search_agent.run(expansion, round_number=current_retries))
                )
                preliminary_competitors = rank_competitors(
                    extract_preliminary_competitors(
                        accumulated_search_results,
                        merchant_context.get("known_competitors") or [],
                        merchant_context=merchant_context,
                    ),
                    accumulated_search_results,
                    merchant_context.get("known_competitors") or [],
                    merchant_context=merchant_context,
                )
                new_strong = {c.product_name for c in preliminary_competitors[:10]} - top_before
                await _report(
                    on_progress,
                    f"[DISCOVERY] Iteration {iteration}: alternatives to {', '.join(leaders)} -> "
                    f"{len(preliminary_competitors)} candidates, {len(new_strong)} new in the top 10",
                )
                if not new_strong:
                    break

            # Mention counts cannot tell a rival from a directory or a neighbouring category;
            # the final pick is by fit with the merchant's own category.
            if judge_category_fit is not None:
                try:
                    preliminary_competitors = await judge_category_fit(preliminary_competitors)
                except Exception as exc:
                    logger.warning("Category-fit judge hook failed: %s", exc)
                fit_verdicts = {
                    c.product_name: (c.relevance_score, c.relevance_reason)
                    for c in preliminary_competitors
                    if c.relevance_reason
                }
            # Named rivals are deep-researched on top of the usual discoveries, never instead
            # of them (see split_named).
            named_now, _, found_now = split_named(
                preliminary_competitors,
                merchant_context.get("merchant_named_competitors"),
                settings.research_max_named_competitors,
            )
            locked_names = [
                c.product_name for c in named_now + found_now[: settings.research_deep_crawl_competitors]
            ]
            await _report(
                on_progress,
                f"[COMPETITOR_LIST] {len(preliminary_competitors)} competitor(s) found; deep research "
                f"and ad search on: {', '.join(locked_names)}",
            )
        else:
            # Profiles are rebuilt each round, so re-apply the judge's verdicts: locked rivals
            # first, then the bench with judged misfits last.
            for c in preliminary_competitors:
                if c.product_name in fit_verdicts:
                    c.relevance_score, c.relevance_reason = fit_verdicts[c.product_name]
            order = {name: i for i, name in enumerate(locked_names)}
            preliminary_competitors.sort(
                key=lambda c: (
                    order.get(c.product_name, len(order)),
                    c.product_name in fit_verdicts and fit_verdicts[c.product_name][0] < 0.4,
                )
            )

        # Deep crawl and ad search start together on the same settled list. Ad lookups need
        # only names; a failure there must not abort the research loop.
        if on_first_competitors is not None and preliminary_competitors:
            try:
                await on_first_competitors(list(preliminary_competitors))
            except Exception as exc:
                logger.warning("on_first_competitors hook failed: %s", exc)
            on_first_competitors = None

        # Step C: Deep-crawl the shortlist's own domains, several pages each.
        shortlist = [c for c in preliminary_competitors if c.product_name in locked_names]
        target_urls = extract_competitor_target_urls(
            shortlist,
            accumulated_search_results,
            pages_per_competitor=settings.research_pages_per_competitor,
            max_urls=settings.deep_search_max_pages,
        )
        if shortlist:
            await _report(
                on_progress,
                f"[DEEP_TARGETS] Round {current_retries}: {len(target_urls)} page(s) across "
                f"{len(shortlist)} shortlisted competitor(s) "
                f"({', '.join(c.brand_name for c in shortlist[:5])})",
            )
        accumulated_source_urls = list({r.url for r in accumulated_search_results} | set(target_urls))
        new_pages = await crawl_agent.run(target_urls)
        accumulated_extracted_pages.extend(new_pages)

        # Crawled pages carry the pricing and claims the snippets lacked, so profiles are
        # rebuilt from the enlarged evidence set before they are scored.
        preliminary_competitors = enrich_competitors_from_pages(
            preliminary_competitors, accumulated_extracted_pages
        )

        # Step D: Dynamically update parameter taxonomy from crawled text
        raw_corpus = [r.snippet for r in accumulated_search_results] + [
            p["markdown"] for p in accumulated_extracted_pages if p.get("markdown")
        ]
        taxonomy = refine_parameters_from_findings(taxonomy, raw_corpus)

        # The framework was drafted from the merchant's brief before any competitor had been
        # looked at, and the regex refinement above can only adjust the minor attributes --
        # the critical drivers are whatever the opening guess made them. Once real pages are
        # in hand, a framework that nothing can be scored against is evidence the guess missed
        # this market's vocabulary, so it gets one chance to be rewritten against what was
        # actually found. Gated on density so a framework that is working costs no LLM call.
        if (
            revise_taxonomy is not None
            and accumulated_extracted_pages
            and calculate_attribute_density(preliminary_competitors, taxonomy)
            < _TAXONOMY_REVISION_DENSITY_FLOOR
        ):
            before = list(taxonomy.critical_jtbd_drivers)
            try:
                taxonomy = await revise_taxonomy(taxonomy, raw_corpus)
            except Exception as exc:
                logger.warning("Taxonomy revision hook failed: %s", exc)
            if taxonomy.critical_jtbd_drivers != before:
                await _report(
                    on_progress,
                    "[TAXONOMY_REVISED] Framework did not fit the evidence; critical drivers "
                    f"rewritten to: {', '.join(taxonomy.critical_jtbd_drivers)}",
                )
            revise_taxonomy = None

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

        # Plateau stop: a round that finds no new competitor and does not improve DQS will not
        # be rescued by running the same play again, and each extra round costs a search plus a
        # crawl and enlarges the synthesis corpus. Observed going 32 -> 44 -> 48 -> 48 with DQS
        # 0.77 -> 0.77 -> 0.76 -> 0.76: the last round was pure cost.
        # A round that crawled nothing new is also a plateau even if the count grew: growth past
        # the shortlist only adds bench names, which get no deep research this run.
        if (
            (len(preliminary_competitors) <= last_competitor_count or not new_pages)
            and dqs_result.score <= last_dqs_score + _PLATEAU_DQS_EPSILON
            and len(preliminary_competitors) >= settings.research_min_competitors
        ):
            await _report(
                on_progress,
                f"[PLATEAU_STOP] Round {current_retries} added no competitors and did not improve "
                f"DQS ({dqs_result.score:.2f}); stopping early instead of spending "
                f"{settings.dqs_max_retries - current_retries} more round(s)",
            )
            logger.info("Research loop plateaued at cycle %d — stopping early", current_retries)
            break
        last_competitor_count = len(preliminary_competitors)
        last_dqs_score = dqs_result.score

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
