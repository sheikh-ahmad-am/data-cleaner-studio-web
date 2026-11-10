"""Preview pattern tests (Table Editor clone round).

The Preview tab renders Supabase's Table Editor, mapped to this
app's own data: a Files sub-sidebar on the left (current file as
the selected row + recent files, name filter, + Load a file,
collapsible), and the data grid on the right — table heading with
typed column headers, Data / Definition tabs (Supabase's
Definition/Data toggle), toolbar (search, rows-per-page, Refresh,
green Clean now), footer pagination (Prev / Page X of Y / Next +
the shown window), and the empty state with Recent items.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_preview_editor.py -q   (from project root)
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import auth  # noqa: E402
import feat_share  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"

NEW_CLASSES = (
    "dcs-file-row", "dcs-file-row-sub", "dcs-file-row-active",
)


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_profile.py / test_supabase_rebuild.py.
    """
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    yield tmp_path


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


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def all_text(at):
    """Every visible string on the page (markdown + captions + headers)."""
    out = []
    out.extend(vals(at.markdown))
    out.extend(vals(at.caption))
    out.extend(e.value for e in at.subheader)
    out.extend(e.value for e in at.header)
    return "\n".join(out)


def expand_rail(at):
    """Open the sidebar rail (it starts collapsed — the dashboard's
    own default, icon-only) so the full sidebar is visible."""
    at.session_state["dcs_rail_mode"] = "expanded"
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert not at.exception, f"exception expanding rail: {at.exception}"


def signup(at, username, password="password"):
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


