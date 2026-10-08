"""
Factual information grounding, citation verification, and anti-hallucination validation.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from orchestrator.agents.market_research.analysis.scoring import PLACEHOLDER_PRICING
from orchestrator.agents.market_research.analysis.freshness import extract_dates, latest_iso
from orchestrator.core.clock import today as _clock_today
from orchestrator.schemas.research import SWOTReportDelta

logger = logging.getLogger(__name__)

_CURRENCY = r"[$€£¥₹]"
# A price amount, optionally prefixed by a currency symbol: "$1,299.00", "49", "€15"
_PRICE_RE = re.compile(rf"({_CURRENCY})?\s?(\d[\d,]*(?:\.\d{{1,2}})?)")


def _price_tokens(pricing_model: str) -> list[tuple[str | None, str]]:
    """Extracts (currency symbol, normalized amount) pairs from a pricing string."""
    tokens = [
        (symbol or None, amount.replace(",", ""))
        for symbol, amount in _PRICE_RE.findall(pricing_model)
    ]
    # When currency amounts exist, bare numbers ("3 tiers", "12 months") are not prices.
    with_currency = [t for t in tokens if t[0]]
    return with_currency or tokens


def _price_in_text(token: tuple[str | None, str], text: str) -> bool:
    """True when the amount appears as a whole number (with its currency symbol, if any)."""
    symbol, amount = token
    integer, _, cents = amount.partition(".")
    # Allow thousands separators in the corpus, and ".00"-style cents to be omitted or present.
    int_pattern = r",?".join(re.escape(d) for d in integer)
    amount_pattern = int_pattern + (rf"\.{re.escape(cents)}" if cents else r"(?:\.\d{1,2})?")
    prefix = rf"{re.escape(symbol)}\s?" if symbol else r"(?<![\d.,])"
    return re.search(prefix + amount_pattern + r"(?![\d])", text) is not None


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SOURCE_LABEL_RE = re.compile(r"^[A-Za-z][\w &/.-]{0,40}:\s*")
# A statement is supported when this share of its 3-word phrases appears in one source document.
# Phrases (not loose words) are compared so a flipped claim ("is not available") fails.
_MIN_PHRASE_SUPPORT = 0.6
_PHRASE_LEN = 3


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _phrases(tokens: list[str]) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + _PHRASE_LEN]) for i in range(len(tokens) - _PHRASE_LEN + 1)}


def _document(text: str) -> tuple[str, set[tuple[str, ...]]]:
    return text.lower(), _phrases(_tokens(text))


def _strip_label(text: str) -> str:
    """'Meta Ad Library: "Copy here..."' -> 'Copy here'."""
    body = _SOURCE_LABEL_RE.sub("", text.strip(), count=1)
    body = body.strip().strip('"“”\'').strip()
    return body.removesuffix("...").removesuffix("…").strip().strip('"“”\'')


def _is_supported(statement: str, documents: list[tuple[str, set[tuple[str, ...]]]]) -> bool:
    """True when the statement appears verbatim, or near-verbatim phrase by phrase, in one source document."""
    body = _strip_label(statement)
    if not body:
        return False
    body_lower = body.lower()
    needed = _phrases(_tokens(body))
    for raw, doc_phrases in documents:
        if body_lower in raw:
            return True
        if needed and len(needed & doc_phrases) / len(needed) >= _MIN_PHRASE_SUPPORT:
            return True
    return False


def is_supported_by(statement: str, texts: list[str]) -> bool:
    """
    Public form of the support check: True when `statement` appears verbatim, or
    near-verbatim phrase by phrase, in any of `texts`.

    Used by later stages (e.g. the dashboard relevance filter) that restate already-grounded
    material and must not quietly introduce a claim no source made.
    """
    return _is_supported(statement, [_document(t) for t in texts if t])


def build_documents(texts: list[str]) -> list[tuple[str, set[tuple[str, ...]]]]:
    """Pre-built match index for `find_support_excerpt` over many statements."""
    return [_document(t) for t in texts if t]


def find_support_excerpt(
    statement: str,
    texts: list[str],
    width: int = 420,
    documents: list[tuple[str, set[tuple[str, ...]]]] | None = None,
) -> str | None:
    """
    The passage a statement was grounded on: ~`width` characters of the first source text
    that supports it, centred on the match. None when no text supports it.

    `documents` may be passed pre-built when checking many statements; it must be
    `[_document(t) for t in texts if t]` for the same `texts`.
    """
    body = _strip_label(statement)
    if not body:
        return None
    body_lower = body.lower()
    needed = _phrases(_tokens(body))
    docs = documents if documents is not None else [_document(t) for t in texts if t]
    for (raw, doc_phrases), text in zip(docs, [t for t in texts if t]):
        at = raw.find(body_lower)
        if at < 0:
            if not needed or len(needed & doc_phrases) / len(needed) < _MIN_PHRASE_SUPPORT:
                continue
            # Near-verbatim: centre on a shared three-word phrase (punctuation may sit between).
            first = next(iter(needed & doc_phrases))
            m = re.search(r"[^a-z0-9]+".join(map(re.escape, first)), raw)
            at = m.start() if m else 0
        start = max(0, at - width // 3)
        return text[start : start + width].strip()
    return None


def _keep_supported(
    items: list[str], documents: list[tuple[str, set[tuple[str, ...]]]], field_name: str, brand: str, diagnostics: list[str]
) -> list[str]:
    kept = [s for s in items if _is_supported(s, documents)]
    dropped = len(items) - len(kept)
    if dropped:
        diagnostics.append(
            f"[FACTUAL_GUARD] Dropped {dropped} {field_name} for {brand} not found in any fetched source."
        )
    return kept


def validate_information_grounding(
    report: SWOTReportDelta,
    scraped_text: list[str],
    verified_urls: set[str],
    max_age_days: int = 548,
    today: date | None = None,
) -> tuple[SWOTReportDelta, list[str]]:
    """
    Validation Gate: Cross-verifies synthesized deliverable against raw crawl corpus.
    - Prunes hallucinated URLs
    - Suppresses ungrounded pricing numbers to prevent false-confidence
    - Extracts and anchors verbatim factual evidence directly from crawl text
    - Stamps each profile with the date of its newest evidence and flags stale data
    - Returns report and diagnostic logs
    """
    diagnostics: list[str] = []
    combined_raw_text = " ".join(scraped_text).lower()
    documents = [_document(t) for t in scraped_text if t]
    stale_before = (today or _clock_today()) - timedelta(days=max_age_days)

    for comp in report.competitors:
        # 0. Every claim, complaint, ad hook and quote must come from a fetched source
        comp.core_claims = _keep_supported(comp.core_claims, documents, "claim(s)", comp.brand_name, diagnostics)
        comp.weaknesses_mined = _keep_supported(
            comp.weaknesses_mined, documents, "complaint(s)", comp.brand_name, diagnostics
        )
        comp.ad_hooks = _keep_supported(comp.ad_hooks, documents, "ad hook(s)", comp.brand_name, diagnostics)
        comp.factual_evidence = _keep_supported(
            comp.factual_evidence, documents, "evidence quote(s)", comp.brand_name, diagnostics
        )

        # 1. Prune hallucinated sources
        original_count = len(comp.sources)
        comp.sources = [u for u in comp.sources if u in verified_urls]
        if original_count > len(comp.sources):
            diagnostics.append(
                f"[FACTUAL_GUARD] Pruned {original_count - len(comp.sources)} unverified source URLs for {comp.brand_name}."
            )

        # 2. Strict Price Grounding: Zero False-Confidence
        if comp.pricing_model and comp.pricing_model != PLACEHOLDER_PRICING:
            price_tokens = _price_tokens(comp.pricing_model)
            if price_tokens:
                is_grounded = all(_price_in_text(tok, combined_raw_text) for tok in price_tokens)
                if not is_grounded:
                    diagnostics.append(
                        f"[FACTUAL_GUARD] Suppressed unverified price '{comp.pricing_model}' for {comp.brand_name} (unsupported by raw crawl text)."
                    )
                    comp.pricing_model = None

        # 3. Direct Factual Evidence Anchoring
        comp_name_lower = comp.brand_name.lower()
        matching_snippets = [
            s.strip() for s in scraped_text
            if comp_name_lower in s.lower() and len(s.strip()) > 30
        ]
        if not comp.factual_evidence and matching_snippets:
            comp.factual_evidence = [
                f'"{s[:180].strip()}..."' for s in matching_snippets[:3]
            ]

        # 4. Recency stamp: date this profile from the newest evidence that names the brand,
        #    and say so when that evidence is old rather than presenting it as current.
        comp_dates = [d for s in matching_snippets for d in extract_dates(s)]
        comp.as_of = latest_iso(comp_dates)
        if comp.as_of and max(comp_dates) < stale_before:
            diagnostics.append(
                f"[RECENCY] Newest dated evidence for {comp.brand_name} is {comp.as_of} "
                f"(older than {max_age_days} days) — treat its pricing and claims as potentially stale."
            )

    report.validation_diagnostics = diagnostics
    return report, diagnostics
