"""Engine tests for the v1.1 upgrades: join, SQLite, fuzzy matching, PDF.

Run: python3 tests/test_engine.py   (from the project root)
No Streamlit needed. PDF validity is checked with pypdf when available.
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
import engine


def test_join():
    left = pd.DataFrame({"customer_id": ["C1", "C2", "C3"],
                         "sales": [100, 200, 300]})
    right = pd.DataFrame({"customer_id": ["C2", "C3", "C4"],
                          "city": ["Delhi", "Patna", "Gaya"]})
    joined, info = engine.join_frames(left, right, "customer_id", "customer_id", "left")
    assert len(joined) == 3 and info["matched_keys"] == 2
    assert info["left_only"] == 1 and info["right_only"] == 1
    assert joined.loc[joined["customer_id"] == "C2", "city"].iloc[0] == "Delhi"
    joined_i, _ = engine.join_frames(left, right, "customer_id", "customer_id", "inner")
    assert len(joined_i) == 2
    print("join OK:", info)


def test_sqlite():
    path = tempfile.mktemp(suffix=".db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE customers (id TEXT, name TEXT, city TEXT)")
    con.executemany("INSERT INTO customers VALUES (?, ?, ?)",
                    [("C1", "Aarav", "Delhi"), ("C2", "Priya", "Patna")])
    con.execute("CREATE TABLE orders (id TEXT, total REAL)")
    con.executemany("INSERT INTO orders VALUES (?, ?)", [("O1", 99.5)])
    con.commit()
    con.close()
    raw = Path(path).read_bytes()
    tables = engine.list_sqlite_tables(raw)
    assert tables == ["customers", "orders"], tables
    df = engine.load_sqlite(raw, "customers")
    assert list(df.columns) == ["id", "name", "city"] and len(df) == 2
    print("sqlite OK:", tables)


def test_fuzzy():
    s = pd.Series(["Aarav", "Arav", "Aarav", "Priya", "Priyaa", "Delhi", "Dehli", "Delhi"])
    groups = engine.fuzzy_groups(s, 0.85)
    by_canonical = {g["canonical"]: [v for v, _ in g["members"]] for g in groups}
    assert "Aarav" in by_canonical and "Arav" in by_canonical["Aarav"], by_canonical
    assert "Delhi" in by_canonical and "Dehli" in by_canonical["Delhi"], by_canonical
    assert "Priya" in by_canonical, by_canonical
    df = pd.DataFrame({"name": ["Aarav", "Arav", "Priyaa", "Delhi", "Dehli"]})
    mapping = {}
    for g in groups:
        for v, _ in g["members"][1:]:
            mapping[v] = g["canonical"]
    out = engine.apply_fuzzy(df, "name", mapping)
    assert sorted(out["name"].unique()) == ["Aarav", "Delhi", "Priya"], out["name"].unique()
    print("fuzzy OK:", by_canonical)


def test_pdf():
    kpis = [{"label": "Rows", "value": "77"}, {"label": "Total unit_price", "value": "78,323.0"}]
    actions = [("Rows", "80 -> 77 rows"), ("Drop duplicate rows", "3 row(s) removed")]
    pdf = engine.to_pdf_bytes("Data Cleaner Studio — Report", kpis, actions,
                              "Rows: 80 loaded -> 77 after cleaning.")
    assert pdf[:5] == b"%PDF-", "must start with %PDF-"
    assert len(pdf) > 500
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(pdf))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        assert "Data Cleaner Studio" in text, "title missing from PDF text"
        assert "78,323.0" in text, "KPI missing from PDF text"
        assert "77 rows" in text, "cleaning log missing from PDF text"
        print(f"pdf OK: {len(reader.pages)} page(s), text extracts cleanly")
    except ImportError:
        print("pdf OK (structural only — pypdf not installed, text not verified)")


def _sample_raw():
    return engine.load_file(
        "messy_sales.csv",
        open("sample_data/messy_sales.csv", "rb").read())


def _sample_clean():
    clean, _actions = engine.clean(_sample_raw())
    return clean


def _kpi_map(kpis):
    return {k["label"]: k["value"] for k in kpis}


def test_kpis_revenue_sample():
    """(a) On the cleaned sample the KPI is real revenue, not a price sum:
    sum(quantity x unit_price) = 207,992.00 with the median-fill fix
    (quantity 2.5 -> 3, total 208; missing unit prices fill at 999).
    The plain 'Total unit_price' label is gone — nothing may read as
    revenue unless it is revenue."""
    clean = _sample_clean()
    kpis = _kpi_map(engine.auto_kpis(clean))
    assert kpis["Revenue (quantity x unit_price)"] == "207,992.00", kpis
    assert kpis["Sum of quantity"] == "208", kpis
    assert kpis["Average quantity"] == "2.7", kpis
    assert kpis["Average unit_price"] == "1,017.18", kpis
    assert "Total unit_price" not in kpis and "Total quantity" not in kpis
    assert not any(l.startswith("Revenue") and l != "Revenue (quantity x unit_price)"
                   for l in kpis)
    print("kpis revenue sample OK: Revenue (quantity x unit_price) = 207,992.00")


def test_kpis_price_only_honest_label():
    """(b) Only a price column, no quantity: the plain sum stays, labelled
    honestly as a sum — never as revenue."""
    df = pd.DataFrame({"unit_price": [100, 200, 300],
                       "city": ["Delhi", "Patna", "Delhi"]})
    kpis = _kpi_map(engine.auto_kpis(df))
    assert kpis["Sum of unit_price"] == "600.00", kpis
    assert not any(l.startswith("Revenue") for l in kpis), kpis
    print("kpis price-only OK: Sum of unit_price = 600.00, no Revenue")


def test_kpis_no_pair_no_revenue():
    """(c) Neither a quantity-like nor a price-like column: no bogus
    revenue KPI appears; plain sums are labelled as sums."""
    df = pd.DataFrame({"score": [1.5, 2.5, 3.0],
                       "city": ["Delhi", "Patna", "Delhi"]})
    kpis = _kpi_map(engine.auto_kpis(df))
    assert kpis["Sum of score"] == "7.0", kpis
    assert not any(l.startswith("Revenue") for l in kpis), kpis
    # Two quantity-like columns is ambiguous: also no revenue.
    df2 = pd.DataFrame({"quantity": [1, 2], "qty": [3, 4],
                        "unit_price": [10, 20]})
    kpis2 = _kpi_map(engine.auto_kpis(df2))
    assert not any(l.startswith("Revenue") for l in kpis2), kpis2
    # A column that already aggregates (total_amount) is not a price.
    df3 = pd.DataFrame({"quantity": [1, 2], "total_amount": [10, 20]})
    kpis3 = _kpi_map(engine.auto_kpis(df3))
    assert not any(l.startswith("Revenue") for l in kpis3), kpis3
    print("kpis no-pair OK: no Revenue without one clear qty + price pair")


def test_format_number():
    assert engine.format_number(198002, "money") == "198,002.00"
    assert engine.format_number(208, "count") == "208"
    assert engine.format_number(1234567, "count") == "1,234,567"
    assert engine.format_number(6.26, "percent") == "6.3%"
    assert engine.format_number(2.75, "number") == "2.8"
    assert engine.format_number(float("nan"), "money") == "—"
    try:
        engine.format_number(1, "zap")
        raise AssertionError("bad kind must raise")
    except ValueError:
        pass
    print("format_number OK: money 2dp, count 0dp, percent 1dp")


def test_smart_title_keeps_acronyms():
    assert engine._smart_title("USB Hub") == "USB Hub"
    assert engine._smart_title("usb hub") == "Usb Hub"  # not all-caps in source
    assert engine._smart_title("ELECTRONICS") == "Electronics"
    assert engine._smart_title("HOME") == "Home"  # short, but a word, not an acronym
    assert engine._smart_title("don't panic") == "Don't Panic"
    assert engine._smart_title("SKU-123 cable") == "SKU-123 Cable"
    df = pd.DataFrame({
        "product": ["USB Hub", "USB Hub", "ELECTRONICS", "electronics",
                    "Desk Lamp", "desk lamp"],
        "category": ["HOME", "Home", "home", "HOME", "Home", "home"],
        "n": [1, 2, 3, 4, 5, 6]})
    clean, _ = engine.clean(df)
    assert sorted(clean["product"].unique()) == [
        "Desk Lamp", "Electronics", "USB Hub"], clean["product"].unique()
    assert clean["category"].unique().tolist() == ["Home"], \
        clean["category"].unique()  # HOME / Home / home still unify
    print("smart title OK: USB Hub stays USB Hub, ELECTRONICS -> Electronics, "
          "HOME -> Home")


def test_median_fill_rounding():
    """A missing value in an integer-like column fills with the median
    rounded to a whole number (2.5 -> 3, halves away from zero), and the
    column becomes int — so 'Total quantity' can never read 198.5."""
    df = pd.DataFrame({"qty": [1, 2, 3, 4, None],
                       "price": [10.0, 20.0, 30.0, 40.0, 50.0]})
    clean, actions = engine.clean(df)
    assert clean["qty"].tolist() == [1, 2, 3, 4, 3], clean["qty"].tolist()
    assert str(clean["qty"].dtype) == "int64", clean["qty"].dtype
    assert any("rounded to a whole number" in d for _s, d in actions)
    # A genuinely fractional column keeps its fractional median.
    # (The second column keeps the missing row from being dropped as
    # an all-empty row.)
    df2 = pd.DataFrame({"amount": [1.5, 2.5, None, 3.5],
                        "n": [1, 2, 3, 4]})
    clean2, _ = engine.clean(df2)
    assert clean2["amount"].tolist() == [1.5, 2.5, 2.5, 3.5]
    assert str(clean2["amount"].dtype) == "float64"
    # On the sample: quantity total is whole, and the chunked path agrees.
    clean_s = _sample_clean()
    assert int(clean_s["quantity"].sum()) == 208
    assert str(clean_s["quantity"].dtype) == "int64"
    chunked, _ = engine.clean_csv_chunked(
        open("sample_data/messy_sales.csv", "rb").read())
    assert chunked.equals(clean_s), "chunked clean must match clean()"
    assert _kpi_map(engine.auto_kpis(chunked)) == _kpi_map(engine.auto_kpis(clean_s))
    print("median fill OK: 2.5 -> 3, sample quantity total 208, chunked parity")


def test_dates_stay_date_only():
    """A date with no time component shows as YYYY-MM-DD — in the
    profile sample and in the Excel export — never with 00:00:00."""
    clean = _sample_clean()
    prof = {r["column"]: r for r in engine.profile(clean)}
    assert prof["order_date"]["sample"] == "2026-06-13", prof["order_date"]
    assert "00:00:00" not in prof["order_date"]["sample"]
    kpis = engine.auto_kpis(clean)
    xlsx = engine.to_excel_bytes(clean, kpis, [("Rows", "80 -> 77 rows")])
    from openpyxl import load_workbook
    import io
    wb = load_workbook(io.BytesIO(xlsx))
    sheet = wb["Cleaned Data"]
    date_col = list(clean.columns).index("order_date") + 1
    assert sheet.cell(row=2, column=date_col).number_format == "yyyy-mm-dd"
    assert sheet.cell(row=2, column=date_col).value.strftime("%Y-%m-%d") == "2026-06-13"
    # A column that DOES carry times keeps a date+time format.
    df = pd.DataFrame({"when": ["2026-06-13 10:30:00", "2026-06-14 09:00:00"],
                       "n": [1, 2]})
    clean_t, _ = engine.clean(df)
    assert engine.profile(clean_t)[0]["sample"] == "2026-06-13 10:30"
    xlsx_t = engine.to_excel_bytes(clean_t, engine.auto_kpis(clean_t), [])
    wb_t = load_workbook(io.BytesIO(xlsx_t))
    assert wb_t["Cleaned Data"].cell(row=2, column=1).number_format == \
        "yyyy-mm-dd hh:mm:ss"
    print("dates OK: date-only stays YYYY-MM-DD in profile + Excel")


if __name__ == "__main__":
    test_join()
    test_sqlite()
    test_fuzzy()
    test_pdf()
    test_kpis_revenue_sample()
    test_kpis_price_only_honest_label()
    test_kpis_no_pair_no_revenue()
    test_format_number()
    test_smart_title_keeps_acronyms()
    test_median_fill_rounding()
    test_dates_stay_date_only()
    print("ALL ENGINE TESTS PASSED")
