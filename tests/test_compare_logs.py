"""Compare pattern tests (Supabase Logs round).

The Compare tab renders Supabase's Logs page, mapped to this app's
own activity: the audit trail (``q_audit``) is the log — a clean, a
join, a file or sample load, a database load, a quality action.
Nothing is invented. Beside the Logs view there is a "Compare runs"
view over the Clean entries and KPI snapshots, and the old
file-comparison feature moved verbatim under "Compare files".

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_compare_logs.py -q   (from project root)
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
# Join rounds.
import auth  # noqa: E402
import feat_compare as fc  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_profile.py / test_kpis_overview.py /
    test_join_tables.py.
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


def _audit():
    return [
        _entry("Sample loaded", "messy_sales.csv (sample) · 80 rows", 30),
        _entry("Clean", "80 -> 77 rows", 25),
        _entry("Outliers: quantity", "2 row(s) removed", 20),
        _entry("Database load", "1,000 rows from customers", 15),
        _entry("Join", "86 rows", 10),
        _entry("File load failed", "bad.json: not valid JSON", 5),
        _entry("Clean", "80 -> 76 rows", 0),
    ]


# --------------------------------------------------------------------------
# Pure model
# --------------------------------------------------------------------------

def test_classify_log_types():
    """Every recorded step lands in its subsystem; unknown steps
    land in "Other" rather than being forced into a bucket."""
    cases = {
        "Clean": "Clean",
        "Suggestion applied": "Clean",
        "One-click flow": "Clean",
        "Sampling applied to full file": "Clean",
        "Outliers: quantity": "Quality",
        "Near-duplicates: customer": "Quality",
        "Fuzzy merge": "Quality",
        "Database load": "Database",
        "Sample loaded": "File",
        "File loaded": "File",
        "File load failed": "File",
        "Join": "Join",
        "Join preview failed": "Join",
        "Something brand new": "Other",
    }
    for step, want in cases.items():
        got = fc.classify_log({"time": "2026-11-12 10:00:00",
                               "step": step, "detail": "x"})
        assert got["type"] == want, f"{step} -> {got['type']}, want {want}"
    print("classify types OK")


def test_classify_log_levels():
    """Success for every completed action, error for a failed load
    or a failed join preview — and nothing else is ever "warning"."""
    assert fc.classify_log({"step": "Clean"})["level"] == "success"
    assert fc.classify_log({"step": "Join"})["level"] == "success"
    assert fc.classify_log({"step": "File load failed"})["level"] == "error"
    assert fc.classify_log({"step": "Join preview failed"})["level"] == "error"
    assert fc.classify_log({"step": "Outliers: quantity"})["level"] == "success"
    assert fc.classify_log({})["level"] == "success", \
        "a bare entry still classifies"
    print("classify levels OK")


def test_filter_logs_time_range():
    """Time Range keeps only entries inside the window; entries
    with no parseable time only ever match "All time"."""
    audit = _audit()
    assert len(fc.filter_logs(audit, time_range="all")) == 7
    assert len(fc.filter_logs(audit, time_range="60m")) == 7
    assert len(fc.filter_logs(audit, time_range="24h")) == 7
    old = _entry("Clean", "80 -> 77 rows", 60 * 26)  # 26h ago
    assert len(fc.filter_logs([old], time_range="24h")) == 0
    assert len(fc.filter_logs([old], time_range="7d")) == 1
    broken = [{"time": "not a time", "step": "Clean",
               "detail": "80 -> 77 rows"}]
    assert len(fc.filter_logs(broken, time_range="all")) == 1
    assert len(fc.filter_logs(broken, time_range="60m")) == 0
    print("filter time range OK")


def test_filter_logs_types_levels_query():
    """Type / level checkboxes and the free-text filter each narrow
    the list; combined they intersect."""
    audit = _audit()
    only_clean = fc.filter_logs(audit, types={"Clean"})
    assert [e["step"] for e in only_clean] == ["Clean", "Clean"]
    no_file = fc.filter_logs(audit, types={"Clean", "Quality",
                                           "Database", "Join"})
    assert all(e["type"] != "File" for e in no_file)
    assert len(no_file) == 5
    errors = fc.filter_logs(audit, levels={"error"})
    assert [e["step"] for e in errors] == ["File load failed"]
    assert fc.filter_logs(audit, levels={"warning"}) == [], \
        "no warning-grade events exist"
    found = fc.filter_logs(audit, query="outlier")
    assert [e["step"] for e in found] == ["Outliers: quantity"]
    found = fc.filter_logs(audit, query="80 -> 77")
    assert [e["step"] for e in found] == ["Clean"]
    combo = fc.filter_logs(audit, types={"Clean"}, query="76")
    assert [e["detail"] for e in combo] == ["80 -> 76 rows"]
    print("filter types/levels/query OK")


def test_histogram_counts():
    """Per-hour buckets within a day, per-day buckets across days;
    unparseable times are skipped, never counted."""
    audit = _audit()
    counts = fc.histogram_counts(audit)
    assert sum(c for _l, c in counts) == 7, "every entry counted once"
    assert all(":" in label for label, _ in counts), \
        "same-day entries bucket per hour"
    two_days = [_entry("Clean", "80 -> 77 rows", 60 * 30),
                _entry("Clean", "80 -> 77 rows", 0)]
    counts = fc.histogram_counts(two_days)
    assert len(counts) == 2 and all(":" not in label
                                    for label, _ in counts), \
        "multi-day entries bucket per day"
    assert fc.histogram_counts([]) == []
    assert fc.histogram_counts([{"time": "junk", "step": "Clean",
                                 "detail": ""}]) == []
    print("histogram counts OK")


def test_parse_clean_detail():
    assert fc.parse_clean_detail("80 -> 77 rows") == (80, 77)
    assert fc.parse_clean_detail("1,000 -> 999 rows") == (1000, 999)
    assert fc.parse_clean_detail("77 rows") is None
    assert fc.parse_clean_detail("") is None
    print("parse clean detail OK")


def test_clean_runs():
    """One run per "Clean" entry, chronological, with the removed
    count derived — and nothing else counts as a run."""
    runs = fc.clean_runs(_audit())
    assert len(runs) == 2
    assert runs[0] == {"time": runs[0]["time"], "before": 80,
                       "after": 77, "removed": 3}
    assert runs[1]["before"] == 80 and runs[1]["after"] == 76
    assert fc.clean_runs([{"step": "Join", "detail": "86 rows"}]) == []
    print("clean runs OK")


def test_snapshot_options():
    """Snapshots without KPIs are skipped (the first snapshot is
    taken before the first clean, when there are no KPIs yet);
    the current KPIs join as "Current" when they exist."""
    kpis = [{"label": "Rows", "value": "77"}]
    snaps = [{"label": "Before cleaning", "kpis": None},
             {"label": "Before cleaning", "kpis": kpis}]
    opts = fc.snapshot_options(snaps, kpis)
    assert [k for k, _l, _k in opts] == ["snap:1", "current"]
    assert fc.snapshot_options([], None) == []
    assert fc.snapshot_options([{"label": "x", "kpis": None}], None) == []
    print("snapshot options OK")


def test_compare_runs_table():
    rows = fc.compare_runs_table(
        {"before": 80, "after": 77, "removed": 3},
        {"before": 80, "after": 76, "removed": 4})
    assert rows[0] == {"Metric": "Rows before", "Run A": 80,
                       "Run B": 80, "Difference": 0}
    assert rows[2] == {"Metric": "Rows removed", "Run A": 3,
                       "Run B": 4, "Difference": 1}
    print("compare runs table OK")


# --------------------------------------------------------------------------
# AppTest helpers (same idiom as test_join_tables.py)
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


def find_checkbox(at, prefix):
    for c in at.checkbox:
        if c.label.startswith(prefix):
            return c
    raise AssertionError(f"checkbox starting {prefix!r} missing")


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


def goto_compare(at):
    goto_section(at, "Compare")
    text = all_text(at)
    assert "Logs" in text, "Compare page heading missing"
    return text


def goto_nav(at, label, key):
    """Navigate via a sidebar nav row (the path that works with no data
    loaded, when the Section radio does not exist yet)."""
    expand_rail(at)
    find_button(at, label, key=key).click().run()
    assert not at.exception, f"exception going to {label}: {at.exception}"


# --------------------------------------------------------------------------
# AppTest: no data loaded
# --------------------------------------------------------------------------

def test_compare_no_data_empty_state(_tmp_env):
    """Compare opens with no data loaded (the Tools/Clean/Join
    reachability fix): the sub-nav renders, the empty state names
    the next step, and the "Try the sample data" CTA loads the
    sample — after which the Logs view shows the load itself as
    the first entry ("Sample loaded")."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "cmp_nodata")
    goto_nav(at, "Compare", key="dcs_nav_compare")
    text = all_text(at)
    assert "No data loaded yet" in text, "empty state missing"
    find_button(at, "Try the sample data")
    assert "Sample loaded" not in dataframe_text(at), \
        "no log rows must render with no data"
    find_button(at, "Try the sample data").click().run()
    assert not at.exception, f"exception loading sample: {at.exception}"
    assert at.session_state["raw"] is not None, "sample did not load"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    assert at.session_state["q_audit"][0]["step"] == "Sample loaded", \
        "the load itself must be the first log entry"
    text = all_text(at)
    assert "Showing first 1 of 1 logs" in text, "log count caption missing"
    assert "Sample loaded" in dataframe_text(at), "load entry missing"
    print("compare no-data empty state OK")


