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


if __name__ == "__main__":
    test_join()
    test_sqlite()
    test_fuzzy()
    test_pdf()
    print("ALL ENGINE TESTS PASSED")
