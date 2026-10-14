"""
Channel listings: where each rival's product is sold, and at what price, offer and terms.

The same product is listed on the brand's own site and on several marketplaces, each with its own
selling price, MRP, coupon or bank offer, rating, return window and COD option. Buying patterns
only say "sells on Myntra"; the campaign planner needs to know it sells there at ₹5,999 with 40%
off and a 7-day exchange, because that sets the price expectation the merchant's ads meet.

Pipeline: one site-restricted search per rival over the region's marketplaces → fetch the listing
pages that belong to that rival → read the values with patterns. Every value is read from the page
text; nothing is inferred, and a page that never names the rival is dropped. Listings are volatile,
so their searches are never reused across runs (see search._VOLATILE_VECTORS).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from orchestrator.agents.market_research.ingestion.search_client import SearchQuery, TavilySearchResult
from orchestrator.agents.market_research.ingestion.source_types import host_of, mentions, resolve_logo_url, search_names
from orchestrator.agents.market_research.workflow.research_loop import _extract_product_image_url
from orchestrator.core.clock import today as clock_today
from orchestrator.schemas.research import ChannelListing, CompetitorProfile, ListingItem, SWOTReportDelta

logger = logging.getLogger(__name__)

SearchFn = Callable[[list[SearchQuery]], Awaitable[list[TavilySearchResult]]]
CrawlFn = Callable[[list[str]], Awaitable[list[dict[str, Any]]]]
# (rival, merchant product or None, currency, marketplace hosts) -> cited listings
AISearchFn = Callable[[CompetitorProfile, dict[str, Any] | None, str | None, list[str]], Awaitable[list[ChannelListing]]]

VECTOR = "channel_listings"
# Each merchant product costs one search batch, so a long line is capped.
MAX_PRODUCTS = 5

# Marketplaces worth checking per market. Hosts only; a listing's site_type comes from here.
MARKETPLACES: dict[str, list[tuple[str, str]]] = {
    # India: the two everything-stores; category stores are added by CATEGORY_STORES.
    "IN": [("amazon.in", "marketplace"), ("flipkart.com", "marketplace")],
    "US": [
        ("amazon.com", "marketplace"), ("walmart.com", "marketplace"), ("target.com", "marketplace"),
        ("ebay.com", "marketplace"), ("etsy.com", "marketplace"),
    ],
    "UK": [("amazon.co.uk", "marketplace"), ("ebay.co.uk", "marketplace"), ("asos.com", "marketplace")],
    "AE": [("amazon.ae", "marketplace"), ("noon.com", "marketplace"), ("namshi.com", "marketplace")],
}

_CURRENCY_FOR_MARKET = {"IN": "INR", "US": "USD", "UK": "GBP", "AE": "AED"}
MARKET_NAMES = {"IN": "India", "US": "the United States", "UK": "the United Kingdom", "AE": "the UAE"}

_MARKET_WORDS = [
    ("IN", r"\b(india|delhi|ncr|mumbai|bengaluru|bangalore|hyderabad|chennai|pune|kolkata|gurugram|noida)\b|₹"),
    ("UK", r"\b(uk|united kingdom|london|england)\b"),
    ("AE", r"\b(uae|dubai|abu dhabi)\b"),
    ("US", r"\b(usa|united states|new york|california|texas)\b"),
]


def market_of(merchant_context: dict[str, Any]) -> str | None:
    text = " ".join(str(merchant_context.get(k) or "") for k in ("target_geography", "currency", "budget")).lower()
    if "inr" in text:
        return "IN"
    for code, pattern in _MARKET_WORDS:
        if re.search(pattern, text):
            return code
    return None


# Category stores checked on top of the general marketplaces, matched on the merchant's category.
CATEGORY_STORES: dict[str, list[tuple[str, list[tuple[str, str]]]]] = {
    "IN": [
        (r"fashion|apparel|cloth|wear|shoe|footwear|sneaker|bag|jewel|accessor|kurta|saree|dress|shirt|jeans",
         [("myntra.com", "marketplace"), ("ajio.com", "marketplace"), ("tatacliq.com", "marketplace"),
          ("nykaafashion.com", "marketplace")]),
        (r"electronic|phone|mobile|laptop|headphone|earbud|speaker|tv\b|appliance|camera|gadget|watch",
         [("croma.com", "marketplace"), ("reliancedigital.in", "marketplace"), ("tatacliq.com", "marketplace")]),
        (r"beauty|skin|cosmetic|makeup|hair|serum|fragrance|perfume|personal care",
         [("nykaa.com", "marketplace"), ("purplle.com", "marketplace")]),
        (r"grocery|food|snack|beverage|drink|tea|coffee|fmcg|household|cleaning|dairy",
         [("blinkit.com", "quick_commerce"), ("zeptonow.com", "quick_commerce"),
          ("swiggy.com", "quick_commerce"), ("bigbasket.com", "quick_commerce")]),
        (r"baby|kid|toy|diaper", [("firstcry.com", "marketplace")]),
    ],
}
# Value marketplaces worth checking for most consumer goods in the market.
_GENERAL_EXTRA = {"IN": [("meesho.com", "marketplace"), ("snapdeal.com", "marketplace"), ("jiomart.com", "marketplace")]}
# A site-restricted search spreads its results across these hosts; past this many, each store gets too few.
MAX_STORES = 9


def marketplaces_for(merchant_context: dict[str, Any]) -> list[tuple[str, str]]:
    """The market's main marketplaces, then stores that specialise in the merchant's category."""
    market = market_of(merchant_context) or ""
    category = " ".join(str(merchant_context.get(k) or "") for k in ("category", "product_name")).lower()
    specialist = [s for pattern, stores in CATEGORY_STORES.get(market, []) if re.search(pattern, category) for s in stores]
    stores = specialist + MARKETPLACES.get(market, []) + _GENERAL_EXTRA.get(market, [])
    # Specialists first so they survive the cap; the big marketplaces are always in it.
    seen: dict[str, str] = {}
    for host, kind in stores:
        seen.setdefault(host, kind)
    return list(seen.items())[:MAX_STORES]


def merchant_products(merchant_context: dict[str, Any]) -> list[dict[str, Any]]:
    """The merchant's product line, or [] for a single-product merchant (rivals' own products are used)."""
    products = [p for p in merchant_context.get("products") or [] if isinstance(p, dict) and p.get("name")]
    return products[:MAX_PRODUCTS]


def _descriptor(product: dict[str, Any] | None, comp: CompetitorProfile) -> str:
    """What to look for on the rival's listings: the merchant product's category, else the rival's product."""
    if product:
        return str(product.get("category") or product.get("name") or "").strip()
    name = (comp.product_name or "").strip()
    return name if name.lower() != comp.brand_name.lower() else ""


