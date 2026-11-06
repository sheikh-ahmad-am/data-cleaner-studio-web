"""Batch 5 (analyse & explain) tests for feat_analyse.py.

Run: .test-venv-analyse/bin/python tests/test_feat_analyse.py
       (from the project root)
Also pytest-collectable (plain asserts, no fixtures). No Streamlit server
needed — the render functions are exercised with a FakeSt stub, and the
AI layer is never called for real: the rule layer is tested directly,
the no-key path is tested with the real ai_settings (no key set), and
the AI path is tested with a stub ai_settings object.
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import engine
import feat_analyse as fa
import feat_automate


def _sample_raw():
    return engine.load_file("messy_sales.csv",
                            open("sample_data/messy_sales.csv", "rb").read())


def _sample_clean():
    clean, _actions = engine.clean(_sample_raw())
    return clean


# --------------------------------------------------------------------------
# FakeSt (same shape as the Group 1 tests)
# --------------------------------------------------------------------------

class FakeUpload:
    def __init__(self, name, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


class FakeSt:
    """Minimal stand-in for the streamlit module: widgets return preset
    values (or the first option / False), display calls are recorded."""

    def __init__(self, presets=None):
        self.session_state = {}
        self.presets = presets or {}
        self.calls = []
        self.sidebar = self

    def _rec(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            self._rec(name, *args, kwargs)
            return None
        return _call

    def selectbox(self, label, options, key=None, **kwargs):
        self._rec("selectbox", label, options, key)
        return self.presets.get(key, options[0])

    def radio(self, label, options, key=None, **kwargs):
        self._rec("radio", label, options, key)
        return self.presets.get(key, options[0])

    def slider(self, label, lo, hi, value, step=None, key=None, **kwargs):
        self._rec("slider", label, lo, hi, value, step, key)
        return self.presets.get(key, value)

    def checkbox(self, label, value=False, key=None, **kwargs):
        self._rec("checkbox", label, key)
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

    def file_uploader(self, label, key=None, **kwargs):
        self._rec("file_uploader", label, key)
        return self.presets.get(key)

    def columns(self, n):
        self._rec("columns", n)
        count = len(n) if isinstance(n, (list, tuple)) else n
        return [self] * count


def _called(fake, name):
    return [c for c in fake.calls if c[0] == name]


def _called_text(fake, name):
    """All text passed to display calls called ``name``."""
    out = []
    for c in fake.calls:
        if c[0] == name:
            out.extend(str(a) for a in c[1])
    return " ".join(out)


# --------------------------------------------------------------------------
# 1. correlations
# --------------------------------------------------------------------------

def test_correlations_synthetic():
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6, 7, 8],
                       "b": [2, 4, 6, 8, 10, 12, 14, 16],
                       "c": [8, 7, 6, 5, 4, 3, 2, 1],
                       "flat": [5, 5, 5, 5, 5, 5, 5, 5]})
    pairs = fa.find_correlations(df)
    by_pair = {(p["col_a"], p["col_b"]): p for p in pairs}
    assert ("a", "b") in by_pair and by_pair[("a", "b")]["r"] == 1.0
    assert "goes up" in by_pair[("a", "b")]["words"]
    assert "strong" in by_pair[("a", "b")]["words"]
    assert ("a", "c") in by_pair and by_pair[("a", "c")]["r"] == -1.0
    assert "goes down" in by_pair[("a", "c")]["words"]
    # Strongest first, no pair twice, flat column never appears.
    assert abs(pairs[0]["r"]) == 1.0
    assert len({(p["col_a"], p["col_b"]) for p in pairs}) == len(pairs)
    assert all("flat" not in (p["col_a"], p["col_b"]) for p in pairs)
    # A strict threshold drops the weak pairs; a loose one keeps them.
    assert fa.find_correlations(df, min_abs=1.0) == [
        p for p in pairs if abs(p["r"]) >= 1.0]
    assert len(fa.find_correlations(df, min_abs=0.99)) == 3
    # One number column -> nothing to compare.
    assert fa.find_correlations(pd.DataFrame({"a": [1, 2, 3]})) == []
    print("correlations synthetic OK")


def test_correlations_sample():
    clean = _sample_clean()
    # quantity vs unit_price correlate at r = -0.098 — below the 0.3 bar.
    assert fa.find_correlations(clean) == []
    assert abs(fa.find_correlations(clean, min_abs=0.05)[0]["r"]
               - clean["quantity"].corr(clean["unit_price"])) < 1e-9
    fake = FakeSt()
    fa.render_correlations(fake, clean)
    assert _called(fake, "subheader") and _called(fake, "slider")
    assert "No number pairs" in _called_text(fake, "info")
    print("correlations sample OK: no pair above 0.3 (r = -0.098)")


# --------------------------------------------------------------------------
# 2. trend forecast
# --------------------------------------------------------------------------

def test_forecast_synthetic():
    df = pd.DataFrame({
        "day": pd.date_range("2026-01-01", periods=5, freq="D"),
        "sales": [10, 12, 14, 16, 18]})
    out = fa.forecast_next(df, "day", "sales")
    assert out["last_value"] == 18.0
    assert abs(out["slope_per_day"] - 2.0) < 1e-9
    assert abs(out["forecast"] - 20.0) < 1e-9  # one day ahead, perfect line
    assert "straight-line guess, not a promise" in out["words"]
    assert out["last_date"] == pd.Timestamp("2026-01-05")
    two = fa.forecast_next(df, "day", "sales", periods=2)
    assert abs(two["forecast"] - 22.0) < 1e-9
    # Falling line: negative slope, forecast below the last value.
    down = pd.DataFrame({
        "day": pd.date_range("2026-01-01", periods=4, freq="D"),
        "sales": [40, 30, 20, 10]})
    out_down = fa.forecast_next(down, "day", "sales")
    assert abs(out_down["slope_per_day"] - (-10.0)) < 1e-9
    assert abs(out_down["forecast"] - 0.0) < 1e-9
    for bad in (lambda: fa.forecast_next(df, "nope", "sales"),
                lambda: fa.forecast_next(df, "day", "nope"),
                lambda: fa.forecast_next(df, "day", "sales", periods=0),
                lambda: fa.forecast_next(
                    pd.DataFrame({"day": ["2026-01-01"], "sales": [5]}),
                    "day", "sales")):
        try:
            bad()
            raise AssertionError("bad forecast input must raise")
        except ValueError:
            pass
    print("forecast synthetic OK")


def test_forecast_sample():
    clean = _sample_clean()
    out = fa.forecast_next(clean, "order_date", "unit_price")
    # Straight line over 2026-01-04..2026-11-08: slope ~0.38/day.
    assert abs(out["slope_per_day"] - 0.3827) < 0.01, out
    assert abs(out["forecast"] - 1083.28) < 1.0, out
    assert out["last_value"] == 1599.0
    assert str(out["last_date"].date()) == "2026-11-08"
    fake = FakeSt(presets={"an_fc_date": "order_date",
                           "an_fc_num": "unit_price", "an_fc_run": True})
    fa.render_forecast(fake, clean)
    assert _called(fake, "metric")
    assert "not a promise" in _called_text(fake, "write")
    print("forecast sample OK: slope 0.38/day, next-day guess 1,083.28")


def test_render_what_if():
    clean = _sample_clean()
    # Total unit_price is 78,323.0 on the cleaned sample.
    cur, new, diff = fa.what_if_total(clean, "unit_price", 10)
    assert (cur, round(new, 2), round(diff, 2)) == (78323.0, 86155.3, 7832.3)
    cur, new, diff = fa.what_if_total(clean, "unit_price", -50)
    assert (cur, round(new, 2), round(diff, 2)) == (78323.0, 39161.5, -39161.5)
    assert fa.what_if_total(clean, "quantity", 0)[1] == float(
        clean["quantity"].sum())
    for bad in (lambda: fa.what_if_total(clean, "nope", 10),
                lambda: fa.what_if_total(clean, "category", 10)):
        try:
            bad()
            raise AssertionError("bad what-if input must raise")
        except ValueError:
            pass
    fake = FakeSt(presets={"an_whatif_col": "unit_price",
                           "an_whatif_pct": 10})
    fa.render_what_if(fake, clean)
    assert len(_called(fake, "metric")) == 3
    print("what-if OK: +10% on unit_price -> 86,155.30 (+7,832.30)")


# --------------------------------------------------------------------------
# 4. row trust score
# --------------------------------------------------------------------------

def test_trust_synthetic():
    df = pd.DataFrame({
        "v": [10, 11, 12, 13, 12, 11, 100, None],
        "w": ["a", "b", "c", "d", "e", "f", "g", "h"]})
    scored = fa.row_trust_scores(df)
    by_row = {r["w"]: r["trust_score"] for _, r in scored.iterrows()}
    assert by_row["g"] == 95  # one outlier value (100)
    assert by_row["h"] == 90  # one missing cell
    assert by_row["a"] == 100
    assert list(scored["trust_score"]) == sorted(scored["trust_score"])
    assert scored.iloc[0]["trust_score"] == 90  # worst first
    assert "v" in scored.columns and df.shape == (8, 2)  # input untouched
    # An exact duplicate loses 20 (second copy only).
    dup = pd.DataFrame({"a": [1, 1, 2, 3, 4, 5], "b": [1, 1, 2, 3, 4, 5]})
    scores = list(fa.row_trust_scores(dup)["trust_score"])
    assert scores[0] == 80 and scores[1:] == [100] * 5, scores
    print("trust synthetic OK")


def test_trust_sample():
    clean = _sample_clean()
    scored = fa.row_trust_scores(clean)
    assert list(scored.columns)[-1] == "trust_score"
    assert scored["trust_score"].min() == 95
    assert int((scored["trust_score"] == 95).sum()) == 10  # quantity-5 rows
    assert int((scored["trust_score"] == 100).sum()) == 67
    raw = _sample_raw()
    raw_scored = fa.row_trust_scores(raw)
    assert raw_scored["trust_score"].min() < 95  # missing cells bite too
    fake = FakeSt()
    fa.render_trust(fake, clean)
    assert _called(fake, "metric") and _called(fake, "dataframe")
    print("trust sample OK: 10 rows at 95, 67 at 100")


# --------------------------------------------------------------------------
# 5. saved views
# --------------------------------------------------------------------------

def test_saved_views():
    with tempfile.TemporaryDirectory() as d:
        tmp_views = str(Path(d) / "views.json")
        _test_saved_views_inner(tmp_views)


def _test_saved_views_inner(tmp_views):
    view = {"chart_type": "Bar", "group_by": "region",
            "num_col": "unit_price", "slicers": {"region": ["West"]}}
    assert fa.list_views(tmp_views) == []
    fa.save_view("Sales by region", view, tmp_views)
    assert fa.list_views(tmp_views) == ["Sales by region"]
    assert fa.load_view("Sales by region", tmp_views) == view
    # Saving under the same name replaces it.
    view2 = dict(view, chart_type="Line")
    fa.save_view("Sales by region", view2, tmp_views)
    assert fa.load_view("Sales by region", tmp_views) == view2
    assert fa.list_views(tmp_views) == ["Sales by region"]
    # The file on disk is plain JSON with the view inside.
    assert json.loads(Path(tmp_views).read_text()) == {
        "Sales by region": view2}
    for bad in (lambda: fa.save_view("", view, tmp_views),
                lambda: fa.save_view("x", "not a dict", tmp_views),
                lambda: fa.load_view("missing", tmp_views)):
        try:
            bad()
            raise AssertionError("bad view input must raise")
        except (ValueError, KeyError):
            pass
    print("saved views OK")


def test_render_saved_views():
    with tempfile.TemporaryDirectory() as d:
        tmp_views = str(Path(d) / "views.json")
        _test_render_saved_views_inner(tmp_views)


def _test_render_saved_views_inner(tmp_views):
    old = fa.VIEWS_FILE
    fa.VIEWS_FILE = Path(tmp_views)
    try:
        view = {"chart_type": "Bar", "group_by": "region",
                "num_col": "unit_price", "slicers": {}}
        fake = FakeSt(presets={"an_view_name": "My view",
                               "an_view_save": True})
        assert fa.render_saved_views(fake, view) is None
        assert fa.list_views(tmp_views) == ["My view"]
        assert fake.session_state["an_views_data"] == {"My view": view}
        fake2 = FakeSt(presets={"an_view_pick": "My view",
                                "an_view_apply": True})
        assert fa.render_saved_views(fake2, None) == view
        fake3 = FakeSt(presets={"an_view_pick": "My view",
                                "an_view_delete": True})
        assert fa.render_saved_views(fake3, None) is None
        assert fa.list_views(tmp_views) == []
    finally:
        fa.VIEWS_FILE = old
    print("render saved views OK")


# --------------------------------------------------------------------------
# 6. client mode
# --------------------------------------------------------------------------

def test_client_mode():
    clean = _sample_clean()
    kpis = engine.auto_kpis(clean)
    summary = fa.client_summary(clean, kpis)
    assert "77 rows" in summary
    assert "78,323.0" in summary  # Total unit_price from the KPIs
    assert "Ananya Rao (13 rows)" in summary  # most common customer
    assert fa.client_summary(pd.DataFrame(), None) == "No data loaded yet."
    assert fa.client_summary(None, None) == "No data loaded yet."
    fake = FakeSt(presets={"an_client_mode_toggle": True})
    # Real Streamlit writes a widget's value into session state under
    # its key; the fake does not, so mirror that here.
    fake.session_state["an_client_mode_toggle"] = True
    fa.render_client_mode_toggle(fake)
    assert fake.session_state["client_mode"] is True
    assert _called(fake, "checkbox")
    fake2 = FakeSt()
    fa.render_client_mode_toggle(fake2)
    assert fake2.session_state["client_mode"] is False
    print("client mode OK")


# --------------------------------------------------------------------------
# 7. shareable recipes
# --------------------------------------------------------------------------

def test_share_recipe():
    recipe = feat_automate.save_recipe(
        dict(feat_automate.DEFAULT_CLEAN_OPTS), {}, "Monthly sales")
    raw = fa.export_recipe_bytes(recipe)
    assert isinstance(raw, bytes)
    back = fa.import_recipe_bytes(raw)
    assert back == recipe
    # Same JSON shape as feat_automate's own save/load.
    assert json.loads(raw) == json.loads(
        feat_automate.recipe_to_json(recipe))
    assert fa.import_recipe_bytes(
        feat_automate.recipe_to_json(recipe)) == recipe
    for bad in (b"not json", b'{"name": "", "clean_opts": {}}',
                b'{"name": "x", "clean_opts": {"bogus": true}}'):
        try:
            fa.import_recipe_bytes(bad)
            raise AssertionError("bad recipe bytes must raise")
        except ValueError:
            pass
    fake = FakeSt(presets={
        "an_recipe_upload": FakeUpload(
            "team_recipe.json", feat_automate.recipe_to_json(recipe).encode())})
    assert fa.render_share_recipe(fake, recipe) == recipe
    assert _called(fake, "download_button")
    print("share recipe OK")


# --------------------------------------------------------------------------
# 8. keyboard shortcuts
# --------------------------------------------------------------------------

def test_shortcuts_panel():
    assert "Ctrl+O" in fa.SHORTCUTS_JS and "Ctrl+S" in fa.SHORTCUTS_JS
    assert "Download cleaned CSV" in fa.SHORTCUTS_JS
    assert 'input[type="file"]' in fa.SHORTCUTS_JS
    assert len(fa.SHORTCUTS) == 2
    fake = FakeSt()
    fa.render_shortcuts_panel(fake)
    md = _called(fake, "markdown")
    # FakeSt records kwargs as the last positional arg (same as Group 1).
    assert md and md[0][1][1].get("unsafe_allow_html") is True
    assert "Ctrl+O" in md[0][1][0] and "Ctrl+S" in md[0][1][0]
    text = _called_text(fake, "write")
    assert "browser shortcuts" in text
    assert "while this app is open" in text
    print("shortcuts panel OK")


# --------------------------------------------------------------------------
# 9. multi-file KPIs
# --------------------------------------------------------------------------

def test_multi_file_kpis():
    clean = _sample_clean()
    small = pd.DataFrame({"qty": [1, 2, 3], "city": ["Delhi", "Delhi", "Patna"]})
    table = fa.multi_file_kpis({"jan.csv": clean, "feb.csv": small})
    assert list(table["file"]) == ["jan.csv", "feb.csv"]
    assert table.loc[0, "Total unit_price"] == "78,323.0"
    assert table.loc[0, "Rows"] == "77"
    assert table.loc[1, "Rows"] == "3"
    assert table.loc[1, "Total qty"] == "6.0"
    assert table.loc[1, "Total unit_price"] == ""  # KPI feb lacks: blank
    one = fa.multi_file_kpis({"only.csv": clean})
    assert len(one) == 1 and one.iloc[0]["file"] == "only.csv"
    try:
        fa.multi_file_kpis({})
        raise AssertionError("empty frames must raise")
    except ValueError:
        pass
    print("multi-file KPIs OK")


def test_render_multi_kpi():
    clean = _sample_clean()
    raw_bytes = open("sample_data/messy_sales.csv", "rb").read()
    fake = FakeSt(presets={
        "an_multi_files": [FakeUpload("messy_sales.csv", raw_bytes)]})
    fa.render_multi_kpi(fake)
    assert _called(fake, "dataframe") and _called(fake, "download_button")
    fake2 = FakeSt()
    fa.render_multi_kpi(fake2)
    assert _called(fake2, "info") and not _called(fake2, "dataframe")
    print("render multi-KPI OK")


# --------------------------------------------------------------------------
# 10. natural-language questions (rule layer; no real AI call anywhere)
# --------------------------------------------------------------------------

def test_answer_question_sample():
    clean = _sample_clean()
    assert fa.answer_question(clean, "which region sold the most?") == (
        "The most common Region is West (19 rows).")
    assert fa.answer_question(clean, "what is the most common category?") == (
        "The most common Category is Electronics (33 rows).")
    assert fa.answer_question(clean, "what is the total unit_price?") == (
        "The total Unit Price is 78,323.00.")
    assert fa.answer_question(clean, "what is the average quantity?") == (
        "The average Quantity is 2.58.")
    assert fa.answer_question(clean, "what is the highest unit_price?") == (
        "The highest Unit Price is 1,599.00.")
    assert fa.answer_question(clean, "what is the lowest unit_price?") == (
        "The lowest Unit Price is 199.00.")
    assert fa.answer_question(clean, "how many orders are Delivered?") == (
        "27 row(s) have Status = Delivered.")
    assert fa.answer_question(clean, "how many rows are there?") == (
        "There are 77 rows in this data.")
    # Top value by the total of a named number column.
    assert fa.answer_question(
        clean, "which region has the highest total unit_price?") == (
        "West has the highest total Unit Price (18,181.00).")
    # No pattern matches -> "" (the caller then tries AI / explains).
    assert fa.answer_question(clean, "tell me a joke") == ""
    assert fa.answer_question(clean, "   ") == ""
    assert fa.answer_question(pd.DataFrame(), "which region?") == (
        "No data loaded yet — load a file first.")
    print("answer_question sample OK")


def test_render_ask_rule_and_no_key():
    clean = _sample_clean()
    fake = FakeSt(presets={"an_ask_q": "which region sold the most?",
                           "an_ask_run": True})
    fa.render_ask(fake, clean)
    assert "West (19 rows)" in _called_text(fake, "success")
    # No pattern + no API key (real ai_settings, no key set) -> plain
    # explanation, and ask_ai is never reached.
    fake2 = FakeSt(presets={"an_ask_q": "tell me a joke",
                            "an_ask_run": True})
    assert fa.ai_settings is not None  # Batch 3 module is present
    assert fa.ai_settings.get_api_key() is None
    fa.render_ask(fake2, clean)
    assert "API key" in _called_text(fake2, "info")
    assert not _called(fake2, "error")
    print("render ask rule + no-key OK")


def test_render_ask_ai_path_stubbed():
    clean = _sample_clean()

    class _StubAI:
        def get_api_key(self):
            return "fake-key-for-test"

        def ask_ai(self, prompt, system=""):
            assert "which region" in prompt.lower() or "joke" in prompt.lower()
            assert "Rows: 77" in prompt  # only a summary travels, not the table
            return "AI says: West, from the summary."

    old = fa.ai_settings
    fa.ai_settings = _StubAI()
    try:
        fake = FakeSt(presets={"an_ask_q": "tell me a joke",
                               "an_ask_run": True})
        fa.render_ask(fake, clean)
        text = _called_text(fake, "write")
        assert "AI-generated answer" in text
        assert "AI says: West" in text
    finally:
        fa.ai_settings = old
    print("render ask AI path (stubbed) OK")


# --------------------------------------------------------------------------
# 11. morning auto-run (runner logic only — never Task Scheduler)
# --------------------------------------------------------------------------

def _load_morning_run():
    spec = importlib.util.spec_from_file_location(
        "morning_run", str(Path(__file__).resolve().parent.parent
                           / "morning_run.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_morning_run_files_exist():
    app = Path(__file__).resolve().parent.parent
    assert (app / "morning_run.py").exists()
    assert (app / "setup_morning_run.bat").exists()
    assert (app / "morning_run.py").read_text(
        encoding="utf-8") == fa.MORNING_RUN_PY
    assert (app / "setup_morning_run.bat").read_text(
        encoding="utf-8") == fa.MORNING_SETUP_BAT
    assert "schtasks" in fa.MORNING_SETUP_BAT
    assert "08:00" in fa.MORNING_SETUP_BAT
    assert "morning_run.py" in fa.MORNING_SETUP_BAT
    assert "run_morning" in fa.MORNING_RUN_PY
    assert "morning_in" in fa.MORNING_RUN_PY
    assert "morning_out" in fa.MORNING_RUN_PY
    print("morning files exist OK")


def test_morning_run_cleans_files(tmp_path):
    morning = _load_morning_run()
    in_dir = tmp_path / "morning_in"
    out_dir = tmp_path / "morning_out"
    in_dir.mkdir()
    raw_bytes = open("sample_data/messy_sales.csv", "rb").read()
    (in_dir / "messy_sales.csv").write_bytes(raw_bytes)
    (in_dir / "notes.txt").write_text("not a data file")
    (tmp_path / "bad.csv").write_bytes(b"")  # outside in_dir: ignored
    results = morning.run_morning(in_dir, out_dir)
    assert len(results) == 1, results
    assert results[0]["name"] == "messy_sales.csv"
    assert results[0]["rows_in"] == 80 and results[0]["rows_out"] == 77
    assert results[0]["status"] == "OK"
    cleaned = pd.read_csv(out_dir / "messy_sales_cleaned.csv")
    assert len(cleaned) == 77 and "unit_price" in cleaned.columns
    assert abs(cleaned["unit_price"].sum() - 78323.0) < 0.01
    assert (out_dir / "messy_sales_log.txt").exists()
    assert (out_dir / "morning_run_summary.json").exists()
    # A bad file inside in_dir is logged and skipped, not fatal.
    (in_dir / "broken.csv").write_bytes(b"")  # empty file: unreadable
    results2 = morning.run_morning(in_dir, out_dir)
    assert len(results2) == 2
    by_name = {r["name"]: r for r in results2}
    assert by_name["messy_sales.csv"]["status"] == "OK"
    assert by_name["broken.csv"]["status"].startswith("Failed:")
    # Empty in_dir -> empty results, folders still created.
    empty_out = tmp_path / "empty_out"
    assert morning.run_morning(tmp_path / "no_such_in", empty_out) == []
    assert empty_out.exists()
    print("morning run cleaning logic OK")


def test_render_morning_run():
    fake = FakeSt()
    fa.render_morning_run(fake)
    text = _called_text(fake, "write")
    assert "cannot be switched on from inside the app" in text
    assert "double-click" in text
    assert len(_called(fake, "download_button")) == 2
    print("render morning run OK")


# --------------------------------------------------------------------------
# 12. what's-new
# --------------------------------------------------------------------------

def test_whats_new():
    with tempfile.TemporaryDirectory() as d:
        tmp_seen = str(Path(d) / "seen_version.json")
        _test_whats_new_inner(tmp_seen)


def _test_whats_new_inner(tmp_seen):
    assert fa.CURRENT_VERSION == "1.3"
    assert "1.3" in fa.WHATS_NEW
    assert len(fa.WHATS_NEW["1.3"]) >= 12
    joined = " ".join(fa.WHATS_NEW["1.3"]).lower()
    for word in ("correlation", "forecast", "what-if", "trust score",
                 "saved view", "client mode", "recipe", "shortcut",
                 "multi-file", "ask your data", "morning", "what's new"):
        assert word in joined, word
    assert fa.should_show_whats_new(tmp_seen) is True  # never seen
    fa.mark_whats_new_seen(tmp_seen)
    assert fa.should_show_whats_new(tmp_seen) is False
    assert json.loads(Path(tmp_seen).read_text()) == {"version": "1.3"}
    print("whats-new OK")


def test_render_whats_new():
    with tempfile.TemporaryDirectory() as d:
        tmp_seen = str(Path(d) / "seen_version.json")
        _test_render_whats_new_inner(tmp_seen)


def _test_render_whats_new_inner(tmp_seen):
    old = fa.SEEN_VERSION_FILE
    fa.SEEN_VERSION_FILE = Path(tmp_seen)
    try:
        fake = FakeSt(presets={"an_whats_new_seen": True})
        fa.render_whats_new(fake)
        assert _called(fake, "subheader")
        assert "What's new in v1.3" in _called_text(fake, "subheader")
        assert fa.should_show_whats_new(tmp_seen) is False  # marked seen
        fake2 = FakeSt()
        fa.render_whats_new(fake2)
        assert not _called(fake2, "subheader")  # shows nothing twice
    finally:
        fa.SEEN_VERSION_FILE = old
    print("render whats-new OK")


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------

if __name__ == "__main__":
    test_correlations_synthetic()
    test_correlations_sample()
    test_forecast_synthetic()
    test_forecast_sample()
    test_render_what_if()
    test_trust_synthetic()
    test_trust_sample()
    test_saved_views()
    test_render_saved_views()
    test_client_mode()
    test_share_recipe()
    test_shortcuts_panel()
    test_multi_file_kpis()
    test_render_multi_kpi()
    test_answer_question_sample()
    test_render_ask_rule_and_no_key()
    test_render_ask_ai_path_stubbed()
    test_morning_run_files_exist()
    with tempfile.TemporaryDirectory() as _d:
        test_morning_run_cleans_files(Path(_d))
    test_render_morning_run()
    test_whats_new()
    test_render_whats_new()
    print("ALL ANALYSE TESTS PASSED")
