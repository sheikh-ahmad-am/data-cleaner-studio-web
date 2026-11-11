"""Clean pattern tests (SQL Editor clone round).

The Clean tab renders Supabase's SQL Editor, mapped to this app's
own cleaning run: a sub-sidebar (Recipes / Templates / Run history /
Reference, search + Filter + "+" new run tab), a tab bar of run
tabs, a Run bar (source caption, Row limit, Save, the existing
"Clean my data" button), the editor (the 8 fixes as numbered lines
+ a script preview of the ticked fixes), and Results / Chart tabs
below. The cleaning itself is unchanged — same engine.clean run,
same 80 -> 77 rows on the messy sample, same log, same undo /
backups / sampling / fuzzy / fix-ups below the results.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_clean_editor.py -q   (from project root)
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# NOTE: app.py is NOT imported here — it executes top-level
# Streamlit code at import (set_page_config, session state), so it
# cannot be imported in a plain pytest; the page is covered through
# AppTest below, like the Dashboard/Preview/KPIs/Settings/Tools rounds.
import auth  # noqa: E402
import feat_automate  # noqa: E402
import feat_clean  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_profile.py / test_kpis_overview.py.
    """
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    yield tmp_path


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------

def test_catalog_labels_are_the_clean_tab_labels():
    """The 8 fix labels are exactly the Clean tab's checkbox labels as
    they stood before this round (the editor's numbered lines are the
    same list, renamed nowhere)."""
    assert [f["key"] for f in feat_clean.CLEAN_FIXES] == \
        feat_automate.CLEAN_OPT_KEYS
    assert [f["label"] for f in feat_clean.CLEAN_FIXES] == [
        "Tidy column names",
        "Strip extra spaces from text",
        "Drop empty columns and rows",
        "Fix numbers stored as text (₹, $, %, commas)",
        "Parse dates",
        "Set categories to one case",
        "Drop duplicate rows",
        "Fill missing values",
    ]
    assert all(f["script"] for f in feat_clean.CLEAN_FIXES)


def test_script_lines_ticked_only():
    """The script preview names the source and lists only the ticked
    fixes, in catalog order; nothing ticked says so plainly."""
    opts = dict(feat_automate.DEFAULT_CLEAN_OPTS)
    lines = feat_clean.script_lines(opts, "messy_sales.csv")
    assert lines[0] == "-- Clean messy_sales.csv"
    assert lines[1:] == [f["script"] for f in feat_clean.CLEAN_FIXES]
    opts["drop_dupes"] = False
    opts["fill_missing"] = False
    lines = feat_clean.script_lines(opts, "messy_sales.csv")
    assert "DROP DUPLICATE ROWS" not in lines
    assert "FILL MISSING VALUES" not in lines
    assert lines[-1] == "SET CATEGORIES TO ONE CASE"
    lines = feat_clean.script_lines(
        {k: False for k in feat_automate.CLEAN_OPT_KEYS}, "x.csv")
    assert lines == ["-- Clean x.csv",
                     "-- (no fixes ticked — tick at least one fix to run.)"]


def test_chart_data_rows_columns_missing():
    raw = pd.DataFrame({"a": [1, None, 3], "b": ["x", "y", "z"]})
    clean = pd.DataFrame({"a": [1.0, 2.0]})
    assert feat_clean.chart_data(raw, clean, "Rows") == {
        "labels": ["Before", "After"], "values": [3, 2]}
    assert feat_clean.chart_data(raw, clean, "Columns") == {
        "labels": ["Before", "After"], "values": [2, 1]}
    assert feat_clean.chart_data(raw, clean, "Missing cells") == {
        "labels": ["Before", "After"], "values": [1, 0]}


def test_tabs_default_add_close_active():
    """Tab-1 tracks the source name; "+" adds "Run N" with a fresh
    key; closing the active tab falls back to the first remaining;
    an unknown active key falls back to the first tab."""
    tabs = feat_clean.default_tabs("messy_sales.csv")
    assert tabs[0]["name"] == "messy_sales.csv"
    assert tabs[0]["opts"] == feat_automate.DEFAULT_CLEAN_OPTS
    tabs, key = feat_clean.add_tab(tabs, 2)
    assert tabs[-1] == {"key": "tab-2", "name": "Run 2",
                        "opts": feat_automate.DEFAULT_CLEAN_OPTS}
    assert feat_clean.active_tab(tabs, "tab-2")["key"] == "tab-2"
    assert feat_clean.active_tab(tabs, "stale-key")["key"] == "tab-1"
    rest, active = feat_clean.close_tab(tabs, "tab-2")
    assert [t["key"] for t in rest] == ["tab-1"]
    assert active == "tab-1"
    rest, active = feat_clean.close_tab(tabs, "tab-1")
    assert [t["key"] for t in rest] == ["tab-2"]
    assert active == "tab-2"


# --------------------------------------------------------------------------
# AppTest helpers (same idiom as test_flow_marker_r3d.py /
# test_tools_integrations.py)
# --------------------------------------------------------------------------