def build_listing_queries(
    competitors: list[CompetitorProfile], hosts: list[str], product: dict[str, Any] | None = None
) -> list[SearchQuery]:
    """One site-restricted query per rival across the region's marketplaces, for one merchant product."""
    queries = []
    for comp in competitors:
        brand = (search_names(comp.brand_name) or [comp.brand_name])[0]
        what = _descriptor(product, comp)
        term = f'"{brand}" {what} (price OR MRP OR buy)' if what else f'"{brand}" (price OR MRP OR buy)'
        queries.append(SearchQuery(vector=VECTOR, query=term, search_depth="basic", include_domains=tuple(hosts)))
    return queries


# ── Reading a listing page ──────────────────────────────────────────────────────

# Word-bounded: "stars. 28 reviews" must not read as "Rs. 28".
_SYM = r"(?:₹|\brs\.?|\binr\b|\$|\busd\b|£|\bgbp\b|€|\beur\b|\baed\b)"
_AMOUNT = rf"{_SYM}\s*([\d,]+(?:\.\d{{1,2}})?)"
_MRP = re.compile(rf"(?:m\.?r\.?p\.?|list price|was|original price)[^\d₹$£€]{{0,20}}{_AMOUNT}", re.I)
_PRICE = re.compile(_AMOUNT, re.I)
_DISCOUNT = re.compile(r"(?:\(?\s*(\d{1,2})\s*%\s*off\b|(?<![\w-])-\s?(\d{1,2})\s?%)", re.I)
# Amazon writes "_1.4 out of 5 stars_", so the left edge is "not a digit", not a word boundary.
_RATING = re.compile(r"(?<![\d.])([1-5](?:\.\d)?)\s*(?:out of 5\b|/\s*5\b|★|stars?\b)", re.I)
_REVIEWS = re.compile(r"\b([\d,]{1,9})\s*(?:global\s+)?(?:ratings?|reviews?)\b", re.I)
_VELOCITY = re.compile(r"([\d,.]+k?\+?\s*bought in (?:the )?past (?:month|week))|\b(best\s?seller)\b", re.I)
# The whole line around an offer keyword: "Upto ₹209.00 cashback…" must not be cut at the decimal point.
_OFFER = re.compile(
    r"[^\n]{0,80}\b(bank offer|cashback|coupon|use code|promo code|extra \d{1,2}% off|buy \d+ get \d+|no cost emi|"
    r"prepaid|first order|discount on)\b[^\n]{0,80}", re.I)
_RETURNS = re.compile(r"[^.\n]{0,60}\b(\d{1,2})[- ]day[s]?\b[^.\n]{0,20}\b(return|exchange|replacement)[^.\n]{0,60}", re.I)
_NO_RETURNS = re.compile(r"\b(non[- ]returnable|no returns?)\b", re.I)
_COD = re.compile(r"\b(cash on delivery|pay on delivery|cod available)\b", re.I)
_NO_COD = re.compile(r"\b(cod not available|cash on delivery not available|pay on delivery not available)\b", re.I)
_DELIVERY = re.compile(r"[^.\n]{0,40}\b(free delivery|free shipping|delivery by|get it by|ships in)\b[^.\n]{0,60}", re.I)
_SOLD_BY = re.compile(r"\b(?:sold by|seller)\s*:?\s*([A-Z][\w&.' -]{2,40})", re.I)

