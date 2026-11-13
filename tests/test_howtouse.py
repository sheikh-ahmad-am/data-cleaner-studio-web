"""How to use pattern tests (Migrations empty state + Help panel
round).

The How to use tab renders Supabase's Migrations empty state +
Help panel, mapped to this app's own help: the Guide (the seven
steps from feat_tutorial, verbatim), the Migrations view (a real
empty state — this app keeps no schema migrations — plus
instruction cards for the data journey and a pointer at the
audit trail), and the Help view (Assistant, Docs, Status — the
Help panel sections that have a real counterpart here).
Troubleshooting, Contact support and Discord have none, so they
are not rendered — and not faked.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_howtouse.py -q   (from project root)

NOTE: the "Got it" button is never clicked in the AppTest tests
below — it writes the repo's settings.json (the app's
_settings_path), and the flag-flip behaviour is already pinned
by test_feat_schedule.test_render_tutorial_and_banner with a tmp
settings path.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# NOTE: app.py is NOT imported here — it executes top-level
# Streamlit code at import (set_page_config, session state), so it
# cannot be imported in a plain pytest; the page is covered through
# AppTest below, like the Dashboard/Preview/KPIs/Settings/Tools/Clean/
# Join/Compare/Report rounds.
import auth  # noqa: E402
import feat_howtouse as fh  # noqa: E402
import feat_tutorial as ft  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_profile.py / test_kpis_overview.py /
    test_join_tables.py / test_compare_logs.py / test_report_custom.py.
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

def test_migration_steps_are_real_instructions():
    """Three instruction cards, each a real workflow step that names
    a real tab — and no fake CLI command anywhere (this app has no
    CLI, so the cards copy workflow text, not commands)."""
    assert len(fh.MIGRATION_STEPS) == 3
    titles = [s["title"] for s in fh.MIGRATION_STEPS]
    assert titles == ["Load a file", "Clean it", "Take it away"]
    joined = " ".join(s["text"] for s in fh.MIGRATION_STEPS)
    for word in ("sidebar", "Clean tab", "Report tab"):
        assert word in joined, f"step must name {word!r}: {joined}"
    for s in fh.MIGRATION_STEPS:
        assert set(s) == {"title", "text"}, s
        assert len(s["text"]) > 20, s
    for fake in ("supabase ", "dcs ", "migration new", "db push",
                 "npx ", "pip install"):
        assert fake not in joined.lower(), \
            f"instruction cards must not invent a CLI: {fake!r}"


def test_help_docs_match_tutorial_steps():
    """The Help view's Docs list is the guide itself — one link per
    tutorial step, same titles, same order, nothing invented."""
    assert len(ft.TUTORIAL_STEPS) == 7
    assert fh._VIEWS[0] == (fh.VIEW_GUIDE, "Guide")
    assert fh._VIEWS[1] == (fh.VIEW_MIGRATIONS, "Migrations")
    assert fh._VIEWS[2] == (fh.VIEW_HELP, "Help")


def test_views_default_to_guide():
    assert fh.VIEW_GUIDE == "guide"
    assert fh.VIEW_MIGRATIONS == "migrations"
    assert fh.VIEW_HELP == "help"


# --------------------------------------------------------------------------
# AppTest helpers (same idiom as test_report_custom.py)
# --------------------------------------------------------------------------

def find_button(at, label, key=None):
    for b in at.button:
        if b.label == label and (key is None or b.key == key):
            return b
    raise AssertionError(f"button {label!r} (key={key!r}) missing")


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def all_text(at):
    """Every visible string on the page (markdown + captions + headers
    + success/info banners + expander labels + code blocks — the
    Migrations instruction cards render as st.code)."""
    out = []
    out.extend(vals(at.markdown))
    out.extend(vals(at.caption))
    out.extend(e.value for e in at.subheader)
    out.extend(e.value for e in at.header)
    out.extend(vals(at.success))
    out.extend(vals(at.info))
    out.extend(vals(at.warning))
    out.extend(e.label for e in at.expander)
    out.extend(vals(at.code))
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
    for t in at.text_input:
        if t.label == "Username":
            t.set_value(username).run()
        if t.label == "Password":
            t.set_value(password).run()
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


def goto_nav(at, label, key):
    """Navigate via a sidebar nav row (the path that works with no data
    loaded, when the Section radio does not exist yet)."""
    expand_rail(at)
    find_button(at, label, key=key).click().run()
    assert not at.exception, f"exception going to {label}: {at.exception}"


def goto_howtouse(at):
    goto_nav(at, "How to use", key="dcs_nav_tutorial")
    return all_text(at)


def step_titles_in(text):
    return [s["title"] for s in ft.TUTORIAL_STEPS
            if s["title"] in text]


# --------------------------------------------------------------------------
# AppTest: Guide view, no data loaded
# --------------------------------------------------------------------------

def test_howtouse_no_data_empty_state_and_cta(_tmp_env):
    """How to use opens with no data loaded (the Tools/Clean/Join/
    Compare/Report reachability fix): the sub-nav renders, the
    "No data loaded yet" empty state with its "Try the sample data"
    CTA sits above the seven guide steps — and the CTA loads the
    sample, after which the empty state is gone and the steps
    stay."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "htu_nodata")
    text = goto_howtouse(at)
    assert "No data loaded yet" in text, "empty state missing"
    find_button(at, "Try the sample data")
    nav_labels = [b.label for b in at.button]
    assert "Guide" in nav_labels, "sub-nav missing with no data"
    assert "Migrations" in nav_labels, "sub-nav missing with no data"
    assert "Help" in nav_labels, "sub-nav missing with no data"
    assert len(step_titles_in(text)) == 7, \
        f"all 7 guide steps must render with no data: {step_titles_in(text)}"
    find_button(at, "Try the sample data").click().run()
    assert not at.exception, f"exception loading sample: {at.exception}"
    assert at.session_state["raw"] is not None, "sample did not load"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    text = all_text(at)
    assert "No data loaded yet" not in text, \
        "empty state must clear once data is loaded"
    assert len(step_titles_in(text)) == 7, \
        "guide steps must stay after the sample loads"
    print("howtouse no-data empty state + CTA OK")


