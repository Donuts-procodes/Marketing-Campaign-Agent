"""
Tier 1 -- wedge scan: a broad, shallow sweep for every player in the merchant's niche.

The main research loop is built to find the rivals that dominate a category's search results,
then profile the top few in depth. That misses exactly the rival a small merchant most needs to
see: the brand that launched three months ago at the same size, is not ranking yet, and is only
visible on launch platforms and in forum threads. The loop also drops those sources on purpose
(a Reddit thread is evidence, never a competitor), so a brand that exists only there never
reaches the shortlist.

This scan covers that gap and stays cheap: three searches aimed at launches, launch platforms
and community threads, one light LLM call to name the niche and size each player, and no crawl.
Every brand it reports is either on its own site, on a launch-platform page, or named verbatim
in a passage we fetched; names a model offers that appear in no fetched text are discarded.

Depth is not the job here. A candidate worth a closer look is promoted with "research deeper",
which runs the full profile through the existing find-more flow.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from orchestrator.agents.market_research.analysis.archetype import (
    CREATOR as ARCH_CREATOR,
    ECOMMERCE as ARCH_ECOMMERCE,
    LOCAL as ARCH_LOCAL,
    SAAS as ARCH_SAAS,
    SERVICE as ARCH_SERVICE,
    resolve as resolve_archetype,
)
from orchestrator.agents.market_research.analysis.freshness import parse_iso_date
from orchestrator.agents.market_research.discovery.source_types import is_never_a_brand
from orchestrator.agents.market_research.discovery.search import (
    SearchQuery,
    TavilySearchResult,
    _clean_search_category,
)
from orchestrator.agents.market_research.pipeline.loop import (
    _norm_key,
    _time_range_since,
    extract_preliminary_competitors,
)
from orchestrator.core.clock import current_year, today as clock_today
from orchestrator.schemas.research import (
    CompetitorProfile,
    SWOTReportDelta,
    WedgeCandidate,
    WedgeScan,
)

logger = logging.getLogger(__name__)

SearchFn = Callable[[list[SearchQuery]], Awaitable[list[TavilySearchResult]]]

# A brand counts as emerging only when the evidence dates its launch or founding this recently.
# Being new to OUR scans is not the same thing: an agency founded in 2008 that we happen to
# see for the first time today is not emerging, and calling it so buries the real newcomers.
_EMERGING_LAUNCH_DAYS = 365

# Where a business shows up before its own site ranks anywhere. A dev agency or a local
# service does not launch on Kickstarter; it appears on an agency directory profile.
_LAUNCH_DOMAINS: dict[str, tuple[str, ...]] = {
    ARCH_ECOMMERCE: ("producthunt.com", "kickstarter.com", "indiegogo.com"),
    ARCH_SAAS: ("producthunt.com", "betalist.com", "indiehackers.com"),
    ARCH_CREATOR: ("producthunt.com", "kickstarter.com", "indiehackers.com"),
    ARCH_SERVICE: ("clutch.co", "goodfirms.co"),
    ARCH_LOCAL: ("clutch.co", "goodfirms.co"),
}
_DEFAULT_LAUNCH_DOMAINS = ("producthunt.com", "clutch.co")
_COMMUNITY_DOMAINS = ("reddit.com", "quora.com")

# How each business type announces itself; "new brand" finds nothing for an agency.
_EMERGING_TERMS: dict[str, str] = {
    ARCH_SERVICE: '("new agency" OR "newly founded" OR "launches" OR "opens" OR "founded in {y}" OR "founded in {y1}")',
    ARCH_LOCAL: '("now open" OR "newly opened" OR "opens" OR "founded in {y}" OR "founded in {y1}")',
    ARCH_SAAS: '("just launched" OR "launches" OR "launched today" OR "founded in {y}" OR "founded in {y1}")',
}
_DEFAULT_EMERGING_TERMS = (
    '("new brand" OR "just launched" OR "launches" OR "founded in {y}" OR "founded in {y1}")'
)

# Path shapes whose last segment is the product's or company's own name.
_LAUNCH_PATHS = (
    ("producthunt.com", re.compile(r"^/(?:products|posts)/([^/?#]+)")),
    ("kickstarter.com", re.compile(r"^/projects/[^/]+/([^/?#]+)")),
    ("indiegogo.com", re.compile(r"^/projects/([^/?#]+)")),
    ("betalist.com", re.compile(r"^/startups/([^/?#]+)")),
    ("clutch.co", re.compile(r"^/profile/([^/?#]+)")),
    ("goodfirms.co", re.compile(r"^/company/([^/?#]+)")),
)

# Platforms whose page date is the launch date (a product's launch post or campaign page).
_DATED_LAUNCH_PLATFORMS = frozenset({"producthunt.com", "kickstarter.com", "indiegogo.com", "betalist.com"})

# Hosts that are never a competitor live in discovery/source_types.py (shared with the deep
# crawl and profile completion).
# URL paths that mark an article, listing or document rather than a company's own site.
_NON_BRAND_PATH = re.compile(
    r"(?:\.pdf$|/(?:stocks?|news|blog|press|article|articles|research|document|documents|download|"
    r"dam|organizations?|companies|profile|price-guide|marketplace|frontend|history|collections)/)",
    re.I,
)

# Evidence phrases that size a company. Checked only inside passages naming the brand, so a
# "Series C" in a passage about someone else never sizes this one.
_INCUMBENT_CUES = re.compile(
    r"\b(publicly traded|nyse|nasdaq|fortune 500|billion[- ]dollar|\$\d+(?:\.\d+)?\s?b(?:illion)?\b"
    r"|global leader|market leader|largest\b)",
    re.I,
)
_LARGER_CUES = re.compile(
    r"\b(series [c-h]\b|unicorn|\$\d{2,3}\s?m(?:illion)?\b raised|raised \$\d{2,3}\s?m"
    r"|\d{3,}\+? (?:employees|stores|locations))",
    re.I,
)
# Cues about the brand's OWN size only. "small business" was dropped: it nearly always
# describes who a company sells to ("for small businesses"), which sized thoughtbot as a peer.
_PEER_CUES = re.compile(
    r"\b(bootstrapped|pre-seed|seed round|self-funded|small brand|indie brand|"
    r"independent brand|just launched|newly launched|crowdfund(?:ed|ing)|solo founder|"
    r"family[- ]owned|team of (?:[2-9]|1\d)\b|\b(?:[2-9]|1\d)[- ]person team)",
    re.I,
)
# Phrases that describe a company's CUSTOMERS' size. A size call resting on one is rejected
# whatever the classifier says: "we work with organizations of all sizes" sized thoughtbot,
# a 100+ person consultancy, as the merchant's peer.
_CUSTOMER_SIZE = re.compile(
    r"of all sizes|of every size|for (?:small|medium|mid-?sized|large)\b|small (?:and|&) medium|"
    r"\bsmbs?\b|\bsmes?\b|startups? (?:and|to|&) (?:enterprises?|large)|from startups|"
    r"(?:serv(?:e|es|ing)|help(?:s|ing)?|work(?:s|ing)? with) (?:small|startups|enterprises)",
    re.I,
)

# Passages per candidate sent to the classifier, and how many candidates it is asked about.
# A long list makes the model skip entries, and a skipped entry is now dropped as unverified.
_JUDGE_PASSAGES = 2
_JUDGE_MAX_CANDIDATES = 35
_SCALE_ORDER = {"peer": 0, "unknown": 1, "larger": 2, "incumbent": 3}
_VALID_SCALES = frozenset(_SCALE_ORDER)


WEDGE_PROMPT = """\
You are mapping one merchant's niche to find every brand it competes with, especially small \
and newly launched ones that a normal "best X" search misses.