def test_compare_failed_load_renders_without_file(_tmp_env):
    """A failed load is still a log entry: with no file loaded but
    one error entry in the trail, the Logs view renders instead
    of the empty state."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "cmp_failed")
    at.session_state["q_audit"] = [
        {"time": "2026-11-12 10:00:00", "step": "File load failed",
         "detail": "bad.json: not valid JSON"}]
    at.run()
    assert not at.exception, f"exception seeding audit: {at.exception}"
    goto_nav(at, "Compare", key="dcs_nav_compare")
    assert "No data loaded yet" not in all_text(at), \
        "an error entry must render the Logs view, not the empty state"
    assert "File load failed" in dataframe_text(at), "error entry missing"
    # Checkbox labels are not in all_text (markdown/captions only),
    # so the count is pinned on the checkbox element itself.
    find_checkbox(at, "Error (1)")
    print("compare failed-load renders OK")


# --------------------------------------------------------------------------
# AppTest: Logs view
# --------------------------------------------------------------------------

def test_compare_logs_filters_and_detail(_tmp_env):
    """With the sample loaded and cleaned: the Logs view lists
    both entries (Sample loaded, Clean), the free-text filter
    narrows to one, unchecking a Log Type hides its entries, and
    opening an entry shows its Overview fields and Raw JSON."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "cmp_logs")
    load_sample(at)
    goto_section(at, "Clean")
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    assert at.session_state["clean"] is not None, "clean did not land"
    assert len(at.session_state["clean"]) == 77, \
        "cleaned data should have 77 rows"
    goto_compare(at)
    text = all_text(at)
    assert "Showing first 2 of 2 logs" in text, "log count caption wrong"
    frame = dataframe_text(at)
    assert "Sample loaded" in frame and "Clean" in frame, \
        "both entries must be listed"
    assert "80 -&gt; 77 rows" in frame or "80 -> 77 rows" in frame, \
        "clean detail wrong"
    # Free-text filter: "clean" narrows to the one Clean entry.
    find_text_input(at, "Filter logs").set_value("clean").run()
    assert not at.exception, f"exception filtering: {at.exception}"
    assert "1 of 2 logs" in all_text(at), \
        "filter must narrow the shown count, not the total"
    assert "Showing first 1 of 1 logs" in all_text(at), \
        "page caption must count the shown entries"
    assert "Clean" in dataframe_text(at)
    assert "Sample loaded" not in dataframe_text(at), \
        "filter must hide the non-matching entry"
    find_text_input(at, "Filter logs").set_value("").run()
    # Log Type filter: unchecking File hides the load entry.
    find_checkbox(at, "File (").set_value(False).run()
    assert not at.exception, f"exception unchecking File: {at.exception}"
    assert "1 of 2 logs" in all_text(at), \
        "type filter must narrow the shown count"
    assert "Sample loaded" not in dataframe_text(at)
    assert "Clean" in dataframe_text(at)
    find_checkbox(at, "File (").set_value(True).run()
    # Detail: open the Clean entry (audit index 1). Tab labels live
    # in at.tabs, not in all_text; the Overview table and the Raw
    # JSON code block carry the entry's fields.
    find_selectbox(at, "Open log entry").set_value(1).run()
    assert not at.exception, f"exception opening detail: {at.exception}"
    assert [t.label for t in at.tabs] == ["Overview", "Raw JSON"], \
        "detail tabs missing"
    assert "80 -&gt; 77 rows" in dataframe_text(at) or \
        "80 -> 77 rows" in dataframe_text(at), \
        "detail must show the entry"
    assert any("80 -> 77 rows" in str(c.value) for c in at.code), \
        "Raw JSON must carry the entry"
    print("compare logs filters + detail OK")


