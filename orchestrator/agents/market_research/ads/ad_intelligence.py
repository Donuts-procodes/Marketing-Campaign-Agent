"""
Competitor ad intelligence from live sources only:

  - Meta Ad Library      Graph API (ads_archive) when META_ACCESS_TOKEN is set, else the public
                         library page rendered through CrawlAPI
  - LinkedIn Ad Library  public ad library search page fetched through CrawlAPI
  - Google Ads           Ads Transparency Center page for the competitor's domain, via CrawlAPI
  - Web mentions         Tavily search for the competitor's ad copy and campaign taglines

Every hook is verbatim text from one of these sources, labelled with where it came from.
When nothing is found a competitor simply has no hooks; nothing is filled in.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from orchestrator.agents.market_research.discovery.crawlapi import CrawlAPIClient
from orchestrator.agents.market_research.discovery.search import SearchQuery, execute_tavily_search
from orchestrator.core.config import get_settings
from orchestrator.schemas.research import CompetitorProfile

logger = logging.getLogger(__name__)

META_LABEL = "Meta Ad Library"
LINKEDIN_LABEL = "LinkedIn Ad Library"
GOOGLE_LABEL = "Google Ads Transparency"
WEB_LABEL = "Web ad mention"

# Ad-library UI text that ends an ad's copy block.
_CARD_BOILERPLATE = re.compile(
    r"^(library id|started running|active|inactive|platforms|see ad details|see summary details|"
    r"this ad has multiple versions|open dropdown|learn more|shop now|sign up|book now|download|"
    r"contact us|apply now|get offer|subscribe|watch more|send message|view details|ad details|"
    r"promoted|sponsored|follow|\d+ ads? use this creative|sorry, we.re having trouble)",
    re.IGNORECASE,
)
_MIN_HOOK_CHARS = 25
_MAX_HOOK_CHARS = 300
_MAX_DOC_CHARS = 8000


@dataclass
class AdIntelResult:
    """Hooks per competitor plus the raw ad-library pages they were read from."""

    hooks_by_competitor: dict[str, list[str]] = field(default_factory=dict)
    documents: list[dict[str, str]] = field(default_factory=list)  # {"url", "markdown"}
    skipped: list[str] = field(default_factory=list)


def _platforms() -> list[str]:
    return [p.strip().lower() for p in get_settings().ad_library_platforms.split(",") if p.strip()]


def _country(merchant_geography: str | None) -> str:
    geo = (merchant_geography or "").strip()
    if len(geo) == 2 and geo.isalpha():
        return geo.upper()
    return get_settings().ad_library_country.upper()


def _brand_key(brand: str) -> str:
    return "".join(c for c in brand.lower() if c.isalnum())


def _competitor_domain(comp: CompetitorProfile) -> str | None:
    """The competitor's own website: a source whose domain carries the brand name."""
    key = _brand_key(comp.brand_name)
    if not key:
        return None
    for url in comp.sources:
        host = (urlparse(url).hostname or "").lower()
        host = host[4:] if host.startswith("www.") else host
        if key in host.replace("-", "").split(".")[0] or host.split(".")[0] == key:
            return host
    # Lookup query only: the Transparency Center page must still name the brand to be used.
    return f"{key}.com"


def _brand_matches(brand: str, text: str) -> bool:
    brand_l = brand.lower().strip()
    if not brand_l:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(brand_l)}(?![a-z0-9])", text.lower()) is not None


_AD_CONTEXT_RE = re.compile(
    r"\b(ad|ads|advert\w*|campaign|commercial|tagline|slogan|sponsored|billboard|promo\w*)\b", re.IGNORECASE
)


def _hook(label: str, text: str) -> str:
    clean = " ".join(text.split())[:_MAX_HOOK_CHARS]
    return f'{label}: "{clean}"'


_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _clean_markdown_line(line: str) -> str:
    """Drops images, keeps link text, and strips emphasis/heading markers."""
    line = _MD_IMAGE_RE.sub("", line)
    line = _MD_LINK_RE.sub(r"\1", line)
    return re.sub(r"[*_#>\[\]]", "", line).strip()


