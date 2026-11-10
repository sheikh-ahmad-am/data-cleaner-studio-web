"""Batch 4 (share & finish) tests.

Run from the project root:  .test-venv-share/bin/python tests/test_feat_share.py
No Streamlit app needed — render functions run against a FakeSt.
Real behaviour asserted on the messy sample + small synthetic frames.
No real email is ever sent and no network call is ever made.
Recent files / backups in these tests use a temp folder (base_dir),
never the real app folder.
"""

import datetime
import io
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import engine
import feat_share


# ------------------------------------------------------------------ helpers
def _sample_raw():
    raw = Path(__file__).resolve().parent.parent / "sample_data" / "messy_sales.csv"
    return engine.load_file("messy_sales.csv", raw.read_bytes())


def _sample_clean():
    raw = _sample_raw()
    clean, actions = engine.clean(raw)
    return raw, clean, actions, engine.auto_kpis(clean)


def _grouped(clean):
    return (clean.groupby("category", dropna=False)["unit_price"].sum()
            .reset_index().sort_values("unit_price", ascending=False))


class _SpinnerCtx:
    """No-op context manager for FakeSt.spinner."""

    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


class FakeSt:
    """Minimal stand-in for the Streamlit module for render tests."""

    def __init__(self, values=None):
        self.values = values or {}
        self.session_state = {}
        self.calls = []
        self.downloads = []

    def _rec(self, method, *args):
        self.calls.append((method,) + args)

    def subheader(self, text):
        self._rec("subheader", text)

    def write(self, text):
        self._rec("write", text)

    def info(self, text):
        self._rec("info", text)

    def warning(self, text):
        self._rec("warning", text)

    def success(self, text):
        self._rec("success", text)

    def error(self, text):
        self._rec("error", text)

    def markdown(self, text, unsafe_allow_html=None):
        self._rec("markdown", text)

    def dataframe(self, df, width=None):
        self._rec("dataframe")
        self.last_frame = df

    def table(self, df):
        self._rec("table")

    def metric(self, label, value):
        self._rec("metric", label, value)

    def progress(self, value):
        self._rec("progress", value)
        self.last_progress = value

    def selectbox(self, label, options, key=None, **kw):
        self._rec("selectbox", label)
        return self.values.get(key, options[0])

    def radio(self, label, options, key=None, **kw):
        self._rec("radio", label)
        return self.values.get(key, options[0])

    def checkbox(self, label, key=None, value=False, help=None):
        self._rec("checkbox", label)
        return self.values.get(key, value)

    def text_input(self, label, key=None, value="", placeholder=None,
                   help=None, type=None):
        self._rec("text_input", label)
        return self.values.get(key, value)

    def number_input(self, label, key=None, value=0, min_value=None,
                     max_value=None, step=None, help=None):
        self._rec("number_input", label)
        return self.values.get(key, value)

    def time_input(self, label, key=None, value=None):
        self._rec("time_input", label)
        return self.values.get(key, value)

    def button(self, label, key=None, **kw):
        self._rec("button", label)
        return self.values.get(key, False)

    def spinner(self, text):
        """Context manager stand-in for st.spinner (records the text)."""
        self._rec("spinner", text)
        return _SpinnerCtx()

    def download_button(self, label, data, file_name=None, mime=None,
                        key=None, help=None):
        self._rec("download_button", label)
        self.downloads.append({"label": label, "data": data,
                               "file_name": file_name, "mime": mime})
        return False

    def messages(self, method):
        return [c[1] for c in self.calls if c[0] == method]


# ------------------------------------------------------------- 1 suggestions
def test_suggest_fixes_sample():
    raw = _sample_raw()
    assert (len(raw), len(raw.columns)) == (80, 10)
    sugg = feat_share.suggest_fixes(raw)
    assert isinstance(sugg, list) and len(sugg) >= 5
    for s in sugg:
        assert set(s) == {"title", "detail", "action"}, s
        assert isinstance(s["action"], dict) and "type" in s["action"]
        assert "column" in s["action"]
    types = {(s["action"]["type"], s["action"]["column"]) for s in sugg}
    assert ("set_case_title", "Category") in types, types
    assert ("parse_dates", "Order Date") in types, types
    assert ("fix_numbers", "Unit Price") in types, types
    assert ("drop_duplicates", "") in types, types
    assert any(t == "fill_missing" for t, _ in types), types
    assert len(sugg) <= 12, "suggestion list is capped at 12"
    print("suggest sample OK:", len(sugg), "suggestions incl. mixed-case, "
          "dates, numbers-as-text, duplicates, missing")


