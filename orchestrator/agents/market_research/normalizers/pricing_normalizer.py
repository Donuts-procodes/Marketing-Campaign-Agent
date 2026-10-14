"""
Pricing normalization: turns free-text `pricing_model` into a comparable `PricingTier`.

The dashboard and chat compare rivals on price, and a string cannot be compared: "$49/mo billed
annually" and "$588/year" are the same price, "$5,000 per project" is not cheaper than "$150/hr"
by any useful measure. A regex pass handles the common shapes; an LLM fallback handles prose,
and its answer is accepted only when the amount it reports appears in the raw string, so the
fallback can restructure a price but never invent one.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from orchestrator.schemas.research import PricingTier, SWOTReportDelta

logger = logging.getLogger(__name__)

_CURRENCY_SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "₹": "INR", "¥": "JPY", "A$": "AUD", "C$": "CAD", "rs": "INR"}
_CURRENCY_CODES = ("USD", "GBP", "EUR", "INR", "JPY", "AUD", "CAD")

# Amount with optional currency before or after: "$49", "49 USD", "€1.299,00" is out of scope.
# Currency may lead as a code ("INR 3,500") or symbol ("Rs 2,499", "$49"), or trail as a code or
# word ("49 USD", "2499 rupees"). "Rs" needs a word boundary or it matches inside "hours 9".
_AMOUNT = re.compile(
    r"(?:\b(?P<pre>USD|GBP|EUR|INR|JPY|AUD|CAD)\s?)?(?P<sym>A\$|C\$|\bRs\.?|[$£€₹¥])?\s?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?(?P<k>k\b)?"
    r"\s?(?P<code>USD|GBP|EUR|INR|JPY|AUD|CAD|rupees?\b|dollars?\b|euros?\b|pounds?\b)?",
    re.I,
)
_WORD_CURRENCY = {
    "rupee": "INR", "rupees": "INR", "dollar": "USD", "dollars": "USD",
    "euro": "EUR", "euros": "EUR", "pound": "GBP", "pounds": "GBP",
}

# Ordered: the first matching period wins, so "per month, billed annually" reads as monthly.
_PERIODS = (
    ("hourly", re.compile(r"/\s?h(?:ou)?r\b|per\s+hour|hourly|an\s+hour", re.I)),
    ("monthly", re.compile(r"/\s?mo(?:nth)?\b|per\s+month|monthly|a\s+month|/\s?m\b|p/?m\b", re.I)),
    ("annual", re.compile(r"/\s?y(?:ea)?r\b|per\s+year|annual(?:ly)?|yearly|a\s+year|p/?a\b", re.I)),
    ("project", re.compile(r"per\s+project|/\s?project|per\s+engagement|fixed\s+(?:fee|price)", re.I)),
    ("usage", re.compile(r"per\s+(?:user|seat|request|call|unit|gb|1k|1,000)|/\s?(?:user|seat)|usage[- ]based", re.I)),
    ("one_time", re.compile(r"one[- ]time|lifetime|once\b|outright", re.I)),
)

_FREE = re.compile(r"\bfree\b(?!\s+shipping)|freemium|free\s+trial|\$0\b", re.I)
_TIER = re.compile(
    r"\b(free|starter|basic|essential|standard|plus|pro|professional|premium|business|team|growth|enterprise|scale)\b",
    re.I,
)

_MONTHLY_FACTOR = {"monthly": 1.0, "annual": 1 / 12}


def _to_float(num: str, k: str | None) -> float | None:
    try:
        value = float(num.replace(",", ""))
    except ValueError:
        return None
    return value * 1000 if k else value


_NON_PRICING_CONTEXT = re.compile(
    r"\b(?:penalt(?:y|ies)|liabilit(?:y|ies)|bond|insurance|processing volume|transaction volume|"
    r"volume of|turnover|valuation|raised|funding|fine|fines|damages|settlement)\b",
    re.I,
)


def _is_plausible_price(amount: float | None, period: str | None) -> bool:
    if amount is None:
        return True
    if period == "hourly":
        return 5.0 <= amount <= 800.0
    if period == "monthly":
        return 0.50 <= amount <= 50_000.0
    if period == "annual":
        return 5.0 <= amount <= 500_000.0
    if period == "project":
        return 50.0 <= amount <= 5_000_000.0
    if period == "one_time":
        return 1.0 <= amount <= 200_000.0
    return 0.50 <= amount <= 200_000.0


def parse_pricing(raw: str | None) -> PricingTier | None:
    """
    Deterministic parse. Returns None when no amount and no free tier is found, so the caller
    can tell "unparsed" apart from "parsed as free".
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if _NON_PRICING_CONTEXT.search(text):
        return None

    amounts: list[tuple[float, str | None]] = []
    for m in _AMOUNT.finditer(text):
        sym = m.group("sym")
        code = m.group("pre") or m.group("code")
        # A bare number with no currency is a plan count, a year or a seat limit, not a price.
        if not sym and not code:
            continue
        value = _to_float(m.group("num"), m.group("k"))
        if value is None or value <= 0:
            continue
        sym_key = (sym or "").rstrip(".").lower() if sym and sym[:2].lower() == "rs" else (sym or "")
        code_ccy = (_WORD_CURRENCY.get(code.lower()) or code.upper()) if code else None
        currency = code_ccy or _CURRENCY_SYMBOLS.get(sym_key)
        amounts.append((value, currency))

    has_free = bool(_FREE.search(text))
    if not amounts and not has_free:
        if text.startswith("Gated") or "demo required" in text.lower() or "custom quote" in text.lower():
            return PricingTier(
                tier_name="Enterprise / Custom",
                amount=None,
                currency=None,
                period="project",
                monthly_equivalent=None,
                has_free_tier=False,
                commercial_motion="sales_gated",
                raw=text,
            )
        return None

    period = next((name for name, rx in _PERIODS if rx.search(text)), None)

    # Lowest paid price is the entry point a buyer compares against.
    amount, currency = min(amounts, key=lambda a: a[0]) if amounts else (None, None)
    if amount is not None and not _is_plausible_price(amount, period):
        amount = None
    if amount is None and not has_free:
        return None

    commercial_motion = None
    if "gated" in text.lower() or "demo" in text.lower() or "contact sales" in text.lower() or "quote" in text.lower():
        commercial_motion = "sales_gated"
    elif period == "usage":
        commercial_motion = "usage_based"
    elif period in ("project", "hourly"):
        commercial_motion = "service_retainer"
    elif has_free and amount is not None:
        commercial_motion = "plg_freemium"
    elif amount is not None and period in ("monthly", "annual"):
        commercial_motion = "flat_subscription"
    elif has_free:
        commercial_motion = "free_tier_only"

    # Name the paid plan the amount belongs to; "Free" is already captured by has_free_tier.
    tiers = [m for m in _TIER.finditer(text) if not (amount is not None and m.group(1).lower() == "free")]
    tier_match = tiers[0] if tiers else None
    monthly = (
        round(amount * _MONTHLY_FACTOR[period], 2)
        if amount is not None and period in _MONTHLY_FACTOR
        else None
    )
    return PricingTier(
        tier_name=tier_match.group(1).title() if tier_match else None,
        amount=amount,
        currency=currency,
        period=period,
        monthly_equivalent=monthly,
        has_free_tier=has_free,
        commercial_motion=commercial_motion,
        raw=text,
    )


