"""
Profile completion: find the facts a competitor profile is missing, without inventing any.

Reports showed "not available" for price, rating, review count, founding year, team size,
revenue and funding. The causes were mechanical, not an absence of data:
  - founding year, HQ and rating were only ever read from pages on the rival's own domain, so
    a Clutch or Crunchbase profile stating all three was ignored;
  - team size, revenue and funding had no field at all;
  - facts that did surface in search text were never looked for (MojoTech's "Founded in 2008"
    came back in a snippet and was never read as a founding year).

This step closes that loop. For each rival it lists the facts still missing, searches where
those facts are published (directory profiles, the rival's about page, news), and asks the
model to extract them -- but the model's answer is a claim, not a fact. Every value must come
with a sentence copied from a page we fetched, and code checks that:
  1. the sentence is really on that page,
  2. the page is about this competitor (its own site, a profile whose slug is its name, or the
     sentence sits next to its name),
  3. the value is really in the sentence (the year, the number, the range),
  4. the sentence is the right kind (a founding year sits next to "founded", a team size next
     to "employees").
Anything that fails is discarded. Up to two rounds; whatever is still missing is recorded with
the reason it is missing and how many pages were checked, so the dashboard can say so.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.agents.market_research.discovery.search import SearchQuery, TavilySearchResult
from orchestrator.agents.market_research.discovery.source_types import (
    PROFILE_DOMAINS,
    host_of,
    is_never_a_brand,
    mentions,
    name_pattern,
    norm_key,
    page_belongs_to,
    profile_page_owner_slug,
    registrable_label,
    search_names,
)
from orchestrator.core.clock import today as clock_today
from orchestrator.schemas.research import CompetitorProfile, FieldStatus, SWOTReportDelta

logger = logging.getLogger(__name__)

SearchFn = Callable[[list[SearchQuery], int], Awaitable[list[TavilySearchResult]]]
CrawlFn = Callable[[list[str]], Awaitable[list[dict[str, Any]]]]


@dataclass(frozen=True)
class FactSpec:
    label: str
    # The sentence must contain one of these: a founding year sits next to "founded", not
    # next to "updated". Keeps a stray number from being read as the fact.
    cue: re.Pattern[str]
    # What to search for when the fact is missing.
    search_terms: str
    # Why it may legitimately be missing, appended to the reason when nothing is found.
    rarely_public: str = ""


FACTS: dict[str, FactSpec] = {
    "pricing_model": FactSpec(
        "price",
        re.compile(r"[$€£₹¥]|\b(?:usd|eur|gbp|inr|rs\.?|price|pricing|cost|rate|per hour|/hr|/mo|"
                   r"per month|starting at|starts at|minimum|budget|fee)\b", re.I),
        '(pricing OR rates OR "per hour" OR "minimum project" OR cost OR "starting at")',
        "Many service firms only quote on request.",
    ),
    "rating": FactSpec(
        "rating",
        re.compile(r"\b(?:rating|rated|stars?|out of 5|/5|reviews?)\b", re.I),
        '(reviews OR rating OR "out of 5")',
    ),
    "review_count": FactSpec(
        "review count",
        re.compile(r"\breviews?\b|\bratings\b", re.I),
        '(reviews OR rating OR "verified reviews")',
    ),
    "founded": FactSpec(
        "founding year",
        re.compile(r"\b(?:founded|established|est\.?|since|started|incorporated|founding|launched in|"
                   r"began)\b", re.I),
        '(founded OR established OR "since")',
    ),
    "headquarters": FactSpec(
        "headquarters",
        re.compile(r"\b(?:headquarter(?:s|ed)?|hq|based in|head office|located in|offices? in)\b", re.I),
        '(headquarters OR "based in" OR "head office")',
    ),
    "employee_count": FactSpec(
        "team size",
        re.compile(r"\b(?:employees?|staff|team members?|people|headcount|engineers|designers|"
                   r"developers|team of|company size)\b", re.I),
        '(employees OR "team of" OR "company size" OR staff)',
    ),
    "annual_revenue": FactSpec(
        "revenue",
        re.compile(r"\b(?:revenue|turnover|annual sales|arr|sales of)\b", re.I),
        '("annual revenue" OR revenue OR turnover)',
        "Private companies rarely publish revenue.",
    ),
    "funding": FactSpec(
        "funding",
        re.compile(r"\b(?:raised|funding|funded|valuation|valued|series [a-h]|seed|investment|"
                   r"investors?|backed|bootstrapped|self-funded)\b", re.I),
        '(raised OR funding OR valuation OR "series A" OR bootstrapped)',
        "Many agencies are self-funded and never announce funding.",
    ),
}

_PLACEHOLDER = re.compile(
    r"^(?:n/?a|none|null|unknown|not (?:available|stated|disclosed|specified|found|published)|"
    r"undisclosed|private|tbd|varies|detected|-+)$",
    re.I,
)

EXTRACT_PROMPT = """\
You extract facts about ONE company from web pages. You never estimate, infer or use outside \
knowledge: a fact counts only if a page we give you states it.

