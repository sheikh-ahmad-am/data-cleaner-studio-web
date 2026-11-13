"""Report pattern tests (Observability custom reports + Reports
section round).

The Report tab renders Supabase's Observability custom reports +
Reports section, mapped to this app's own reports: the saved
custom-reports list (a snapshot — blocks keep the values as of
save time, persisted per user like Clean's recipes), the custom
report builder (Add block over the real metrics: Rows, Columns,
Rows removed, Fixes applied, a KPI, Compare two runs), and the
one-page report moved verbatim under its sub-nav. Nothing is
invented — every block shows a real value from the session's data.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_report_custom.py -q   (from project root)
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# NOTE: app.py is NOT imported here — it executes top-level
# Streamlit code at import (set_page_config, session state), so it
# cannot be imported in a plain pytest; the page is covered through
# AppTest below, like the Dashboard/Preview/KPIs/Settings/Tools/Clean/
# Join/Compare rounds.
import auth  # noqa: E402
import feat_report as fr  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_profile.py / test_kpis_overview.py /
    test_join_tables.py / test_compare_logs.py.
    """
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    yield tmp_path


def _entry(step, detail, minutes_ago=0):
    t = (datetime.now() - timedelta(minutes=minutes_ago)).strftime(
        "%Y-%m-%d %H:%M:%S")
    return {"time": t, "step": step, "detail": detail}


def _state():
    """A cleaned sample state: 80 rows / 10 cols -> 77 rows / 9 cols."""
    raw = pd.read_csv(SAMPLE)
    clean = raw.drop_duplicates().reset_index(drop=True)
    clean = clean.drop(columns=[c for c in ["Notes"] if c in clean.columns])
    assert len(raw) == 80 and len(clean) == 77
    assert len(raw.columns) == 10 and len(clean.columns) == 9
    actions = [("Trimmed", "60 cells trimmed"),
               ("Dropped column", "notes"),
               ("Removed duplicates", "3 duplicate rows removed")]
    kpis = [{"label": "Rows", "value": "77"},
            {"label": "Revenue", "value": "207,992"}]
    audit = [_entry("Sample loaded",
                    "messy_sales.csv (sample) · 80 rows", 30),
             _entry("Clean", "80 -> 77 rows", 25),
             _entry("Clean", "80 -> 76 rows", 5)]
    return {"raw": raw, "clean": clean, "actions": actions,
            "kpis": kpis, "audit": audit}


# --------------------------------------------------------------------------
# Pure model
# --------------------------------------------------------------------------

def test_compute_block_rows_columns_removed():
    state = _state()
    rows = fr.compute_block("rows", state)
    assert rows == {"kind": "rows", "label": "Rows",
                    "data": {"before": 80, "after": 77, "removed": 3}}
    cols = fr.compute_block("columns", state)
    assert cols == {"kind": "columns", "label": "Columns",
                    "data": {"before": 10, "after": 9}}
    removed = fr.compute_block("removed", state)
    assert removed == {"kind": "removed", "label": "Rows removed",
                       "data": {"removed": 3}}


def test_compute_block_none_without_clean():
    """No clean yet means no block with data behind it — the builder
    must say so instead of adding an empty block."""
    state = _state()
    state["clean"] = None
    state["actions"] = []
    state["kpis"] = []
    assert fr.compute_block("rows", state) is None
    assert fr.compute_block("columns", state) is None
    assert fr.compute_block("removed", state) is None
    assert fr.compute_block("fixes", state) is None
    assert fr.compute_block("kpi", state, kpi_label="Rows") is None
    assert fr.compute_block("bogus", state) is None


def test_compute_block_fixes_and_kpi():
    state = _state()
    fixes = fr.compute_block("fixes", state)
    assert fixes["data"]["count"] == 3
    assert fixes["data"]["steps"] == [
        "Trimmed", "Dropped column", "Removed duplicates"]
    kpi = fr.compute_block("kpi", state, kpi_label="Revenue")
    assert kpi == {"kind": "kpi", "label": "KPI — Revenue",
                   "data": {"label": "Revenue", "value": "207,992"}}
    assert fr.compute_block("kpi", state, kpi_label="Nope") is None