def _amount_in_raw(amount: float, raw: str) -> bool:
    """Guards the LLM fallback: the number it reports must be written in the source string."""
    digits = re.sub(r"[^\d.]", " ", raw.replace(",", ""))
    for token in digits.split():
        try:
            value = float(token)
        except ValueError:
            continue
        if abs(value - amount) < 0.01 or abs(value * 1000 - amount) < 0.01:
            return True
    return False


async def _llm_parse(raw: str, llm: Any) -> PricingTier | None:
    if _NON_PRICING_CONTEXT.search(raw):
        return None
    result = await llm.with_structured_output(PricingTier).ainvoke([
        {
            "role": "system",
            "content": (
                "Parse this competitor pricing text into structured fields. Use the LOWEST paid "
                "price as amount. period is one of monthly, annual, one_time, project, hourly, "
                "usage, or null. Only use numbers that appear in the text. If no price is "
                "stated, return amount null."
            ),
        },
        {"role": "user", "content": raw},
    ])
    if not isinstance(result, PricingTier):
        result = PricingTier.model_validate(result)
    if result.amount is not None and not _amount_in_raw(result.amount, raw):
        return None
    if result.amount is not None and not _is_plausible_price(result.amount, result.period):
        result.amount = None
        result.monthly_equivalent = None
    if result.amount is None and not result.has_free_tier:
        return None
    if result.period in _MONTHLY_FACTOR and result.amount is not None:
        result.monthly_equivalent = round(result.amount * _MONTHLY_FACTOR[result.period], 2)
    else:
        result.monthly_equivalent = None
    result.raw = raw
    return result


async def normalize_report_pricing(
    report: SWOTReportDelta,
    llm: Any = None,
) -> tuple[SWOTReportDelta, list[str]]:
    """Sets `pricing_parsed` on every competitor whose pricing can be parsed."""
    diagnostics: list[str] = []
    by_regex = by_llm = 0
    unparsed: list[str] = []

    for c in report.competitors:
        c.pricing_parsed = None
        raw = c.pricing_model
        if not raw or raw == "detected":
            continue
        parsed = parse_pricing(raw)
        if parsed is not None and (parsed.amount is not None or parsed.has_free_tier):
            c.pricing_parsed = parsed
            by_regex += 1
            continue
        if llm is not None:
            try:
                parsed = await _llm_parse(raw, llm)
            except Exception as exc:
                logger.warning("Pricing LLM parse failed for %s: %s", c.brand_name, exc)
                parsed = None
            if parsed is not None:
                c.pricing_parsed = parsed
                by_llm += 1
                continue
        unparsed.append(c.brand_name)

    diagnostics.append(
        f"[PRICE_NORM] Parsed pricing for {by_regex + by_llm}/{len(report.competitors)} "
        f"competitors ({by_regex} rule-based, {by_llm} via LLM)."
    )
    if unparsed:
        diagnostics.append(f"[PRICE_NORM] Pricing text present but no amount stated: {', '.join(unparsed)}.")
    return report, diagnostics