# Machine-readable buy-box price: Amazon's buybox JSON, schema.org Offer JSON-LD, product meta.
_STRUCTURED_PRICE = [
    re.compile(r'"priceAmount"\s*:\s*"?([\d.]+)'),
    re.compile(r'"@type"\s*:\s*"Offer"[^{}]{0,400}?"price"\s*:\s*"?([\d,]+(?:\.\d+)?)'),
    re.compile(r'product:price:amount"?\s+content="([\d.]+)'),
]
# An amount in a promo, EMI, filter or nav line is not the product's price.
_NOISE_BEFORE = re.compile(
    r"(under|upto|up to|cashback|emi|save|savings|discount|above|over|min(?:imum)?|starts at|worth|"
    r"interest|coupon|extra|flat|get)\W{0,12}$", re.I)
_NOISE_AFTER = re.compile(r"^[\d.,]*\s*(?:per month|/\s*mo|cashback|off\b|discount|emi|interest)", re.I)
# Carousel items ("Customers also viewed") are markdown links: [₹5,490.00](http…).
_IN_LINK = re.compile(r"^[^\[\]\n]{0,80}\]\(https?:", re.I)


_SYMBOL_CCY = (("₹", "INR"), ("rs", "INR"), ("inr", "INR"), ("£", "GBP"), ("gbp", "GBP"), ("€", "EUR"),
               ("eur", "EUR"), ("aed", "AED"), ("usd", "USD"), ("$", "$"))
_DOLLAR_CCYS = {"USD", "AUD", "CAD", "SGD", "NZD", "HKD"}


def page_currency(text: str, default: str | None) -> str | None:
    """The currency most of the page's prices are written in; "$" follows a dollar market's own currency."""
    counts: dict[str, int] = {}
    for m in _PRICE.finditer(text):
        sym = m.group(0).strip().lower()
        code = next((c for s, c in _SYMBOL_CCY if sym.startswith(s)), None)
        if code == "$":
            code = default if default in _DOLLAR_CCYS else "USD"
        if code:
            counts[code] = counts.get(code, 0) + 1
    return max(counts, key=counts.get) if counts else default


