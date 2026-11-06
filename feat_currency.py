"""Data Cleaner Studio — Group C: live currency rates (v1.4).

The app's original currency feature (feat_enrich.convert_currency) works
off FIXED estimates — 1 USD = Rs. 83, 1 EUR = Rs. 90, 1 GBP = Rs. 105 —
and says so on screen. This module adds the live option on top of it:

* get_rates() tries the free, no-key API https://open.er-api.com/v6/latest/USD
  and returns (rates, "live") — rates are INR per 1 unit of each currency.
* On ANY failure (no network, bad response, missing keys, nonsense values)
  it falls back to the same fixed estimates and returns (rates,
  "estimated"). The source string is part of the return value, so the UI
  can never show an estimate as a live rate: it must label the number
  with whichever source came back.
* convert_currency() / convert_column() do the maths on a rates dict from
  either source — they never fetch anything themselves.

Pure logic, no Streamlit imports, so it is unit-testable on its own.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pandas as pd

#: Fixed estimates, INR per 1 unit of the currency — the same numbers
#: feat_enrich.DEFAULT_FX_RATES uses. Shown on screen as "estimated",
#: never as live rates.
FIXED_RATES = {"USD": 83.0, "EUR": 90.0, "GBP": 105.0}

#: Currencies get_rates() reports, in INR per 1 unit. INR itself is 1.0.
CURRENCIES = ("INR", "USD", "EUR", "GBP")

API_URL = "https://open.er-api.com/v6/latest/{base}"
API_TIMEOUT_SECONDS = 5


def _inr_per_unit(api_rates: dict, base: str) -> dict | None:
    """Turn an API "rates" mapping (1 `base` = rates[cur] units of cur)
    into INR per 1 unit for each currency in CURRENCIES. Returns None
    when a needed rate is missing, not a number, or not positive."""
    try:
        inr_per_base = float(api_rates["INR"])
        if inr_per_base <= 0:
            return None
        out = {"INR": 1.0}
        for cur in ("USD", "EUR", "GBP"):
            rate = float(api_rates[cur])
            if rate <= 0:
                return None
            # 1 cur = (inr_per_base / rate) INR.
            out[cur] = inr_per_base / rate
        return out
    except (KeyError, TypeError, ValueError):
        return None


def _fetch_live_rates(base: str) -> dict | None:
    """One attempt at the live API. Returns the INR-per-unit dict, or
    None on any failure — the caller turns None into the estimate."""
    url = API_URL.format(base=base.upper())
    req = urllib.request.Request(url, headers={"User-Agent": "DataCleanerStudio/1.4"})
    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("result") != "success":
        return None
    rates = payload.get("rates")
    if not isinstance(rates, dict):
        return None
    return _inr_per_unit(rates, base)


def get_rates(base: str = "USD") -> tuple:
    """Fetch exchange rates as INR per 1 unit.

    Returns (rates, source) where source is "live" when the numbers came
    from the free API just now, or "estimated" when anything went wrong
    and the fixed estimates were used instead. The rates dict always
    covers INR, USD, EUR and GBP. The UI must show the source next to
    the numbers — an estimate is never presented as a live rate.
    """
    live = _fetch_live_rates(base)
    if live is not None:
        return live, "live"
    estimated = {"INR": 1.0}
    estimated.update(FIXED_RATES)
    return estimated, "estimated"


def convert_currency(amount, from_cur: str, to_cur: str, rates: dict) -> float:
    """Convert one amount: amount * rates[from] / rates[to], where rates
    maps currency -> INR per 1 unit (as get_rates returns). Same
    currency in and out returns the amount unchanged. Unknown currency
    or a zero rate raises ValueError. `amount` must be a number."""
    if amount is None or (isinstance(amount, float) and pd.isna(amount)):
        raise ValueError("Cannot convert a missing amount.")
    try:
        value = float(amount)
    except (TypeError, ValueError):
        raise ValueError(f"Cannot convert non-numeric amount: {amount!r}") from None
    src = str(from_cur).upper()
    dst = str(to_cur).upper()
    if src not in rates:
        raise ValueError(f"Unknown currency: {from_cur} "
                         f"(use one of {', '.join(sorted(rates))})")
    if dst not in rates:
        raise ValueError(f"Unknown currency: {to_cur} "
                         f"(use one of {', '.join(sorted(rates))})")
    if rates[dst] == 0:
        raise ValueError(f"Rate for {dst} is 0 — fix it before converting.")
    if src == dst:
        return value
    return round(value * float(rates[src]) / float(rates[dst]), 2)


def convert_column(df: pd.DataFrame, column: str, from_cur: str,
                   to_cur: str, rates: dict) -> pd.DataFrame:
    """Convert one numeric column from one currency to another. Returns a
    NEW DataFrame (the original is untouched) with an added column
    "{column}_{to_cur}" holding the converted values, rounded to 2
    decimals. Blank / non-numeric cells stay blank. The source column is
    kept, so nothing is lost."""
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not in the data.")
    out = df.copy()
    converted = []
    for value in out[column]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            converted.append(None)
            continue
        try:
            converted.append(convert_currency(value, from_cur, to_cur, rates))
        except ValueError:
            converted.append(None)
    out[f"{column}_{str(to_cur).upper()}"] = converted
    return out
