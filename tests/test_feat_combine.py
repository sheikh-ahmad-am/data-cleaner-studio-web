"""Tests for Group 2 — combine & compare (feat_combine.py).

Run from the project root:
    .test-venv/bin/python tests/test_feat_combine.py
    .test-venv/bin/python -m pytest tests/test_feat_combine.py -q   (if pytest)

No Streamlit needed for the logic tests; render functions are checked
with a small fake `st` object (no real Streamlit calls).
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import engine
import feat_combine as fc

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "messy_sales.csv"


def _sample_raw():
    return engine.load_file("messy_sales.csv", SAMPLE.read_bytes())


def _sample_clean():
    cleaned, _actions = engine.clean(_sample_raw())
    return cleaned


# ---------------------------------------------------------------- compare --
def test_compare_by_key():
    old = pd.DataFrame({"id": ["A", "B", "C"], "sales": [100, 200, 300],
                        "city": ["Delhi", "Patna", "Gaya"]})
    new = pd.DataFrame({"id": ["B", "C", "D"], "sales": [200, 350, 400],
                        "city": ["Patna", "Gaya", "Ranchi"]})
    r = fc.compare_files(old, new, key="id")
    assert r["added"] == 1 and r["removed"] == 1, r
    assert r["changed_rows"] == 1 and r["changed_cells"] == 1, r
    assert "1 added, 1 removed, 1 row(s) changed (1 cell(s))" in r["summary"]
    det = r["detail_df"]
    assert list(det.columns) == ["change", "key", "column", "old", "new"]
    changed = det[det["change"] == "changed"]
    assert len(changed) == 1
    assert changed.iloc[0]["key"] == "C" and changed.iloc[0]["column"] == "sales"
    assert changed.iloc[0]["old"] == 300 and changed.iloc[0]["new"] == 350
    assert set(det[det["change"] == "added"]["key"]) == {"D"}
    assert set(det[det["change"] == "removed"]["key"]) == {"A"}
    print("compare_by_key OK:", r["summary"])


def test_compare_by_position_and_identical():
    old = pd.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})
    new = pd.DataFrame({"x": [1, 9, 3, 4], "y": ["a", "b", "c", "d"]})
    r = fc.compare_files(old, new)
    assert r["added"] == 1 and r["removed"] == 0, r
    assert r["changed_rows"] == 1 and r["changed_cells"] == 1, r
    r2 = fc.compare_files(old, old.copy())
    assert r2["added"] == r2["removed"] == 0
    assert r2["changed_rows"] == r2["changed_cells"] == 0
    assert len(r2["detail_df"]) == 0
    print("compare_by_position OK:", r["summary"])


def test_compare_nan_equal_and_missing_key():
    old = pd.DataFrame({"id": [1, 2], "v": [np.nan, 5]})
    new = pd.DataFrame({"id": [1, 2], "v": [np.nan, 6]})
    r = fc.compare_files(old, new, key="id")
    assert r["changed_rows"] == 1 and r["changed_cells"] == 1, r  # NaN==NaN
    try:
        fc.compare_files(old, new, key="nope")
    except ValueError:
        pass
    else:
        raise AssertionError("missing key column must raise ValueError")
    print("compare_nan/missing-key OK")


def test_compare_on_messy_sample():
    raw = _sample_raw()
    clean = _sample_clean()
    assert len(raw) == 80 and len(clean) == 77, (len(raw), len(clean))
    # Same rows, cleaned values: compare raw vs clean on order id.
    # Raw column is 'Order ID'; clean it is 'order_id' — no common key
    # name, so compare by position on the shared values instead.
    old = raw[["Order ID", "Quantity"]].copy()
    new = clean[["order_id", "quantity"]].copy()
    new.columns = ["Order ID", "Quantity"]
    r = fc.compare_files(old, new, key="Order ID")
    # The 3 dropped rows are exact duplicates sharing an order ID with a
    # kept row, so key matching sees duplicate keys, not removals — and
    # the median-filled quantities show up as changed cells.
    assert r["added"] == 0 and r["removed"] == 0, r
    assert "duplicate keys ignored" in r["summary"], r["summary"]
    assert r["changed_rows"] == 19 and r["changed_cells"] == 19, r
    # Dropping rows outright IS a removal: clean vs clean-minus-3-rows.
    r2 = fc.compare_files(clean, clean.iloc[:74].copy(), key="order_id")
    assert r2["removed"] == 3 and r2["added"] == 0, r2
    assert "3 removed" in r2["summary"]
    print("compare_on_sample OK:", r["summary"], "|", r2["summary"])


# ---------------------------------------------------------------- append ---
def test_append_same_columns():
    a = pd.DataFrame({"id": [1, 2], "sales": [10, 20]})
    b = pd.DataFrame({"id": [3], "sales": [30]})
    combined, report = fc.append_files([a, b])
    assert len(combined) == 3 and list(combined.columns) == ["id", "sales"]
    assert report["rows_per_file"] == [2, 1] and report["total_rows"] == 3
    assert report["missing_columns"] == {} and report["extra_columns"] == {}
    assert "same columns" in report["notes"][0]
    print("append_same OK:", report)


def test_append_column_mismatch():
    a = pd.DataFrame({"id": [1], "sales": [10], "city": ["Delhi"]})
    b = pd.DataFrame({"id": [2], "sales": [20], "region": ["North"]})
    combined, report = fc.append_files([a, b])
    assert len(combined) == 2
    assert set(combined.columns) == {"id", "sales", "city", "region"}
    assert pd.isna(combined.loc[1, "city"]) and pd.isna(combined.loc[0, "region"])
    assert report["missing_columns"]["file_2"] == ["city"], report
    assert report["extra_columns"]["file_2"] == ["region"], report
    assert any("missing" in n for n in report["notes"])
    assert any("extra" in n for n in report["notes"])
    empty, rep0 = fc.append_files([])
    assert len(empty) == 0 and rep0["rows_per_file"] == []
    print("append_mismatch OK:", report["notes"])


def test_append_sample_split():
    clean = _sample_clean()
    first, second = clean.iloc[:40].copy(), clean.iloc[40:].copy()
    combined, report = fc.append_files([first, second])
    assert len(combined) == 77 and report["rows_per_file"] == [40, 37]
    assert combined["unit_price"].sum() == clean["unit_price"].sum()
    print("append_sample OK: rows", report["rows_per_file"])


# ------------------------------------------------------- multi-sheet xlsx --
def _two_sheet_bytes():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame({"id": [1, 2], "sales": [10, 20]}).to_excel(
            w, sheet_name="Jan", index=False)
        pd.DataFrame({"id": [3], "sales": [30]}).to_excel(
            w, sheet_name="Feb", index=False)
    return buf.getvalue()


def test_excel_sheets():
    raw = _two_sheet_bytes()
    assert fc.list_excel_sheets(raw) == ["Jan", "Feb"]
    jan = fc.load_excel_sheet(raw, "Jan")
    assert list(jan.columns) == ["id", "sales"] and len(jan) == 2
    feb = fc.load_excel_sheet(raw, "Feb")
    assert feb["sales"].iloc[0] == 30
    combined, names = fc.load_excel_all(raw)
    assert names == ["Jan", "Feb"] and len(combined) == 3
    assert combined["sales"].sum() == 60
    print("excel_sheets OK:", names, len(combined))


def test_excel_empty_string_becomes_nan():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame({"a": ["x", ""], "b": [1, 2]}).to_excel(
            w, sheet_name="S", index=False)
    df = fc.load_excel_sheet(buf.getvalue(), "S")
    assert pd.isna(df["a"].iloc[1]), df
    print("excel_empty_string OK")


# ----------------------------------------------------------------- pivot ---
def test_pivot():
    df = pd.DataFrame({
        "region": ["North", "North", "South", "South"],
        "category": ["A", "B", "A", "B"],
        "sales": [10, 20, 30, 40]})
    out = fc.pivot_table(df, "region", "category", "sales", "Sum")
    assert set(out.columns) == {"region", "A", "B"}, list(out.columns)
    north = out[out["region"] == "North"].iloc[0]
    assert north["A"] == 10 and north["B"] == 20
    south = out[out["region"] == "South"].iloc[0]
    assert south["A"] == 30 and south["B"] == 40
    avg = fc.pivot_table(df, "region", None, "sales", "Average")
    assert avg[avg["region"] == "North"]["sales"].iloc[0] == 15
    cnt = fc.pivot_table(df, "region", None, "sales", "Count")
    assert cnt["sales"].tolist() == [2, 2]
    try:
        fc.pivot_table(df, "region", None, "sales", "Median")
    except ValueError:
        pass
    else:
        raise AssertionError("bad agg must raise ValueError")
    print("pivot OK:\n", out.to_string(index=False))


def test_pivot_on_messy_sample():
    clean = _sample_clean()
    out = fc.pivot_table(clean, "category", None, "unit_price", "Sum")
    by_cat = dict(zip(out["category"], out["unit_price"]))
    assert by_cat["Electronics"] == clean[clean["category"] == "Electronics"]["unit_price"].sum()
    total = fc.pivot_table(clean, "category", None, "unit_price", "Sum")["unit_price"].sum()
    assert total == 78323.0, total  # task-stated sample total
    top = clean["category"].value_counts()
    assert top.index[0] == "Electronics" and top.iloc[0] == 33
    print("pivot_sample OK: total unit_price =", total)


# ------------------------------------------------------- calculated col ----
def test_calculated_column():
    df = pd.DataFrame({"qty": [2, 3, 4], "price": [100, 50, 25]})
    out = fc.add_calculated_column(df, "total", "qty", "*", "price")
    assert out["total"].tolist() == [200, 150, 100]
    assert "total" not in df.columns  # input not mutated
    out2 = fc.add_calculated_column(df, "double", "qty", "*", 2)
    assert out2["double"].tolist() == [4, 6, 8]
    out3 = fc.add_calculated_column(df, "half", "qty", "/", "2")
    assert out3["half"].tolist() == [1.0, 1.5, 2.0]
    print("calculated OK")


def test_calculated_division_by_zero():
    df = pd.DataFrame({"a": [10, 20, 30], "b": [2, 0, 5]})
    out = fc.add_calculated_column(df, "ratio", "a", "/", "b")
    assert out["ratio"].iloc[0] == 5.0 and out["ratio"].iloc[2] == 6.0
    assert pd.isna(out["ratio"].iloc[1]), out["ratio"].tolist()
    assert not np.isinf(out["ratio"].dropna()).any()
    out2 = fc.add_calculated_column(df, "r2", "a", "/", 0)
    assert out2["r2"].isna().all()
    try:
        fc.add_calculated_column(df, "x", "a", "/", "no_such_col")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown column/number must raise ValueError")
    print("calculated_div_zero OK:", out["ratio"].tolist())


def test_calculated_on_messy_sample():
    clean = _sample_clean()
    out = fc.add_calculated_column(clean, "line_total", "quantity",
                                   "*", "unit_price")
    assert "line_total" in out.columns and len(out) == 77
    row = out.iloc[0]
    assert row["line_total"] == row["quantity"] * row["unit_price"]
    print("calculated_sample OK: line_total sum =",
          round(float(out["line_total"].sum()), 1))


# ------------------------------------------------------------------ kpis ---
def test_compare_kpis():
    old = [{"label": "Rows", "value": "100"},
           {"label": "Total sales", "value": "10,000.0"},
           {"label": "Top category", "value": "Electronics (33)"},
           {"label": "Date range", "value": "2026-01-01 to 2026-08-29"}]
    new = [{"label": "Rows", "value": "77"},
           {"label": "Total sales", "value": "7,500.0"},
           {"label": "Top category", "value": "Electronics (20)"},
           {"label": "Date range", "value": "2026-01-01 to 2026-08-29"}]
    r = fc.compare_kpis(old, new, pct_threshold=20)
    by_label = {x["label"]: x for x in r}
    assert "Date range" not in by_label, "date ranges have no number to compare"
    assert by_label["Rows"]["pct_change"] == -23.0
    assert by_label["Rows"]["flagged"] is True
    assert by_label["Total sales"]["pct_change"] == -25.0
    assert by_label["Total sales"]["flagged"] is True
    assert by_label["Top category"]["old"] == 33.0
    assert by_label["Top category"]["new"] == 20.0
    assert by_label["Top category"]["flagged"] is True
    small = fc.compare_kpis(
        [{"label": "Rows", "value": "100"}],
        [{"label": "Rows", "value": "105"}], pct_threshold=20)
    assert small[0]["pct_change"] == 5.0 and small[0]["flagged"] is False
    zero = fc.compare_kpis(
        [{"label": "Rows", "value": "0"}],
        [{"label": "Rows", "value": "5"}])
    assert zero[0]["pct_change"] == float("inf") and zero[0]["flagged"] is True
    print("compare_kpis OK:", r)


def test_compare_kpis_on_sample():
    clean = _sample_clean()
    kpis = engine.auto_kpis(clean)
    labels = [k["label"] for k in kpis]
    assert "Revenue (quantity x unit_price)" in labels and "Top category" in labels
    r = fc.compare_kpis(kpis, kpis)
    assert all(x["pct_change"] == 0.0 and x["flagged"] is False for x in r)
    half = clean.iloc[:40].copy()
    r2 = fc.compare_kpis(kpis, engine.auto_kpis(half))
    flagged = [x["label"] for x in r2 if x["flagged"]]
    assert "Rows" in flagged, r2  # 77 -> 40 is a -48% move
    print("compare_kpis_sample OK: flagged on half-sample:", flagged)


# ------------------------------------------------- render fns (fake st) ----
class _FakeWidget:
    """Stand-in for a Streamlit widget return value holder."""

    def __init__(self, value=None):
        self.value = value


class FakeSt:
    """Minimal fake `st` — records widget keys, never crashes."""

    def __init__(self):
        self.session_state = {}
        self.widget_keys = []
        self.messages = []

    # -- display (no-ops that record text) --
    def subheader(self, *a, **k):
        self.messages.append(("subheader", a))

    def write(self, *a, **k):
        self.messages.append(("write", a))

    def info(self, *a, **k):
        self.messages.append(("info", a))

    def error(self, *a, **k):
        self.messages.append(("error", a))

    def success(self, *a, **k):
        self.messages.append(("success", a))

    def warning(self, *a, **k):
        self.messages.append(("warning", a))

    def dataframe(self, *a, **k):
        self.messages.append(("dataframe", a))

    def rerun(self):
        self.messages.append(("rerun", ()))

    def columns(self, n):
        return [FakeSt() for _ in range(n)]

    # -- widgets: record key, return a harmless default --
    def _key(self, kwargs):
        key = kwargs.get("key")
        if key is not None:
            self.widget_keys.append(key)
        return key

    def file_uploader(self, *a, **k):
        self._key(k)
        return None

    def selectbox(self, *a, **k):
        self._key(k)
        options = a[1] if len(a) > 1 else k.get("options", [])
        return options[0] if options else None

    def button(self, *a, **k):
        self._key(k)
        return False

    def slider(self, *a, **k):
        self._key(k)
        return k.get("value", a[3] if len(a) > 3 else 0)

    def number_input(self, *a, **k):
        self._key(k)
        return k.get("value", 0.0)

    def text_input(self, *a, **k):
        self._key(k)
        return k.get("value", "")

    def download_button(self, *a, **k):
        self._key(k)
        return False


def test_render_functions_safe_without_data():
    st = FakeSt()
    st.session_state["raw"] = None
    st.session_state["clean"] = None
    # Every render must run without raising when there is no data.
    fc.render_compare(st)
    fc.render_append(st)
    fc.render_pivot(st, None)
    fc.render_calculated(st, None)
    fc.render_anomaly(st, None)
    # Every widget key used must start with "c_".
    bad = [k for k in st.widget_keys if not k.startswith("c_")]
    assert not bad, f"widget keys must start with c_: {bad}"
    print("render_no_data OK, widget keys:", sorted(set(st.widget_keys)))


def test_render_calculated_returns_none_without_click():
    st = FakeSt()
    df = _sample_clean()
    new_df, actions = fc.render_calculated(st, df)
    assert new_df is None and actions == []
    bad = [k for k in st.widget_keys if not k.startswith("c_")]
    assert not bad, bad
    print("render_calculated_no_click OK")


def test_render_pivot_and_anomaly_with_data():
    st = FakeSt()
    df = _sample_clean()
    fc.render_pivot(st, df)
    fc.render_anomaly(st, df)
    bad = [k for k in st.widget_keys if not k.startswith("c_")]
    assert not bad, bad
    print("render_pivot/anomaly_with_data OK")


if __name__ == "__main__":
    test_compare_by_key()
    test_compare_by_position_and_identical()
    test_compare_nan_equal_and_missing_key()
    test_compare_on_messy_sample()
    test_append_same_columns()
    test_append_column_mismatch()
    test_append_sample_split()
    test_excel_sheets()
    test_excel_empty_string_becomes_nan()
    test_pivot()
    test_pivot_on_messy_sample()
    test_calculated_column()
    test_calculated_division_by_zero()
    test_calculated_on_messy_sample()
    test_compare_kpis()
    test_compare_kpis_on_sample()
    test_render_functions_safe_without_data()
    test_render_calculated_returns_none_without_click()
    test_render_pivot_and_anomaly_with_data()
    print("ALL FEAT_COMBINE TESTS PASSED")