You get the company's names, the facts still missing, and numbered documents (id, url, text).
For each missing fact that a document states ABOUT THIS COMPANY, return:
- field: one of the requested field names
- value: the value as written (keep ranges and units: "50-249", "$150-$199/hr", "2008", \
"Chicago, IL", "$12M Series A", "4.9", "52")
- quote: a sentence or phrase COPIED CHARACTER FOR CHARACTER from that document that states \
the value. Do not paraphrase, fix typos, or join text from different places.
- doc_id: the document it is copied from

Rules:
- Only facts about THIS company. A directory or article listing several companies: use only \
the part about this one, and on a document marked about_this_company=false the quote MUST \
contain the company's name.
- employee_count is the company's own team size, not its clients'.
- funding is money the company raised or its valuation, not its clients' funding.
- rating is a review score out of 5; review_count is how many reviews it is based on.
- If no document states a fact, leave it out. An empty list is a correct answer.
"""


class _Extracted(BaseModel):
    field: str
    value: str
    quote: str
    doc_id: str


class _Extraction(BaseModel):
    facts: list[_Extracted] = Field(default_factory=list)


# ── Text normalization and verification ─────────────────────────────────────────


_MD_LINK = re.compile(r"\]\(\s*https?://[^)]*\)")
_KEEP = re.compile(r"[^a-z0-9$€£₹¥%.,+/\-]+")


def _norm(text: str) -> str:
    """Comparison form: links and markdown gone, punctuation that carries meaning kept."""
    text = _MD_LINK.sub(" ", (text or "").lower())
    text = text.replace("–", "-").replace("—", "-").replace("’", "'")
    return " ".join(_KEEP.sub(" ", text).split())


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    out = set()
    for n in _NUM.findall(text or ""):
        n = n.replace(",", "").rstrip(".")
        if n:
            out.add(n.split(".")[0] if n.endswith(".0") else n)
    return out


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or bool(_PLACEHOLDER.match(value.strip()))
    return False


def current_value(comp: CompetitorProfile, field: str) -> Any:
    return getattr(comp, field, None)


def missing_facts(comp: CompetitorProfile) -> list[str]:
    return [f for f in FACTS if _is_empty(current_value(comp, f))]


@dataclass
class _Doc:
    doc_id: str
    url: str
    text: str
    norm: str
    owned: bool  # the page is about this competitor (own site or its directory profile)


def own_hosts(comp: CompetitorProfile) -> set[str]:
    """Hosts that are the competitor's own website, recognised by name."""
    from orchestrator.agents.market_research.discovery.source_types import MULTI_TENANT_DOMAINS

    keys = [norm_key(n) for n in search_names(comp.brand_name) + [comp.product_name or ""] if n]
    hosts = set()
    for url in comp.sources:
        if is_never_a_brand(url) or profile_page_owner_slug(url):
            continue
        h = host_of(url)
        if h in MULTI_TENANT_DOMAINS or any(h == m or h == f"www.{m}" for m in MULTI_TENANT_DOMAINS):
            continue
        label = registrable_label(url)
        if len(label) >= 3 and any(k and (k.startswith(label) or label.startswith(k[:6])) for k in keys):
            hosts.add(h)
    return hosts