You get the merchant's context and a list of candidate brands, each with evidence passages. \
Return:
1. wedge: one line naming the merchant's specific niche (segment + angle + buyer), not just \
the broad category. "Affordable everyday running shoes for first-time runners in India", not \
"Shoes".
2. For EVERY candidate, by its exact brand_name:
   - in_niche: true only when it sells something a buyer of the merchant's product would \
   genuinely consider instead. False for directories, blogs, publishers, marketplaces, \
   suppliers and different categories.
   - positioning: its one-line angle, taken from the evidence. Empty if the evidence states none.
   - scale: "peer" (roughly the merchant's size, or a small/new brand), "larger" (clearly \
   bigger: significant funding, wide distribution), "incumbent" (a category giant the \
   merchant cannot match on budget), or "unknown". Use "unknown" whenever the evidence does \
   not support a call. Do not use outside knowledge to size a brand.
   - scale_evidence: copy, word for word, the phrase from that brand's evidence that states \
   THE BRAND'S OWN size: its team size, funding, revenue, founding year, office or store count. \
   A phrase about its CUSTOMERS' size ("we work with organizations of all sizes", "for small \
   businesses") says nothing about the brand itself: use "unknown" then. Empty for unknown.
   - launch_date: ISO date (YYYY-MM-DD, or YYYY-MM-01 when only the month is stated) of the \
   brand's own launch or founding, stated in the evidence. Null when none is stated. A date on \
   a news story or a page is not a launch date.
3. discovered: brands NAMED in the community passages that are not already candidates and \
that are genuinely in the niche. For each, quote the passage words that name it. Only brands \
whose name appears verbatim in the passages.

Never return filler like "N/A" or "unknown" in positioning; leave it empty instead.
"""


class _CandidateJudgement(BaseModel):
    brand_name: str
    in_niche: bool = True
    positioning: str = ""
    scale: str = "unknown"
    scale_evidence: str = ""
    launch_date: str | None = None


class _DiscoveredBrand(BaseModel):
    brand_name: str
    quote: str = ""


class _WedgeJudgement(BaseModel):
    wedge: str = ""
    candidates: list[_CandidateJudgement] = Field(default_factory=list)
    discovered: list[_DiscoveredBrand] = Field(default_factory=list)


# ── Queries ────────────────────────────────────────────────────────────────────


def build_wedge_queries(
    merchant_context: dict[str, Any],
    baseline_date: str | None = None,
) -> list[SearchQuery]:
    """
    Three searches aimed where emerging brands show up first: launch coverage, launch
    platforms and community threads. A repeat scan narrows to the time since the last one,
    because the question it answers is "who is new since I last looked".
    """
    context_str = f"{merchant_context.get('category', '')} {merchant_context.get('business_model', '')}".lower()
    archetype = resolve_archetype(merchant_context, context_str)
    category = _clean_search_category(merchant_context.get("category", ""), archetype) or "products"
    geography = (merchant_context.get("target_geography") or "").strip()
    # A quoted multi-region phrase ("North America, Western Europe, Asia-Pacific") matches
    # almost no page verbatim and drags results toward whatever happens to contain it.
    single_region = geography and not re.search(r",|;|/|\band\b", geography) and len(geography) <= 40
    geo_clause = f' "{geography}"' if single_region else ""
    year = current_year()
    time_range = _time_range_since(baseline_date) if baseline_date else "year"

    terms = _EMERGING_TERMS.get(archetype, _DEFAULT_EMERGING_TERMS).format(y=year, y1=year - 1)
    emerging = f'"{category}" {terms}{geo_clause}'
    launch_domains = _LAUNCH_DOMAINS.get(archetype, _DEFAULT_LAUNCH_DOMAINS)
    launch = f'"{category}"{geo_clause}'
    community = (
        f'"{category}" ("anyone tried" OR "anyone used" OR underrated OR "hidden gem" OR '
        f'"alternative to" OR recommend){geo_clause}'
    )
    return [
        SearchQuery(vector="wedge_emerging", query=emerging, time_range=time_range),
        SearchQuery(vector="wedge_launch", query=launch, include_domains=launch_domains, time_range=time_range),
        # Community threads stay on a year window: a thread recommending a new brand is still
        # the best evidence that it exists, even on a repeat scan.
        SearchQuery(vector="wedge_community", query=community, include_domains=_COMMUNITY_DOMAINS, time_range="year"),
    ]


# ── Extraction ─────────────────────────────────────────────────────────────────


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").removeprefix("www.").lower()
    except Exception:
        return ""


def _launch_platform(url: str) -> str | None:
    host = _host(url)
    return next((d for d, _ in _LAUNCH_PATHS if host == d or host.endswith("." + d)), None)


def launch_candidate_name(url: str, title: str) -> str | None:
    """Product name from a launch-platform page: the title's lead, else the URL slug."""
    platform = _launch_platform(url)
    if platform is None:
        return None
    path = urlparse(url).path or ""
    pattern = dict(_LAUNCH_PATHS)[platform]
    match = pattern.match(path)
    if not match:
        return None  # a category or search page on the platform, not one product
    lead = re.split(r"\s+[|–—-]\s+|:\s+|\s+by\s+", title or "", maxsplit=1)[0].strip()
    platform_word = platform.split(".")[0]
    if lead and platform_word not in lead.lower() and len(lead) <= 60:
        return lead
    slug = match.group(1).replace("-", " ").replace("_", " ").strip()
    return slug.title() if slug else None


def _heuristic_scale(texts: list[str]) -> tuple[str, str]:
    """Deterministic scale call from sizing phrases in passages naming the brand."""
    for rx, scale in ((_INCUMBENT_CUES, "incumbent"), (_LARGER_CUES, "larger"), (_PEER_CUES, "peer")):
        for text in texts:
            m = rx.search(text)
            if m:
                return scale, m.group(0)
    return "unknown", ""


def _name_pattern(name: str) -> re.Pattern[str] | None:
    """Whole-word match for a brand name. A substring match counted "Hal" in every "half"."""
    name = (name or "").strip()
    if len(name) < 3:
        return None
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.I)