def test_suggest_fixes_phones_and_apply():
    df = pd.DataFrame({
        "name": ["Asha", "Ben", "Cara", "Dev"],
        "phone": ["9876543210", "+91 98765-43210", "09876543210",
                  "98765 43210"],
        "city": ["Delhi", "Delhi", "Mumbai", "Delhi"],
    })
    sugg = feat_share.suggest_fixes(df)
    phone = [s for s in sugg if s["action"]["type"] == "standardize_phones"]
    assert len(phone) == 1, sugg
    assert phone[0]["action"]["column"] == "phone"
    assert "phone" in phone[0]["title"].lower()
    new_df, action = feat_share.apply_suggestion(df, phone[0]["action"])
    assert list(new_df["phone"]) == ["+91 98765 43210"] * 4
    assert action[0] == "Standardize phones: phone"
    assert "4 formatted" in action[1] and "0 left unchanged" in action[1]
    # A column with only half phone-like values must NOT suggest phones.
    df2 = pd.DataFrame({"phone": ["9876543210", "call me", "n/a", "123"]})
    assert not [s for s in feat_share.suggest_fixes(df2)
                if s["action"]["type"] == "standardize_phones"]
    print("suggest phones OK: 4/4 detected, applied to +91 98765 43210")


def test_apply_suggestion_other_types():
    df = pd.DataFrame({
        "cat": ["Electronics", "ELECTRONICS", "home"],
        "amt": ["$1,200", "300", "₹500"],
        "when": ["2026-01-05", "2026-02-06", "2026-03-07"],
        "note": ["  hi  there ", "ok", "  x "],
    })
    new_df, _ = feat_share.apply_suggestion(
        df, {"type": "set_case_title", "column": "cat"})
    assert list(new_df["cat"]) == ["Electronics", "Electronics", "Home"]
    new_df, _ = feat_share.apply_suggestion(
        df, {"type": "fix_numbers", "column": "amt"})
    assert list(new_df["amt"]) == [1200.0, 300.0, 500.0]
    new_df, _ = feat_share.apply_suggestion(
        df, {"type": "parse_dates", "column": "when"})
    assert pd.api.types.is_datetime64_any_dtype(new_df["when"])
    new_df, _ = feat_share.apply_suggestion(
        df, {"type": "strip_spaces", "column": "note"})
    assert list(new_df["note"]) == ["hi there", "ok", "x"]
    try:
        feat_share.apply_suggestion(df, {"type": "nope", "column": "cat"})
    except ValueError as e:
        assert "Unknown suggestion" in str(e)
    else:
        raise AssertionError("unknown action type must raise ValueError")
    try:
        feat_share.apply_suggestion(df, {"type": "fix_numbers", "column": "zzz"})
    except ValueError as e:
        assert "not in the data" in str(e)
    else:
        raise AssertionError("missing column must raise ValueError")
    print("apply_suggestion OK: case/numbers/dates/spaces + error paths")


# ------------------------------------------------------- 2 type override
def test_override_column_type():
    df = pd.DataFrame({
        "amount": ["₹1,200", "300", "$45.50", None],
        "when": ["2026-01-05", "05 Feb 2026", "2026/03/07", None],
        "code": [101, 202, 303, 404],
    })
    num = feat_share.override_column_type(df, "amount", "number")
    assert pd.api.types.is_numeric_dtype(num["amount"])
    assert list(num["amount"].dropna()) == [1200.0, 300.0, 45.5]
    assert pd.isna(num["amount"].iloc[3])
    dt = feat_share.override_column_type(df, "when", "date")
    assert pd.api.types.is_datetime64_any_dtype(dt["when"])
    assert str(dt["when"].iloc[0].date()) == "2026-01-05"
    txt = feat_share.override_column_type(df, "code", "text")
    assert list(txt["code"]) == ["101", "202", "303", "404"]
    for bad_kind in ("bool", "Number", ""):
        try:
            feat_share.override_column_type(df, "code", bad_kind)
        except ValueError as e:
            assert "text" in str(e) and "number" in str(e)
        else:
            raise AssertionError(f"kind {bad_kind!r} must raise")
    try:
        feat_share.override_column_type(df, "nope", "text")
    except ValueError as e:
        assert "not in the data" in str(e)
    else:
        raise AssertionError("missing column must raise")
    print("type override OK: ₹1,200 -> 1200.0, dates parsed, ints -> text")


