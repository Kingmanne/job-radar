"""Salary helpers: convert to GBP and read salaries written as free text.

Rates are rough and only used to compare against your pay floor.
Override them with "fx_to_gbp" in the searches config.
"""
from __future__ import annotations

import re

DEFAULT_FX = {"GBP": 1.0, "USD": 0.78, "EUR": 0.85, "CAD": 0.56, "AUD": 0.51, "CHF": 0.89}
SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR"}

# Multiply to get a yearly figure, or (for "day") leave as a day rate.
PERIODS = {"year": ("year", 1), "annual": ("year", 1), "annually": ("year", 1),
           "month": ("year", 12), "monthly": ("year", 12), "week": ("year", 52), "weekly": ("year", 52),
           "fortnightly": ("year", 26), "day": ("day", 1), "daily": ("day", 1),
           "hour": ("day", 8), "hourly": ("day", 8)}


def to_gbp(amount: float | None, currency: str | None, fx: dict | None = None) -> float | None:
    if amount is None:
        return None
    rate = (fx or DEFAULT_FX).get((currency or "GBP").upper())
    return round(amount * rate) if rate else None


def normalise_period(amount: float | None, period: str | None) -> tuple[float | None, str]:
    """Return (amount, "year"|"day")."""
    kind, mult = PERIODS.get((period or "year").lower(), ("year", 1))
    return (amount * mult if amount is not None else None), kind


_NUM = re.compile(r"(\d+(?:[.,]\d+)*)\s*(k)?\b", re.I)


def parse_salary_text(text: str | None) -> tuple[float | None, float | None, str | None, str]:
    """'$120k - $150k' -> (120000, 150000, 'USD', 'year'). Unknown -> (None, None, None, 'year')."""
    if not text:
        return None, None, None, "year"
    t = text.strip()
    currency = next((c for s, c in SYMBOLS.items() if s in t), None)
    if currency is None:
        m = re.search(r"\b(GBP|USD|EUR|CAD|AUD|CHF)\b", t, re.I)
        currency = m.group(1).upper() if m else None
    period = "year"
    for word in ("hour", "day", "month", "week"):
        if re.search(rf"\b(per|/|an?)\s*{word}|{word}ly\b|\bp\.?\s*{word[0]}\b", t, re.I):
            period = word
            break
    values = []
    for num, k in _NUM.findall(t):
        v = float(num.replace(",", ""))
        if k:
            v *= 1000
        values.append(v)
    if not values:
        return None, None, currency, period
    lo, hi = min(values), max(values)
    if period == "year" and hi < 1000:      # "120-150" with no k: too ambiguous
        return None, None, currency, period
    return lo, hi, currency or "USD", period