def verify(
    fact: _Extracted,
    docs: dict[str, _Doc],
    names: list[str],
) -> tuple[bool, str]:
    """Deterministic check of one extracted fact. Returns (ok, reason when rejected)."""
    spec = FACTS.get(fact.field)
    if spec is None:
        return False, "not a requested field"
    doc = docs.get(fact.doc_id)
    if doc is None:
        return False, "cited a document that does not exist"
    value, quote = fact.value.strip(), fact.quote.strip()
    if _is_empty(value) or len(quote) < 6:
        return False, "no value or no quote"
    q = _norm(quote)
    pos = doc.norm.find(q)
    if pos < 0:
        return False, "quote is not on the cited page"
    if not doc.owned:
        # A page about many companies (a listicle, an article): the sentence itself must name
        # this company. Nearness is not enough: "Acme Digital has 100 employees" sat two lines
        # above "MojoTech is listed below" and was credited to MojoTech.
        if not any(_norm(n) and re.search(rf"(?<![a-z0-9]){re.escape(_norm(n))}(?![a-z0-9])", q) for n in names):
            return False, "sentence does not name this company"
    if not spec.cue.search(quote):
        return False, f"sentence does not state a {spec.label}"

    q_numbers = _numbers(quote)
    v_numbers = _numbers(value)
    # Only a place, or a funding status such as "bootstrapped", may be stated without a number;
    # then every word of it must be in the sentence.
    wordy = fact.field == "headquarters" or (
        fact.field == "funding" and re.search(r"bootstrap|self-funded|self funded|privately held", value, re.I)
    )
    if wordy and not v_numbers:
        words = re.findall(r"[a-z]{3,}", value.lower())
        if not words or not all(w in q for w in words):
            return False, "value is not in the sentence"
        return True, ""
    if not v_numbers:
        return False, "value has no number"
    if not v_numbers <= q_numbers:
        # "$150-$199/hr" -> {150, 199}; every number in the value must be in the sentence.
        return False, "value is not in the sentence"

    if fact.field == "founded":
        year = int(next(iter(v_numbers))) if len(v_numbers) == 1 else 0
        if not (1800 <= year <= clock_today().year):
            return False, "not a plausible founding year"
    elif fact.field == "rating":
        try:
            r = float(value.split("/")[0])
        except ValueError:
            return False, "rating is not a number"
        if not (0 < r <= 5):
            return False, "rating is not on a 0-5 scale"
    elif fact.field == "review_count":
        if not value.replace(",", "").isdigit():
            return False, "review count is not a whole number"
    elif fact.field == "headquarters":
        words = [w for w in re.findall(r"[a-z]{3,}", value.lower())]
        if not words or not all(w in q for w in words):
            return False, "place is not in the sentence"
    return True, ""


# ── Evidence gathering ──────────────────────────────────────────────────────────

_FACT_HINT = re.compile(
    r"founded|established|employees|team of|company size|headquarter|based in|revenue|raised|"
    r"funding|valuation|rating|reviews?|\$|per hour|/hr|minimum project|hourly rate",
    re.I,
)