def test_compare_download_logs(_tmp_env):
    """Download logs exports the filtered entries as CSV (the
    Supabase "Download logs" action, real data). AppTest cannot
    read a download button's bytes (its value is a bool), so the
    button is pinned by label + key here and the CSV content is
    pinned by the pure check below."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "cmp_dl")
    load_sample(at)
    goto_compare(at)
    dl = [b for b in at.download_button if b.label == "Download logs"]
    assert dl and dl[0].key == "cmp_download", \
        "Download logs button missing or wrong key"
    print("compare download logs OK")


def test_compare_download_csv_content():
    """The CSV Download logs serves is the filtered trail itself:
    time, type, level, step, detail — the real entries, one row
    each, newest first in the render."""
    shown = list(reversed(fc.filter_logs(_audit())))
    csv = pd.DataFrame(shown).to_csv(index=False)
    assert "Sample loaded" in csv and "File load failed" in csv
    assert "Clean" in csv and "80 -> 77 rows" in csv
    lines = csv.strip().split("\n")
    assert lines[0].startswith("time,step,detail,type,level"), \
        "CSV header must carry the log fields"
    assert len(lines) == 1 + len(_audit()), "one CSV row per entry"
    print("compare download CSV content OK")


# --------------------------------------------------------------------------
# AppTest: Compare runs + Compare files
# --------------------------------------------------------------------------

def test_compare_runs_two_cleans(_tmp_env):
    """Two cleans make two runs: the runs table lists both, the
    Run A / Run B pickers compare them, and the KPI comparison
    opens once a second clean has stored KPIs in a snapshot."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "cmp_runs")
    load_sample(at)
    goto_section(at, "Clean")
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception on first clean: {at.exception}"
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception on second clean: {at.exception}"
    assert len([e for e in at.session_state["q_audit"]
                if e["step"] == "Clean"]) == 2, "two Clean entries expected"
    goto_compare(at)
    find_button(at, "Compare runs", key="cmp_nav_runs").click().run()
    assert not at.exception, f"exception opening runs: {at.exception}"
    text = all_text(at)
    assert "Compare runs" in text, "runs heading missing"
    frame = dataframe_text(at)
    assert "80" in frame and "77" in frame, "runs table missing"
    find_selectbox(at, "Run A")
    find_selectbox(at, "Run B")
    # KPI comparison: snapshot 2 carries KPIs, and so does Current.
    find_selectbox(at, "Snapshot A")
    find_selectbox(at, "Snapshot B")
    print("compare runs two cleans OK")


