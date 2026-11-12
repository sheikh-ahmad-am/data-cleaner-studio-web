"""Join pattern tests (Database Tables + Schema Visualizer round).

The Join tab renders Supabase's Database page, mapped to this app's
own tables: the loaded file is one table (named after the file), the
cleaned copy is a second table once a clean exists, the Schema
Visualizer is a static dotted canvas with one card per table, and
"Copy as SQL" renders a real CREATE TABLE statement. The join-two-
files form moved verbatim from the old inline Join section.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_join_tables.py -q   (from project root)
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
# AppTest below, like the Dashboard/Preview/KPIs/Settings/Tools/Clean
# rounds.
import auth  # noqa: E402
import feat_clean  # noqa: E402
import feat_join  # noqa: E402
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
# Pure model
# --------------------------------------------------------------------------

def _raw_df():
    return pd.DataFrame({
        "order_id": [1, 2, 3],
        "city": ["Patna", "Gaya", "Patna"],
        "total": [10.5, 20.0, 30.25],
    })


def _clean_df():
    return pd.DataFrame({
        "order_id": [1, 2],
        "city": ["Patna", "Gaya"],
        "total": [10.5, 20.0],
    })


def test_list_tables_no_data():
    """No file loaded, no clean: no tables — nothing is invented."""
    assert feat_join.list_tables(None, None, None) == []


def test_list_tables_raw_only():
    """The loaded file is one table, named after the file, with its
    real row/column counts and size."""
    tables = feat_join.list_tables(_raw_df(), None, "messy_sales.csv")
    assert len(tables) == 1
    table = tables[0]
    assert table["key"] == "raw"
    assert table["name"] == "messy_sales.csv"
    assert table["rows"] == 3
    assert table["columns"] == 3
    assert table["size_bytes"] > 0
    assert table["size"].endswith(("B", "KB", "MB"))
    print("list_tables raw-only OK")


def test_list_tables_raw_and_cleaned():
    """After a clean there are two tables: the raw one and the
    cleaned copy (same name + " (cleaned)"), in that order."""
    tables = feat_join.list_tables(_raw_df(), _clean_df(),
                                   "messy_sales.csv")
    assert [t["key"] for t in tables] == ["raw", "cleaned"]
    assert tables[1]["name"] == "messy_sales.csv (cleaned)"
    assert tables[1]["rows"] == 2
    print("list_tables raw+cleaned OK")


def test_filter_tables():
    """Case-insensitive substring on the name; empty matches all."""
    tables = feat_join.list_tables(_raw_df(), _clean_df(),
                                   "messy_sales.csv")
    assert feat_join.filter_tables(tables, "") == tables
    assert [t["key"] for t in feat_join.filter_tables(tables, "CLEANED")] == [
        "cleaned"]
    assert feat_join.filter_tables(tables, "zzz") == []
    print("filter_tables OK")


def test_sql_type():
    assert feat_join.sql_type("number") == "numeric"
    assert feat_join.sql_type("date") == "timestamp"
    assert feat_join.sql_type("category") == "text"
    assert feat_join.sql_type("text") == "text"
    assert feat_join.sql_type("weird") == "text"
    print("sql_type OK")


def test_create_table_sql():
    """A CREATE TABLE statement for the table's actual columns and
    guessed types, identifiers quoted."""
    df = pd.DataFrame({
        "id": [1, 2],
        "total": [1.5, 2.5],
        "placed": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "city": ["Patna", "Gaya"],
    })
    assert feat_join.create_table_sql("orders", df) == (
        'CREATE TABLE "orders" (\n'
        '  "id" numeric,\n'
        '  "total" numeric,\n'
        '  "placed" timestamp,\n'
        '  "city" text\n'
        ");")
    # A name with spaces and a quote is quoted, never interpolated raw.
    sql = feat_join.create_table_sql('my "table".csv', df)
    assert sql.startswith('CREATE TABLE "my ""table"".csv" (')
    print("create_table_sql OK")


def test_column_lines_capped():
    """Column lines are "name — type", capped at 8 with an
    "… and N more columns" line."""
    df = pd.DataFrame({f"c{i}": [1] for i in range(10)})
    lines = feat_join.column_lines(df)
    assert len(lines) == 9
    assert lines[0] == "c0 — number"
    assert lines[-1] == "… and 2 more columns"
    assert feat_join.column_lines(df, limit=20) == [
        f"c{i} — number" for i in range(10)]
    print("column_lines OK")


# --------------------------------------------------------------------------
# AppTest helpers (same idiom as test_flow_marker_r3d.py /
# test_tools_integrations.py / test_clean_editor.py)
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


def code_text(at):
    """The rendered code blocks as text (st.code is its own
    element, not markdown)."""
    return "\n".join(str(c.value) for c in at.code)


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


def goto_join(at):
    goto_section(at, "Join")
    text = all_text(at)
    assert "Tables" in text, "Join page heading missing"
    return text


# --------------------------------------------------------------------------
# AppTest: no data loaded
# --------------------------------------------------------------------------

def test_join_no_data_empty_state(_tmp_env):
    """Join opens with no data loaded (the Tools/Clean reachability
    fix): the sub-nav renders, the empty state names the next step,
    and the "Try the sample data" CTA loads the sample — after
    which the tables list appears with one table."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "join_nodata")
    goto_nav(at, "Join", key="dcs_nav_join")
    text = all_text(at)
    assert "No data loaded yet" in text, "empty state missing"
    # The CTA is a button, so it is not in all_text (markdown /
    # captions only) — locating it by label proves it renders.
    find_button(at, "Try the sample data")
    assert "Total:" not in text, "tables list must not render with no data"
    find_button(at, "Try the sample data").click().run()
    assert not at.exception, f"exception loading sample: {at.exception}"
    assert at.session_state["raw"] is not None, "sample did not load"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    text = all_text(at)
    assert "messy_sales.csv (sample)" in dataframe_text(at), \
        "sample table missing"
    assert "Total: 1 table" in text, "tables footer missing"
    print("join no-data empty state OK")