def _passages_naming(name: str, texts: list[str], limit: int = 3) -> list[str]:
    rx = _name_pattern(name)
    if rx is None:
        return []
    out: list[str] = []
    for t in texts:
        if t and rx.search(t):
            out.append(t[:600])
            if len(out) >= limit:
                break
    return out


def _count_mentions(name: str, texts: list[str]) -> int:
    rx = _name_pattern(name)
    return sum(1 for t in texts if t and rx.search(t)) if rx else 0


def _looks_like_brand_site(url: str) -> bool:
    """A company's own site, not an aggregator, a stock page, a news story or a PDF."""

    if is_never_a_brand(url):
        return False
    return not _NON_BRAND_PATH.search(urlparse(url).path or "")


def _merchant_keys(merchant_context: dict[str, Any]) -> set[str]:
    keys = set()
    for field in ("product_name", "brand_name", "company_name"):
        value = merchant_context.get(field)
        if isinstance(value, str) and value.strip():
            keys.add(_norm_key(value))
    return keys


def _collect_candidates(
    results: list[TavilySearchResult],
    report_competitors: list[CompetitorProfile],
    bench: list[CompetitorProfile],
    merchant_keys: set[str],
) -> dict[str, WedgeCandidate]:
    """Every brand the scan can stand behind, keyed by normalized name, in discovery order."""
    found: dict[str, WedgeCandidate] = {}

    def add(name: str, url: str | None, *, deep: bool = False, source: str | None = None) -> None:
        key = _norm_key(name)
        if not key or len(key) < 2 or key in merchant_keys or key == "unknown":
            return
        cand = found.get(key)
        if cand is None:
            cand = WedgeCandidate(brand_name=name.strip(), url=url, deep_researched=deep)
            found[key] = cand
        cand.deep_researched = cand.deep_researched or deep
        if not cand.url and url:
            cand.url = url
        if source and source not in cand.sources and len(cand.sources) < 5:
            cand.sources.append(source)

    for c in report_competitors:
        add(c.brand_name, c.sources[0] if c.sources else None, deep=True)
    for c in bench:
        add(c.brand_name, c.sources[0] if c.sources else None)

    launch_results = [r for r in results if r.url and _launch_platform(r.url)]
    other_results = [r for r in results if r.url and not _launch_platform(r.url)]

    for r in launch_results:
        name = launch_candidate_name(r.url, r.title)
        if name:
            add(name, r.url, source=r.url)

    # Brand sites among the emerging/launch results. The loop's extractor already refuses
    # forums, review sites and listicles; this scan's queries also pull in stock pages, data
    # aggregators and documents, so those are refused before extraction.
    site_results = [r for r in other_results if _looks_like_brand_site(r.url)]
    for profile in extract_preliminary_competitors(site_results):
        url = profile.sources[0] if profile.sources else None
        add(profile.brand_name, url, source=url)

    return found


