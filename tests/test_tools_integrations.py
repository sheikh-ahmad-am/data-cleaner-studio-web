"""Tools pattern tests (Integrations clone round).

The Tools tab renders Supabase's Integrations page, mapped to this
app's own tools: search box, Category/Type/Source dropdowns, grid/list
toggle, Featured row, 3-col card grid with badges; a card's Open
button (or an Installed sub-nav row) opens the detail — breadcrumb,
badges, the tool's own section, TYPE / BUILT BY / STATUS rail.
The sections themselves are the existing real ones (watch folder,
schedule, morning run, shortcuts, backups, live DB, Sheets, email
report, Supabase backend) — this file pins the new chrome and the
live statuses, not the sections.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_tools_integrations.py -q   (from project root)
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# NOTE: app.py is NOT imported here — it executes top-level
# Streamlit code at import (set_page_config, session state), so it
# cannot be imported in a plain pytest; the page is covered through
# AppTest below, like the Dashboard/Preview/KPIs rounds.
import auth  # noqa: E402
import feat_db  # noqa: E402
import feat_export  # noqa: E402
import feat_tools  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")


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


def goto_nav(at, label, key):
    """Navigate via a sidebar nav row (the path that works with no data
    loaded, when the Section radio does not exist yet)."""
    expand_rail(at)
    find_button(at, label, key=key).click().run()
    assert not at.exception, f"exception going to {label}: {at.exception}"


def goto_tools(at):
    goto_nav(at, "Tools", key="dcs_nav_tools")
    text = all_text(at)
    assert "Tools" in text, "Tools page heading missing"
    return text


# ---------------------------------------------------------------------------
# Catalog + filtering (pure)
# ---------------------------------------------------------------------------

def test_catalog_shape():
    keys = [t["key"] for t in feat_tools.TOOLS]
    assert len(keys) == len(set(keys)) == 8, "tool keys must be unique"
    for tool in feat_tools.TOOLS:
        for field in ("key", "name", "desc", "category", "type",
                      "source", "icon", "svg", "built_by"):
            assert tool[field], f"{tool['key']}: {field} must be non-empty"
        assert isinstance(tool["featured"], bool)
        # The icon must be a real Material icon, not the fallback.
        assert ui_design.icon_for(tool["icon"]) != ui_design.icon_for(
            "definitely-not-an-icon"), f"{tool['key']}: unknown icon"
        assert tool["svg"] in ui_design._SVG_PATHS, \
            f"{tool['key']}: unknown svg icon"
    featured = [t for t in feat_tools.TOOLS if t["featured"]]
    assert len(featured) == 3, "Featured row is three cards (Supabase)"


def test_filter_options_derive_from_catalog():
    for opts, field in ((feat_tools.categories(), "category"),
                        (feat_tools.types(), "type"),
                        (feat_tools.sources(), "source")):
        assert opts[0] == "All"
        assert set(opts[1:]) == {t[field] for t in feat_tools.TOOLS}


def test_filter_query_matches_name_and_desc():
    got = feat_tools.filter_tools(feat_tools.TOOLS, "watch")
    assert [t["key"] for t in got] == ["watch-folder"]
    # Case-insensitive, description included.
    got = feat_tools.filter_tools(feat_tools.TOOLS, "GOOGLE")
    assert [t["key"] for t in got] == ["sheets"]
    got = feat_tools.filter_tools(feat_tools.TOOLS, "")
    assert len(got) == len(feat_tools.TOOLS)


def test_filter_dropdowns():
    by_cat = feat_tools.filter_tools(feat_tools.TOOLS,
                                    category="Data sources")
    assert [t["key"] for t in by_cat] == ["live-db", "sheets"]
    by_type = feat_tools.filter_tools(feat_tools.TOOLS, type_="Connection")
    assert [t["key"] for t in by_type] == ["live-db", "sheets", "supabase"]
    by_src = feat_tools.filter_tools(feat_tools.TOOLS, source="Google")
    assert [t["key"] for t in by_src] == ["sheets"]
    # A stale/unknown dropdown value matches nothing, never the grid.
    assert feat_tools.filter_tools(feat_tools.TOOLS,
                                   category="Nope") == []
    # Combined: query + category.
    got = feat_tools.filter_tools(feat_tools.TOOLS, "backup",
                                  category="Storage")
    assert [t["key"] for t in got] == ["backups", "supabase"]


# ---------------------------------------------------------------------------
# Live status (reads only)
# ---------------------------------------------------------------------------

def test_status_builtin_tools_are_installed():
    for key in ("watch-folder", "shortcuts", "backups"):
        tool = next(t for t in feat_tools.TOOLS if t["key"] == key)
        status = feat_tools.tool_status(tool)
        assert status["installed"] is True
        assert status["badge"][0] == "BUILT-IN"
        assert status["status"]


def test_status_live_db_reflects_drivers(monkeypatch):
    tool = next(t for t in feat_tools.TOOLS if t["key"] == "live-db")
    monkeypatch.setattr(
        feat_db, "db_driver_status",
        lambda: {"mysql": True, "postgres": False, "sqlserver": False})
    status = feat_tools.tool_status(tool)
    assert status["installed"] is True
    assert status["badge"] == ("PARTIAL", "amber")
    assert "1 of 3 drivers" in status["status"]
    monkeypatch.setattr(
        feat_db, "db_driver_status",
        lambda: {"mysql": False, "postgres": False, "sqlserver": False})
    status = feat_tools.tool_status(tool)
    assert status["installed"] is False
    assert status["badge"] == ("NOT INSTALLED", "grey")
    assert "No drivers installed" in status["status"]


def test_status_morning_clean_not_installed_off_windows():
    if sys.platform == "win32":
        pytest.skip("task_status can be set up on Windows")
    tool = next(t for t in feat_tools.TOOLS if t["key"] == "morning-clean")
    status = feat_tools.tool_status(tool)
    assert status["installed"] is False
    assert status["badge"] == ("NOT INSTALLED", "grey")


def test_status_email_report_follows_schedule():
    tool = next(t for t in feat_tools.TOOLS if t["key"] == "email-report")
    assert feat_tools.tool_status(tool, session_state={})["badge"] == (
        "NEEDS SETUP", "amber")
    sched = {feat_export.EMAIL_SCHED_KEY: {
        "enabled": True, "time": "09:00", "recipient": "a@b.c"}}
    status = feat_tools.tool_status(tool, session_state=sched)
    assert status["installed"] is True
    assert status["badge"] == ("INSTALLED", "green")
    assert "09:00" in status["status"] and "a@b.c" in status["status"]


def test_status_supabase_local_in_test_env(_tmp_env):
    tool = next(t for t in feat_tools.TOOLS if t["key"] == "supabase")
    status = feat_tools.tool_status(tool)
    assert status["installed"] is False
    assert status["badge"] == ("LOCAL", "grey")
    assert "Local (this server)" in status["status"]


# ---------------------------------------------------------------------------
# Page (AppTest — no data loaded, like the real first visit)
# ---------------------------------------------------------------------------

def test_tools_page_renders_all_cards(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser1")
    text = goto_tools(at)
    for tool in feat_tools.TOOLS:
        assert tool["name"] in text, f"{tool['name']} card missing"
    assert "8 of 8 tools" in text
    find_text_input(at, "Search tools")
    # Featured row: the three featured tools render twice (featured +
    # grid) — AppTest sees both copies; the Open keys must differ.
    open_keys = [b.key for b in at.button
                 if b.label == "Open" and b.key.startswith("tools_open_")]
    assert len(open_keys) == len(set(open_keys)), \
        "duplicate Open button keys (featured vs grid)"
    assert "tools_open_watch-folder" in open_keys
    assert "tools_open_watch-folder_featured" in open_keys


def test_tools_search_filters_grid(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser2")
    goto_tools(at)
    find_text_input(at, "Search tools").set_value("sheets").run()
    assert not at.exception, f"exception on search: {at.exception}"
    text = all_text(at)
    assert "Google Sheets" in text
    assert "Watch folder" not in text
    assert "1 of 8 tools" in text


def test_tools_category_filter(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser3")
    goto_tools(at)
    find_selectbox(at, "Category").set_value("Data sources").run()
    assert not at.exception, f"exception on filter: {at.exception}"
    text = all_text(at)
    assert "Live databases" in text and "Google Sheets" in text
    assert "Watch folder" not in text
    assert "Backups" not in text
    assert "2 of 8 tools" in text


def test_tools_browse_nav_sets_category(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser4")
    goto_tools(at)
    find_button(at, "Data sources",
                key="tools_nav_cat_Data sources").click().run()
    assert not at.exception, f"exception on browse nav: {at.exception}"
    text = all_text(at)
    assert "Live databases" in text and "Google Sheets" in text
    assert "Watch folder" not in text


def test_tools_list_view(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser5")
    goto_tools(at)
    find_selectbox(at, "View").set_value("List").run()
    assert not at.exception, f"exception on list view: {at.exception}"
    text = all_text(at)
    for tool in feat_tools.TOOLS:
        assert tool["name"] in text, f"{tool['name']} missing in list view"


def test_tools_no_match_empty_state(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser6")
    goto_tools(at)
    find_text_input(at, "Search tools").set_value("zzzz-no-such-tool").run()
    assert not at.exception, f"exception on empty search: {at.exception}"
    assert "No tools match" in all_text(at)


def test_tools_open_watch_folder_detail(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser7")
    goto_tools(at)
    find_button(at, "Open", key="tools_open_watch-folder").click().run()
    assert not at.exception, f"exception opening detail: {at.exception}"
    text = all_text(at)
    # The breadcrumb is raw HTML in the markdown value, so the ">"
    # arrives escaped as "&gt;".
    assert "Tools &gt; Watch folder" in text
    assert "Watch folder (automatic cleaning)" in text
    assert any(b.label == "Download watch_folder.py"
               for b in at.download_button), \
        "watch-folder download button missing"
    assert "Type" in text and "Built-in" in text
    # Back to the grid.
    find_button(at, "← All tools").click().run()
    assert not at.exception, f"exception going back: {at.exception}"
    assert "8 of 8 tools" in all_text(at)


def test_tools_open_live_db_detail_shows_driver_state(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser8")
    goto_tools(at)
    find_button(at, "Open", key="tools_open_live-db").click().run()
    assert not at.exception, f"exception opening live-db: {at.exception}"
    text = all_text(at)
    assert "Live database connections" in text
    find_button(at, "Test connection")
    # The test venv has all three drivers importable (the known
    # test_feat_db failures are about the portable-build wheel, not
    # the importable driver) — the detail reports that honestly.
    assert "MySQL driver: installed." in text
    assert "PostgreSQL driver: installed." in text
    assert "SQL Server driver: installed." in text


def test_tools_open_supabase_detail_local(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser9")
    goto_tools(at)
    find_button(at, "Open", key="tools_open_supabase").click().run()
    assert not at.exception, f"exception opening supabase: {at.exception}"
    text = all_text(at)
    assert "Account backend:" in text
    assert "Local (this server)" in text
    find_button(at, "Open Status", key="tools_open_status")


def test_tools_installed_nav_opens_detail(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser10")
    goto_tools(at)
    find_button(at, "Watch folder",
                key="tools_nav_installed_watch-folder").click().run()
    assert not at.exception, f"exception on installed nav: {at.exception}"
    assert "Tools &gt; Watch folder" in all_text(at)


def test_tools_backups_detail_empty_state(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "toolsuser11")
    goto_tools(at)
    find_button(at, "Open", key="tools_open_backups").click().run()
    assert not at.exception, f"exception opening backups: {at.exception}"
    assert "No backups yet" in all_text(at)