# ---------------------------------------------------------------- 3 phones
def test_standardize_phones():
    s = pd.Series(["9876543210", "+91 98765-43210", "09876543210",
                   "98765 43210", "+91-9876543210", "12345", "call me",
                   None, "", "6123456789"])
    out, changed, skipped = feat_share.standardize_phones(s)
    assert list(out[:5]) == ["+91 98765 43210"] * 5
    assert out.iloc[5] == "12345" and out.iloc[6] == "call me"
    assert pd.isna(out.iloc[7]), "None stays empty"
    assert out.iloc[8] == ""
    assert out.iloc[9] == "+91 61234 56789"
    assert changed == 6, changed
    assert skipped == 2, skipped
    # Already-formatted values count as neither changed nor skipped.
    out2, changed2, skipped2 = feat_share.standardize_phones(
        pd.Series(["+91 98765 43210"]))
    assert (changed2, skipped2) == (0, 0) and out2.iloc[0] == "+91 98765 43210"
    print("phones OK: 6 changed, 2 skipped, unparseable left untouched")


# ---------------------------------------------------------------- 4 strip
def test_strip_specials():
    s = pd.Series(["Hello 😀 World!", "A&B, C-D. E", "price $5 #deal @shop",
                   "café ☕ time", None, 42])
    out = feat_share.strip_specials(s)
    assert out.iloc[0] == "Hello World"
    assert out.iloc[1] == "A&B, C-D. E"
    assert out.iloc[2] == "price 5 deal shop"
    assert out.iloc[3] == "café time"
    assert pd.isna(out.iloc[4])
    assert out.iloc[5] == 42, "non-text values pass through unchanged"
    print("strip specials OK: emoji/$/#/@ removed, ., - & kept")


# ------------------------------------------------------------------ 5 goal
def test_goal_progress():
    _, clean, _, _ = _sample_clean()
    value, pct = feat_share.goal_progress(clean, "unit_price", "Sum", 100000)
    assert value == 78323.0 and abs(pct - 78.323) < 1e-9, (value, pct)
    value, pct = feat_share.goal_progress(clean, "unit_price", "Average", 1000)
    assert abs(value - 1017.1818181818181) < 1e-9
    assert abs(pct - 101.71818181818181) < 1e-9, "over target shows over 100%"
    value, pct = feat_share.goal_progress(clean, "quantity", "Count", 77)
    assert value == 77.0 and pct == 100.0
    for bad in (lambda: feat_share.goal_progress(clean, "nope", "Sum", 10),
                lambda: feat_share.goal_progress(clean, "unit_price", "Max", 10),
                lambda: feat_share.goal_progress(clean, "unit_price", "Sum", 0),
                lambda: feat_share.goal_progress(clean, "unit_price", "Sum", "x")):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("bad goal input must raise ValueError")
    print("goal OK: Sum 78,323 of 100,000 = 78.323%; Count 77/77 = 100%")


# --------------------------------------------------------------- 6 search
def test_search_rows():
    raw, clean, _, _ = _sample_clean()
    assert len(feat_share.search_rows(clean, "ananya")) == 13
    assert len(feat_share.search_rows(clean, "ANANYA")) == 13, "case-insensitive"
    assert len(feat_share.search_rows(clean, "Electronics")) == 33
    assert len(feat_share.search_rows(clean, "ORD-1001")) == 1
    assert len(feat_share.search_rows(clean, "zzz-no-match")) == 0
    assert len(feat_share.search_rows(clean, "")) == 77, "blank query = all rows"
    assert len(feat_share.search_rows(clean, "   ")) == 77
    # Whitespace-normalized matching (fix round, 2026-11-10): the raw
    # Customer column carries padded variants ("  Aarav Sharma "),
    # so a search for the name must find all 9 rows — including with
    # a doubled-space query — agreeing with the profile's top-value
    # count for "Aarav Sharma" (9).
    assert len(feat_share.search_rows(raw, "Aarav")) == 9
    assert len(feat_share.search_rows(raw, "Aarav Sharma")) == 9
    assert len(feat_share.search_rows(raw, "Aarav  Sharma")) == 9, \
        "a doubled-space query must match the single-space rows too"
    print("search OK: ananya 13, Electronics 33, ORD-1001 1, no-match 0")