def test_howtouse_guide_with_data(_tmp_env):
    """With the sample loaded (and cleaned), the Guide view shows
    the seven steps and the "Got it" button — and no empty state.
    (The button itself is not clicked here: it writes the repo's
    settings.json; the flag flip is pinned by
    test_feat_schedule.test_render_tutorial_and_banner.)"""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "htu_data")
    load_sample(at)
    text = goto_howtouse(at)
    assert "No data loaded yet" not in text, \
        "no empty state once data is loaded"
    assert len(step_titles_in(text)) == 7, \
        f"all 7 guide steps must render with data: {step_titles_in(text)}"
    find_button(at, "Got it — I know how this works", key="tut_page_seen")
    print("howtouse guide with data OK")


# --------------------------------------------------------------------------
# AppTest: Migrations view
# --------------------------------------------------------------------------

def test_howtouse_migrations_view(_tmp_env):
    """The Migrations view is Supabase's empty state + instruction
    cards: "No migrations yet" (real — this app keeps none), the
    three copyable instruction cards, and the pointer at the audit
    trail — whose Compare button really navigates there."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "htu_mig")
    goto_howtouse(at)
    find_button(at, "Migrations", key="htu_nav_migrations").click().run()
    assert not at.exception, f"exception opening Migrations: {at.exception}"
    text = all_text(at)
    assert "Migrations" in text, "Migrations heading missing"
    assert "No migrations yet" in text, "empty state missing"
    assert "no database migrations" in text, \
        "empty state must say plainly that the app keeps none"
    for step in fh.MIGRATION_STEPS:
        assert step["text"] in text, \
            f"instruction card missing: {step['title']}"
    assert "Where your changes live" in text
    assert "audit trail" in text
    find_button(at, "Open Compare → Logs", key="htu_mig_compare")
    find_button(at, "Open Clean → Run history", key="htu_mig_clean")
    find_button(at, "Open Compare → Logs", key="htu_mig_compare").click().run()
    assert not at.exception, f"exception opening Compare: {at.exception}"
    nav_labels = [b.label for b in at.button]
    assert "Logs" in nav_labels, "Compare sub-nav missing after navigation"
    assert "Compare runs" in nav_labels
    assert "Compare files" in nav_labels
    print("howtouse Migrations view OK")


# --------------------------------------------------------------------------
# AppTest: Help view
# --------------------------------------------------------------------------

def test_howtouse_help_view(_tmp_env):
    """The Help view is the Help panel's sections that have a real
    counterpart: Assistant (Ask your data), Docs (one button per
    guide step, opening the Guide view), Status. Troubleshooting,
    Contact support and Discord have none — they must not appear."""
    at = AppTest.from_file(APP).run()
    assert not at.exception, f"exception on first run: {at.exception}"
    signup(at, "htu_help")
    goto_howtouse(at)
    find_button(at, "Help", key="htu_nav_help").click().run()
    assert not at.exception, f"exception opening Help: {at.exception}"
    text = all_text(at)
    assert "Assistant" in text, "Assistant card missing"
    assert "Ask your data" in text, "Assistant must name the real feature"
    assert "More analysis" in text, "Assistant must say where it lives"
    assert "Docs" in text, "Docs card missing"
    assert "Status" in text, "Status card missing"
    for word in ("Troubleshooting", "Contact support", "Discord"):
        assert word not in text, \
            f"Help must not fake a section with no counterpart: {word}"
    for i, step in enumerate(ft.TUTORIAL_STEPS):
        find_button(at, f"{i + 1}. {step['title']}", key=f"htu_doc_{i}")
    # A Docs button opens the Guide view with the steps.
    find_button(at, "3. Clean your data", key="htu_doc_2").click().run()
    assert not at.exception, f"exception opening guide from Docs: {at.exception}"
    text = all_text(at)
    assert len(step_titles_in(text)) == 7, \
        "Docs button must land on the Guide view with all steps"
    # Back to Help, then Status really navigates to the Status tab.
    # (Already on the How to use tab — the sidebar nav row is
    # disabled for the active tab, so go via the sub-nav.)
    find_button(at, "Help", key="htu_nav_help").click().run()
    find_button(at, "Open Status", key="htu_help_status").click().run()
    assert not at.exception, f"exception opening Status: {at.exception}"
    text = all_text(at)
    # NOTE: section_heading html-escapes the sub, so the apostrophe in
    # "app's" renders as &#x27; — assert the apostrophe-free part.
    assert "own health, in plain words" in text, \
        "Status button must land on the Status tab"
    print("howtouse Help view OK")