def _num(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _mode(values: list[float]) -> float | None:
    """Most repeated value; the buy box restates its price and rating, carousels show each once."""
    if not values:
        return None
    counts: dict[float, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    best = max(counts.values())
    return next(v for v in values if counts[v] == best)


def _clean_matches(pattern: re.Pattern[str], text: str) -> list[re.Match[str]]:
    out = []
    for m in pattern.finditer(text):
        before = text[max(0, m.start() - 30): m.start()]
        after = text[m.end(): m.end() + 120]
        if _NOISE_BEFORE.search(before) or _NOISE_AFTER.search(after) or _IN_LINK.search(after):
            continue
        out.append(m)
    return out


def _selling_price(text: str) -> tuple[float | None, int]:
    """(price, buy-box position): structured data first, then the most repeated clean amount."""
    for pattern in _STRUCTURED_PRICE:
        m = pattern.search(text)
        if m and (value := _num(m.group(1))):
            visible = re.search(rf"{_SYM}\s*{re.escape(f'{value:,.0f}')}", text, re.I)
            return value, visible.start() if visible else m.start()
    # "M.R.P: ₹4,999 ₹1,499": the amount after an MRP label is the list price, not the selling price.
    mrp_at = {m.start(1) for m in _MRP.finditer(text)}
    candidates = [
        (v, m.start()) for m in _clean_matches(_PRICE, text)
        if (v := _num(m.group(1))) and v >= 1 and m.start(1) not in mrp_at
    ]
    price = _mode([v for v, _ in candidates])
    at = next((pos for v, pos in candidates if v == price), 0)
    return price, at


# Product photo, most reliable first: schema.org Product image, og:image, then a markdown image
# whose alt text names the brand (a banner or "Customers also viewed" tile does not).
_JSONLD_IMAGE = re.compile(r'"image"\s*:\s*\[?\s*"(https?://[^"\s]+)"')
_OG_IMAGE = re.compile(r"""og:image["']?\s+content=["'](https?://[^"']+)""", re.I)
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")
_IMAGE_NOISE = re.compile(r"(sprite|banner|logo|icon|favicon|pixel|badge|placeholder|loader|transparent|1x1)", re.I)


def listing_image(text: str, names: list[str]) -> str | None:
    for pattern in (_JSONLD_IMAGE, _OG_IMAGE):
        m = pattern.search(text)
        if m and not _IMAGE_NOISE.search(m.group(1)):
            return m.group(1)
    for m in _MD_IMAGE.finditer(text):
        alt, url = m.group(1), m.group(2)
        if alt and mentions(alt, names) and not _IMAGE_NOISE.search(url):
            return url
    return None


# ── Product grids: search, category and brand-store pages ───────────────────────
# Search for "Red Tape formal shoes" on a marketplace lands on a grid of 20-40 product cards,
# each with its own price. Reading that as one product picks an arbitrary card's price. So each
# card is read on its own: the product link, then the prices before the next product link.

# Product-detail URLs across stores: Amazon /dp/ASIN, Flipkart /p/itm…, Ajio /p/123_colour,
# Myntra /12345/buy, Shopify /products/…, generic /product/ and -p-123 / .html item pages.
_PRODUCT_URL = re.compile(
    r"https?://[^\s)\]\"']+?(?:/dp/[A-Z0-9]{10}|/gp/product/[A-Z0-9]{10}|/p/itm[0-9a-z]+|/p/\d{5,}[\w-]*|"
    r"/\d{5,}/buy|/products?/[\w-]{3,}|/item/\d+|-p-\d{4,}|/pd/[\w-]+|/ip/[\w-]+/\d+)",
    re.I,
)
# A struck "MRP"/"was" price and a labelled sale price, when the card says which is which.
_SALE_LABEL = re.compile(r"(?:sale|offer|deal|special|our)\s+price\D{0,6}" + _AMOUNT, re.I)
MIN_GRID_CARDS = 3


def _card_name(window: str, url: str) -> str:
    for pattern in (r'\(%s\s+"([^"]{6,160})"\)' % re.escape(url), r"!\[(?:Image \d+: )?(?:Product image of |Image of )?([^\]]{6,160})\]",
                    r"\[([^\]\[]{6,160})\]\(%s" % re.escape(url[:60])):
        m = re.search(pattern, window, re.I)
        if m and not re.search(r"[₹$£€]\s?\d", m.group(1)) and not re.fullmatch(r"Image \d+", m.group(1).strip()):
            return re.sub(r"\s+", " ", m.group(1)).strip(" .|")
    slug = re.sub(r"[-_/]+", " ", re.sub(r"https?://[^/]+/", "", url).split("?")[0])
    return re.sub(r"\b(dp|p|itm\w+|[A-Z0-9]{10}|\d{5,}\w*|buy)\b", " ", slug).strip()[:120]


def read_grid(text: str, comp: CompetitorProfile) -> list[ListingItem]:
    """The rival's product cards on a grid page, each with its own price; [] when it is not a grid."""
    names = search_names(comp.brand_name) or [comp.brand_name]
    # A card is every line that links to its product page. Flipkart spreads name, price and image
    # over several such lines; Ajio and Myntra put a whole card on one. Ads and "similar" tiles
    # link elsewhere, so their names and prices never join a card.
    cards: dict[str, tuple[str, list[str]]] = {}
    for line in text.splitlines():
        for m in _PRODUCT_URL.finditer(line):
            key = re.sub(r"[?#].*$", "", m.group(0)).rstrip("/")
            url, lines = cards.setdefault(key, (m.group(0), []))
            if not lines or lines[-1] is not line:
                lines.append(line)
    if len(cards) < MIN_GRID_CARDS:
        return []
    items: list[ListingItem] = []
    for key, (url, lines) in cards.items():
        own = "\n".join(lines)
        window = own
        # Prices inside link text are the card's own here, so only promo/filter context is excluded.
        amounts = [
            v for m in _PRICE.finditer(own)
            if (v := _num(m.group(1))) and v >= 10
            and not _NOISE_BEFORE.search(own[max(0, m.start() - 30): m.start()])
            and not _NOISE_AFTER.search(own[m.end(): m.end() + 120])
        ]
        if not amounts:
            continue
        sale = _SALE_LABEL.search(own)
        selling = _num(sale.group(1)) if sale else min(amounts)
        mrp = max(amounts) if max(amounts) > (selling or 0) else None
        name = _card_name(window, url)
        # The brand may sit on its own line in the card ("RED TAPE" above the name on Flipkart).
        if not selling or not mentions(f"{name} {key.replace('-', ' ')} {own[:600]}", names):
            continue  # another brand's card (ads and "similar products" sit in the same grid)
        rating_m = _RATING.search(own)
        image = next((u for _, u in _MD_IMAGE.findall(window) if not _IMAGE_NOISE.search(u)), None)
        items.append(ListingItem(
            name=name[:160], url=url, selling_price=selling, mrp=mrp,
            rating=float(rating_m.group(1)) if rating_m else None, image_url=image,
        ))
    return items if len(items) >= MIN_GRID_CARDS else []


# Search, category, brand-store and collection pages.
_LISTING_URL = re.compile(
    r"/(?:s|search|find|stores?|brand|category|categories|collections?|shop|catalog|c|l)(?:/|\?|$)|"
    r"[?&](?:q|k|query|search|keyword)=|~brand|/pr\?",
    re.I,
)


def _looks_like_listing_page(url: str, text: str) -> bool:
    """A page that lists many products: by its URL, or by linking to several product pages."""
    if _PRODUCT_URL.match(url):
        return False
    distinct = {re.sub(r"[?#].*$", "", m.group(0)) for m in _PRODUCT_URL.finditer(text)}
    return bool(_LISTING_URL.search(url)) or len(distinct) >= MIN_GRID_CARDS


def _median(values: list[float]) -> float:
    v = sorted(values)
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else round((v[mid - 1] + v[mid]) / 2, 2)


def read_listing(
    url: str,
    text: str,
    comp: CompetitorProfile,
    site_type: str,
    currency: str | None,
    *,
    title: str = "",
    source: str = "page",
    matched_product: str | None = None,
) -> ChannelListing | None:
    """A listing with the values the page states, or None when the page is not this rival's."""
    names = search_names(comp.brand_name) or [comp.brand_name]
    if not text or not mentions(text, names):
        return None
    # The store's own currency (amazon.com in USD for a merchant in India), not the market's.
    currency = page_currency(text, currency)

    if source == "page" and (grid := read_grid(text, comp)):
        prices = [it.selling_price for it in grid]
        mrps = [it.mrp for it in grid if it.mrp]
        return ChannelListing(
            competitor=comp.brand_name,
            product=title.strip() or f"{comp.brand_name} products",
            site=host_of(url),
            site_type=site_type,  # type: ignore[arg-type]
            url=url,
            currency=currency,
            page_kind="grid",
            selling_price=_median(prices),
            price_from=min(prices),
            mrp=_median(mrps) if mrps else None,
            product_count=len(grid),
            items=grid[:40],
            image_url=next((it.image_url for it in grid if it.image_url), None),
            observed_at=clock_today().isoformat(),
            evidence=f"{len(grid)} {comp.brand_name} product cards on {host_of(url)}",
            matched_product=matched_product,
            source="page",
        )
    # A search, category or store page whose cards could not be read: any single price on it
    # belongs to a menu, a filter or another product, so it is not used.
    if source == "page" and _looks_like_listing_page(url, text) and not any(p.search(text) for p in _STRUCTURED_PRICE):
        return None

    selling, at = _selling_price(text)
    box = text[max(0, at - 1500): at + 3500]  # the buy box: price, MRP, discount, offers, delivery
    mrp_m = _MRP.search(box)
    mrp = _num(mrp_m.group(1)) if mrp_m else None
    if mrp and selling and mrp <= selling:
        mrp = None  # an "MRP" at or below the selling price belongs to something else
    if selling is None and mrp is None:
        return None  # a page with no price on it is not a listing we can use
    discount_m = _DISCOUNT.search(box)
    discount = (
        float(discount_m.group(1) or discount_m.group(2)) if discount_m and mrp
        else round((1 - selling / mrp) * 100, 1) if mrp and selling else None
    )

    ratings = [float(m.group(1)) for m in _clean_matches(_RATING, text)]
    reviews = [n for m in _clean_matches(_REVIEWS, text) if (n := _num(m.group(1)))]
    velocity_m = _VELOCITY.search(box)
    returns_m = _RETURNS.search(text)
    # "COD not available" contains "cash on delivery" too, so the negative is checked first.
    cod = False if _NO_COD.search(text) else (True if _COD.search(text) else None)
    delivery_m = _DELIVERY.search(box)
    seller_m = _SOLD_BY.search(box)
    offers = list(dict.fromkeys(
        re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(0)).strip(" -•|#*") for m in _OFFER.finditer(box)
    ))[:5]

    returns = returns_m.group(0).strip() if returns_m else ("Non-returnable" if _NO_RETURNS.search(text) else None)

    evidence = text[max(0, at - 120): at + 200].strip()

    return ChannelListing(
        competitor=comp.brand_name,
        product=title.strip() or comp.product_name or "",
        site=host_of(url),
        site_type=site_type,  # type: ignore[arg-type]
        url=url,
        currency=currency,
        mrp=mrp,
        selling_price=selling,
        discount_pct=discount,
        offers=offers,
        rating=_mode(ratings),
        review_count=int(_mode(reviews) or 0) or None,
        velocity_signal=(velocity_m.group(0).strip() if velocity_m else None),
        seller=seller_m.group(1).strip() if seller_m else None,
        delivery=delivery_m.group(0).strip() if delivery_m else None,
        returns_policy=returns,
        cod_available=cod,
        observed_at=clock_today().isoformat(),
        evidence=evidence,
        image_url=listing_image(text, names) if source == "page" else None,
        matched_product=matched_product,
        source=source,  # type: ignore[arg-type]
    )


async def collect_channel_listings(
    report: SWOTReportDelta,
    merchant_context: dict[str, Any],
    documents: list[tuple[str, str]],
    search_fn: SearchFn,
    crawl_fn: CrawlFn,
    *,
    max_per_competitor: int = 4,
    ai_search_fn: AISearchFn | None = None,
    llm: Any = None,
) -> tuple[SWOTReportDelta, list[str]]:
    """Fills competitor.channel_listings. Returns (report, diagnostics)."""
    diagnostics: list[str] = []
    competitors = list(report.competitors)
    if not competitors:
        return report, diagnostics
    marketplaces, currency = await resolve_stores(merchant_context, search_fn, llm, diagnostics)
    site_types = dict(marketplaces)

    products = merchant_products(merchant_context)
    hosts = [h for h, _ in marketplaces]
    # (merchant product or None, results). None means "the rival's own product" (single-product merchant).
    batches: list[tuple[dict[str, Any] | None, list[TavilySearchResult]]] = []
    if marketplaces:
        for product in products or [None]:
            try:
                batches.append((product, await search_fn(build_listing_queries(competitors, hosts, product))))
            except Exception as exc:
                logger.warning("Listing search failed: %s", exc)
                diagnostics.append(f"[LISTINGS] Marketplace search failed ({type(exc).__name__}).")
    else:
        diagnostics.append("[LISTINGS] No marketplace set for this market; reading own-site listings only.")

    def site_of(url: str) -> str | None:
        host = host_of(url or "")
        return next((h for h in site_types if host == h or host.endswith("." + h)), None)

    pool = {u: t for u, t in documents if u and t}
    # (rival, merchant product name) -> picked search results
    picks: dict[tuple[str, str | None], list[TavilySearchResult]] = {}
    for comp in competitors:
        names = search_names(comp.brand_name) or [comp.brand_name]
        for product, results in batches:
            picked: list[TavilySearchResult] = []
            seen_sites: set[str] = set()
            for r in results:
                site = site_of(r.url)
                # One listing per site per rival per product: the buy box, not every colour variant.
                if not site or site in seen_sites or not mentions(f"{r.title} {r.url}", names):
                    continue
                picked.append(r)
                seen_sites.add(site)
                if len(picked) >= max_per_competitor:
                    break
            picks[(comp.brand_name, product.get("name") if product else None)] = picked

    new_urls = list(dict.fromkeys(r.url for rs in picks.values() for r in rs if r.url not in pool))
    if new_urls:
        try:
            for page in await crawl_fn(new_urls):
                if page.get("url") and page.get("markdown"):
                    pool[page["url"]] = page["markdown"]
        except Exception as exc:
            logger.warning("Listing crawl failed: %s", exc)
            diagnostics.append(f"[LISTINGS] Listing page fetch failed ({type(exc).__name__}).")

    total = 0
    snippet_total = 0
    ai_total = 0
    for comp in competitors:
        listings: list[ChannelListing] = []
        for (brand, product_name), picked in picks.items():
            if brand != comp.brand_name:
                continue
            for r in picked:
                site_type = site_types.get(site_of(r.url) or "", "marketplace")
                listing = read_listing(
                    r.url, pool.get(r.url, ""), comp, site_type, currency,
                    title=r.title, matched_product=product_name,
                )
                if listing is None and r.snippet:
                    # Blocked or script-rendered page: the search engine's excerpt of it often still
                    # carries "MRP ₹6,999 ₹2,499". Same page's text, labelled as an excerpt.
                    listing = read_listing(
                        r.url, f"{r.title}\n{r.snippet}", comp, site_type, currency,
                        title=r.title, source="search_snippet", matched_product=product_name,
                    )
                    snippet_total += bool(listing)
                if listing:
                    listings.append(listing)
        # The rival's own store: product pages the research already fetched on its own host.
        own = _own_site_listing(comp, pool, currency)
        if own:
            listings.insert(0, own)

        # Last resort per product still unpriced: a web-search model, kept only with a cited page.
        if ai_search_fn is not None:
            for product in products or [None]:
                name = product.get("name") if product else None
                if any(l.selling_price is not None and l.matched_product == name for l in listings):
                    continue
                try:
                    found = await ai_search_fn(comp, product, currency, hosts)
                except Exception as exc:
                    logger.warning("AI price search failed for %s: %s", comp.brand_name, exc)
                    diagnostics.append(f"[LISTINGS] AI price search failed for {comp.brand_name} ({type(exc).__name__}).")
                    continue
                for l in found:
                    l.matched_product = name
                listings.extend(found)
                ai_total += len(found)

        comp.channel_listings = listings
        total += len(listings)

        # If competitor is missing logo_url or product_image_url, resolve from listings or pool
        if not comp.logo_url:
            for s in comp.sources:
                logo = resolve_logo_url(s)
                if logo:
                    comp.logo_url = logo
                    break
        if not comp.product_image_url:
            for l in listings:
                img = l.image_url or _extract_product_image_url(pool.get(l.url, ""))
                if img:
                    comp.product_image_url = img
                    break

        # No stated price model: say what the listed price is for and where it was seen.
        if not comp.pricing_model or comp.pricing_model == "detected":
            comp.pricing_model = listing_price_summary(listings)

        if listings:
            sites = ", ".join(f"{l.site} {_price_label(l)}" for l in listings)
            diagnostics.append(f"[LISTINGS] {comp.brand_name}: {sites}")
    diagnostics.extend(await add_shopping_offers(competitors, products, merchant_context, currency))
    diagnostics.extend(await add_amazon_history(competitors))
    for comp in competitors:
        for l in comp.channel_listings:
            fold_variants(l)
            match_items(l, products)
    if currency:
        diagnostics.extend(await convert_listings(competitors, currency))
    diagnostics.append(
        f"[LISTINGS] {total} listing(s) across {len(competitors)} competitor(s)"
        f" ({snippet_total} from search excerpts, {ai_total} from AI web search)."
    )
    return report, diagnostics


_SOURCE_OK_STORES = re.compile(r"[^a-z0-9]")


async def add_shopping_offers(
    competitors: list[CompetitorProfile], products: list[dict[str, Any]], merchant_context: dict[str, Any],
    currency: str | None, max_queries: int = 15,
) -> list[str]:
    """Google Shopping offers (SerpApi) per rival and product, grouped by store, for stores not already read."""
    from orchestrator.agents.market_research.ingestion.data_sources import DataSourceError, google_shopping
    from orchestrator.agents.market_research.ingestion.search_client import market_for
    from orchestrator.core.config import get_settings

    if not get_settings().serpapi_api_key:
        return []
    market = market_for(merchant_context)
    added = queries = 0
    for comp in competitors:
        names = search_names(comp.brand_name) or [comp.brand_name]
        have = {_SOURCE_OK_STORES.sub("", l.site.split(".")[0].lower()) for l in comp.channel_listings if l.source == "page"}
        for product in products or [None]:
            if queries >= max_queries:
                break
            what = _descriptor(product, comp)
            queries += 1
            try:
                offers = await google_shopping(f"{names[0]} {what}".strip(), market[0] if market else None)
            except DataSourceError as exc:
                return [f"[SHOPPING] Google Shopping unavailable ({exc})."]
            by_store: dict[str, list[dict[str, Any]]] = {}
            for o in offers:
                if o["store"] and mentions(o["title"], names):
                    by_store.setdefault(o["store"], []).append(o)
            for store, rows in by_store.items():
                key = _SOURCE_OK_STORES.sub("", store.lower())
                if any(key.startswith(h) or h.startswith(key) for h in have if h):
                    continue  # a page read of this store beats an offer summary
                items = [ListingItem(name=r["title"][:160], url=r["link"], selling_price=r["price"], mrp=r["old_price"],
                                     rating=r["rating"] if isinstance(r["rating"], (int, float)) else None,
                                     image_url=r["image"]) for r in rows]
                prices = [i.selling_price for i in items]
                comp.channel_listings.append(ChannelListing(
                    competitor=comp.brand_name, product=f"{comp.brand_name} {what}".strip(), site=store,
                    site_type="marketplace", url=rows[0]["link"], currency=page_currency(rows[0]["price_text"], currency),
                    page_kind="grid" if len(items) > 1 else "product", selling_price=_median(prices),
                    price_from=min(prices), product_count=len(items), items=items,
                    image_url=next((i.image_url for i in items if i.image_url), None),
                    observed_at=clock_today().isoformat(), evidence=f"Google Shopping offers from {store}",
                    matched_product=product.get("name") if product else None, source="shopping_api",
                ))
                have.add(key)
                added += 1
    return [f"[SHOPPING] {added} store listing(s) from Google Shopping ({queries} quer{'y' if queries == 1 else 'ies'})."]


async def add_amazon_history(competitors: list[CompetitorProfile]) -> list[str]:
    """Keepa 90-day price history and sales rank for every Amazon product the listings found."""
    from orchestrator.agents.market_research.ingestion.data_sources import DataSourceError, asin_of, keepa_history
    from orchestrator.core.config import get_settings

    if not get_settings().keepa_api_key:
        return []
    by_host: dict[str, list[Any]] = {}
    for comp in competitors:
        for l in comp.channel_listings:
            if "amazon." in l.site:
                for target in [l, *l.items]:
                    if asin_of(target.url):
                        by_host.setdefault(l.site, []).append(target)
    done = 0
    for host, targets in by_host.items():
        asins = list(dict.fromkeys(asin_of(t.url) for t in targets))
        try:
            history = await keepa_history(asins, host)
        except DataSourceError as exc:
            return [f"[KEEPA] Amazon history unavailable ({exc})."]
        for t in targets:
            h = history.get(asin_of(t.url))
            if not h:
                continue
            t.avg_90d, t.min_90d, t.sales_rank = h["avg_90d"], h["min_90d"], h["sales_rank"]
            if isinstance(t, ChannelListing):
                t.max_90d, t.sales_rank_drops_30d = h["max_90d"], h["sales_rank_drops_30d"]
            done += 1
    return [f"[KEEPA] Price history and sales rank for {done} Amazon product(s)."] if done else []


# ── Variants and matching ───────────────────────────────────────────────────────
# Words that describe a size or colour, not a different product.
_VARIANT_WORDS = re.compile(
    r"(?i)(?:^|[\s,|(/-])(?:uk|us|eu|size)?\s?\d{1,2}(?:\.\d)?(?=$|[\s,|)/-])|"
    r"(?:^|[\s,|(/-])(?:black|brown|tan|teak|navy|blue|white|grey|gray|beige|olive|maroon|red|green|"
    r"cherry|wine|camel|cognac|burgundy|khaki|cream|pink|multicolou?r)(?=$|[\s,|)/-])"
)
# Product-type words used to match a rival product to the merchant's.
_TYPE_WORDS = re.compile(r"[a-z]+")
_STOP = {"for", "men", "mens", "women", "womens", "with", "and", "the", "shoes", "shoe", "leather", "red", "tape",
         "formal", "casual", "new", "pack", "of", "in", "on", "slip"}


def _base_name(name: str) -> str:
    return re.sub(r"\s+", " ", _VARIANT_WORDS.sub(" ", name.lower())).strip(" |-,")


def fold_variants(listing: ChannelListing) -> None:
    """Folds size/colour variants of one product (same base name, prices within 3%) into one item."""
    if len(listing.items) < 2:
        return
    kept: list[ListingItem] = []
    for it in sorted(listing.items, key=lambda i: i.selling_price):
        base = _base_name(it.name)
        twin = next((k for k in kept if _base_name(k.name) == base
                     and abs(k.selling_price - it.selling_price) <= 0.03 * k.selling_price), None)
        if twin:
            twin.variants += 1
        else:
            kept.append(it)
    if len(kept) != len(listing.items):
        listing.items = kept
        listing.product_count = len(kept)
        prices = [i.selling_price for i in kept]
        listing.selling_price, listing.price_from = _median(prices), min(prices)


def _type_tokens(text: str) -> set[str]:
    return {w.rstrip("s") for w in _TYPE_WORDS.findall(text.lower()) if len(w) > 2 and w not in _STOP}


def match_items(listing: ChannelListing, products: list[dict[str, Any]]) -> None:
    """Marks each rival item with the merchant product it is closest to (shared type words, then price)."""
    if not products or not listing.items:
        return
    profiles = [(p.get("name"), _type_tokens(f"{p.get('name', '')} {p.get('category', '')}"), p.get("price"))
                for p in products]
    for it in listing.items:
        words = _type_tokens(it.name)
        best, best_score = None, 0.0
        for name, tokens, price in profiles:
            overlap = len(words & tokens)
            if not overlap:
                continue
            score = overlap + (1 - min(1.0, abs(it.selling_price - price) / price) if isinstance(price, (int, float)) and price else 0)
            if score > best_score:
                best, best_score = name, score
        it.matched_product = best


async def convert_listings(competitors: list[CompetitorProfile], target: str) -> list[str]:
    """Puts every foreign-currency price in the merchant's currency, keeping the original and the rate."""
    from orchestrator.core.config import get_settings
    from orchestrator.core.fx import convert

    foreign = [l for c in competitors for l in c.channel_listings
               if l.currency and l.currency != target and l.selling_price is not None]
    if not foreign:
        return []
    if not get_settings().fx_conversion_enabled:
        return [f"[FX] {len(foreign)} listing(s) priced in another currency; conversion is off."]
    done = 0
    for l in foreign:
        result = await convert(l.selling_price, l.currency, target)
        if result is None:
            continue
        l.price_in_merchant_currency, l.fx_rate = result
        l.merchant_currency = target
        done += 1
    missing = len(foreign) - done
    return [f"[FX] Converted {done} listing price(s) to {target} at today's ECB rates"
            + (f"; {missing} left in their own currency (no rate)." if missing else ".")]


async def resolve_stores(
    merchant_context: dict[str, Any], search_fn: SearchFn, llm: Any, diagnostics: list[str]
) -> tuple[list[tuple[str, str]], str | None]:
    """
    Stores to check and the currency to read prices in.

    Known markets start from the seed list; every market with a country gets the stores discovery
    finds for it (so a country nobody listed still works); no country falls back to global stores.
    """
    from orchestrator.agents.market_research.ingestion.search_client import market_for
    from orchestrator.agents.market_research.intelligence.profiling.store_discovery import (
        CURRENCY_BY_ISO, GLOBAL_STORES, discover_stores, merge_stores,
    )

    seed = marketplaces_for(merchant_context)
    market = market_for(merchant_context)
    discovered, note = await discover_stores(merchant_context, search_fn, llm) if market else ([], "")
    if note:
        diagnostics.append(f"[STORES] Discovery: {note}" + (f": {', '.join(h for h, _ in discovered)}" if discovered else ""))
    if market is None:
        diagnostics.append("[STORES] No target country; checking global marketplaces.")
        stores = GLOBAL_STORES
    else:
        # Seed first (known specialists and the big marketplaces), then what discovery adds.
        stores = merge_stores(seed, discovered, cap=MAX_STORES)
    currency = (
        str(merchant_context.get("currency") or "").upper()[:3]
        or _CURRENCY_FOR_MARKET.get(market_of(merchant_context) or "")
        or (CURRENCY_BY_ISO.get(market[0]) if market else None)
        or None
    )
    return stores, currency


def _own_site_listing(comp: CompetitorProfile, pool: dict[str, str], currency: str | None) -> ChannelListing | None:
    names = search_names(comp.brand_name) or [comp.brand_name]
    keys = [re.sub(r"[^a-z0-9]", "", n.lower()) for n in names if n]
    for url in comp.sources or []:
        host = host_of(url)
        label = re.sub(r"[^a-z0-9]", "", host.split(".")[0] if not host.startswith("www.") else host.split(".")[1])
        if not label or not any(k and (k.startswith(label) or label.startswith(k[:6])) for k in keys):
            continue
        listing = read_listing(url, pool.get(url, ""), comp, "d2c", currency)
        if listing:
            return listing
    return None


def _price_label(listing: ChannelListing) -> str:
    if listing.selling_price is None:
        return "(no price)"
    off = f", {listing.discount_pct:g}% off" if listing.discount_pct else ""
    return f"{listing.currency or ''} {listing.selling_price:,.0f}{off}".strip()


_SOURCE_RANK = ("page", "shopping_api", "search_snippet", "ai_search")
_SYMBOL = {"INR": "₹", "USD": "$", "GBP": "£", "EUR": "€"}


def listing_price_summary(listings: list[ChannelListing]) -> str | None:
    """'Oxford Leather Shoes: ₹2,499 (MRP ₹6,999) on amazon.in'. Prefers prices read off the page."""
    priced = sorted((l for l in listings if l.selling_price is not None), key=lambda l: _SOURCE_RANK.index(l.source))
    if not priced:
        return None
    best = priced[0]
    sym = _SYMBOL.get(best.currency or "", f"{best.currency} " if best.currency else "")
    mrp = f" (MRP {sym}{best.mrp:,.0f})" if best.mrp else ""
    what = (best.product or best.matched_product or "").strip()
    what = f"{what[:60]}: " if what else ""
    return f"{what}{sym}{best.selling_price:,.0f}{mrp} on {best.site}"