# ------------------------------------------------- 7/8/9/10/11/13 renders
def test_render_sort():
    _, clean, _, _ = _sample_clean()
    st = FakeSt(values={"s_sort_col": "unit_price", "s_sort_dir": "Descending"})
    out = feat_share.render_sort(st, clean)
    assert out["unit_price"].iloc[0] == 1599.0
    assert out["unit_price"].iloc[-1] == 199.0
    st2 = FakeSt(values={"s_sort_col": "unit_price", "s_sort_dir": "Ascending"})
    out2 = feat_share.render_sort(st2, clean)
    assert out2["unit_price"].iloc[0] == 199.0
    assert out2["unit_price"].iloc[-1] == 1599.0
    assert len(out) == 77
    print("sort OK: desc 1599 first, asc 199 first")


def test_render_goal_and_search_and_type_override():
    _, clean, _, _ = _sample_clean()
    st = FakeSt(values={"s_goal_col": "unit_price", "s_goal_agg": "Sum",
                        "s_goal_target": 100000})
    value, pct = feat_share.render_goal(st, clean)
    assert value == 78323.0 and abs(pct - 78.323) < 1e-9
    assert any("78,323" in m and "78.3%" in m for m in st.messages("write")), \
        st.calls
    assert abs(st.last_progress - 0.78323) < 1e-9

    st = FakeSt(values={"s_search_q": "Ananya"})
    matches = feat_share.render_search(st, clean)
    assert matches is not None and len(matches) == 13
    st = FakeSt(values={"s_search_q": ""})
    assert feat_share.render_search(st, clean) is None

    df = pd.DataFrame({"amount": ["₹1,200", "300"]})
    st = FakeSt(values={"s_type_col": "amount", "s_type_kind": "number",
                        "s_type_apply": True})
    out = feat_share.render_type_override(st, df)
    assert out is not None and list(out["amount"]) == [1200.0, 300.0]
    st = FakeSt(values={"s_type_col": "amount", "s_type_kind": "number",
                        "s_type_apply": False})
    assert feat_share.render_type_override(st, df) is None
    print("render goal/search/type-override OK")


def test_render_phones_and_strip():
    df = pd.DataFrame({"phone": ["9876543210", "12345"],
                       "note": ["hi 😀 there", "plain"]})
    st = FakeSt(values={"s_phone_col": "phone", "s_phone_apply": True})
    new_df, actions = feat_share.render_standardize_phones(st, df)
    assert list(new_df["phone"]) == ["+91 98765 43210", "12345"]
    assert actions == [("Standardize phones: phone",
                        "1 formatted, 1 left unchanged")]
    st = FakeSt(values={"s_strip_col": "note", "s_strip_apply": True})
    new_df, actions = feat_share.render_strip_specials(st, df)
    assert list(new_df["note"]) == ["hi there", "plain"]
    assert actions[0][0] == "Strip special characters: note"
    st = FakeSt(values={"s_strip_col": "note", "s_strip_apply": False})
    assert feat_share.render_strip_specials(st, df) == (None, [])
    print("render phones/strip OK")


def test_render_suggestions_apply():
    df = pd.DataFrame({"cat": ["Electronics", "ELECTRONICS", "home"],
                       "n": [1, 2, 3]})
    sugg = feat_share.suggest_fixes(df)
    assert sugg[0]["action"]["type"] == "set_case_title"
    st = FakeSt(values={"s_sugg_apply_0": True})
    new_df, actions = feat_share.render_suggestions(st, df)
    assert new_df is not None
    assert list(new_df["cat"]) == ["Electronics", "Electronics", "Home"]
    assert actions[0][0] == "Fix categories: cat"
    st = FakeSt(values={})
    assert feat_share.render_suggestions(st, df) == (None, [])
    st = FakeSt(values={})
    new_df, actions = feat_share.render_suggestions(
        st, pd.DataFrame({"a": [1, 2, 3]}))
    assert (new_df, actions) == (None, [])
    assert any("No suggestions" in m for m in st.messages("info"))
    print("render suggestions OK: first card applies mixed-case fix")