def _windows(text: str, names: list[str], owned: bool, cap: int) -> str:
    """Fact-dense parts of a page: around fact words (owned pages) or around the name."""
    spans: list[tuple[int, int]] = []
    if owned:
        for m in _FACT_HINT.finditer(text):
            spans.append((max(0, m.start() - 220), m.end() + 220))
    for n in names:
        rx = name_pattern(n)
        if rx is None:
            continue
        for m in rx.finditer(text):
            spans.append((max(0, m.start() - 260), m.end() + 260))
    if not spans:
        return text[:cap] if owned else ""
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out, total = [], 0
    for s, e in merged:
        piece = text[s:e]
        if total + len(piece) > cap:
            piece = piece[: max(0, cap - total)]
        out.append(piece)
        total += len(piece)
        if total >= cap:
            break
    return " … ".join(out)


def build_queries(comp: CompetitorProfile, missing: list[str], round_number: int) -> list[SearchQuery]:
    names = search_names(comp.brand_name) or [comp.brand_name]
    primary = names[0]
    alt = names[1] if len(names) > 1 else primary
    company_facts = [f for f in missing if f in ("founded", "headquarters", "employee_count", "annual_revenue", "funding")]
    queries: list[SearchQuery] = []
    if round_number == 1:
        # Directory profiles state founded, team size, rating, reviews and rates in one place.
        queries.append(SearchQuery(vector="profile_facts", query=f'"{primary}"', include_domains=PROFILE_DOMAINS))
        if company_facts:
            terms = " OR ".join(sorted({FACTS[f].search_terms.strip("()") for f in company_facts}))
            queries.append(SearchQuery(vector="profile_facts", query=f'"{primary}" ({terms})'))
        if "pricing_model" in missing:
            queries.append(SearchQuery(vector="profile_facts", query=f'"{primary}" {FACTS["pricing_model"].search_terms}'))
        if "rating" in missing or "review_count" in missing:
            queries.append(SearchQuery(vector="profile_facts", query=f'"{primary}" {FACTS["rating"].search_terms}'))
    else:
        # Second pass: the other name it goes by, its about page, and news coverage.
        queries.append(SearchQuery(vector="profile_facts", query=f'"{alt}" company profile about us'))
        if company_facts:
            queries.append(SearchQuery(
                vector="profile_facts",
                query=f'"{alt}" (acquired OR raised OR "revenue of" OR employees OR "founded in")',
                time_range=None,
            ))
        if "pricing_model" in missing:
            queries.append(SearchQuery(vector="profile_facts", query=f'{alt} hourly rate minimum project size cost'))
    return queries


def _deterministic_facts(doc: _Doc, missing: list[str]) -> list[_Extracted]:
    """High-precision regex reads, used on the competitor's own pages and profiles only."""
    from orchestrator.agents.market_research.pipeline.loop import (
        _extract_founded,
        _extract_price,
        _extract_rating,
        _extract_review_count,
    )

    if not doc.owned:
        return []
    out: list[_Extracted] = []
    sentences = re.split(r"(?<=[.!?\n])\s+", doc.text)

    def first(field: str, reader) -> None:
        if field not in missing:
            return
        for s in sentences:
            v = reader(s)
            if v:
                out.append(_Extracted(field=field, value=str(v), quote=s.strip()[:300], doc_id=doc.doc_id))
                return

    first("founded", _extract_founded)
    first("pricing_model", _extract_price)
    first("rating", _extract_rating)
    first("review_count", _extract_review_count)
    if "employee_count" in missing:
        rx = re.compile(r"(\d[\d,]*\s?(?:-|–|to)\s?\d[\d,]*|\d[\d,]*\+?)\s+(?:employees|staff|team members)", re.I)
        for s in sentences:
            m = rx.search(s)
            if m:
                out.append(_Extracted(field="employee_count", value=m.group(1), quote=s.strip()[:300], doc_id=doc.doc_id))
                break
    return out


