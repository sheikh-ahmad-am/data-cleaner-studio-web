"""Tests for engine.py chunked CSV + Parquet (v1.4, Group A).

Run: .test-venv-db/bin/python tests/test_feat_bigfiles.py   (from the project root)
Also pytest-collectable (plain asserts, no fixtures). No Streamlit needed.

Covers: chunked clean == non-chunked clean on the sample (exact frame
equality, incl. dtypes, at several chunksizes), chunked profile == profile,
Parquet round-trip, and chunked profile/clean numbers on a generated
50,000-row CSV checked against the in-memory equivalents.
"""

import csv
import io
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import engine

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = (ROOT / "sample_data" / "messy_sales.csv").read_bytes()
SAMPLE_PACK = (ROOT / "test-pack" / "messy_sales.parquet").read_bytes()


def test_chunked_clean_matches_sample():
    raw_df = engine.load_file("messy_sales.csv", SAMPLE)
    clean1, _a1 = engine.clean(raw_df)
    assert len(raw_df) == 80 and len(clean1) == 77, (len(raw_df), len(clean1))
    for cs in (50000, 7, 3):
        clean2, actions = engine.clean_csv_chunked(SAMPLE, chunksize=cs)
        pd.testing.assert_frame_equal(clean1, clean2)
        assert engine.auto_kpis(clean1) == engine.auto_kpis(clean2)
        assert actions[0] == ("Rows", "80 -> 77 rows"), actions[0]
        print(f"chunked clean == clean at chunksize={cs} (77 rows, exact)")
    print("chunked clean matches sample OK")


def test_chunked_profile_matches_sample():
    raw_df = engine.load_file("messy_sales.csv", SAMPLE)
    expected = engine.profile(raw_df)
    got = engine.profile_csv_chunked(SAMPLE)
    assert got == expected, (got, expected)
    got_small = engine.profile_csv_chunked(SAMPLE, chunksize=7)
    assert got_small == expected
    print("chunked profile == profile on sample OK")


def test_chunked_global_stats_sample():
    stats = engine.chunked_global_stats(SAMPLE)
    assert stats["rows_before"] == 80
    assert stats["duplicate_rows"] == 3
    assert stats["empty_rows"] == 0
    assert stats["empty_columns"] == ["notes"]
    assert stats["medians"] == {"quantity": 2.5, "unit_price": 999.0}, stats["medians"]
    assert stats["modes"]["category"] == "Electronics"
    assert stats["modes"]["region"] == "West"
    assert stats["kinds"]["quantity"] == "number"
    assert stats["kinds"]["order_date"] == "date"
    print("chunked global stats OK:", {k: stats[k] for k in
          ("rows_before", "duplicate_rows", "medians", "modes")})


def test_parquet_round_trip():
    raw_df = engine.load_file("messy_sales.csv", SAMPLE)
    clean1, _ = engine.clean(raw_df)
    blob = engine.to_parquet_bytes(clean1)
    assert blob[:4] == b"PAR1", "not a Parquet file"
    back = engine.load_parquet(blob)
    assert list(back.columns) == list(clean1.columns)
    pd.testing.assert_frame_equal(clean1, back, check_dtype=False)
    assert len(back) == 77
    print(f"parquet round-trip OK ({len(blob):,} bytes, 77 rows)")


def test_parquet_sample_in_test_pack():
    assert SAMPLE_PACK[:4] == b"PAR1", "test-pack parquet is not Parquet"
    df = engine.load_parquet(SAMPLE_PACK)
    raw_df = engine.load_file("messy_sales.csv", SAMPLE)
    assert len(df) == len(raw_df) == 80
    assert list(df.columns) == list(raw_df.columns)
    pd.testing.assert_frame_equal(raw_df, df, check_dtype=False)
    print("test-pack/messy_sales.parquet OK (80 rows, matches messy_sales.csv)")


def _gen_50k_csv() -> bytes:
    """Deterministic 50,000-row CSV with known properties: currency symbols,
    missing values, blank strings, mixed date formats, exact duplicate rows,
    and one all-empty column."""
    rng = random.Random(20261106)
    cities = ["Delhi", "Patna", "Gaya", "Mumbai", "delhi", "PATNA"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Order ID", "Order Date", "Customer", "Amount", "City", "Notes"])
    rows = []
    for i in range(1, 50001):
        amt = rng.choice([f"${rng.randint(100, 5000):,}.00", "",
                          f"{rng.randint(100, 5000)}", "Rs. 1,250.50"])
        date = rng.choice(["2026-01-05", "05/02/2026", "3 Mar 2026", ""])
        city = rng.choice(cities + [""])
        row = [f"ORD-{i}", date, f"Cust {i % 500}", amt, city, ""]
        rows.append(row)
        w.writerow(row)
    # 200 exact duplicate rows (copies of earlier rows, after cleaning they
    # are still duplicates).
    for j in range(200):
        w.writerow(rows[(j * 37) % 50000])
    return buf.getvalue().encode("utf-8")


def test_chunked_50k_profile_numbers():
    raw = _gen_50k_csv()
    raw_df = engine.load_file("big.csv", raw)
    assert len(raw_df) == 50200, len(raw_df)
    expected = engine.profile(raw_df)
    got = engine.profile_csv_chunked(raw, chunksize=50000)
    assert got == expected, [
        (e, g) for e, g in zip(expected, got) if e != g]
    got_small = engine.profile_csv_chunked(raw, chunksize=1000)
    assert got_small == expected
    by_col = {r["column"]: r for r in got}
    assert by_col["Notes"]["missing"] == 50200  # all-empty column
    assert by_col["Order ID"]["unique"] == 50000
    assert by_col["City"]["unique"] == 6  # '' counts as missing, not a value
    print("50k chunked profile OK:",
          {c: (by_col[c]["missing"], by_col[c]["unique"])
           for c in ("Order ID", "Amount", "City", "Notes")})


def test_chunked_50k_clean_matches():
    raw = _gen_50k_csv()
    raw_df = engine.load_file("big.csv", raw)
    clean1, _a1 = engine.clean(raw_df)
    clean2, actions = engine.clean_csv_chunked(raw, chunksize=10000)
    assert len(clean2) == len(clean1), (len(clean2), len(clean1))
    pd.testing.assert_frame_equal(clean1, clean2, check_dtype=False)
    assert engine.auto_kpis(clean1) == engine.auto_kpis(clean2)
    assert actions[0][0] == "Rows"
    assert actions[0][1] == f"50,200 -> {len(clean1):,} rows", actions[0]
    print(f"50k chunked clean OK: 50,200 -> {len(clean1):,} rows, "
          f"KPIs identical")
    # Global stats on the big file: median must be the true median of the
    # de-duplicated numeric values, not a per-chunk median.
    stats = engine.chunked_global_stats(raw, chunksize=10000)
    assert stats["duplicate_rows"] == 200, stats["duplicate_rows"]
    assert stats["empty_columns"] == ["notes"]
    assert abs(stats["medians"]["amount"]
               - float(clean1["amount"].median())) < 1e-9
    print("50k global stats OK: dupes=200, median(amount) exact")


if __name__ == "__main__":
    test_chunked_clean_matches_sample()
    test_chunked_profile_matches_sample()
    test_chunked_global_stats_sample()
    test_parquet_round_trip()
    test_parquet_sample_in_test_pack()
    test_chunked_50k_profile_numbers()
    test_chunked_50k_clean_matches()
    print("ALL BIGFILES TESTS PASSED")
