"""Group C (v1.4) tests — GAP 7: live currency rates (feat_currency).

Run: .test-venv-mobile/bin/python tests/test_feat_currency.py  (from project root)
Also pytest-collectable (plain asserts, no fixtures).

The live API is NEVER hit for real here: urlopen is mocked for both the
live path (a canned good response) and the fallback path (a raised
error / bad payload). Whether the real API is reachable from this VM is
checked separately by hand and reported, not asserted — the tests must
pass offline too.
"""

import json
import sys
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import feat_currency as fc


class FakeResponse:
    """Minimal urlopen stand-in: a context manager whose .read() returns
    the given bytes."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


def _good_api_payload():
    # 1 USD = 94.50 INR, 1 EUR = 106.18 INR, 1 GBP = 127.70 INR.
    return json.dumps({
        "result": "success",
        "base_code": "USD",
        "rates": {"INR": 94.5, "USD": 1.0, "EUR": 0.89, "GBP": 0.74,
                  "JPY": 150.0},
    }).encode("utf-8")


def test_fixed_rates_match_enrich():
    """The fallback estimates are the same numbers feat_enrich uses."""
    assert fc.FIXED_RATES == {"USD": 83.0, "EUR": 90.0, "GBP": 105.0}
    import feat_enrich
    for cur, rate in fc.FIXED_RATES.items():
        assert feat_enrich.DEFAULT_FX_RATES[cur] == rate
    print("fixed rates OK: USD 83 / EUR 90 / GBP 105, same as feat_enrich")


def test_fallback_on_network_error():
    """No network -> estimated source, fixed rates, INR included at 1.0."""
    def boom(request, timeout=None):
        raise urllib.error.URLError("no network here")

    with mock.patch.object(fc.urllib.request, "urlopen", boom):
        rates, source = fc.get_rates()
    assert source == "estimated", source
    assert rates == {"INR": 1.0, "USD": 83.0, "EUR": 90.0, "GBP": 105.0}
    print("fallback on URLError OK: estimated, fixed rates")


def test_fallback_on_bad_payloads():
    """Bad JSON, a failed result, missing keys, zero/negative rates —
    every bad response falls back to estimated, never to a half rate."""
    bad_payloads = [
        b"{not json",
        json.dumps({"result": "error", "rates": {}}).encode(),
        json.dumps({"result": "success"}).encode(),  # no rates at all
        json.dumps({"result": "success",
                    "rates": {"INR": 94.5, "USD": 1.0}}).encode(),  # EUR/GBP missing
        json.dumps({"result": "success", "rates": {
            "INR": 94.5, "USD": 1.0, "EUR": 0.89, "GBP": 0.0}}).encode(),
        json.dumps({"result": "success", "rates": {
            "INR": -94.5, "USD": 1.0, "EUR": 0.89, "GBP": 0.74}}).encode(),
        json.dumps({"result": "success", "rates": "nope"}).encode(),
    ]
    for payload in bad_payloads:
        with mock.patch.object(fc.urllib.request, "urlopen",
                               lambda req, timeout=None, p=payload:
                               FakeResponse(p)):
            rates, source = fc.get_rates()
        assert source == "estimated", (payload, source)
        assert rates["USD"] == 83.0 and rates["EUR"] == 90.0
    # A timeout is a failure too.
    def slow(request, timeout=None):
        raise TimeoutError("timed out")

    with mock.patch.object(fc.urllib.request, "urlopen", slow):
        _, source = fc.get_rates()
    assert source == "estimated"
    print(f"fallback on {len(bad_payloads)} bad payloads + timeout OK")


def test_live_path_mocked():
    """A good API response -> source 'live' and INR-per-unit maths:
    USD 94.50, EUR 94.5/0.89, GBP 94.5/0.74."""
    with mock.patch.object(fc.urllib.request, "urlopen",
                           lambda req, timeout=None:
                           FakeResponse(_good_api_payload())):
        rates, source = fc.get_rates()
    assert source == "live", source
    assert rates["INR"] == 1.0
    assert rates["USD"] == 94.5
    assert abs(rates["EUR"] - 94.5 / 0.89) < 1e-9, rates["EUR"]
    assert abs(rates["GBP"] - 94.5 / 0.74) < 1e-9, rates["GBP"]
    # Sanity: live USD rate is NOT the fixed estimate.
    assert rates["USD"] != 83.0
    print(f"live path OK: USD {rates['USD']}, EUR {rates['EUR']:.2f}, "
          f"GBP {rates['GBP']:.2f} (mocked)")


def test_live_path_other_base():
    """get_rates(base='EUR'): the API quotes per 1 EUR, so INR per unit
    is rates['INR'] / rates[cur] — EUR itself is rates['INR'] / 1."""
    payload = json.dumps({
        "result": "success", "base_code": "EUR",
        "rates": {"INR": 106.0, "USD": 1.12, "EUR": 1.0, "GBP": 0.83},
    }).encode("utf-8")
    with mock.patch.object(fc.urllib.request, "urlopen",
                           lambda req, timeout=None: FakeResponse(payload)):
        rates, source = fc.get_rates(base="EUR")
    assert source == "live"
    assert rates["EUR"] == 106.0
    assert abs(rates["USD"] - 106.0 / 1.12) < 1e-9
    assert abs(rates["GBP"] - 106.0 / 0.83) < 1e-9
    print("live path with base=EUR OK")


def test_convert_currency_math():
    fixed = {"INR": 1.0, "USD": 83.0, "EUR": 90.0, "GBP": 105.0}
    assert fc.convert_currency(100, "USD", "INR", fixed) == 8300.0
    assert fc.convert_currency(8300, "INR", "USD", fixed) == 100.0
    assert fc.convert_currency(90, "EUR", "INR", fixed) == 8100.0
    assert fc.convert_currency(100, "USD", "EUR", fixed) == round(100 * 83 / 90, 2)
    assert fc.convert_currency(50, "GBP", "GBP", fixed) == 50.0  # same -> same
    assert fc.convert_currency(100, "usd", "inr", fixed) == 8300.0  # case-insensitive
    assert fc.convert_currency(10.555, "USD", "INR", fixed) == round(10.555 * 83, 2)
    for call in (lambda: fc.convert_currency(100, "JPY", "INR", fixed),
                 lambda: fc.convert_currency(100, "USD", "JPY", fixed),
                 lambda: fc.convert_currency(None, "USD", "INR", fixed),
                 lambda: fc.convert_currency("abc", "USD", "INR", fixed),
                 lambda: fc.convert_currency(100, "USD", "INR",
                                             {"USD": 83.0, "INR": 0.0})):
        try:
            call()
            raise AssertionError("bad conversion must raise")
        except ValueError:
            pass
    print("convert_currency math + errors OK")


def test_convert_column():
    df = pd.DataFrame({"price": [10.0, 20.0, None, "not money", 5]})
    fixed = {"INR": 1.0, "USD": 83.0, "EUR": 90.0, "GBP": 105.0}
    out = fc.convert_column(df, "price", "USD", "INR", fixed)
    assert "price_INR" in out.columns
    assert list(out["price_INR"].head(2)) == [830.0, 1660.0]
    assert pd.isna(out["price_INR"].iloc[2])  # blank stays blank
    assert pd.isna(out["price_INR"].iloc[3])  # unparseable stays blank
    assert out["price_INR"].iloc[4] == 415.0
    # Original frame untouched, source column kept.
    assert "price_INR" not in df.columns
    assert list(df["price"].head(2)) == [10.0, 20.0]
    assert list(out["price"].head(2)) == [10.0, 20.0]

    eur = fc.convert_column(df.head(2), "price", "USD", "EUR", fixed)
    assert list(eur["price_EUR"]) == [round(10 * 83 / 90, 2),
                                      round(20 * 83 / 90, 2)]
    try:
        fc.convert_column(df, "nope", "USD", "INR", fixed)
        raise AssertionError("missing column must raise")
    except ValueError:
        pass
    print("convert_column OK: new column, originals kept, blanks stay blank")


def test_live_and_estimated_never_confused():
    """The source string is the whole point: a live dict and an estimated
    dict are distinguishable by the return value alone."""
    with mock.patch.object(fc.urllib.request, "urlopen",
                           lambda req, timeout=None:
                           FakeResponse(_good_api_payload())):
        _, live_source = fc.get_rates()
    with mock.patch.object(fc.urllib.request, "urlopen",
                           lambda req, timeout=None:
                           (_ for _ in ()).throw(
                               urllib.error.URLError("down"))):
        _, est_source = fc.get_rates()
    assert live_source == "live" and est_source == "estimated"
    assert live_source != est_source
    print("source labelling OK: live != estimated")


if __name__ == "__main__":
    test_fixed_rates_match_enrich()
    test_fallback_on_network_error()
    test_fallback_on_bad_payloads()
    test_live_path_mocked()
    test_live_path_other_base()
    test_convert_currency_math()
    test_convert_column()
    test_live_and_estimated_never_confused()
    print("ALL CURRENCY TESTS PASSED")