async def _llm_extract(llm: Any, comp: CompetitorProfile, missing: list[str], docs: list[_Doc], names: list[str]) -> list[_Extracted]:
    budget = 14000
    payload_docs = []
    for d in docs:
        if budget <= 0:
            break
        text = _windows(d.text, names, d.owned, cap=min(3500 if d.owned else 1500, budget))
        if not text:
            continue
        budget -= len(text)
        payload_docs.append({"id": d.doc_id, "url": d.url, "about_this_company": d.owned, "text": text})
    if not payload_docs:
        return []
    payload = {
        "company": {"names": names, "product": comp.product_name},
        "missing_fields": {f: FACTS[f].label for f in missing},
        "documents": payload_docs,
    }
    result = await llm.with_structured_output(_Extraction).ainvoke([
        {"role": "system", "content": EXTRACT_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ])
    if not isinstance(result, _Extraction):
        result = _Extraction.model_validate(result)
    return result.facts


def _apply(comp: CompetitorProfile, fact: _Extracted, doc: _Doc) -> None:
    value = fact.value.strip()
    if fact.field == "review_count":
        setattr(comp, "review_count", int(value.replace(",", "")))
    elif fact.field == "rating":
        setattr(comp, "rating", value.split("/")[0].strip())
    else:
        setattr(comp, fact.field, value[:160])
    if doc.url and doc.url not in comp.sources:
        comp.sources.append(doc.url)
    comp.fact_status[fact.field] = FieldStatus(
        status="found", source_url=doc.url or None, quote=fact.quote.strip()[:300],
        reason=f"Stated on {host_of(doc.url) or 'a fetched page'}.",
    )


# ── Orchestration ───────────────────────────────────────────────────────────────


async def complete_profiles(
    report: SWOTReportDelta,
    documents: list[tuple[str, str]],
    search_fn: SearchFn,
    crawl_fn: CrawlFn,
    llm: Any = None,
    *,
    rounds: int = 2,
    pages_per_competitor: int = 3,
) -> tuple[SWOTReportDelta, list[str], list[str], list[str]]:
    """
    Fills missing profile facts with verified values. Returns (report, diagnostics, new texts,
    new urls); the new evidence is handed back so later stages see the pages fetched here.
    """
    diagnostics: list[str] = []
    new_texts: list[str] = []
    new_urls: list[str] = []
    pool: list[tuple[str, str]] = [(u or "", t) for u, t in documents if t]
    fetched = {u for u, _ in pool if u}

    # Facts already held (from the main research) are marked found, so the dashboard can tell
    # them apart from facts this step could not find.
    for comp in report.competitors:
        for f in FACTS:
            if not _is_empty(current_value(comp, f)) and f not in comp.fact_status:
                comp.fact_status[f] = FieldStatus(status="found", reason="From the main research pages.")

    checked: dict[tuple[str, str], int] = {}
    rejected_total = 0
    filled_total = 0

    for round_number in range(1, rounds + 1):
        todo = [(c, missing_facts(c)) for c in report.competitors]
        todo = [(c, m) for c, m in todo if m]
        if not todo:
            break

        # Search for every rival's missing facts in one batch.
        queries = [q for c, m in todo for q in build_queries(c, m, round_number)]
        try:
            results = await search_fn(queries, round_number) if queries else []
        except Exception as exc:
            logger.warning("Profile completion search failed: %s", exc)
            diagnostics.append(f"[PROFILE_COMPLETER] Round {round_number} search failed ({type(exc).__name__}).")
            results = []
        for r in results:
            text = f"{r.title}\n{r.snippet}" if r.snippet else ""
            if text:
                pool.append((r.url or "", text))
                new_texts.append(text)
                if r.url:
                    new_urls.append(r.url)

        # Crawl the pages that belong to each rival: its directory profiles and own pages.
        to_crawl: list[str] = []
        for comp, _missing in todo:
            names = search_names(comp.brand_name)
            hosts = own_hosts(comp)
            picked = 0
            for r in results:
                if picked >= pages_per_competitor:
                    break
                if r.url and r.url not in fetched and r.url not in to_crawl and page_belongs_to(r.url, names, hosts):
                    to_crawl.append(r.url)
                    picked += 1
        if to_crawl:
            try:
                pages = await crawl_fn(to_crawl)
            except Exception as exc:
                logger.warning("Profile completion crawl failed: %s", exc)
                pages = []
            for p in pages:
                if p.get("markdown") and p.get("url"):
                    pool.append((p["url"], p["markdown"]))
                    fetched.add(p["url"])
                    new_texts.append(p["markdown"])
                    new_urls.append(p["url"])

        for comp, missing in todo:
            names = search_names(comp.brand_name) or [comp.brand_name]
            hosts = own_hosts(comp)
            docs: list[_Doc] = []
            for i, (url, text) in enumerate(pool):
                owned = bool(url) and page_belongs_to(url, names, hosts)
                if owned or mentions(text, names):
                    docs.append(_Doc(f"d{i}", url, text, _norm(text), owned))
            # Own pages and profiles first: they are about this company by construction.
            docs.sort(key=lambda d: (not d.owned,))
            for f in missing:
                checked[(comp.brand_name, f)] = len(docs)
            by_id = {d.doc_id: d for d in docs}

            # Model readings first: they keep the full value ("$50,000 to over $6 million")
            # where a regex stops at the first amount. Both pass the same verifier; the regex
            # reads are the fallback, and the whole answer when no model is configured.
            candidates: list[_Extracted] = []
            if llm is not None and docs:
                try:
                    candidates.extend(await _llm_extract(llm, comp, missing, docs, names))
                except Exception as exc:
                    logger.warning("Profile extraction failed for %s: %s", comp.brand_name, exc)
                    diagnostics.append(
                        f"[PROFILE_COMPLETER] {comp.brand_name}: extraction skipped ({type(exc).__name__})."
                    )
            for d in docs:
                candidates.extend(_deterministic_facts(d, missing))

            filled: list[str] = []
            rejections: list[str] = []
            for fact in candidates:
                if fact.field not in missing or not _is_empty(current_value(comp, fact.field)):
                    continue
                ok, why = verify(fact, by_id, names)
                if ok:
                    _apply(comp, fact, by_id[fact.doc_id])
                    filled.append(f"{FACTS[fact.field].label} {fact.value.strip()[:40]}")
                else:
                    rejected_total += 1
                    label = FACTS[fact.field].label if fact.field in FACTS else fact.field
                    rejections.append(f"{label} '{fact.value[:30]}' ({why})")
            filled_total += len(filled)
            if filled:
                diagnostics.append(f"[PROFILE_COMPLETER] {comp.brand_name}: found {', '.join(filled)}.")
            if rejections:
                diagnostics.append(
                    f"[PROFILE_COMPLETER] {comp.brand_name}: rejected unverifiable {'; '.join(rejections[:4])}."
                )

    # Whatever is still missing gets the honest reason.
    for comp in report.competitors:
        for f in missing_facts(comp):
            prior = comp.fact_status.get(f)
            n = checked.get((comp.brand_name, f), 0)
            spec = FACTS[f]
            if prior and prior.status == "removed":
                prior.reason = (prior.reason + f" Searched {n} more page(s); none stated a verifiable {spec.label}.").strip()
                prior.pages_checked = n
                continue
            reason = (
                f"Searched {n} page(s), including directory profiles and their own site; none states their {spec.label}."
                if n else f"No page about them could be found to check for a {spec.label}."
            )
            if spec.rarely_public:
                reason += " " + spec.rarely_public
            comp.fact_status[f] = FieldStatus(status="not_stated", reason=reason, pages_checked=n)

    still = sum(len(missing_facts(c)) for c in report.competitors)
    diagnostics = list(dict.fromkeys(diagnostics))  # a second round re-rejects the same claims
    diagnostics.insert(
        0,
        f"[PROFILE_COMPLETER] Filled {filled_total} missing fact(s) with verified quotes; "
        f"rejected {rejected_total} unverifiable; {still} still not stated anywhere we looked.",
    )
    return report, diagnostics, new_texts, new_urls