# ── Classification ─────────────────────────────────────────────────────────────


def _valid_iso(value: str | None, today: date) -> str | None:
    parsed = parse_iso_date(value) if value else None
    if parsed is None or parsed > today + timedelta(days=1):
        return None
    return parsed.isoformat()


async def _judge(
    llm: Any,
    merchant_context: dict[str, Any],
    candidates: dict[str, WedgeCandidate],
    evidence: dict[str, list[str]],
    community_texts: list[str],
) -> _WedgeJudgement | None:
    merchant_keys = (
        "product_name", "category", "primary_value_prop", "target_audience", "price_usd",
        "target_geography", "business_model",
    )
    payload = {
        "merchant": {k: merchant_context.get(k) for k in merchant_keys if merchant_context.get(k)},
        "candidates": [
            {"brand_name": c.brand_name, "evidence": [t[:400] for t in evidence.get(key, [])[:_JUDGE_PASSAGES]]}
            for key, c in candidates.items()
        ],
        "community_passages": [t[:500] for t in community_texts[:12]],
    }
    result = await llm.with_structured_output(_WedgeJudgement).ainvoke([
        {"role": "system", "content": WEDGE_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ])
    if not isinstance(result, _WedgeJudgement):
        result = _WedgeJudgement.model_validate(result)
    return result


def _order(c: WedgeCandidate) -> tuple[int, int, int, int]:
    # Peers and unknowns first: the incumbent is already on the merchant's radar; the small
    # brand that launched last month is the one this scan exists to surface.
    return (_SCALE_ORDER.get(c.scale, 1), 0 if c.emerging else 1, 0 if c.deep_researched else 1, -c.mentions)


async def scan_wedge(
    merchant_context: dict[str, Any],
    report_competitors: list[CompetitorProfile],
    bench: list[CompetitorProfile],
    corpus: list[str],
    search_fn: SearchFn,
    llm: Any = None,
    baseline: SWOTReportDelta | None = None,
    baseline_date: str | None = None,
    max_candidates: int = 25,
) -> tuple[WedgeScan, list[str]]:
    """
    Runs the broad scan. Never raises for a search or LLM failure: whatever was found is
    returned, and the diagnostics say what was skipped.
    """
    today = clock_today()
    diagnostics: list[str] = []

    results: list[TavilySearchResult] = []
    try:
        results = await search_fn(build_wedge_queries(merchant_context, baseline_date))
    except Exception as exc:
        logger.warning("Wedge scan search failed: %s", exc)
        diagnostics.append(f"[WEDGE_FINDER] Emerging-brand search skipped ({type(exc).__name__}).")

    merchant_keys = _merchant_keys(merchant_context)
    candidates = _collect_candidates(results, report_competitors, bench, merchant_keys)

    scan_texts = [f"{r.title} {r.snippet}" for r in results if r.snippet]
    all_texts = scan_texts + [t for t in corpus if t]
    community_texts = [
        f"{r.title} {r.snippet}" for r in results if r.vector == "wedge_community" and r.snippet
    ]
    published = {r.url: parse_iso_date(r.published_date) for r in results if r.url and r.published_date}

    evidence = {key: _passages_naming(c.brand_name, all_texts) for key, c in candidates.items()}

    # Deterministic sizing first; the model may refine it, never replace it with a guess.
    for key, c in candidates.items():
        c.scale, c.scale_evidence = _heuristic_scale(evidence[key])

    # With a classifier available, only what it can verify is kept, so ask about the most
    # promising slice: every profiled rival, then the most-mentioned of the rest.
    if llm is not None and len(candidates) > _JUDGE_MAX_CANDIDATES:
        deep = [k for k, c in candidates.items() if c.deep_researched]
        rest = sorted(
            (k for k, c in candidates.items() if not c.deep_researched),
            key=lambda k: -len(evidence.get(k, [])),
        )
        keep = set(deep + rest[: max(0, _JUDGE_MAX_CANDIDATES - len(deep))])
        candidates = {k: c for k, c in candidates.items() if k in keep}

    wedge_line = ""
    judged = False
    if llm is not None and (candidates or community_texts):
        try:
            verdict = await _judge(llm, merchant_context, candidates, evidence, community_texts)
        except Exception as exc:
            logger.warning("Wedge scan classification failed: %s", exc)
            diagnostics.append(f"[WEDGE_FINDER] Niche classification skipped ({type(exc).__name__}).")
            verdict = None
        if verdict is not None:
            judged = True
            wedge_line = verdict.wedge.strip()
            by_key = {_norm_key(j.brand_name): j for j in verdict.candidates}
            dropped: list[str] = []
            unverified: list[str] = []
            for key in list(candidates):
                j = by_key.get(key)
                c = candidates[key]
                # Kept only on an explicit "in niche". A candidate the model skipped is
                # unverified, and keeping unverified names is how Visa and a stock page reached
                # the niche list. Fully profiled rivals stay regardless.
                if j is None:
                    if not c.deep_researched:
                        unverified.append(c.brand_name)
                        del candidates[key]
                    continue
                if not j.in_niche and not c.deep_researched:
                    dropped.append(c.brand_name)
                    del candidates[key]
                    continue
                c.positioning = j.positioning.strip()[:200]
                scale = j.scale.strip().lower()
                cited = j.scale_evidence.strip()
                passages = " ".join(evidence.get(key, [])).lower()
                # The model's size call stands only when the phrase it cites is really in this
                # brand's passages; otherwise the deterministic call (often "unknown") stands.
                if (
                    scale in _VALID_SCALES and scale != "unknown" and cited
                    and cited.lower() in passages and not _CUSTOMER_SIZE.search(cited)
                ):
                    c.scale, c.scale_evidence = scale, cited[:160]
                c.launch_date = _valid_iso(j.launch_date, today)
            if dropped:
                diagnostics.append(
                    f"[WEDGE_FINDER] Dropped {len(dropped)} out-of-niche result(s): {', '.join(dropped[:8])}."
                )
            if unverified:
                diagnostics.append(
                    f"[WEDGE_FINDER] Dropped {len(unverified)} unverified name(s): {', '.join(unverified[:8])}."
                )

            haystack = "\n".join(community_texts + scan_texts)
            added = 0
            for d in verdict.discovered:
                name = d.brand_name.strip()
                key = _norm_key(name)
                rx = _name_pattern(name)
                # Grounding guard: the name must be in text we actually fetched, as a whole word.
                if not key or key in candidates or key in merchant_keys or rx is None or not rx.search(haystack):
                    continue
                cand = WedgeCandidate(brand_name=name)
                candidates[key] = cand
                evidence[key] = _passages_naming(name, all_texts)
                cand.scale, cand.scale_evidence = _heuristic_scale(evidence[key])
                added += 1
            if added:
                diagnostics.append(f"[WEDGE_FINDER] {added} brand(s) found only in community threads.")

    # Carry first-seen dates forward. "New since last scan" is only meaningful against a
    # previous niche scan: compared with a run that had none, every name looks new.
    baseline_first_seen: dict[str, str | None] = {}
    baseline_keys: set[str] = set()
    comparable_baseline = baseline is not None and baseline.wedge_scan is not None
    if comparable_baseline:
        baseline_keys |= {_norm_key(c.brand_name) for c in baseline.competitors}
        for prior in baseline.wedge_scan.candidates:
            k = _norm_key(prior.brand_name)
            baseline_keys.add(k)
            baseline_first_seen[k] = prior.first_seen

    today_iso = today.isoformat()
    new_names: list[str] = []
    for key, c in candidates.items():
        c.mentions = _count_mentions(c.brand_name, all_texts)
        c.first_seen = baseline_first_seen.get(key) or today_iso
        if comparable_baseline and key not in baseline_keys:
            new_names.append(c.brand_name)

        launch = parse_iso_date(c.launch_date) if c.launch_date else None
        platform = _launch_platform(c.url) if c.url else None
        if launch is None and platform in _DATED_LAUNCH_PLATFORMS and published.get(c.url):
            # A dated Product Hunt / Kickstarter page is a launch date in all but name. A
            # directory profile's page date is not: it says when the listing was edited.
            launch = published[c.url]
            c.launch_date = launch.isoformat()
        # Emerging means new to the MARKET, proven by a dated launch or founding. Being new to
        # our scans is reported separately and never counts.
        c.emerging = launch is not None and (today - launch).days <= _EMERGING_LAUNCH_DAYS

    ordered = sorted(candidates.values(), key=_order)[:max_candidates]
    if not wedge_line:
        wedge_line = (merchant_context.get("category") or "").strip()

    scan = WedgeScan(
        wedge=wedge_line,
        scanned_at=today_iso,
        candidates=ordered,
        new_since_last_scan=[n for n in new_names if any(c.brand_name == n for c in ordered)],
    )

    peers = sum(1 for c in ordered if c.scale == "peer")
    emerging = [c.brand_name for c in ordered if c.emerging]
    diagnostics.insert(
        0,
        f"[WEDGE_FINDER] {len(ordered)} player(s) in the niche"
        + (f" “{wedge_line}”" if wedge_line else "")
        + f": {peers} peer-scale, {len(emerging)} emerging"
        + ("" if judged else " (sized from evidence phrases only)")
        + ".",
    )
    if emerging:
        diagnostics.append(f"[WEDGE_FINDER] Emerging: {', '.join(emerging[:8])}.")
    if scan.new_since_last_scan:
        diagnostics.append(f"[WEDGE_FINDER] New since last scan: {', '.join(scan.new_since_last_scan[:8])}.")
    return scan, diagnostics