def test_compare_runs_one_clean_note(_tmp_env):
    """With a single clean the runs view shows that run's
    before/after and says plainly what would add a second one."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "cmp_runs1")
    load_sample(at)
    goto_section(at, "Clean")
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    goto_compare(at)
    find_button(at, "Compare runs", key="cmp_nav_runs").click().run()
    assert not at.exception, f"exception opening runs: {at.exception}"
    text = all_text(at)
    assert "80" in text and "77" in text, "single run must show"
    assert "add a second run" in text, "one-run note missing"
    print("compare runs one clean OK")


def test_compare_files_view_intact(_tmp_env):
    """The old file-comparison feature moved verbatim under
    "Compare files": its heading, uploader prompt and the
    Combine & check expander all still render."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "cmp_files")
    load_sample(at)
    goto_compare(at)
    find_button(at, "Compare files", key="cmp_nav_files").click().run()
    assert not at.exception, f"exception opening files: {at.exception}"
    text = all_text(at)
    assert "Compare two files" in text, "compare heading missing"
    assert "Combine & check (stack files, anomalies, multi-KPI)" in text, \
        "combine expander missing"
    print("compare files view intact OK")


# --------------------------------------------------------------------------
# AppTest: regressions the harness CAN reproduce
# --------------------------------------------------------------------------

def test_compare_nav_keeps_persisted_prefs(_tmp_env):
    """Navigating through Compare does not disturb the persisted
    prefs (the round-56/57 theme + row-limit work) or the Join
    pattern: Row limit 50 and the Light theme pref survive
    Compare -> Join -> Dashboard -> Clean at the session-state
    level, and the Join tables list still renders. The frontend
    remount quirk behind rounds 56/57 cannot be reproduced by
    AppTest (the probe is the pin there — probe54/56/57/58);
    this test pins that the Compare page itself never touches
    those keys.
    """
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "cmp_prefs")
    load_sample(at)
    goto_section(at, "Clean")
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    find_selectbox(at, "Row limit").set_value(50).run()
    assert find_selectbox(at, "Row limit").value == 50, \
        "Row limit did not take 50"
    at.session_state["dcs_theme_pref"] = "light"
    at.run()
    assert not at.exception, f"exception setting theme pref: {at.exception}"
    goto_compare(at)
    goto_section(at, "Join")
    assert "Total: 2 tables" in all_text(at), \
        "Join tables list must still render after Compare"
    goto_section(at, "Dashboard")
    goto_section(at, "Clean")
    assert find_selectbox(at, "Row limit").value == 50, \
        "Row limit fell back after navigating through Compare"
    assert at.session_state.get("dcs_theme_pref") == "light", \
        "theme pref changed after navigating through Compare"
    print("compare nav keeps persisted prefs OK")