# ------------------------------------------------------------- 8 recent
def test_recent_roundtrip_and_cap():
    raw_bytes = (Path(__file__).resolve().parent.parent
                 / "sample_data" / "messy_sales.csv").read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        assert feat_share.list_recent(tmp) == []
        entry = feat_share.add_recent("messy_sales.csv", raw_bytes, tmp)
        assert entry["name"] == "messy_sales.csv"
        assert entry["where"] == "recent/messy_sales.csv"
        assert "when" in entry and entry["when"].startswith("2026")
        assert (Path(tmp) / "recent.json").exists()
        assert (Path(tmp) / "recent" / "messy_sales.csv").exists()
        entries = feat_share.list_recent(tmp)
        assert len(entries) == 1 and entries[0]["name"] == "messy_sales.csv"
        loaded = feat_share.load_recent("messy_sales.csv", tmp)
        assert (len(loaded), len(loaded.columns)) == (80, 10)
        # DataFrame input saves as CSV; path input copies the file.
        feat_share.add_recent("from_frame", pd.DataFrame({"a": [1], "b": [2]}), tmp)
        assert feat_share.load_recent("from_frame", tmp).shape == (1, 2)
        # Cap at 5, newest first.
        for i in range(5):
            feat_share.add_recent(f"f{i}.csv", b"a,b\n1,2\n", tmp)
        entries = feat_share.list_recent(tmp)
        assert len(entries) == 5, entries
        assert entries[0]["name"] == "f4.csv"
        assert "messy_sales.csv" not in [e["name"] for e in entries]
        try:
            feat_share.load_recent("gone.csv", tmp)
        except ValueError as e:
            assert "not in the recent files list" in str(e)
        else:
            raise AssertionError("unknown recent name must raise")
        try:
            feat_share.add_recent("  ", b"x", tmp)
        except ValueError:
            pass
        else:
            raise AssertionError("empty recent name must raise")
    print("recent OK: add/list/load round-trip, 5-file cap, newest first")


def test_render_recent_keep_and_open():
    raw_bytes = (Path(__file__).resolve().parent.parent
                 / "sample_data" / "messy_sales.csv").read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        # Tick off (default): nothing is saved.
        st = FakeSt(values={"s_recent_keep": False})
        assert feat_share.render_recent(
            st, df=None, source_name="messy_sales.csv",
            raw_bytes=raw_bytes, base_dir=tmp) is None
        assert feat_share.list_recent(tmp) == []
        # Tick on: a copy is saved, once only across reruns.
        st = FakeSt(values={"s_recent_keep": True})
        assert feat_share.render_recent(
            st, df=None, source_name="messy_sales.csv",
            raw_bytes=raw_bytes, base_dir=tmp) is None
        assert len(feat_share.list_recent(tmp)) == 1
        feat_share.render_recent(
            st, df=None, source_name="messy_sales.csv",
            raw_bytes=raw_bytes, base_dir=tmp)
        assert len(feat_share.list_recent(tmp)) == 1, "must not re-save"
        # Open button returns the stored frame.
        st2 = FakeSt(values={"s_recent_open_0": True})
        st2.session_state = st.session_state
        opened = feat_share.render_recent(st2, base_dir=tmp)
        assert opened is not None and len(opened) == 80
    print("render recent OK: off saves nothing, on saves once, Open returns 80 rows")


# ------------------------------------------------------------ 9 backups
def test_backup_restore():
    raw = _sample_raw()
    with tempfile.TemporaryDirectory() as tmp:
        assert feat_share.list_backups(tmp) == []
        path = feat_share.backup_raw(raw, "messy_sales.csv", tmp)
        assert re.search(r"messy_sales_2026-11-06_\d{4}\.csv$", path) or \
            re.search(r"messy_sales_\d{4}-\d{2}-\d{2}_\d{4}\.csv$", path), path
        assert Path(path).exists()
        entries = feat_share.list_backups(tmp)
        assert len(entries) == 1
        assert entries[0]["name"] == Path(path).name
        assert entries[0]["path"] == path and entries[0]["size_bytes"] > 0
        restored = feat_share.restore_backup(path)
        assert (len(restored), len(restored.columns)) == (80, 10)
        assert restored["Order ID"].iloc[0] == "ORD-1001"
        try:
            feat_share.restore_backup(str(Path(tmp) / "nope.csv"))
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("missing backup must raise FileNotFoundError")
    print("backup OK: timestamped name, list + restore round-trip (80 rows)")