def parse_ad_cards(markdown: str, marker: str, brand: str) -> list[str]:
    """
    Pulls ad copy out of a rendered ad-library page: the text that follows each `marker`
    line ("Sponsored" on Meta, "Promoted" on LinkedIn) whose advertiser line (just above the
    marker) names the brand. Returns verbatim copy only.
    """
    lines = [_clean_markdown_line(ln) for ln in markdown.splitlines()]
    lines = [ln for ln in lines if ln]
    copies: list[str] = []
    for i, line in enumerate(lines):
        if line.lower() != marker.lower():
            continue
        advertiser = lines[i - 1] if i > 0 else ""
        if not _brand_matches(brand, advertiser):
            continue
        body: list[str] = []
        for nxt in lines[i + 1 : i + 6]:
            if _CARD_BOILERPLATE.match(nxt) or nxt.lower().startswith(("http", "(http")):
                break
            body.append(nxt)
        copy = " ".join(body).strip()
        if len(copy) >= _MIN_HOOK_CHARS and copy not in copies:
            copies.append(copy)
    return copies


# ── Meta ─────────────────────────────────────────────────────────────────────

def meta_library_url(brand: str, country: str) -> str:
    return (
        "https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
        f"&country={country}&q={quote_plus(brand)}&search_type=keyword_unordered&media_type=all"
    )


async def _meta_graph_api(brand: str) -> tuple[list[str], dict[str, str] | None]:
    settings = get_settings()
    countries = [c.strip().upper() for c in settings.meta_ad_reached_countries.split(",") if c.strip()]
    params = {
        "access_token": settings.meta_access_token,
        "search_terms": brand,
        "ad_reached_countries": json.dumps(countries),
        "ad_active_status": "ACTIVE",
        "ad_type": "ALL",
        "fields": "page_name,ad_creative_bodies,ad_creative_link_titles,ad_creative_link_descriptions,ad_snapshot_url",
        "limit": 25,
    }
    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/ads_archive"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)
    if response.status_code != 200:
        # Never surface the request URL: it carries the access token.
        try:
            reason = response.json().get("error", {}).get("message", "")
        except ValueError:
            reason = ""
        raise RuntimeError(f"Meta Ad Library API HTTP {response.status_code}: {reason[:200]}")

    copies: list[str] = []
    doc_lines: list[str] = []
    for ad in response.json().get("data", []):
        page_name = ad.get("page_name", "")
        if not _brand_matches(brand, page_name):
            continue
        texts = (ad.get("ad_creative_link_titles") or []) + (ad.get("ad_creative_bodies") or []) + (
            ad.get("ad_creative_link_descriptions") or []
        )
        for text in texts:
            text = " ".join((text or "").split())
            if len(text) >= _MIN_HOOK_CHARS and text not in copies:
                copies.append(text)
        if texts:
            doc_lines.append(f"Advertiser: {page_name}\nSnapshot: {ad.get('ad_snapshot_url', '')}\n" + "\n".join(texts))

    document = None
    if doc_lines:
        document = {"url": meta_library_url(brand, countries[0] if countries else "ALL"), "markdown": "\n\n".join(doc_lines)}
    return copies, document


async def _meta_ads(brand: str, country: str, crawl_client: CrawlAPIClient) -> tuple[list[str], dict[str, str] | None]:
    if get_settings().meta_access_token:
        try:
            return await _meta_graph_api(brand)
        except Exception as exc:
            logger.warning("Meta Ad Library API failed for %s, trying the public library page: %s", brand, exc)

    url = meta_library_url(brand, country)
    page = await crawl_client.fetch(url, javascript=True, page_wait_ms=5000, scroll=True)
    markdown = page.get("body", "")
    copies = parse_ad_cards(markdown, "Sponsored", brand)
    document = {"url": url, "markdown": markdown[:_MAX_DOC_CHARS]} if _brand_matches(brand, markdown) else None
    return copies, document


# ── LinkedIn ─────────────────────────────────────────────────────────────────

def linkedin_library_url(brand: str) -> str:
    return f"https://www.linkedin.com/ad-library/search?keyword={quote_plus(brand)}"