def load_rows(at, n, name="big.csv"):
    """Upload a generated n-row CSV through the sidebar uploader."""
    body = ("a,b\n" + "\n".join(f"{i},{i * 2}" for i in range(n)) + "\n")
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([(name, body.encode("utf-8"), "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert at.session_state["raw"] is not None, "raw data not loaded"
    assert len(at.session_state["raw"]) == n, f"file should have {n} rows"


def seed_recent(at, name, data):
    """Save a recent file the way the app does, into the app's own
    user root for this test user."""
    root = at.session_state["user_paths"]["root"]
    feat_share.add_recent(name, data, base_dir=root)


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


# ---------------------------------------------------------------------------
# CSS: the new classes exist in both themes, no :has(), app.py in sync
# ---------------------------------------------------------------------------

def test_preview_css_in_both_themes():
    """Every new file-row class ships in the light sheet, the dark
    sheet, and the app.py literal (the verbatim-copy rule) — and the
    new rules carry no :has() (the ban stands)."""
    import re
    light = ui_design.theme_css("light")
    dark = ui_design.theme_css("dark")
    for cls in NEW_CLASSES:
        assert cls in light, f"{cls} missing from the light stylesheet"
        assert cls in dark, f"{cls} missing from the dark stylesheet"
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r'DESIGN_SYSTEM_CSS = """<style>(.*?)</style>"""', source, re.DOTALL)
    assert match, "DESIGN_SYSTEM_CSS block missing from app.py"
    assert "<style>" + match.group(1) + "</style>" == \
        ui_design.DESIGN_SYSTEM_CSS, \
        "app.py literal must be the verbatim light stylesheet"
    for cls in NEW_CLASSES:
        assert cls in match.group(1), \
            f"{cls} missing from the app.py literal"
    new_block = light.split(".dcs-file-row")[1]
    assert ":has(" not in new_block, \
        "new file-row CSS must not use :has()"
    print("preview CSS in both themes + app.py literal OK")


# ---------------------------------------------------------------------------
# No data: the empty state carries Recent items, no sub-sidebar
# ---------------------------------------------------------------------------

def test_preview_no_data(_tmp_env):
    """With nothing loaded: the guided empty state, the Recent items
    section saying there are none yet, and NO Files sub-sidebar
    (the Table Editor's list needs a file to list)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    text = all_text(at)
    assert "Nothing loaded yet" in text, "empty state missing"
    assert "Recent items" in text, "empty state must list Recent items"
    assert "No recent files yet" in text, \
        "empty state must say so honestly when there are none"
    find_button(at, "Try the sample data")
    assert not any(b.key == "preview_files_collapse" for b in at.button), \
        "no Files sub-sidebar with no data loaded"
    assert not any(t.label == "Search files" for t in at.text_input), \
        "no Files search with no data loaded"
    print("preview no-data empty state OK")


def test_preview_no_data_recent_items(_tmp_env):
    """With a saved recent file and nothing loaded: Recent items
    lists it with an Open button, and Open loads it into the grid."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    seed_recent(at, "old.csv", b"a,b\n1,2\n3,4\n")
    at.run()
    assert not at.exception, f"exception re-running: {at.exception}"
    assert "old.csv" in all_text(at), "Recent items must list old.csv"
    find_button(at, "Open", key="preview_empty_recent_0").click().run()
    assert not at.exception, f"exception opening recent: {at.exception}"
    assert at.session_state["raw"] is not None, "recent file not loaded"
    assert len(at.session_state["raw"]) == 2, \
        "old.csv should have 2 rows"
    assert "Loaded:" in all_text(at), "must land on the Preview grid"
    print("preview no-data Recent items OK")


# ---------------------------------------------------------------------------
# Loaded: sub-sidebar, tabs, toolbar, pagination footer
# ---------------------------------------------------------------------------

def test_preview_loaded(_tmp_env):
    """Sample loaded (80 rows): the Files sub-sidebar shows the
    current file as the selected row, Data / Definition tabs render,
    the toolbar carries search + rows + Refresh + Clean now, and the
    footer shows the single-page window."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    md = "\n".join(vals(at.markdown))
    text = all_text(at)
    assert "Files" in md, "Files sub-sidebar heading missing"
    # The rendered row div — not the bare class name, which also
    # appears in the injected stylesheet.
    assert '<div class="dcs-file-row dcs-file-row-active">' in md, \
        "current file must render as the selected row"
    assert "messy_sales.csv" in md, "current file name missing"
    assert "Current" in md, "selected row must say Current"
    assert "80 rows" in md and "10 columns" in md, \
        "selected row must show the row/column counts"
    find_button(at, "Collapse", key="preview_files_collapse")
    find_button(at, "Load a file", key="preview_files_new")
    find_text_input(at, "Search files")
    assert [t.label for t in at.tabs] == ["Data", "Definition"], \
        f"tabs wrong: {[t.label for t in at.tabs]!r}"
    assert "Loaded:" in text, "table heading missing"
    # Typed column headers: the name + dtype line above the grid.
    assert "dcs-coltype" in md, "typed column header line missing"
    find_text_input(at, "Search the preview")
    rows = next(s for s in at.selectbox if s.label == "Rows")
    assert list(rows.options) == ["50", "100", "200"], \
        f"rows-per-page options wrong: {list(rows.options)!r}"
    find_button(at, "", key="preview_refresh")
    find_button(at, "Clean now", key="preview_clean_now")
    assert any("Showing 1–80 of 80 rows" in v for v in vals(at.caption)), \
        "footer must show the single-page window"
    assert any("Page 1 of 1" in v for v in vals(at.caption)), \
        "footer must say Page 1 of 1"
    prev_btn = find_button(at, "", key="preview_page_prev")
    next_btn = find_button(at, "", key="preview_page_next")
    assert prev_btn.disabled, "Prev must be disabled on the first page"
    assert next_btn.disabled, "Next must be disabled on the only page"
    # Sort + whole-file search + filter expander still live in Data.
    assert any(s.label == "Sort by" for s in at.selectbox), \
        "sort control missing"
    assert "Search the whole file" in text, "whole-file search missing"
    assert any(e.label == "Search, filter & suggested fixes"
               for e in at.expander), "filter expander missing"
    print("preview loaded OK")


def test_preview_definition_tab(_tmp_env):
    """Definition tab: health numbers, the per-column profile table,
    and the data dictionary with its download — the content that
    used to sit in the expander under the grid."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    text = all_text(at)
    assert "Health check" in text, "Definition must show the health check"
    assert "Missing cells" in text, "health numbers missing"
    assert "Duplicate rows" in text, "health numbers missing"
    assert "Data dictionary" in text, "Definition must show the dictionary"
    assert len(at.table) >= 1, "profile table missing from Definition"
    assert any(d.label == "Download data dictionary (.md)"
               for d in at.download_button), "dictionary download missing"
    print("preview Definition tab OK")


def test_preview_refresh(_tmp_env):
    """Refresh reloads the current file from its saved copy: same
    80 rows, a success note, no exception."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    find_button(at, "", key="preview_refresh").click().run()
    assert not at.exception, f"exception on Refresh: {at.exception}"
    assert len(at.session_state["raw"]) == 80, \
        "Refresh must reload the same 80 rows"
    # The reload confirmation travels as a flash (a toast would not
    # survive the rerun) and renders as a success alert.
    assert any("Reloaded messy_sales.csv" in v
               for v in vals(at.success)), \
        "Refresh must confirm the reload"
    print("preview Refresh OK")


# ---------------------------------------------------------------------------
# Pagination: 250 rows across pages, reset on a new search
# ---------------------------------------------------------------------------

def test_preview_pagination(_tmp_env):
    """250 rows at 100/page: Page 1 of 3, Next walks the window
    (1–100, 101–200, 201–250), Next disables on the last page, Prev
    walks back, and a new toolbar search resets to page 1."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_rows(at, 250)
    assert any("Page 1 of 3" in v for v in vals(at.caption)), \
        "250 rows at 100/page must be Page 1 of 3"
    assert any("Showing 1–100 of 250 rows" in v
               for v in vals(at.caption)), "first window wrong"
    find_button(at, "", key="preview_page_next").click().run()
    assert not at.exception, f"exception paging next: {at.exception}"
    assert any("Page 2 of 3" in v for v in vals(at.caption)), \
        "Next must land on Page 2 of 3"
    assert any("Showing 101–200 of 250 rows" in v
               for v in vals(at.caption)), "second window wrong"
    find_button(at, "", key="preview_page_next").click().run()
    assert not at.exception, f"exception paging next: {at.exception}"
    assert any("Page 3 of 3" in v for v in vals(at.caption)), \
        "Next must land on Page 3 of 3"
    assert any("Showing 201–250 of 250 rows" in v
               for v in vals(at.caption)), "last window wrong"
    assert find_button(at, "", key="preview_page_next").disabled, \
        "Next must be disabled on the last page"
    find_button(at, "", key="preview_page_prev").click().run()
    assert not at.exception, f"exception paging prev: {at.exception}"
    assert any("Page 2 of 3" in v for v in vals(at.caption)), \
        "Prev must land back on Page 2 of 3"
    # A new search resets the page: "249" matches one row only.
    find_text_input(at, "Search the preview").set_value("249").run()
    assert not at.exception, f"exception searching: {at.exception}"
    assert any("Page 1 of 1" in v for v in vals(at.caption)), \
        "a new search must reset to page 1"
    assert any("Showing 1–1 of 1 rows" in v for v in vals(at.caption)), \
        "filtered window wrong"
    print("preview pagination OK")


# ---------------------------------------------------------------------------
# Files sub-sidebar: recents, search filter, collapse
# ---------------------------------------------------------------------------

def test_preview_files_recent_open(_tmp_env):
    """A saved recent file appears in the Files list (the current
    file stays the selected row) and its Open button loads it."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    seed_recent(at, "old.csv", b"a,b\n1,2\n3,4\n")
    load_sample(at)
    md = "\n".join(vals(at.markdown))
    assert "old.csv" in md, "Files list must show the recent file"
    assert "messy_sales.csv" in md, \
        "current file must stay listed"
    find_button(at, "Open", key="preview_files_open_0").click().run()
    assert not at.exception, f"exception opening recent: {at.exception}"
    assert len(at.session_state["raw"]) == 2, \
        "old.csv should have 2 rows after Open"
    assert at.session_state["source_name"] == "Recent file (reopened)", \
        "source name must follow the reopen"
    print("preview Files recent Open OK")


def test_preview_files_search_filters(_tmp_env):
    """The Files search filters the list by name: a query matching
    only the recent file hides the selected current-file row, and
    clearing it brings the row back."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    seed_recent(at, "old.csv", b"a,b\n1,2\n3,4\n")
    load_sample(at)
    md = "\n".join(vals(at.markdown))
    # The rendered row div — not the bare class name, which also
    # appears in the injected stylesheet.
    assert '<div class="dcs-file-row dcs-file-row-active">' in md, \
        "selected row must render at first"
    find_text_input(at, "Search files").set_value("old").run()
    assert not at.exception, f"exception filtering files: {at.exception}"
    md = "\n".join(vals(at.markdown))
    assert '<div class="dcs-file-row dcs-file-row-active">' not in md, \
        "a non-matching query must hide the current-file row"
    assert "old.csv" in md, "the matching recent file must stay listed"
    find_text_input(at, "Search files").set_value("").run()
    assert not at.exception, f"exception clearing filter: {at.exception}"
    assert '<div class="dcs-file-row dcs-file-row-active">' in \
        "\n".join(vals(at.markdown)), \
        "clearing the filter must bring the selected row back"
    print("preview Files search OK")


def test_preview_files_collapse(_tmp_env):
    """Collapse hides the Files list (and shows the slim expand
    button); expanding brings it back."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    find_button(at, "Collapse", key="preview_files_collapse").click().run()
    assert not at.exception, f"exception collapsing: {at.exception}"
    assert not any(b.key == "preview_files_collapse" for b in at.button), \
        "Collapse button must be gone once collapsed"
    assert not any(t.label == "Search files" for t in at.text_input), \
        "Files search must be gone once collapsed"
    find_button(at, "", key="preview_files_expand").click().run()
    assert not at.exception, f"exception expanding: {at.exception}"
    find_button(at, "Collapse", key="preview_files_collapse")
    find_text_input(at, "Search files")
    print("preview Files collapse OK")
