"""Group C (v1.4) tests — GAP 6: live Excel formulas in the export.

Run: .test-venv-mobile/bin/python tests/test_feat_formulas.py  (from project root)
Also pytest-collectable (plain asserts, no fixtures).

The formulas are checked with openpyxl opened data_only=False, so the
formula STRINGS are visible (openpyxl never evaluates them — Excel does
that when the file is opened). Expected values are computed in Python
and matched against the formula's target range, not against a computed
cell value.
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl
import pandas as pd

import engine


def _small_df():
    # price is column B, qty is column C; 3 data rows -> rows 2..4.
    return pd.DataFrame({
        "item": ["Pen", "Book", "Bag"],
        "price": [10.0, 20.0, 30.0],
        "qty": [1, 2, 3],
    })


def _formulas_by_label(wb):
    """{'Total price': '=SUM(...)', ...} from the KPIs (live) sheet."""
    ws = wb["KPIs (live)"]
    out = {}
    for row in ws.iter_rows(min_row=2):
        label, formula = row[0].value, row[1].value
        if label:
            out[label] = formula
    return out


def test_default_has_no_live_sheet():
    """formulas=False (the default) keeps the old workbook exactly:
    three sheets, KPIs sheet holds plain values, no live sheet."""
    df = _small_df()
    kpis = engine.auto_kpis(df)
    actions = [("Rows", "3 -> 3 rows")]
    raw = engine.to_excel_bytes(df, kpis, actions)
    assert raw[:4] == b"PK\x03\x04"
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=False)
    assert wb.sheetnames == ["Cleaned Data", "KPIs", "Cleaning Log"]
    # KPIs sheet still holds the values (not formulas).
    ws = wb["KPIs"]
    assert ws["A1"].value == "label" and ws["B1"].value == "value"
    assert [r[0].value for r in ws.iter_rows(min_row=2)] == [
        k["label"] for k in kpis]
    # And the data sheet is unchanged.
    back = pd.read_excel(io.BytesIO(raw), sheet_name="Cleaned Data")
    assert back["price"].tolist() == [10.0, 20.0, 30.0]
    print("default (no formulas) OK: 3 sheets, KPIs values untouched")


def test_formulas_small_frame():
    df = _small_df()
    raw = engine.to_excel_bytes(df, engine.auto_kpis(df), [], formulas=True)
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=False)
    assert wb.sheetnames == ["Cleaned Data", "KPIs", "Cleaning Log",
                             "KPIs (live)"]
    formulas = _formulas_by_label(wb)
    # price is column B, qty is column C; 3 rows -> 2..4.
    assert formulas["Total price"] == "=SUM('Cleaned Data'!B2:B4)"
    assert formulas["Average price"] == "=AVERAGE('Cleaned Data'!B2:B4)"
    assert formulas["Total qty"] == "=SUM('Cleaned Data'!C2:C4)"
    assert formulas["Average qty"] == "=AVERAGE('Cleaned Data'!C2:C4)"
    # Text column gets no formula row.
    assert not any("item" in label.lower() for label in formulas)
    assert len(formulas) == 4
    # The ranges really do cover the data: check the maths by hand.
    assert df["price"].sum() == 60.0 and df["price"].mean() == 20.0
    assert df["qty"].sum() == 6 and df["qty"].mean() == 2.0
    # KPIs (values) sheet is still there and unchanged.
    ws = wb["KPIs"]
    assert ws["A2"].value == "Rows" and ws["B2"].value == "3"
    print("formulas small frame OK: B2:B4 / C2:C4, 4 formula rows")


def test_formulas_sample_data_row_count():
    """The real messy sample: 77 cleaned rows -> data rows 2..78, and the
    numeric columns are quantity (G) and unit_price (H)."""
    raw = engine.load_file("messy_sales.csv",
                           open("sample_data/messy_sales.csv", "rb").read())
    clean, actions = engine.clean(raw)
    assert len(clean) == 77
    out = engine.to_excel_bytes(clean, engine.auto_kpis(clean), actions,
                                formulas=True)
    wb = openpyxl.load_workbook(io.BytesIO(out), data_only=False)
    formulas = _formulas_by_label(wb)
    assert formulas["Total quantity"] == "=SUM('Cleaned Data'!G2:G78)"
    assert formulas["Average quantity"] == "=AVERAGE('Cleaned Data'!G2:G78)"
    assert formulas["Total unit_price"] == "=SUM('Cleaned Data'!H2:H78)"
    assert formulas["Average unit_price"] == "=AVERAGE('Cleaned Data'!H2:H78)"
    assert len(formulas) == 4
    # Cross-check the ranges against the real totals.
    assert clean["quantity"].sum() == 198.5, clean["quantity"].sum()
    assert clean["unit_price"].sum() == 78323.0
    print("formulas sample OK: G2:G78 / H2:H78 over 77 rows")


def test_formulas_no_numeric_columns():
    df = pd.DataFrame({"name": ["Aarav", "Priya"], "city": ["Patna", "Delhi"]})
    raw = engine.to_excel_bytes(df, engine.auto_kpis(df), [], formulas=True)
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=False)
    ws = wb["KPIs (live)"]
    assert ws["A2"].value == "No numeric columns — nothing to total"
    assert _formulas_by_label(wb) == {"No numeric columns — nothing to total": None}
    print("formulas no-numeric-columns OK")


def test_formulas_empty_frame():
    df = pd.DataFrame({"price": pd.Series([], dtype=float)})
    raw = engine.to_excel_bytes(df, engine.auto_kpis(df), [], formulas=True)
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=False)
    ws = wb["KPIs (live)"]
    assert ws["A2"].value == "No data rows — nothing to total"
    print("formulas empty frame OK (no invalid H2:H1 range written)")


def test_formulas_flag_is_keyword_only_safe():
    """Calling with the old 3 positional args still works — the new
    parameter is optional and defaults to False."""
    df = _small_df()
    raw = engine.to_excel_bytes(df, [], [])
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=False)
    assert "KPIs (live)" not in wb.sheetnames
    print("old 3-arg call OK")


if __name__ == "__main__":
    test_default_has_no_live_sheet()
    test_formulas_small_frame()
    test_formulas_sample_data_row_count()
    test_formulas_no_numeric_columns()
    test_formulas_empty_frame()
    test_formulas_flag_is_keyword_only_safe()
    print("ALL FORMULA TESTS PASSED")