async def _linkedin_ads(brand: str, crawl_client: CrawlAPIClient) -> tuple[list[str], dict[str, str] | None]:
    url = linkedin_library_url(brand)
    # LinkedIn blocks Firecrawl, so this page always goes through Crawlbase.
    extra = {"provider": "crawlbase"} if getattr(crawl_client, "provider", None) == "firecrawl" else {}
    page = await crawl_client.fetch(url, javascript=bool(getattr(crawl_client, "js_token", False)), page_wait_ms=3000, **extra)
    markdown = page.get("body", "")
    copies = parse_ad_cards(markdown, "Promoted", brand)
    document = {"url": url, "markdown": markdown[:_MAX_DOC_CHARS]} if _brand_matches(brand, markdown) else None
    return copies, document


# ── Google ───────────────────────────────────────────────────────────────────

def google_transparency_url(domain: str, country: str) -> str:
    return f"https://adstransparency.google.com/?region={country}&domain={quote_plus(domain)}"


_GOOGLE_AD_COUNT_RE = re.compile(r"^(~?[\d.,]+\s?[KkMm]?\+?)\s+ads?$")


def parse_google_activity(markdown: str, brand: str, country: str) -> str | None:
    """
    Google shows creatives (even text ads) as images, so the page yields activity facts rather
    than copy: the verified advertiser accounts and how many ads point at the domain.
    """
    lines = [re.sub(r"[*_]", "", ln).strip() for ln in markdown.splitlines()]
    lines = [ln for ln in lines if ln]
    count = next((m.group(1) for ln in lines if (m := _GOOGLE_AD_COUNT_RE.match(ln))), None)
    advertisers = list(dict.fromkeys(
        lines[i - 1] for i, ln in enumerate(lines) if ln == "Verified" and i > 0 and _brand_matches(brand, lines[i - 1])
    ))
    if not (count and advertisers):
        return None
    return f"{', '.join(advertisers[:2])} (Verified) — {count} ads in {country}"


async def _google_ads(
    domain: str, brand: str, country: str, crawl_client: CrawlAPIClient
) -> tuple[list[str], dict[str, str] | None]:
    """Returns (activity summary lines, page document) from the Ads Transparency Center."""
    url = google_transparency_url(domain, country)
    page = await crawl_client.fetch(url, javascript=True, page_wait_ms=6000, scroll=True)
    markdown = page.get("body", "")
    if not (_brand_matches(brand, markdown) or domain.lower() in markdown.lower()):
        return [], None
    activity = parse_google_activity(markdown, brand, country)
    return ([activity] if activity else []), {"url": url, "markdown": markdown[:_MAX_DOC_CHARS]}


# ── Web mentions (Tavily) ────────────────────────────────────────────────────

async def _web_mentions(
    competitors: list[CompetitorProfile], tavily_client: Any, category: str = ""
) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    """Hooks per competitor, plus the snippets they came from as evidence documents."""
    # Two queries per competitor: a specific ad-copy search, and a broader brand
    # messaging search so something always surfaces even without ad library access.
    queries = []
    for comp in competitors:
        brand = comp.brand_name
        queries.append(SearchQuery(
            vector="ad_intelligence",
            query=f'"{brand}" {category} ("sponsored ad" OR "ad copy" OR "campaign tagline" OR "new campaign" OR slogan)',
        ))
        queries.append(SearchQuery(
            vector="ad_intelligence",
            query=f'"{brand}" (marketing OR "value proposition" OR "why choose" OR "how it works" OR tagline OR headline)',
        ))

    results = await execute_tavily_search(queries, tavily_client=tavily_client)
    mentions: dict[str, list[str]] = {}
    # The grounding gate checks every hook against the evidence corpus; these snippets come from
    # a search of their own, so without them as documents every web-mention hook was dropped.
    documents: list[dict[str, str]] = []
    for comp in competitors:
        found: list[str] = []
        for r in results:
            snippet = r.snippet or ""
            if len(snippet) < _MIN_HOOK_CHARS:
                continue
            if not _brand_matches(comp.brand_name, snippet):
                continue
            # Accept ad-context snippets OR messaging snippets (broader net for
            # brands that don't appear in ad libraries).
            is_ad_context = _AD_CONTEXT_RE.search(snippet)
            is_messaging = re.search(
                r"\b(tagline|headline|slogan|value prop|why choose|how it works|mission|vision)\b",
                snippet, re.IGNORECASE,
            )
            if not (is_ad_context or is_messaging):
                continue
            hook = _hook(WEB_LABEL, snippet)
            if hook not in found:
                found.append(hook)
                if r.url:
                    documents.append({"url": r.url, "markdown": snippet})
        mentions[comp.product_name] = found
    return mentions, documents