def test_compute_block_runs():
    """Two Clean entries compare; one run, or the same run twice,
    is not a comparison."""
    state = _state()
    runs = fr.compute_block("runs", state, run_a=0, run_b=1)
    assert runs is not None
    assert runs["label"] == "Compare two runs"
    table = runs["data"]["table"]
    assert table[0] == {"Metric": "Rows before", "Run A": 80,
                        "Run B": 80, "Difference": 0}
    assert table[1] == {"Metric": "Rows after", "Run A": 77,
                        "Run B": 76, "Difference": -1}
    assert table[2] == {"Metric": "Rows removed", "Run A": 3,
                        "Run B": 4, "Difference": 1}
    assert fr.compute_block("runs", state, run_a=0, run_b=0) is None
    assert fr.compute_block("runs", state, run_a=0, run_b=9) is None
    one_run = dict(state)
    one_run["audit"] = state["audit"][:2]
    assert fr.compute_block("runs", one_run, run_a=0, run_b=1) is None


def test_report_markdown_is_a_snapshot():
    """The Markdown renders stored block data — the values as of
    save time — and never recomputes from today's state."""
    state = _state()
    blocks = [fr.compute_block("rows", state),
              fr.compute_block("fixes", state),
              fr.compute_block("kpi", state, kpi_label="Revenue")]
    md = fr.report_markdown("Probe report", "2026-11-12 21:00", blocks)
    assert "# Probe report" in md
    assert "Saved 2026-11-12 21:00" in md
    assert "Rows: 80 → 77 (3 removed)." in md
    assert "Fixes applied: 3." in md
    assert "- Trimmed" in md
    assert "Revenue: 207,992." in md
    # The state changes; the stored markdown does not.
    state["clean"] = state["clean"].head(10)
    md2 = fr.report_markdown("Probe report", "2026-11-12 21:00", blocks)
    assert md2 == md


def test_slug():
    assert fr._slug("Probe report 1") == "probe_report_1"
    assert fr._slug("!!!") == "custom-report"


# --------------------------------------------------------------------------
# AppTest helpers (same idiom as test_compare_logs.py)
# --------------------------------------------------------------------------

def find_button(at, label, key=None):
    for b in at.button:
        if b.label == label and (key is None or b.key == key):
            return b
    raise AssertionError(f"button {label!r} (key={key!r}) missing")


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
    """Load the sample the way a user does: the sidebar "Try the
    messy sample" button (the _load_messy_sample loader), so the
    table is named "messy_sales.csv (sample)"."""
    find_button(at, "Try the messy sample").click().run()
    assert not at.exception, f"exception on sample load: {at.exception}"
    assert at.session_state["raw"] is not None, "raw data not loaded"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    assert at.session_state.get("source_name") == "messy_sales.csv (sample)", \
        "sample source name wrong"


def dataframe_text(at):
    """The rendered dataframe/table cell values as text (all_text
    does not include them — a dataframe's cells live in its own
    element, not in markdown/captions)."""
    out = []
    for el in list(at.dataframe) + list(at.table):
        try:
            out.append(el.value.to_string())
        except Exception:  # noqa: BLE001 - a non-frame value
            out.append(str(el.value))
    return "\n".join(out)


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


def goto_report(at):
    goto_section(at, "Report")
    text = all_text(at)
    assert "Reports" in text, "Report page heading missing"
    return text


def clean_sample(at):
    """Clean the loaded sample the way a user does: the Clean tab's
    "Clean my data" button."""
    goto_section(at, "Clean")
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    assert at.session_state["clean"] is not None, "clean did not land"
    assert len(at.session_state["clean"]) == 77, \
        "cleaned data should have 77 rows"


# --------------------------------------------------------------------------
# AppTest: no data loaded
# --------------------------------------------------------------------------