# --------------------------------------------------------------------------
# AppTest: tables list + detail
# --------------------------------------------------------------------------

def test_join_tables_list_and_detail(_tmp_env):
    """With the sample loaded: the Tables list shows the sample
    (80 rows, 10 columns), the sub-nav table button opens the
    detail (breadcrumb, columns with types, row preview), and
    "← All tables" returns to the list."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "join_tables")
    load_sample(at)
    goto_join(at)
    text = all_text(at)
    assert "messy_sales.csv (sample)" in dataframe_text(at), \
        "sample table missing"
    assert "Total: 1 table" in text, "tables footer missing"
    # Search: a non-matching query empties the list honestly.
    find_text_input(at, "Search tables").set_value("zzz").run()
    assert not at.exception, f"exception searching: {at.exception}"
    assert "No tables match" in all_text(at), "no-match state missing"
    find_text_input(at, "Search tables").set_value("").run()
    assert "Total: 1 table" in all_text(at), "clearing search must restore"
    # Detail via the sub-nav table button.
    find_button(at, "messy_sales.csv (sample)",
                key="join_nav_table_raw").click().run()
    assert not at.exception, f"exception opening detail: {at.exception}"
    text = all_text(at)
    # The breadcrumb is markdown HTML, so ">" renders as "&gt;".
    assert "Join &gt; messy_sales.csv (sample)" in text, \
        "breadcrumb missing"
    assert "Data preview" in text, "preview heading missing"
    assert "Showing all 80 rows" in text, "preview caption missing"
    assert "Order ID" in dataframe_text(at), "profile column missing"
    find_button(at, "← All tables").click().run()
    assert not at.exception, f"exception going back: {at.exception}"
    assert "Total: 1 table" in all_text(at), "back must return to the list"
    print("join tables list + detail OK")


# --------------------------------------------------------------------------
# AppTest: visualizer + join files
# --------------------------------------------------------------------------

def test_join_visualizer_and_join_files(_tmp_env):
    """The Schema Visualizer renders the static canvas (table card,
    the "not clickable" note, Copy as SQL) and the Join files view
    renders the moved form (same uploader label and keys)."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "join_viz")
    load_sample(at)
    goto_join(at)
    find_button(at, "Schema Visualizer",
                key="join_nav_visualizer").click().run()
    assert not at.exception, f"exception opening visualizer: {at.exception}"
    text = all_text(at)
    assert "Schema Visualizer" in text, "visualizer heading missing"
    assert "Static diagram" in text, "static-diagram note missing"
    assert "Copy as SQL" in text, "Copy as SQL missing"
    assert "CREATE TABLE" in code_text(at), "SQL block missing"
    assert "messy_sales.csv (sample)" in text, "table card missing"
    find_button(at, "Join files", key="join_nav_join-files").click().run()
    assert not at.exception, f"exception opening join files: {at.exception}"
    assert any(f.label == "Second file (CSV, Excel or JSON)"
               for f in at.file_uploader), \
        "moved join form uploader missing"
    # "Preview join" renders only after a second file is uploaded —
    # upload the sample again as the second file and run the join:
    # the moved form previews the join exactly as the old inline
    # section did (same join_frames call, same preview lines).
    up = next(f for f in at.file_uploader
              if f.label == "Second file (CSV, Excel or JSON)")
    up.set_value([("messy_sales.csv", SAMPLE.read_bytes(),
                   "text/csv")]).run()
    assert not at.exception, f"exception on second upload: {at.exception}"
    find_button(at, "Preview join", key="join_preview_btn").click().run()
    assert not at.exception, f"exception previewing join: {at.exception}"
    # 86, not 80: the messy sample's Order ID has duplicate keys
    # (77 unique), so the left join fans out — the real messy data,
    # not a tidy fixture.
    assert "Joined: 86 rows" in all_text(at), "join preview missing"
    print("join visualizer + join files OK")