# ── Coordinator ──────────────────────────────────────────────────────────────

async def search_competitor_ad_hooks(
    competitors: list[CompetitorProfile],
    category: str,
    tavily_client: Any = None,
    crawl_client: Any = None,
    target_geography: str | None = None,
    max_competitors: int | None = None,
    max_hooks_per_comp: int = 6,
) -> AdIntelResult:
    """
    Collects real ad copy for the top competitors from the Meta, LinkedIn and Google ad
    libraries (where credentials allow) plus Tavily web mentions.
    """
    settings = get_settings()
    targets = competitors[: max_competitors or settings.ad_library_max_competitors]
    country = _country(target_geography)
    platforms = _platforms()
    crawl_client = crawl_client if crawl_client is not None else CrawlAPIClient()
    has_crawl = bool(getattr(crawl_client, "configured", True))
    has_js = bool(getattr(crawl_client, "can_render_js", True))

    result = AdIntelResult()
    if "meta" in platforms and not (settings.meta_access_token or has_js):
        result.skipped.append("Meta Ad Library (set META_ACCESS_TOKEN, FIRECRAWL_API_KEY or CRAWLAPI_JS_TOKEN)")
        platforms.remove("meta")
    firecrawl_only = getattr(crawl_client, "provider", None) == "firecrawl" and not (
        getattr(crawl_client, "token", "") or getattr(crawl_client, "js_token", "")
    )
    if "linkedin" in platforms and (not has_crawl or firecrawl_only):
        result.skipped.append("LinkedIn Ad Library (blocks Firecrawl; set CRAWLAPI_TOKEN for Crawlbase)")
        platforms.remove("linkedin")
    if "google" in platforms and not has_js:
        result.skipped.append("Google Ads Transparency (set FIRECRAWL_API_KEY or CRAWLAPI_JS_TOKEN)")
        platforms.remove("google")

    library_hooks: dict[str, list[str]] = {c.product_name: [] for c in targets}

    async def _collect(comp: CompetitorProfile, platform: str) -> None:
        brand = comp.brand_name
        try:
            if platform == "meta":
                copies, doc = await _meta_ads(brand, country, crawl_client)
                library_hooks[comp.product_name].extend(_hook(META_LABEL, c) for c in copies)
            elif platform == "linkedin":
                copies, doc = await _linkedin_ads(brand, crawl_client)
                library_hooks[comp.product_name].extend(_hook(LINKEDIN_LABEL, c) for c in copies)
            elif platform == "google":
                domain = _competitor_domain(comp)
                if not domain:
                    return
                activity, doc = await _google_ads(domain, brand, country, crawl_client)
                library_hooks[comp.product_name].extend(_hook(GOOGLE_LABEL, a) for a in activity)
            else:
                return
        except Exception as exc:
            logger.warning("%s ad lookup failed for %s: %s", platform, brand, exc)
            return
        if doc:
            result.documents.append(doc)

    library_task = asyncio.gather(*[_collect(c, p) for c in targets for p in platforms])
    mentions_task = _web_mentions(targets, tavily_client, category)
    _, (mentions, mention_docs) = await asyncio.gather(library_task, mentions_task)

    for comp in targets:
        # Web mentions describe ads second-hand; use them only when no ad library had real copy.
        library = library_hooks.get(comp.product_name, [])
        hooks = list(dict.fromkeys(library or mentions.get(comp.product_name, [])))
        result.hooks_by_competitor[comp.product_name] = hooks[:max_hooks_per_comp]
        if not library:
            used = set(hooks[:max_hooks_per_comp])
            result.documents.extend(
                d for d in mention_docs if _hook(WEB_LABEL, d["markdown"]) in used and d not in result.documents
            )

    return result
