"""
Currency for the campaign brief. Every amount in a brief is in one currency, resolved once from
what the merchant told us (explicit code, a symbol in the budget, their market) and then the
research's parsed prices. Nothing is converted: a ₹10,000 budget stays 10,000 rupees.
"""

from __future__ import annotations

import re
from typing import Any

SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AED": "AED ", "SGD": "S$", "AUD": "A$", "CAD": "C$", "JPY": "¥"}

_SYMBOL_TO_CODE = [("₹", "INR"), ("rs", "INR"), ("inr", "INR"), ("€", "EUR"), ("£", "GBP"), ("¥", "JPY"),
                   ("aed", "AED"), ("s$", "SGD"), ("a$", "AUD"), ("c$", "CAD"), ("$", "USD"), ("usd", "USD")]

# Market words that settle the currency when nothing explicit was given.
_GEO_TO_CODE = [
    (r"\b(india|indian|delhi|ncr|mumbai|bengaluru|bangalore|hyderabad|chennai|pune|kolkata|gurgaon|gurugram|noida)\b", "INR"),
    (r"\b(uk|united kingdom|london|england|britain)\b", "GBP"),
    (r"\b(uae|dubai|abu dhabi)\b", "AED"),
    (r"\b(singapore)\b", "SGD"),
    (r"\b(australia|sydney|melbourne)\b", "AUD"),
    (r"\b(canada|toronto|vancouver)\b", "CAD"),
    (r"\b(germany|france|spain|italy|netherlands|europe|eu)\b", "EUR"),
    (r"\b(usa|united states|new york|california|texas)\b", "USD"),
]


def resolve_currency(merchant_context: dict[str, Any], swot_report: Any = None) -> str:
    """ISO code for this brief. Explicit beats inferred; USD only when nothing points elsewhere."""
    explicit = str(merchant_context.get("currency") or "").strip().upper()
    if explicit in SYMBOLS:
        return explicit

    budget = str(merchant_context.get("budget") or "").lower()
    for marker, code in _SYMBOL_TO_CODE:
        if marker in budget:
            return code

    # The stated market first; the dossier only when no market was given.
    for key in ("target_geography", "dossier"):
        text = str(merchant_context.get(key) or "").lower()[:20000]
        if key == "dossier" and "₹" in text:
            return "INR"
        for pattern, code in _GEO_TO_CODE:
            if re.search(pattern, text):
                return code

    # The research parsed rivals' prices; the most common currency there is the market's.
    counts: dict[str, int] = {}
    for comp in getattr(swot_report, "competitors", None) or []:
        parsed = getattr(comp, "pricing_parsed", None)
        if parsed and parsed.currency:
            counts[parsed.currency.upper()] = counts.get(parsed.currency.upper(), 0) + 1
    if counts:
        return max(counts, key=counts.get)
    return "USD"


def currency_of(merchant_context: dict[str, Any]) -> str:
    return str(merchant_context.get("currency") or "USD").upper()


def fmt_money(amount: float | None, currency: str) -> str:
    if amount is None:
        return "—"
    return f"{SYMBOLS.get(currency.upper(), currency.upper() + ' ')}{amount:,.0f}"
