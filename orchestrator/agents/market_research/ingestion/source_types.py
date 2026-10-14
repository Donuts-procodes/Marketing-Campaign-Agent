"""
What kind of page a URL is, and which competitor it belongs to.

Three stages need the same answers and used to guess separately:
  - the deep crawl spent its page budget on GitHub, Clutch and Crunchbase as if they were
    competitors, so the real rivals' own sites were never read;
  - the wedge scan listed Visa, Robinhood and stock pages as "players in the niche";
  - profile facts on a Clutch or Crunchbase profile (founded, team size, rating) were ignored,
    because only pages on a rival's own domain were ever read for them.

One module now answers: is this host ever a competitor, is this page a company profile on a
directory, and if so, whose.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Never a competitor, however often it appears: data aggregators, directories, finance and
# stock pages, newswires, reference and code-hosting sites, payment networks, site builders.
NEVER_A_BRAND = frozenset({
    "crunchbase", "dealroom", "pitchbook", "rocketreach", "zoominfo", "cbinsights", "tracxn",
    "owler", "signalhire", "comparably", "glassdoor", "indeed", "builtin", "prospeo", "leadiq",
    "marketbeat", "robinhood", "msn", "yahoo", "bloomberg", "reuters", "cnbc", "marketwatch",
    "nasdaq", "nyse", "investing", "seekingalpha", "businesswire", "prnewswire", "globenewswire",
    "einpresswire", "drugs", "webmd", "hal", "arxiv", "researchgate", "springer", "sciencedirect",
    "academia", "scribd", "slideshare", "vendr", "superbcompanies", "clutch", "goodfirms",
    "designrush", "sortlist", "themanifest", "upwork", "fiverr", "toptal", "github", "gitlab",
    "stackoverflow", "visa", "mastercard", "paypal", "stripe", "apple", "microsoft", "aws",
    "amazonaws", "wordpress", "blogspot", "substack", "wix", "linkedin", "bootcamprankings",
    "webflow", "vercel", "netlify", "squarespace", "carrd", "framer", "shopify", "myshopify",
    "render", "fly", "heroku",
})

# Multi-tenant site-builder and hosting domains where subdomains identify user projects
# rather than the platform itself.
MULTI_TENANT_DOMAINS = frozenset({
    "webflow.io", "vercel.app", "netlify.app", "wixsite.com", "framer.app",
    "squarespace.com", "carrd.co", "myshopify.com", "github.io", "gitlab.io",
    "wordpress.com", "blogspot.com", "fly.dev", "herokuapp.com", "onrender.com",
})

# Company-profile pages on directories: the slug in the path names the company the page is
# about. These pages state exactly the facts a profile needs (founded, team size, rating,
# review count, hourly rate, minimum project), so they are read and credited to that company.
PROFILE_PATHS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("clutch.co", re.compile(r"^/profile/([^/?#]+)")),
    ("goodfirms.co", re.compile(r"^/company/([^/?#]+)")),
    ("crunchbase.com", re.compile(r"^/organization/([^/?#]+)")),
    ("linkedin.com", re.compile(r"^/company/([^/?#]+)")),
    ("designrush.com", re.compile(r"^/agency/profile/([^/?#]+)")),
    ("g2.com", re.compile(r"^/products/([^/?#]+)")),
    ("capterra.com", re.compile(r"^/p/\d+/([^/?#]+)")),
    ("trustpilot.com", re.compile(r"^/review/([^/?#]+)")),
    ("glassdoor.com", re.compile(r"^/Overview/Working-at-([^-/?#]+)", re.I)),
)
PROFILE_DOMAINS = tuple(d for d, _ in PROFILE_PATHS)

_LEGAL_SUFFIX = re.compile(
    r"[,\s]+(?:inc|inc\.|llc|l\.l\.c\.|ltd|ltd\.|limited|corp|corp\.|corporation|co\.|gmbh|"
    r"pvt|pvt\.|private limited|plc|s\.a\.|ag)$",
    re.I,
)


def registrable_label(url: str) -> str:
    """'microsoft' for store.microsoft.co.uk: the organisation part of a host."""
    host = (urlparse(url).hostname or "").lower()
    for mtd in MULTI_TENANT_DOMAINS:
        if host == mtd:
            return mtd.split(".")[0]
        if host.endswith("." + mtd):
            sub = host[: -len(mtd) - 1]
            sub_parts = sub.split(".")
            return sub_parts[-1] if sub_parts else mtd.split(".")[0]

    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "ac", "gov", "edu"} and len(parts[-1]) == 2:
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").removeprefix("www.").lower()
    except Exception:
        return ""


def is_never_a_brand(url_or_name: str) -> bool:
    """True for hosts (or bare brand names) that are never a competitor."""
    value = (url_or_name or "").strip()
    if not value:
        return False
    label = registrable_label(value) if "://" in value else re.sub(r"[^a-z0-9]", "", value.lower())
    return label in NEVER_A_BRAND


def norm_key(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def search_names(brand: str) -> list[str]:
    """
    The names a competitor is actually written as on the web.

    "Table XI (TXI)" was searched verbatim, brackets included; almost no page contains that
    string, so the rival came back with two sources. This returns "Table XI" and "TXI", and
    strips legal suffixes ("MojoTech Inc" -> "MojoTech").
    """
    brand = (brand or "").strip()
    if not brand:
        return []
    names: list[str] = []
    inner = re.findall(r"\(([^)]+)\)", brand)
    outer = re.sub(r"\s*\([^)]*\)", "", brand).strip()
    for n in [outer, *inner, brand if not inner else ""]:
        n = _LEGAL_SUFFIX.sub("", n).strip(" ,.-")
        if len(n) >= 2 and n not in names:
            names.append(n)
    return names


def name_pattern(name: str) -> re.Pattern[str] | None:
    """Whole-word, case-insensitive match. A substring match counted 'Hal' in every 'half'."""
    name = (name or "").strip()
    if len(name) < 2:
        return None
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.I)


def mentions(text: str, names: list[str]) -> bool:
    return any((rx := name_pattern(n)) is not None and rx.search(text or "") for n in names)


def profile_page_owner_slug(url: str) -> tuple[str, str] | None:
    """(directory domain, company slug) for a directory company-profile page, else None."""
    host = host_of(url)
    path = urlparse(url).path or ""
    for domain, rx in PROFILE_PATHS:
        if host == domain or host.endswith("." + domain):
            m = rx.match(path)
            if m:
                return domain, m.group(1)
    return None


def page_belongs_to(url: str, names: list[str], own_hosts: set[str]) -> bool:
    """
    True when a page is about this competitor: on its own site, or a directory profile whose
    slug is its name ("clutch.co/profile/big-nerd-ranch" belongs to Big Nerd Ranch).
    """
    host = host_of(url)
    if host:
        for h in own_hosts:
            if host == h:
                return True
            # Never treat subdomains of multi-tenant hosts as belonging to the platform
            if host.endswith("." + h) and h not in MULTI_TENANT_DOMAINS and not any(h.endswith("." + m) for m in MULTI_TENANT_DOMAINS):
                return True
    owned = profile_page_owner_slug(url)
    if owned is None:
        return False
    slug = norm_key(owned[1])
    keys = {norm_key(n) for n in names} | {norm_key(h.split(".")[0]) for h in own_hosts}
    # Exact, or slug carries a suffix the directory added ("thoughtbot-inc", "praxent-1").
    return any(k and (slug == k or slug.startswith(k)) and len(k) >= 3 for k in keys)


def merchant_identifiers(merchant_context: dict[str, Any] | None) -> tuple[set[str], set[str]]:
    """Returns (merchant_name_keys, merchant_hosts) normalized for matching against candidates."""
    if not merchant_context:
        return set(), set()

    raw_names = [
        merchant_context.get("product_name"),
        merchant_context.get("brand_name"),
        merchant_context.get("company_name"),
    ]
    raw_urls = [
        merchant_context.get("website"),
        merchant_context.get("url"),
    ]
    prod = str(merchant_context.get("product_name") or "")
    if "://" in prod or ("." in prod and " " not in prod):
        raw_urls.append(prod)

    name_keys: set[str] = set()
    for n in raw_names:
        if not n or not isinstance(n, str):
            continue
        for sn in search_names(n):
            k = norm_key(sn)
            if len(k) >= 3:
                name_keys.add(k)
        k_full = norm_key(n)
        if len(k_full) >= 3:
            name_keys.add(k_full)

    hosts: set[str] = set()
    for u in raw_urls:
        if not u or not isinstance(u, str):
            continue
        u_str = u if "://" in u else f"https://{u}"
        h = host_of(u_str)
        if h:
            hosts.add(h)
            lbl = registrable_label(u_str)
            if len(lbl) >= 3:
                name_keys.add(norm_key(lbl))

    return name_keys, hosts


def is_merchant_identity(
    brand_or_product: str,
    urls: list[str],
    merchant_name_keys: set[str],
    merchant_hosts: set[str],
) -> bool:
    """True if the brand/product or any of its source URLs belongs to the merchant."""
    if not merchant_name_keys and not merchant_hosts:
        return False

    for u in urls:
        h = host_of(u)
        if h and (h in merchant_hosts or any(h.endswith("." + mh) for mh in merchant_hosts)):
            return True
        lbl = norm_key(registrable_label(u))
        if lbl in merchant_name_keys:
            return True

    b_key = norm_key(brand_or_product)
    if not b_key:
        return False

    if b_key in merchant_name_keys:
        return True

    for mk in merchant_name_keys:
        if len(mk) >= 4 and (b_key == mk or b_key.startswith(mk) or mk.startswith(b_key)):
            return True

    return False


def resolve_logo_url(domain_or_url: str | None) -> str | None:
    """
    Resolves a high-resolution logo/favicon URL for a given domain or URL.
    Uses Google Favicon V2 high-res service with 128px rendering.
    """
    if not domain_or_url:
        return None
    host = host_of(domain_or_url) if "://" in domain_or_url else domain_or_url.strip().lower()
    host = host.removeprefix("www.").split("/")[0]
    if not host or "." not in host or is_never_a_brand(host):
        return None
    return f"https://www.google.com/s2/favicons?domain={host}&sz=128"
