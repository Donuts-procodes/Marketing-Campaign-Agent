"""
Pre-crawl URL guard: HTTPS enforcement + relevance check.

Two cheap, deterministic passes that run before any crawl request is sent:

  1. HTTPS enforcement — HTTP URLs are upgraded when the hostname is trusted; otherwise
     dropped.  A plain-HTTP page in 2024 is almost always a redirect wall or a parked
     domain; crawling it is a wasted call and a potential security risk (MITM on the
     response).

  2. Path/domain relevance — skips URLs whose path or domain signals they cannot contain
     the content we are looking for (login walls, cart pages, CDN assets, irrelevant
     domain-to-vector combinations, etc.). Every skipped URL saves a CrawlAPI / Tavily
     Extract call, which is billed per page.

Both checks are deterministic and cost nothing.  They deliberately do not make network
requests (no HEAD call) — that would serialize the whole crawl budget and negate the
saving for borderline pages.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ── HTTPS enforcement ─────────────────────────────────────────────────────────

# Well-known domains that reliably serve HTTPS — upgrade rather than drop.
# We keep this list tight: anything not here stays at its original scheme.
_HTTPS_UPGRADE_TLDS = (".com", ".org", ".net", ".io", ".co", ".ai", ".app", ".dev")

# Domains we know redirect HTTP→HTTPS and whose crawl content is worth keeping.
_ALWAYS_UPGRADE = frozenset({
    "reddit.com", "g2.com", "capterra.com", "trustpilot.com",
    "sitejabber.com", "yelp.com", "bbb.org", "quora.com",
    "linkedin.com", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "youtube.com", "medium.com", "substack.com",
    "producthunt.com", "techcrunch.com", "forbes.com", "bloomberg.com",
})


def enforce_https(url: str) -> str | None:
    """
    Returns an https:// version of the URL, or None if the URL should be dropped.

    - Already https:// → returned unchanged.
    - http:// on a known-safe domain → upgraded to https://.
    - http:// on an unknown domain → dropped (could be a redirect trap or plain-HTTP
      only site with no TLS; not worth the risk or the extra redirect hop).
    - Non-http(s) scheme (ftp://, file://, etc.) → dropped.
    """
    if not url:
        return None

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()

    if scheme == "https":
        return url

    if scheme != "http":
        logger.debug("URL guard: dropped non-http(s) scheme %r: %s", scheme, url)
        return None

    hostname = (parsed.hostname or "").lower().removeprefix("www.")

    # Upgrade when the domain is explicitly trusted.
    if hostname in _ALWAYS_UPGRADE:
        upgraded = "https" + url[4:]
        logger.debug("URL guard: upgraded http→https for trusted domain %s", hostname)
        return upgraded

    # Upgrade when the TLD looks like a modern web property.
    if any(hostname.endswith(tld) for tld in _HTTPS_UPGRADE_TLDS):
        upgraded = "https" + url[4:]
        logger.debug("URL guard: upgraded http→https for %s", hostname)
        return upgraded

    logger.debug("URL guard: dropped plain-http URL (unknown domain): %s", url)
    return None


# ── Path relevance ────────────────────────────────────────────────────────────

# Path prefixes that guarantee non-content pages regardless of domain.
_BLOCKED_PATH_PREFIXES: tuple[str, ...] = (
    "/login", "/logout", "/signin", "/signup", "/register", "/auth",
    "/account", "/profile", "/settings", "/dashboard",
    "/cart", "/checkout", "/payment", "/order", "/basket",
    "/admin", "/wp-admin", "/wp-login",
    "/cdn-cgi",                          # Cloudflare internal
    "/static/", "/assets/", "/dist/",
    "/api/", "/graphql", "/webhook",
    "/unsubscribe", "/email-preferences",
    "/.well-known",
)

# File extensions that are assets, not web pages.  PDFs are intentionally kept
# because competitor pricing pages sometimes live in a PDF brochure.
_BLOCKED_EXTENSIONS: tuple[str, ...] = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".exe", ".dmg",
    ".xml",           # sitemaps / feeds, not readable content
    ".json",          # API responses (raw data, not prose)
)

# Path fragments that flag redirect, tracking, or ad pages.
_BLOCKED_PATH_PATTERNS = re.compile(
    r"/redirect|/track(ing)?|/click|/exit|/aff(iliate)?|/referral"
    r"|utm_|/pixel|/beacon|/analytics",
    re.IGNORECASE,
)


def is_crawlable_path(url: str) -> bool:
    """
    Returns False when the URL path signals the page cannot contain prose content
    relevant to market research (auth walls, assets, tracking endpoints, etc.).
    """
    parsed = urlparse(url)
    path = (parsed.path or "/").lower()

    if any(path.startswith(prefix) for prefix in _BLOCKED_PATH_PREFIXES):
        return False

    if any(path.endswith(ext) for ext in _BLOCKED_EXTENSIONS):
        return False

    if _BLOCKED_PATH_PATTERNS.search(parsed.query or ""):
        return False
    if _BLOCKED_PATH_PATTERNS.search(path):
        return False

    # Guard against deep blog/article branching (e.g. /blog/2022/08/15/how-to-...)
    segments = [s for s in path.split("/") if s]
    if len(segments) >= 3 and any(
        s in ("blog", "blogs", "article", "articles", "post", "posts", "news", "tag", "tags", "category", "categories", "author", "archive")
        for s in segments
    ):
        return False

    return True


# ── Domain-to-vector relevance ────────────────────────────────────────────────

# Domains that are only relevant for specific vectors.  A social-profile URL on
# a pricing_scrape vector is almost never going to have a pricing table on it.
# Keys are domain fragments (matched with `in`); values are the ALLOWED vectors.
_DOMAIN_VECTOR_ALLOW: dict[str, frozenset[str]] = {
    "reddit.com":       frozenset({"gripe_mining"}),
    "g2.com":           frozenset({"gripe_mining"}),
    "capterra.com":     frozenset({"gripe_mining"}),
    "trustpilot.com":   frozenset({"gripe_mining"}),
    "sitejabber.com":   frozenset({"gripe_mining"}),
    "yelp.com":         frozenset({"gripe_mining"}),
    "bbb.org":          frozenset({"gripe_mining"}),
    "quora.com":        frozenset({"gripe_mining", "alternative_discovery"}),
    "trustradius.com":  frozenset({"gripe_mining"}),
    "getapp.com":       frozenset({"gripe_mining"}),
    "sitejabber.com":   frozenset({"gripe_mining"}),
    # Job boards are useful for alternative_discovery (tech stack, company size)
    # but not for pricing or claims.
    "linkedin.com":     frozenset({"alternative_discovery"}),
    "glassdoor.com":    frozenset({"alternative_discovery"}),
    "indeed.com":       frozenset({"alternative_discovery"}),
    # News aggregators: useful for discovery and claims, not pricing.
    "producthunt.com":  frozenset({"alternative_discovery", "messaging_claims"}),
    "techcrunch.com":   frozenset({"alternative_discovery", "messaging_claims"}),
    "hackernews.com":   frozenset({"alternative_discovery"}),
    "news.ycombinator.com": frozenset({"alternative_discovery"}),
    # Social profiles are rarely useful for any vector.
    "twitter.com":      frozenset({"messaging_claims"}),
    "x.com":            frozenset({"messaging_claims"}),
    "facebook.com":     frozenset({"messaging_claims", "alternative_discovery"}),
    "instagram.com":    frozenset({"messaging_claims"}),
    "youtube.com":      frozenset({"messaging_claims", "alternative_discovery"}),
}

# Domains that are always irrelevant for market-research purposes.
_ALWAYS_BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "google.com", "google.co.uk", "google.ca",  # search results pages, not content
    "bing.com",
    "yahoo.com",
    "duckduckgo.com",
    "amazon.com",    # product pages are noisy; Ad Library is a different URL
    "ebay.com",
    "wikipedia.org", "wikimedia.org", # encyclopedic, not competitor intelligence
    "maps.google.com",
    "apple.com",     # app store pages don't carry competitor pricing prose
    "play.google.com",
    # Tutorial, academic, and advice networks that cause irrelevant deep branching
    "geeksforgeeks.org",
    "w3schools.com",
    "tutorialspoint.com",
    "stackoverflow.com",
    "stackexchange.com",
    "pewresearch.org",
    "nih.gov",
    "ncbi.nlm.nih.gov",
    "investopedia.com",
    "statista.com",
    "coursera.org",
    "udemy.com",
    "edx.org",
    "khanacademy.org",
    "medium.com",
    "substack.com",
    "scribd.com",
    "slideshare.net",
    "pinterest.com",
    # Ad and tracking networks.
    "doubleclick.net",
    "googleadservices.com",
    "googletagmanager.com",
    "googlesyndication.com",
    "adsystem.amazon.com",
    "facebook.net",
    "adnxs.com",
    "criteo.com",
    "taboola.com",
    "outbrain.com",
    # CDN / hosting infra — not content.
    "cloudflare.com",
    "amazonaws.com",
    "fastly.net",
    "cdn.jsdelivr.net",
    "unpkg.com",
})


def is_relevant_for_vector(url: str, vector: str) -> bool:
    """
    Returns False when the domain is known to be irrelevant for the given search vector,
    saving a crawl call that would return noise.

    Unknown domains (a competitor's own website) are always allowed — we only block when
    we positively know the domain cannot serve the right content for that vector.
    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().removeprefix("www.")

    if any(blocked in hostname for blocked in _ALWAYS_BLOCKED_DOMAINS):
        return False

    for fragment, allowed_vectors in _DOMAIN_VECTOR_ALLOW.items():
        if fragment in hostname:
            if vector not in allowed_vectors:
                logger.debug(
                    "URL guard: skipping %s for vector=%s (domain only relevant for %s)",
                    url, vector, allowed_vectors,
                )
                return False
            break  # domain matched and vector is allowed

    return True


# ── Main entry point ──────────────────────────────────────────────────────────

def filter_crawl_urls(
    url_vector_pairs: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """
    Runs HTTPS enforcement + path/domain relevance checks on a list of (url, vector)
    pairs and returns only those that pass all checks.

    Logs a single summary line at INFO level showing how many URLs were kept vs dropped
    and why, so the pipeline log stays readable without drowning in per-URL noise.
    """
    kept: list[tuple[str, str]] = []
    dropped_https = 0
    dropped_path = 0
    dropped_domain = 0

    for url, vector in url_vector_pairs:
        secure_url = enforce_https(url)
        if secure_url is None:
            dropped_https += 1
            continue

        if not is_crawlable_path(secure_url):
            dropped_path += 1
            logger.debug("URL guard: non-content path dropped: %s", secure_url)
            continue

        if not is_relevant_for_vector(secure_url, vector):
            dropped_domain += 1
            continue

        kept.append((secure_url, vector))

    total_dropped = dropped_https + dropped_path + dropped_domain
    if total_dropped:
        logger.info(
            "URL guard: kept %d/%d URLs (dropped %d insecure, %d non-content paths, %d wrong-domain-for-vector)",
            len(kept),
            len(kept) + total_dropped,
            dropped_https,
            dropped_path,
            dropped_domain,
        )

    return kept