def test_render_backups():
    raw = _sample_raw()
    with tempfile.TemporaryDirectory() as tmp:
        st = FakeSt(values={"s_backup_now": True})
        assert feat_share.render_backups(
            st, df=raw, source_name="messy_sales.csv", base_dir=tmp) is None
        assert len(feat_share.list_backups(tmp)) == 1
        st2 = FakeSt(values={"s_backup_restore_0": True})
        restored = feat_share.render_backups(st2, base_dir=tmp)
        assert restored is not None and len(restored) == 80
    print("render backups OK: backup button saves, Restore returns 80 rows")


# ---------------------------------------------------------- 10 one-click
def test_render_one_click():
    raw, clean, actions, kpis = _sample_clean()
    with tempfile.TemporaryDirectory() as tmp:
        # Not pressed yet: waiting, nothing happens.
        st = FakeSt(values={})
        status = feat_share.render_one_click(st, raw, None, base_dir=tmp)
        assert status["status"] == "waiting"
        assert feat_share.list_backups(tmp) == []
        # Pressed, no SMTP details: done, email pending, nothing sent.
        st = FakeSt(values={"s_oneclick_run": True})
        st.session_state["source_name"] = "messy_sales.csv"
        status = feat_share.render_one_click(st, raw, None, base_dir=tmp)
        assert status["status"] == "done", status
        assert (len(status["cleaned"]), len(status["cleaned"].columns)) == (77, 9)
        assert any(k["label"] == "Revenue (quantity x unit_price)"
                   and k["value"] == "207,992.00" for k in status["kpis"])
        assert "80 -> 77 rows" in status["report"]
        assert status["pdf_bytes"][:5] == b"%PDF-"
        assert Path(status["backup_path"]).exists()
        assert status["email"] == "pending"
        assert status["email_details_missing"] is True
        assert any("pending" in m.lower() for m in st.messages("warning")), \
            "email step must be labelled pending when details are missing"
        # Pressed with SMTP details filled: email ready (scheduled), still
        # nothing sent by this function itself.
        st = FakeSt(values={
            "s_oneclick_run": True,
            "e_email_server": "smtp.gmail.com", "e_email_port": "587",
            "e_email_user": "a@b.com", "e_email_pass": "s3cret",
            "e_email_recipient": "c@d.com", "e_email_enable": True,
            "e_email_time": datetime.time(9, 0),
        })
        st.session_state["source_name"] = "messy_sales.csv"
        status = feat_share.render_one_click(st, raw, None, base_dir=tmp)
        assert status["email"] == "ready"
        assert status["email_details_missing"] is False
        sched = st.session_state.get("e_email_sched")
        assert sched is not None and sched["server"] == "smtp.gmail.com"
        assert "s3cret" not in json.dumps(st.session_state)
        # No data at all.
        st = FakeSt(values={"s_oneclick_run": True})
        status = feat_share.render_one_click(st, None, None, base_dir=tmp)
        assert status["status"] == "not_ready"
    print("one-click OK: waiting -> done 80->77, PDF built, backup saved, "
          "email pending without SMTP / ready with it, never sent directly")


# ------------------------------------------------------- 11 html dashboard
def test_html_dashboard():
    _, clean, actions, kpis = _sample_clean()
    grouped = _grouped(clean)
    data = feat_share.html_dashboard_bytes(kpis, actions, grouped,
                                           "category", "unit_price")
    text = data.decode("utf-8")
    assert "207,992.00" in text, "Revenue KPI must appear"
    assert "Electronics (33)" in text, "Top category KPI must appear"
    assert "35,367" in text, "Electronics bar value must appear"
    assert "<svg" in text and "#117f50" in text, "hand-drawn SVG chart"
    # Supabase look: white page, white cards, ink text — no dark chrome.
    assert "background: #ffffff" in text
    assert "#121212" not in text and "#1e1e1e" not in text
    assert "#2F5D5A" not in text
    assert "<style>" in text and "http://" not in text \
        and "https://" not in text and "<script" not in text, \
        "self-contained: inline CSS only, no external links or scripts"
    assert "What was cleaned" in text
    # Empty grouped frame still builds a valid page.
    empty = feat_share.html_dashboard_bytes([], [], pd.DataFrame(),
                                            "category", "unit_price")
    assert b"No chart data yet" in empty
    print("HTML dashboard OK: KPIs + log + SVG bars, no external links")