def test_report_no_data_empty_state(_tmp_env):
    """Report opens with no data loaded (the Tools/Clean/Join/Compare
    reachability fix): the sub-nav renders, the empty state names
    the next step, and the "Try the sample data" CTA loads the
    sample — after which the Reports view shows Supabase's empty
    state ("Build a custom report")."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "rep_nodata")
    goto_nav(at, "Report", key="dcs_nav_report")
    text = all_text(at)
    assert "No data loaded yet" in text, "empty state missing"
    find_button(at, "Try the sample data")
    # Sub-nav labels live on buttons, not in markdown/captions.
    nav_labels = [b.label for b in at.button]
    assert "Reports" in nav_labels, "sub-nav missing with no data"
    assert "Custom report" in nav_labels, "sub-nav missing with no data"
    assert "One-page report" in nav_labels, "sub-nav missing with no data"
    find_button(at, "Try the sample data").click().run()
    assert not at.exception, f"exception loading sample: {at.exception}"
    assert at.session_state["raw"] is not None, "sample did not load"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    text = all_text(at)
    assert "Build a custom report" in text, \
        "Reports empty state missing after load"
    assert "Keep track of your most important metrics" in text
    print("report no-data empty state OK")


def test_report_builder_needs_clean(_tmp_env):
    """With data loaded but not cleaned, the builder says plainly
    that blocks need a cleaned result, and the one-page view shows
    the existing "No report yet" state."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "rep_noclean")
    load_sample(at)
    goto_report(at)
    find_button(at, "Custom report", key="rep_nav_builder").click().run()
    assert not at.exception, f"exception opening builder: {at.exception}"
    assert "Clean the file first" in all_text(at), \
        "builder must say blocks need a clean"
    find_button(at, "Go to the Clean tab", key="rep_go_clean")
    goto_report(at)
    find_button(at, "One-page report", key="rep_nav_onepage").click().run()
    assert not at.exception, f"exception opening one-page: {at.exception}"
    assert "No report yet" in all_text(at), \
        "one-page view must show the no-clean state"
    print("report builder needs clean OK")


# --------------------------------------------------------------------------
# AppTest: builder + saved reports + one-page report
# --------------------------------------------------------------------------

def test_builder_add_block_and_save(_tmp_env):
    """With the sample cleaned: Add block puts a real Rows block
    (80 -> 77) in the draft; Save stores it as a snapshot in the
    Reports list; opening it shows the saved values."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "rep_save")
    load_sample(at)
    clean_sample(at)
    goto_report(at)
    find_button(at, "Custom report", key="rep_nav_builder").click().run()
    assert not at.exception, f"exception opening builder: {at.exception}"
    assert "Custom report" in all_text(at), "builder heading missing"
    find_button(at, "Add block", key="rep_add_block").click().run()
    assert not at.exception, f"exception adding block: {at.exception}"
    draft = at.session_state.get("report_draft_blocks") or []
    assert len(draft) == 1 and draft[0]["kind"] == "rows", \
        "draft must hold the added Rows block"
    text = all_text(at)
    assert "80 → 77" in text or "80 -&gt; 77" in text, \
        "draft Rows block must show the real values"
    assert "3 removed" in text, "draft Rows block must show removed"
    find_text_input(at, "Report name").set_value("Probe report").run()
    find_button(at, "Save custom report", key="rep_save").click().run()
    assert not at.exception, f"exception saving report: {at.exception}"
    reports = at.session_state.get("q_reports") or []
    assert len(reports) == 1, "one report must be saved"
    assert reports[0]["name"] == "Probe report"
    assert reports[0]["blocks"][0]["data"] == {
        "before": 80, "after": 77, "removed": 3}, \
        "saved block must snapshot the values"
    text = all_text(at)
    assert "Probe report" in text, "saved report must list"
    # Saving opens the new report directly; return to the list to
    # check its card caption.
    at.session_state["report_open"] = None
    at.run()
    assert not at.exception, f"exception returning to list: {at.exception}"
    assert "1 blocks" in all_text(at), \
        "saved report must show its block count"
    # Opening the saved report shows the snapshot values.
    find_button(at, "Open", key="rep_open_0").click().run()
    assert not at.exception, f"exception opening report: {at.exception}"
    text = all_text(at)
    assert "80 → 77" in text or "80 -&gt; 77" in text, \
        "opened report must show the saved values"
    assert "Download (.md)" in [b.label for b in at.download_button], \
        "saved report must offer .md"
    print("builder add block + save OK")


def test_builder_runs_default_picks_different_runs(_tmp_env):
    """Run B defaults to a DIFFERENT run from Run A: both pickers
    start at index 0, and comparing a run with itself has no data
    behind it (compute_block returns None), so the first Add click
    would only warn. With two cleans, Run A = 0 and Run B = 1, and
    Add block renders the comparison table ("Rows before")."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "rep_runs")
    load_sample(at)
    clean_sample(at)
    clean_sample(at)
    assert len(at.session_state.get("q_audit") or []) == 3, \
        "two cleans + the load must be three log entries"
    goto_report(at)
    find_button(at, "Custom report", key="rep_nav_builder").click().run()
    assert not at.exception, f"exception opening builder: {at.exception}"
    find_selectbox(at, "Block").set_value("Compare two runs").run()
    assert not at.exception, f"exception picking runs: {at.exception}"
    run_a = find_selectbox(at, "Run A")
    run_b = find_selectbox(at, "Run B")
    assert run_a.value == 0, "Run A must default to the first run"
    assert run_b.value == 1, \
        "Run B must default to a different run (probe60 C7)"
    find_button(at, "Add block", key="rep_add_block").click().run()
    assert not at.exception, f"exception adding runs block: {at.exception}"
    assert "Rows before" in dataframe_text(at), \
        "runs block must render the comparison table"
    assert "That block has no data yet" not in all_text(at), \
        "the runs block must not warn"
    print("builder runs default OK")


