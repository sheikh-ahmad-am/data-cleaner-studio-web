"""Group 1 (data quality & trust) tests for feat_quality.py.

Run: .test-venv/bin/python tests/test_feat_quality.py   (from project root)
Also pytest-collectable (plain asserts, no fixtures). No Streamlit server
needed — the render functions are exercised with a FakeSt stub.
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import engine
import feat_quality as fq


def _sample_raw():
    return engine.load_file("messy_sales.csv",
                            open("sample_data/messy_sales.csv", "rb").read())


def _sample_clean():
    clean, _actions = engine.clean(_sample_raw())
    return clean


# --------------------------------------------------------------------------
# 1. quality score
# --------------------------------------------------------------------------

def test_quality_score_sample():
    raw = _sample_raw()
    score, breakdown = fq.quality_score(raw)
    labels = {b["label"] for b in breakdown}
    # 16.6% missing -> 8 pts; 3/80 dup rows -> 4 pts; Notes empty -> 5 pts.
    assert score == 83, (score, breakdown)
    assert labels == {"Missing values", "Duplicate rows", "Empty columns"}, labels
    for b in breakdown:
        assert b["points_lost"] > 0 and isinstance(b["detail"], str) \
            and len(b["detail"]) > 10
    assert sum(b["points_lost"] for b in breakdown) == 100 - score

    clean = _sample_clean()
    score_c, breakdown_c = fq.quality_score(clean)
    assert score_c == 100 and breakdown_c == [], (score_c, breakdown_c)
    print("quality_score sample OK: raw 83 -> clean 100")


def test_quality_score_synthetic():
    perfect = pd.DataFrame({"a": [1, 2, 3, 4], "b": ["x", "y", "z", "w"]})
    assert fq.quality_score(perfect) == (100, [])

    # Half the cells empty: 50% missing -> 25 pts lost, nothing else wrong.
    half_missing = pd.DataFrame({"a": [1, None, 3, None],
                                 "b": ["x", "y", None, None]})
    score, breakdown = fq.quality_score(half_missing)
    assert score == 75, (score, breakdown)
    assert [b["label"] for b in breakdown] == ["Missing values"]

    # Mixed numbers and text in one column.
    mixed = pd.DataFrame({"qty": [1, 2, "N/A", 3, "unknown", 4, 5, 6],
                          "ok": [1, 2, 3, 4, 5, 6, 7, 8]})
    score, breakdown = fq.quality_score(mixed)
    assert score == 95, (score, breakdown)
    assert breakdown[0]["label"] == "Mixed-type columns"
    assert "qty" in breakdown[0]["detail"]

    # One stray text value is not "mixed" — needs >= 2 minority values.
    one_stray = pd.DataFrame({"qty": [1, 2, 3, 4, 5, 6, 7, "oops"]})
    assert fq.quality_score(one_stray)[0] == 100

    # Empty frame scores 0 with an explanation.
    assert fq.quality_score(pd.DataFrame())[0] == 0
    print("quality_score synthetic OK")


# --------------------------------------------------------------------------
# 2. outliers
# --------------------------------------------------------------------------

def test_outliers_synthetic():
    df = pd.DataFrame({"v": [10, 11, 12, 13, 12, 11, 100],
                       "flat": [5, 5, 5, 5, 5, 5, 5]})
    outs = fq.find_outliers(df)
    assert len(outs) == 1, outs
    o = outs[0]
    assert o["column"] == "v" and o["row_index"] == 6 and o["value"] == 100.0
    assert o["lower"] == 8.75 and o["upper"] == 14.75, o

    new_df, n = fq.apply_outliers(df, "v", "drop")
    assert n == 1 and len(new_df) == 6 and 100 not in new_df["v"].values

    capped, n = fq.apply_outliers(df, "v", "cap")
    assert n == 1 and capped["v"].iloc[6] == 14.75

    kept, n = fq.apply_outliers(df, "v", "keep")
    assert n == 0 and kept.equals(df)

    try:
        fq.apply_outliers(df, "v", "zap")
        raise AssertionError("bad mode must raise")
    except ValueError:
        pass
    try:
        fq.apply_outliers(df, "nope", "drop")
        raise AssertionError("bad column must raise")
    except ValueError:
        pass
    print("outliers synthetic OK")


def test_outliers_sample():
    clean = _sample_clean()
    outs = fq.find_outliers(clean)
    by_col = {}
    for o in outs:
        by_col.setdefault(o["column"], []).append(o)
    # Quantity 5 sits above Q3 + 1.5*IQR (4.5); unit_price has none.
    assert len(by_col.get("quantity", [])) == 10, by_col.keys()
    assert by_col.get("unit_price", []) == []
    assert all(o["value"] == 5.0 for o in by_col["quantity"])
    print("outliers sample OK: 10 quantity outliers, 0 unit_price")


# --------------------------------------------------------------------------
# 3. validation rules
# --------------------------------------------------------------------------

def test_rules():
    today = date.today()
    df = pd.DataFrame({
        "age": [25, 15, 30, None, "abc"],
        "name": ["Aarav", "", "Priya", None, "Rohan"],
        "city": ["Delhi", "Patna", "delhi", "Gaya", "Mumbai"],
        "status": ["Active", "active", "Pending", "Active", "ACTIVE"],
        "signup": [(today - timedelta(days=300)).isoformat(),
                   (today + timedelta(days=200)).isoformat(),
                   (today - timedelta(days=2000)).isoformat(),
                   None, "not a date"],
    })
    cases = [
        ([{"column": "age", "rule": "greater_than", "value": 18}], {1, 4}),
        ([{"column": "age", "rule": "less_than", "value": 20}], {0, 2, 4}),
        ([{"column": "name", "rule": "not_empty"}], {1, 3}),
        ([{"column": "city", "rule": "contains", "value": "del"}], {1, 3, 4}),
        ([{"column": "status", "rule": "equals", "value": "Active"}], {2}),
        ([{"column": "signup", "rule": "date_not_future"}], {1, 4}),
        ([{"column": "signup", "rule": "date_not_past"}], {0, 2, 4}),
    ]
    for rules, want_rows in cases:
        got = fq.check_rules(df, rules)
        assert {v["row_index"] for v in got} == want_rows, (rules, got)
        assert all(v["rule_index"] == 0 for v in got)
        assert all(set(v) == {"rule_index", "column", "rule",
                              "row_index", "value"} for v in got)
    # Several rules at once: indices track the rule each violation came from.
    both = fq.check_rules(df, [{"column": "age", "rule": "greater_than",
                                "value": 18},
                               {"column": "name", "rule": "not_empty"}])
    assert {(v["rule_index"], v["row_index"]) for v in both} == {
        (0, 1), (0, 4), (1, 1), (1, 3)}, both
    try:
        fq.check_rules(df, [{"column": "age", "rule": "newer_than",
                             "value": 1}])
        raise AssertionError("unknown rule must raise")
    except ValueError:
        pass
    try:
        fq.check_rules(df, [{"column": "nope", "rule": "not_empty"}])
        raise AssertionError("unknown column must raise")
    except ValueError:
        pass
    print("rules OK")


# --------------------------------------------------------------------------
# 4. near-duplicates
# --------------------------------------------------------------------------

def test_near_dupes():
    df = pd.DataFrame({
        "customer": ["Aarav Sharma", "Arav Sharma", "Priya Patel",
                     "Priya Patil", "Rohan Das"],
        "amount": [100, 101, 50, 50, 70],
    })
    groups = fq.near_duplicates(df, "customer")
    by_canon = {g["canonical"]: g["members"] for g in groups}
    assert by_canon == {"Aarav Sharma": [0, 1],
                        "Priya Patel": [2, 3]}, by_canon

    # Numeric gate: 100 vs 101 is within 1%, so both groups still form.
    groups_num = fq.near_duplicates(df, "customer", "amount")
    assert {g["canonical"]: g["members"] for g in groups_num} == by_canon

    # But 100 vs 200 is far apart, so the Aarav group must NOT form.
    far = df.copy()
    far.loc[1, "amount"] = 200
    groups_far = fq.near_duplicates(far, "customer", "amount")
    assert {g["canonical"]: g["members"] for g in groups_far} == {
        "Priya Patel": [2, 3]}, groups_far

    new_df, removed = fq.merge_near_duplicates(df, groups, keep="first")
    assert removed == 2 and len(new_df) == 3
    assert list(new_df["customer"]) == ["Aarav Sharma", "Priya Patel",
                                        "Rohan Das"]
    new_last, removed_last = fq.merge_near_duplicates(df, groups, keep="last")
    assert removed_last == 2
    assert list(new_last["customer"]) == ["Arav Sharma", "Priya Patil",
                                          "Rohan Das"]

    # Stale row indices (after a re-clean) are ignored, not fatal.
    stale, removed_stale = fq.merge_near_duplicates(
        df, [{"canonical": "x", "members": [0, 99]}])
    assert removed_stale == 0 and len(stale) == 5
    print("near-duplicates OK")


# --------------------------------------------------------------------------
# 5. audit trail
# --------------------------------------------------------------------------

def test_audit():
    st_state = {}
    fq.record_audit(st_state, "Outliers: quantity", "2 row(s) removed")
    fq.record_audit(st_state, "Near-duplicates: customer", "1 row(s) merged")
    log = st_state["q_audit"]
    assert len(log) == 2
    assert log[0]["step"] == "Outliers: quantity"
    assert log[1]["detail"] == "1 row(s) merged"
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", log[0]["time"])
    assert set(log[0]) == {"time", "step", "detail"}
    print("audit OK")


# --------------------------------------------------------------------------
# 6. data dictionary
# --------------------------------------------------------------------------

def test_dictionary():
    raw = _sample_raw()
    md_text, table = fq.data_dictionary(raw)
    assert list(table.columns) == ["column", "type", "missing %",
                                   "unique", "sample"]
    assert len(table) == 10
    by_col = table.set_index("column").to_dict("index")

    assert by_col["Unit Price"]["type"] == "number"
    assert " to " in by_col["Unit Price"]["sample"]  # min-max, not one value
    assert by_col["Unit Price"]["sample"] == "199 to 1,599", by_col["Unit Price"]
    assert by_col["Category"]["sample"].startswith("Home (16)"), by_col["Category"]
    assert by_col["Notes"]["type"] == "empty"
    assert by_col["Notes"]["missing %"] == 100.0
    assert by_col["Notes"]["sample"] == "—"
    assert by_col["Order ID"]["unique"] == 77  # 3 order IDs appear twice

    assert md_text.startswith("# Data dictionary")
    assert "| Order ID |" in md_text and "| Notes | empty | 100.0 |" in md_text

    clean = _sample_clean()
    _md, table_c = fq.data_dictionary(clean)
    assert len(table_c) == 9
    assert table_c["missing %"].max() == 0.0
    print("dictionary OK")


# --------------------------------------------------------------------------
# render functions (FakeSt — no Streamlit server)
# --------------------------------------------------------------------------

class FakeSt:
    """Minimal stand-in for the streamlit module: widgets return preset
    values (or the first option / False), display calls are recorded."""

    def __init__(self, presets=None):
        self.session_state = {}
        self.presets = presets or {}
        self.calls = []

    def _rec(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            self._rec(name, *args, **kwargs)
            return None
        return _call

    def selectbox(self, label, options, key=None, **kwargs):
        self._rec("selectbox", label, options, key)
        return self.presets.get(key, options[0])

    def radio(self, label, options, key=None, **kwargs):
        self._rec("radio", label, options, key)
        return self.presets.get(key, options[0])

    def slider(self, label, lo, hi, value, step, key=None, **kwargs):
        self._rec("slider", label, lo, hi, value, step, key)
        return self.presets.get(key, value)

    def text_input(self, label, key=None, **kwargs):
        self._rec("text_input", label, key)
        return self.presets.get(key, "")

    def button(self, label, key=None, **kwargs):
        self._rec("button", label, key)
        return bool(self.presets.get(key, False))

    def download_button(self, label, data, key=None, **kwargs):
        self._rec("download_button", label, key)
        return False

    def columns(self, n):
        self._rec("columns", n)
        return [self] * n


def _called(fake, name):
    return [c for c in fake.calls if c[0] == name]


def test_render_smoke():
    raw, clean = _sample_raw(), _sample_clean()
    fake = FakeSt()
    fq.render_quality_panel(fake, raw)
    assert _called(fake, "metric") and _called(fake, "progress")

    fake = FakeSt()
    assert fq.render_outliers(fake, clean) == (None, [])
    assert _called(fake, "selectbox") and _called(fake, "radio")

    fake = FakeSt()
    fq.render_validation(fake, clean)
    assert _called(fake, "selectbox")
    assert fake.session_state["q_rules_data"] == []

    fake = FakeSt()
    assert fq.render_near_dupes(fake, clean) == (None, [])

    fake = FakeSt()
    fq.render_audit(fake)
    assert _called(fake, "info") and not _called(fake, "dataframe")

    fake = FakeSt()
    fq.render_dictionary(fake, raw)
    assert _called(fake, "markdown") and _called(fake, "download_button")
    print("render smoke OK")


def test_render_outlier_apply():
    clean = _sample_clean()
    fake = FakeSt(presets={"q_outlier_col": "quantity",
                           "q_outlier_mode": "Drop the outlier rows",
                           "q_outlier_apply": True})
    new_df, actions = fq.render_outliers(fake, clean)
    assert new_df is not None and len(new_df) == 67, len(new_df)
    assert len(actions) == 1 and actions[0][0] == "Outliers: quantity"
    assert "10 row(s) removed" in actions[0][1]
    assert len(fake.session_state["q_audit"]) == 1
    assert fake.session_state["q_audit"][0]["step"] == "Outliers: quantity"
    print("render outlier apply OK")


def test_render_validation_add_and_violations():
    clean = _sample_clean()
    fake = FakeSt(presets={"q_rule_col": "quantity",
                           "q_rule_type": "greater_than",
                           "q_rule_value": "0",
                           "q_rule_add": True})
    fq.render_validation(fake, clean)
    assert fake.session_state["q_rules_data"] == [
        {"column": "quantity", "rule": "greater_than", "value": 0.0}]

    # A rule that fails on the sample: quantity > 4 catches the 5s.
    fake2 = FakeSt()
    fake2.session_state["q_rules_data"] = [
        {"column": "quantity", "rule": "greater_than", "value": 4.0}]
    fq.render_validation(fake2, clean)
    assert _called(fake2, "dataframe"), "violations table should show"
    print("render validation OK")


def test_render_near_dupes_merge():
    df = pd.DataFrame({
        "customer": ["Aarav Sharma", "Arav Sharma", "Priya Patel",
                     "Priya Patil", "Rohan Das"],
        "amount": [100, 101, 50, 50, 70],
    })
    fake = FakeSt(presets={"q_nd_col": "customer", "q_nd_num": "(none)",
                           "q_nd_keep": "first", "q_nd_find": True,
                           "q_nd_merge": True})
    new_df, actions = fq.render_near_dupes(fake, df)
    assert new_df is not None and len(new_df) == 3, new_df
    assert len(actions) == 1 and "2 row(s) merged" in actions[0][1]
    assert len(fake.session_state["q_audit"]) == 1
    assert fake.session_state["q_nd_groups_data"] is None  # cleared
    print("render near-dupes merge OK")


def test_render_audit_with_entries():
    fake = FakeSt()
    fq.record_audit(fake.session_state, "Outliers: quantity",
                    "2 row(s) removed")
    fq.render_audit(fake)
    assert _called(fake, "dataframe") and _called(fake, "download_button")
    dl = _called(fake, "download_button")[0]
    assert dl[1][1] == "q_audit_download"
    print("render audit OK")


if __name__ == "__main__":
    test_quality_score_sample()
    test_quality_score_synthetic()
    test_outliers_synthetic()
    test_outliers_sample()
    test_rules()
    test_near_dupes()
    test_audit()
    test_dictionary()
    test_render_smoke()
    test_render_outlier_apply()
    test_render_validation_add_and_violations()
    test_render_near_dupes_merge()
    test_render_audit_with_entries()
    print("ALL QUALITY TESTS PASSED")