# ------------------------------------------------------------ 12 portfolio
def test_portfolio_zip():
    _, clean, actions, kpis = _sample_clean()
    data = feat_share.portfolio_zip_bytes(clean, kpis, actions,
                                          "Messy sales — case study")
    assert data[:2] == b"PK", "must be a zip file"
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = zf.namelist()
    assert "cleaned_data.csv" in names and "README.md" in names, names
    png_names = [n for n in names if n.endswith(".png")]
    assert len(png_names) == 1, names
    readme = zf.read("README.md").decode("utf-8")
    assert "Messy sales — case study" in readme
    assert "77 rows" in readme and "9 columns" in readme
    assert "207,992.00" in readme and "Electronics (33)" in readme
    assert "What was cleaned" in readme and "What the data was" in readme
    csv = zf.read("cleaned_data.csv").decode("utf-8")
    assert len(csv.strip().splitlines()) == 78, "header + 77 rows"
    png = zf.read(png_names[0])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    from PIL import Image
    img = Image.open(io.BytesIO(png))
    assert img.size == (1200, 675)
    print("portfolio ZIP OK: csv + README + 1 chart PNG (1200x675)")


# ------------------------------------------------------------ 13 chart png
def test_chart_png():
    _, clean, _, _ = _sample_clean()
    grouped = _grouped(clean)
    for kind in ("bar", "line"):
        data = feat_share.chart_png_bytes(grouped, "category", "unit_price",
                                          "Sales by category", kind=kind)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        assert img.size == (1200, 675), img.size
        assert img.getpixel((0, 0)) == (255, 255, 255), \
            "white #ffffff background"
    try:
        feat_share.chart_png_bytes(grouped, "category", "unit_price", "T",
                                   kind="pie")
    except ValueError as e:
        assert "bar" in str(e) and "line" in str(e)
    else:
        raise AssertionError("unknown chart kind must raise ValueError")
    empty = feat_share.chart_png_bytes(pd.DataFrame(), "category",
                                       "unit_price", "Empty")
    from PIL import Image
    empty_img = Image.open(io.BytesIO(empty))
    assert empty_img.size == (1200, 675)
    assert empty_img.getpixel((0, 0)) == (255, 255, 255), \
        "empty chart is white too"
    print("chart PNG OK: bar + line 1200x675, white background, empty handled")


# ------------------------------------------- white charts + column types
def test_svg_bar_chart_white():
    _, clean, _, _ = _sample_clean()
    grouped = _grouped(clean)
    svg = feat_share._svg_bar_chart(grouped, "category", "unit_price",
                                    "Sales by category")
    assert svg.startswith("<svg")
    assert 'fill="#ffffff"' in svg, "chart background must be white"
    assert "#121212" not in svg and "#2e2e2e" not in svg
    assert "#117f50" in svg, "bars use the Supabase green accent"
    assert "#030303" in svg, "labels are ink"
    # A custom accent recolours the bars only, not the background.
    custom = feat_share._svg_bar_chart(grouped, "category", "unit_price",
                                       "T", accent="#ff8800")
    assert "#ff8800" in custom and 'fill="#ffffff"' in custom
    # An invalid accent falls back to the Supabase green.
    bad = feat_share._svg_bar_chart(grouped, "category", "unit_price",
                                    "T", accent="banana")
    assert "#117f50" in bad
    print("SVG chart OK: white background, green bars, ink labels")


def test_column_type_labels():
    df = pd.DataFrame({"name": ["a"], "price": [1.5], "n": [2],
                       "when": pd.to_datetime(["2026-01-01"]),
                       "ok": [True]})
    labels = feat_share.column_type_labels(df)
    assert len(labels) == 5
    joined = " ".join(labels)
    assert "name" in joined and "text" in joined
    assert "price" in joined and "numeric" in joined
    assert "when" in joined and "timestamp" in joined
    assert "ok" in joined and "boolean" in joined
    assert "dcs-coltype" in joined
    assert feat_share.column_type_labels(None) == []
    # render_type_override shows the picked column with its type.
    st = FakeSt(values={"s_type_col": "price", "s_type_kind": "number",
                        "s_type_apply": False})
    assert feat_share.render_type_override(st, df) is None
    md = " ".join(st.messages("markdown"))
    assert "price" in md and "numeric" in md, md
    print("column type labels OK: name text / price numeric, shown in "
          "the type-override panel")


