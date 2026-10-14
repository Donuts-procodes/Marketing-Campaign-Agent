"""
Exchange rates for putting rival prices in the merchant's currency.

ECB reference rates via frankfurter.dev (free, no key), fetched once per base currency per day
and cached in-process. A failed fetch returns None and callers leave prices unconverted; a
converted price always keeps the original amount and the rate used beside it.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx

logger = logging.getLogger(__name__)

FX_URL = "https://api.frankfurter.dev/v1/latest"
_cache: dict[tuple[str, str], dict[str, float]] = {}


async def rates_from(base: str, timeout: float = 10.0) -> dict[str, float] | None:
    """{currency: units of that currency per 1 `base`} for today, or None when unavailable."""
    base = base.upper()
    key = (base, date.today().isoformat())
    if key in _cache:
        return _cache[key]
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(FX_URL, params={"from": base})
            r.raise_for_status()
            rates = {k.upper(): float(v) for k, v in r.json().get("rates", {}).items()}
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("FX rates for %s unavailable: %s", base, exc)
        return None
    rates[base] = 1.0
    _cache[key] = rates
    return rates


# Currencies the ECB does not publish that are officially pegged to the US dollar (units per USD).
USD_PEGS = {"AED": 3.6725, "SAR": 3.75, "QAR": 3.64, "OMR": 0.3845, "BHD": 0.376, "JOD": 0.709}


async def _rate(from_ccy: str, to_ccy: str) -> float | None:
    if from_ccy == to_ccy:
        return 1.0
    # Through USD for pegged currencies: AED -> USD at the peg, then USD -> target at today's rate.
    if from_ccy in USD_PEGS:
        to_usd = 1 / USD_PEGS[from_ccy]
        onward = await _rate("USD", to_ccy)
        return to_usd * onward if onward is not None else None
    if to_ccy in USD_PEGS:
        to_usd = await _rate(from_ccy, "USD")
        return to_usd * USD_PEGS[to_ccy] if to_usd is not None else None
    rates = await rates_from(from_ccy)
    return rates.get(to_ccy) if rates else None


async def convert(amount: float, from_ccy: str, to_ccy: str) -> tuple[float, float] | None:
    """(converted amount, rate) or None when either currency has no rate today."""
    rate = await _rate(from_ccy.upper(), to_ccy.upper())
    if rate is None:
        return None
    return round(amount * rate, 2), round(rate, 6)