def find_button(at, label, key=None):
    for b in at.button:
        if b.label == label and (key is None or b.key == key):
            return b
    raise AssertionError(f"button {label!r} (key={key!r}) missing")


def find_button_by_key(at, key):
    for b in at.button:
        if b.key == key:
            return b
    raise AssertionError(f"button with key={key!r} missing")


def find_text_input(at, label):
    for t in at.text_input:
        if t.label == label:
            return t
    raise AssertionError(f"text input {label!r} missing")


def find_selectbox(at, label):
    for s in at.selectbox:
        if s.label == label:
            return s
    raise AssertionError(f"selectbox {label!r} missing")


def find_checkbox(at, label):
    for c in at.checkbox:
        if c.label == label:
            return c
    raise AssertionError(f"checkbox {label!r} missing")


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def all_text(at):
    """Every visible string on the page (markdown + captions + headers
    + success/info banners + expander labels)."""
    out = []
    out.extend(vals(at.markdown))
    out.extend(vals(at.caption))
    out.extend(e.value for e in at.subheader)
    out.extend(e.value for e in at.header)
    out.extend(vals(at.success))
    out.extend(vals(at.info))
    out.extend(vals(at.warning))
    out.extend(e.label for e in at.expander)
    return "\n".join(out)


def expand_rail(at):
    """Open the sidebar rail (it starts collapsed) so the full
    sidebar is visible: labelled nav rows, uploader, sample button."""
    at.session_state["dcs_rail_mode"] = "expanded"
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert not at.exception, f"exception expanding rail: {at.exception}"


def signup(at, username, password="<redacted>"):
    """Sign up (auto-login) and return the new user's id."""
    at.radio[0].set_value("Sign up").run()
    find_text_input(at, "Username").set_value(username).run()
    find_text_input(at, "Password").set_value(password).run()
    find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    expand_rail(at)
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "signup should log the user straight in"
    return at.session_state["current_user"]["id"]