# --------------------------------------------------------------------------
# AppTest: cleaned table appears
# --------------------------------------------------------------------------

def test_join_cleaned_table_appears(_tmp_env):
    """The cleaning itself is unchanged (80 -> 77): after a clean
    the Tables list has two rows, the cleaned table is named after
    the file + " (cleaned)", and the visualizer names the lineage
    ("Derived from")."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "join_cleaned")
    load_sample(at)
    goto_section(at, "Clean")
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    assert at.session_state["clean"] is not None, "clean did not land"
    assert len(at.session_state["clean"]) == 77, \
        "cleaned data should have 77 rows"
    goto_join(at)
    text = all_text(at)
    assert "Total: 2 tables" in text, "cleaned table missing from the list"
    assert "messy_sales.csv (sample) (cleaned)" in dataframe_text(at), \
        "cleaned table name wrong"
    find_button(at, "Schema Visualizer",
                key="join_nav_visualizer").click().run()
    assert not at.exception, f"exception opening visualizer: {at.exception}"
    assert "Derived from" in all_text(at), "lineage label missing"
    print("join cleaned table OK")


# --------------------------------------------------------------------------
# AppTest: regressions the harness CAN reproduce
# --------------------------------------------------------------------------

def test_join_nav_keeps_persisted_prefs(_tmp_env):
    """Navigating through Join does not disturb the persisted prefs
    (the round-56/57 theme + row-limit work): Row limit 50 and the
    Light theme pref survive Join -> Dashboard -> Clean at the
    session-state level. The frontend remount quirk behind rounds
    56/57 cannot be reproduced by AppTest (the probe is the pin
    there — probe54/56/57); this test pins that the Join page
    itself never touches those keys.
    """
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "join_prefs")
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
    goto_join(at)
    goto_section(at, "Dashboard")
    goto_section(at, "Clean")
    assert find_selectbox(at, "Row limit").value == 50, \
        "Row limit fell back after navigating through Join"
    assert at.session_state.get("dcs_theme_pref") == "light", \
        "theme pref changed after navigating through Join"
    print("join nav keeps persisted prefs OK")