# ------------------------------------------------------- 14 styled excel
def test_styled_excel():
    _, clean, actions, kpis = _sample_clean()
    df = clean.copy()
    df.loc[0, "region"] = None          # a missing cell
    df.loc[1, "unit_price"] = 99999.0   # a clear IQR outlier
    data = feat_share.to_excel_bytes_styled(df, kpis, actions)
    assert data[:2] == b"PK", "must be an xlsx (zip) file"
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Cleaned Data", "KPIs", "Cleaning Log"], \
        wb.sheetnames
    ws = wb["Cleaned Data"]
    assert ws.max_row == len(df) + 1 and ws.max_column == len(df.columns)
    header_fill = ws.cell(row=1, column=1).fill
    assert header_fill.fgColor.rgb[-6:] == "C6EFCE", \
        f"header must be light green, got {header_fill.fgColor.rgb}"
    region_col = list(df.columns).index("region") + 1
    missing_cell = ws.cell(row=2, column=region_col)
    assert missing_cell.fill.fgColor.rgb[-6:] == "FFC7CE", \
        "missing cell must be light red"
    price_col = list(df.columns).index("unit_price") + 1
    outlier_cell = ws.cell(row=3, column=price_col)
    assert outlier_cell.fill.fgColor.rgb[-6:] == "FFC7CE", \
        "IQR outlier must be light red"
    normal_cell = ws.cell(row=2, column=price_col)
    assert normal_cell.fill.patternType is None, \
        "normal cells must stay plain (no fill)"
    assert wb["KPIs"].max_row == len(kpis) + 1
    assert wb["Cleaning Log"].max_row == len(actions) + 1
    print("styled Excel OK: header green, missing + outlier red, normal plain")


# ------------------------------------------------------------- render downloads
def test_render_downloads():
    _, clean, actions, kpis = _sample_clean()
    grouped = _grouped(clean)
    st = FakeSt()
    feat_share.render_html_download(st, kpis, actions, grouped,
                                    "category", "unit_price")
    assert st.downloads[0]["file_name"] == "dashboard.html"
    assert st.downloads[0]["data"].decode("utf-8").startswith("<!DOCTYPE html>")
    st = FakeSt()
    feat_share.render_portfolio_download(st, clean, kpis, actions)
    assert st.downloads[0]["file_name"] == "portfolio_case_study.zip"
    assert st.downloads[0]["data"][:2] == b"PK"
    st = FakeSt(values={"s_chart_kind": "bar"})
    feat_share.render_chart_png(st, grouped, "category", "unit_price")
    assert st.downloads[0]["file_name"] == "chart.png"
    assert st.downloads[0]["data"][:8] == b"\x89PNG\r\n\x1a\n"
    st = FakeSt()
    feat_share.render_styled_excel_download(st, clean, kpis, actions)
    assert st.downloads[0]["file_name"] == "cleaned_data_styled.xlsx"
    assert st.downloads[0]["data"][:2] == b"PK"
    st = FakeSt()
    feat_share.render_portfolio_download(st, None, kpis, actions)
    assert not st.downloads and st.messages("info"), \
        "no cleaned data -> info, no download"
    print("render downloads OK: html / zip / png / styled xlsx")


# ------------------------------------------------------- forbidden imports
def test_no_forbidden_imports():
    src = (Path(__file__).resolve().parent.parent
           / "feat_share.py").read_text()
    # Import statements only — naming a library in a docstring comment
    # ("no matplotlib here") is not importing it.
    for bad in ("import matplotlib", "from matplotlib",
                "import vl_convert", "from vl_convert",
                "import googleapiclient", "from google",
                "import streamlit", "import pptx", "from pptx"):
        assert bad not in src, f"feat_share.py must not contain {bad!r}"
    print("no forbidden imports OK (stdlib / pandas / PIL / openpyxl only)")


if __name__ == "__main__":
    test_suggest_fixes_sample()
    test_suggest_fixes_phones_and_apply()
    test_apply_suggestion_other_types()
    test_override_column_type()
    test_standardize_phones()
    test_strip_specials()
    test_goal_progress()
    test_search_rows()
    test_render_sort()
    test_render_goal_and_search_and_type_override()
    test_render_phones_and_strip()
    test_render_suggestions_apply()
    test_recent_roundtrip_and_cap()
    test_render_recent_keep_and_open()
    test_backup_restore()
    test_render_backups()
    test_render_one_click()
    test_html_dashboard()
    test_portfolio_zip()
    test_chart_png()
    test_svg_bar_chart_white()
    test_column_type_labels()
    test_styled_excel()
    test_render_downloads()
    test_no_forbidden_imports()
    print("ALL BATCH 4 TESTS PASSED")