def load_sample(at):
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([("messy_sales.csv", SAMPLE.read_bytes(), "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert at.session_state["raw"] is not None, "raw data not loaded"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"


def goto_section(at, label):
    radio = next(r for r in at.radio if r.label == "Section")
    radio.set_value(label).run()
    assert not at.exception, f"exception going to {label}: {at.exception}"
    assert radio.value == label, "section switcher did not stick"


def goto_nav(at, label, key):
    """Navigate via a sidebar nav row (the path that works with no data
    loaded, when the Section radio does not exist yet)."""
    expand_rail(at)
    find_button(at, label, key=key).click().run()
    assert not at.exception, f"exception going to {label}: {at.exception}"


def goto_clean(at):
    goto_section(at, "Clean")
    text = all_text(at)
    assert "Clean my data" in text, "Clean page heading missing"
    return text


# --------------------------------------------------------------------------
# AppTest: the chrome
# --------------------------------------------------------------------------

def test_clean_editor_chrome(_tmp_env):
    """The SQL Editor chrome renders on the Clean tab: sub-sidebar
    sections, the tab bar (tab-1 named after the loaded file), the
    Run bar (source caption, Row limit, Save, Clean my data), the 8
    fixes as numbered lines, the script preview, Results/Chart tabs."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "clean_editor")
    load_sample(at)
    goto_clean(at)
    text = all_text(at)
    # Sub-sidebar sections (the SQL Editor's SHARED / PRIVATE /
    # REFERENCE, mapped to this app's lists).
    for section in ("Recipes", "Templates", "Run history", "Reference"):
        assert section in text, f"sub-sidebar section {section!r} missing"
    # Tab bar: tab-1 tracks the loaded file.
    find_button(at, "messy_sales.csv")
    # Run bar.
    assert "Source: messy_sales.csv" in text, "source caption missing"
    find_selectbox(at, "Row limit")
    find_button(at, "Save", key="clean_save")
    find_button(at, "Clean my data", key="clean_btn")
    # Editor: the 8 fixes, each a checkbox with the old label.
    for fix in feat_clean.CLEAN_FIXES:
        assert find_checkbox(at, fix["label"]).value is True, \
            f"fix {fix['label']!r} should start ticked"
    # Script preview lists every fix (all ticked).
    code = "\n".join(vals(at.code))
    assert "-- Clean messy_sales.csv" in code, "script header missing"
    assert "TIDY COLUMN NAMES" in code, "script lines missing"
    assert "DROP DUPLICATE ROWS" in code
    # Results / Chart tabs below the editor.
    assert [t.label for t in at.tabs] == ["Results", "Chart"], \
        f"tabs wrong: {[t.label for t in at.tabs]!r}"
    print("clean editor chrome OK")


def test_clean_run_80_to_77(_tmp_env):
    """Run cleans the sample exactly as before (80 -> 77 rows, 10 ->
    9 columns): the "Done" line, the "What was fixed" log and the
    Results grid all render in the Results tab."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "clean_run")
    load_sample(at)
    goto_clean(at)
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    clean = at.session_state["clean"]
    assert clean is not None and len(clean) == 77, \
        f"cleaned data should have 77 rows, got {None if clean is None else len(clean)}"
    assert len(clean.columns) == 9, "cleaned data should have 9 columns"
    text = all_text(at)
    assert "Done: 80 rows -> 77 rows" in text, "Done line missing"
    assert "What was fixed" in text, "fix log heading missing"
    assert "Showing first 77 of 77 rows" in text, \
        "Results grid caption missing"
    print("clean run 80 -> 77 OK")


def test_clean_row_limit_survives_navigation(_tmp_env):
    """The Row limit survives leaving the Clean section and coming
    back (live-check find, 2026-11-11): pick 50, nav Dashboard ->
    Preview -> Clean, and the selectbox still reads 50 with the
    grid caption "Showing first 50 of 77 rows". Without
    persist_state="session" on the selectbox the value fell back
    to 100 on the return (Streamlit drops a widget's value when it
    stops rendering), so this test fails on the old code and passes
    with the fix — AppTest reproduces the prune, the probe pins it
    in the real DOM too (probe56 R1)."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "clean_rowlimit")
    load_sample(at)
    goto_clean(at)
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    assert "Showing first 77 of 77 rows" in all_text(at), \
        "Results grid caption missing after the run"
    find_selectbox(at, "Row limit").set_value(50).run()
    assert not at.exception, f"exception picking 50: {at.exception}"
    assert find_selectbox(at, "Row limit").value == 50, \
        "Row limit did not take 50"
    assert "Showing first 50 of 77 rows" in all_text(at), \
        "grid caption should follow the picked limit"
    goto_section(at, "Dashboard")
    goto_section(at, "Preview")
    goto_clean(at)
    assert find_selectbox(at, "Row limit").value == 50, \
        "Row limit fell back to 100 after navigating away and back"
    assert "Showing first 50 of 77 rows" in all_text(at), \
        "grid caption should still show the picked limit after navs"
    print("clean row limit survives navigation OK")


def test_clean_save_creates_recipe(_tmp_env):
    """Save stores the active tab's fixes as a recipe under the tab's
    name, and the flash names it."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "clean_save")
    load_sample(at)
    goto_clean(at)
    find_button(at, "Save", key="clean_save").click().run()
    assert not at.exception, f"exception saving: {at.exception}"
    recipes = at.session_state.get("a_recipes") or []
    assert any(r["name"] == "messy_sales.csv" for r in recipes), \
        f"recipe named after the tab missing: {[r['name'] for r in recipes]!r}"
    assert "Saved recipe 'messy_sales.csv'" in all_text(at), \
        "save flash missing"
    print("clean save creates recipe OK")


def test_clean_tab_opts_preserved_across_switch(_tmp_env):
    """Each run tab keeps its own fix set: untick a fix on tab-1,
    add a tab (defaults, all ticked), switch back — tab-1's untick
    is still there."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "clean_tabs")
    load_sample(at)
    goto_clean(at)
    find_checkbox(at, "Drop duplicate rows").set_value(False).run()
    assert not at.exception, f"exception unticking: {at.exception}"
    assert at.session_state["clean_tabs"][0]["opts"]["drop_dupes"] is False, \
        "untick did not reach the tab"
    find_button_by_key(at, "clean_tab_add").click().run()
    assert not at.exception, f"exception adding tab: {at.exception}"
    assert at.session_state["clean_tab_active"] == "tab-2", \
        "new tab should become active"
    assert find_checkbox(at, "Drop duplicate rows").value is True, \
        "new tab should start with the defaults (all ticked)"
    find_button(at, "messy_sales.csv").click().run()
    assert not at.exception, f"exception switching back: {at.exception}"
    assert find_checkbox(at, "Drop duplicate rows").value is False, \
        "tab-1's untick was lost on the switch back"
    print("clean tab opts preserved across switch OK")


def test_clean_no_data_renders(_tmp_env):
    """With no data loaded the Clean tab is reachable (not the generic
    empty state): the editor lists the fixes, Run/Save are disabled,
    the Results tab names the next step — and its CTA loads the
    sample."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "clean_nodata")
    goto_nav(at, "Clean", key="dcs_nav_clean")
    text = all_text(at)
    assert "Clean my data" in text, "Clean page heading missing"
    for fix in feat_clean.CLEAN_FIXES:
        assert find_checkbox(at, fix["label"]).value is True, \
            f"fix {fix['label']!r} missing with no data"
    assert find_button(at, "Clean my data", key="clean_btn").disabled, \
        "Run must be disabled with no data"
    assert find_button(at, "Save", key="clean_save").disabled, \
        "Save must be disabled with no data"
    assert "No data loaded yet" in text, "Results empty state missing"
    find_button(at, "Try the sample data").click().run()
    assert not at.exception, f"exception loading sample: {at.exception}"
    assert at.session_state["raw"] is not None, "sample did not load"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    print("clean no-data renders OK")