def test_onepage_report_moved_verbatim(_tmp_env):
    """The one-page report still renders exactly what it did before
    this round: the build_report markdown with the real row counts,
    and the five download buttons."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "rep_onepage")
    load_sample(at)
    clean_sample(at)
    goto_report(at)
    find_button(at, "One-page report", key="rep_nav_onepage").click().run()
    assert not at.exception, f"exception opening one-page: {at.exception}"
    text = all_text(at)
    assert "Rows: 80 loaded -> 77 after cleaning" in text, \
        "one-page report must carry the real counts"
    assert "Columns: 10 -> 9" in text, "one-page report columns wrong"
    assert "What was cleaned" in text, "one-page report sections missing"
    # Download buttons are their own elements — their labels are
    # not in all_text (markdown/captions only).
    dl_labels = [b.label for b in at.download_button]
    assert "Download report (.md)" in dl_labels, "report .md download missing"
    assert "Download cleaned CSV" in dl_labels, "CSV download missing"
    assert "Download cleaned Excel" in dl_labels, "Excel download missing"
    assert "Download PDF report" in dl_labels, "PDF download missing"
    assert "Download cleaned Parquet" in dl_labels, \
        "Parquet download missing"
    print("one-page report verbatim OK")


# --------------------------------------------------------------------------
# AppTest: regressions the harness CAN reproduce
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# AppTest: saved reports persist across a reload / fresh sign-in
# --------------------------------------------------------------------------

def _build_and_save_probe_report(at, name="Probe report"):
    """Build one Rows block and save it under ``name``; return the
    saved report dict from session state. (The builder half of
    test_builder_add_block_and_save, factored out for the
    persistence tests below.)"""
    goto_report(at)
    find_button(at, "Custom report", key="rep_nav_builder").click().run()
    assert not at.exception, f"exception opening builder: {at.exception}"
    find_button(at, "Add block", key="rep_add_block").click().run()
    assert not at.exception, f"exception adding block: {at.exception}"
    find_text_input(at, "Report name").set_value(name).run()
    find_button(at, "Save custom report", key="rep_save").click().run()
    assert not at.exception, f"exception saving report: {at.exception}"
    reports = at.session_state.get("q_reports") or []
    assert len(reports) == 1, "one report must be saved"
    assert reports[0]["name"] == name
    assert reports[0]["blocks"][0]["data"] == {
        "before": 80, "after": 77, "removed": 3}, \
        "saved block must snapshot the values"
    return reports[0]


def login(at, username, password="<redacted>"):
    """Log in as an existing user — the fresh-sign-in half of a
    page reload (a new AppTest has a fresh session and no login
    cookie, so the form is the only way back in)."""
    find_text_input(at, "Username").set_value(username).run()
    find_text_input(at, "Password").set_value(password).run()
    find_button(at, "Log in").click().run()
    assert not at.exception, f"exception on login: {at.exception}"
    expand_rail(at)
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "login should land on the main app"


def test_reports_subfolder_roundtrip(_tmp_env):
    """The storage layer accepts the reports subfolder: a
    save_json/load_json round-trip works, exactly like recipes
    (the mechanism reports mirror). Before the fix this raised
    ValueError: "reports" was missing from storage.SUBFOLDERS,
    so _persist_reports failed silently on every save and the
    restore read nothing back — a saved report vanished on
    reload while the in-session list still looked fine."""
    assert "reports" in storage.SUBFOLDERS, \
        "reports must be a whitelisted storage subfolder"
    report = [{"name": "Probe report", "created": "2026-11-13 10:00",
               "blocks": [{"kind": "rows", "label": "Rows",
                           "data": {"before": 80, "after": 77,
                                    "removed": 3}}]}]
    storage.save_json("rep_store", "reports", "reports.json", report)
    assert storage.load_json(
        "rep_store", "reports", "reports.json") == report, \
        "a saved report must round-trip through storage"
    # Parity with recipes, the mechanism reports mirror.
    storage.save_json("rep_store", "recipes", "recipes.json",
                      [{"name": "r"}])
    assert storage.load_json(
        "rep_store", "recipes", "recipes.json") == [{"name": "r"}]
    # A user with nothing saved yet still loads as None, not an error.
    assert storage.load_json("rep_store", "reports", "nope.json") is None
    print("reports subfolder round-trip OK")


def test_saved_report_written_to_disk(_tmp_env):
    """Saving a report in the UI writes reports/reports.json to
    the user's own storage folder — the write the old code
    silently skipped (ValueError swallowed by _persist_reports),
    so the report existed only in session state."""
    import json

    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "rep_disk")
    load_sample(at)
    clean_sample(at)
    _build_and_save_probe_report(at)
    path = (_tmp_env / "users" / "rep_disk"
            / "reports" / "reports.json")
    assert path.is_file(), \
        "saving a report must write reports/reports.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 1 and saved[0]["name"] == "Probe report"
    assert saved[0]["blocks"][0]["data"] == {
        "before": 80, "after": 77, "removed": 3}, \
        "the file must hold the snapshot values, not a live view"
    print("saved report written to disk OK")


def test_saved_report_restores_after_reload(_tmp_env):
    """The live-check bug, pinned: a saved report survives a page
    reload and a fresh sign-in. Save "Probe report" (Rows 80 ->
    77), then start a FRESH AppTest (new session, no cookie) and
    log back in as the same user — the Reports list still shows
    it, with no data loaded, and opening it shows the saved
    snapshot values."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "rep_reload")
    load_sample(at)
    clean_sample(at)
    _build_and_save_probe_report(at)
    # --- reload: a fresh session, the way a browser refresh is. ---
    fresh = AppTest.from_file(APP).run()
    assert not fresh.exception, f"exception on reload: {fresh.exception}"
    assert fresh.session_state.get("current_user") is None, \
        "a fresh session must start logged out"
    login(fresh, "rep_reload")
    assert fresh.session_state.get("current_user", {}).get(
        "username") == "rep_reload"
    # The restore runs at startup: the report is back before any
    # data is loaded — the Reports list, not the empty state. (No
    # data is loaded in the fresh session, so the Section radio
    # does not exist yet — navigate via the sidebar nav row, the
    # same path as the no-data test.)
    goto_nav(fresh, "Report", key="dcs_nav_report")
    text = all_text(fresh)
    assert "Reports" in text, "Report page heading missing"
    assert "Probe report" in text, \
        "a saved report must survive a reload"
    assert "1 blocks" in text, \
        "the restored report must keep its block count"
    assert "Build a custom report" not in text, \
        "the empty state must not replace a restored report"
    # Opening it shows the snapshot values (80 -> 77), not today's.
    find_button(fresh, "Open", key="rep_open_0").click().run()
    assert not fresh.exception, \
        f"exception opening restored report: {fresh.exception}"
    text = all_text(fresh)
    assert "80 → 77" in text or "80 -&gt; 77" in text, \
        "the restored report must show its saved values"
    assert "Download (.md)" in [b.label for b in fresh.download_button], \
        "the restored report must offer .md"
    print("saved report restores after reload OK")


def test_report_does_not_break_compare_logs(_tmp_env):
    """Visiting Report and building a report must not disturb the
    audit trail Compare reads: after a clean, Compare still lists
    both entries. (Theme / row-limit / Tools-filter / Join-visualizer
    regressions are frontend quirks AppTest cannot reproduce — the
    probe is the pin there, probe54/56/57/58/59.)"""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "rep_regress")
    load_sample(at)
    clean_sample(at)
    goto_report(at)
    find_button(at, "Custom report", key="rep_nav_builder").click().run()
    find_button(at, "Add block", key="rep_add_block").click().run()
    assert not at.exception, f"exception adding block: {at.exception}"
    goto_section(at, "Compare")
    text = all_text(at)
    assert "Showing first 2 of 2 logs" in text, \
        "Compare Logs must still list both entries after Report use"
    assert "Sample loaded" in dataframe_text(at)
    print("report does not break compare logs OK")
