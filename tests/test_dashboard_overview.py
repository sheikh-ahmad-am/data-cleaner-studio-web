"""Dashboard Overview pattern tests (Project Overview clone round).

The Dashboard tab renders Supabase's Project Overview, mapped to
this app's own state: URL row + Copy menu, six info tiles, the
infrastructure diagram (Upload → Clean → KPIs → Export), the "Get
connected" strip, the API metrics strip (Rows processed / Success
rate + service cards), the Advisor block + Ask Assistant, and the
Reports section. No Free-plan usage panel — Supabase's Overview has
none, and neither does this page.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_dashboard_overview.py -q   (from project root)
"""

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import auth  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"
APP_URL = "https://datacleanerstudio.streamlit.app"
REPO_URL = "https://github.com/sheikh-ahmad-am/data-cleaner-studio-web"

NEW_CLASSES = (
    "dcs-overview-url", "dcs-infra-canvas", "dcs-infra-row",
    "dcs-infra-node", "dcs-infra-node-title", "dcs-infra-node-count",
    "dcs-infra-node-sub", "dcs-infra-arrow",
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


def load_clean_file(at):
    """Upload a tiny file with no missing cells and no duplicates, so
    the Advisor reaches its no-issues state."""
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([("clean.csv", b"a,b\n1,2\n3,4\n", "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert at.session_state["raw"] is not None, "raw data not loaded"


def clean_sample(at):
    find_button(at, "Clean my data").click().run()
    assert not at.exception, f"exception on clean: {at.exception}"
    clean = at.session_state["clean"]
    assert clean is not None and len(clean) == 77, \
        "cleaned data should have 77 rows"


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


def node_count(md, title):
    """The infra-diagram node's count for ``title`` (regex over the
    rendered HTML: title div followed by count div)."""
    m = re.search(
        re.escape(title) + r"</div><div class=\"dcs-infra-node-count\">"
        r"([^<]+)</div>", md)
    assert m, f"infra node {title!r} missing from the diagram"
    return m.group(1)


# ---------------------------------------------------------------------------
# CSS: the new classes exist in both themes, no :has(), app.py in sync
# ---------------------------------------------------------------------------

def test_overview_css_in_both_themes():
    """Every new Overview class ships in the light sheet, the dark
    sheet, and the app.py literal (the verbatim-copy rule) — and the
    new rules carry no :has() (the ban stands)."""
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
    new_block = light.split(".dcs-bar-error")[1]
    assert ":has(" not in new_block, \
        "new Overview CSS must not use :has()"
    print("overview CSS in both themes + app.py literal OK")


# ---------------------------------------------------------------------------
# No data: the whole Overview renders with honest empty states
# ---------------------------------------------------------------------------

def test_overview_no_data(_tmp_env):
    """Dashboard with nothing loaded: URL row + Copy, six tiles,
    the pipeline diagram with "—" counts, API numbers "—", the
    Advisor pointing at loading a file, the Reports empty state —
    and no Free-plan usage panel."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    goto_nav(at, "Dashboard", "dcs_nav_dashboard")
    md = "\n".join(vals(at.markdown))
    text = all_text(at)
    assert APP_URL in md, "app URL missing under the Dashboard H1"
    # The Copy popover's trigger button is not exposed as a button
    # by AppTest (popover triggers are not in at.button) — but the
    # menu's contents ARE in the tree: both addresses as code blocks.
    # Opening the popover itself is covered by the real-DOM probe.
    codes = vals(at.code)
    assert APP_URL in codes, "Copy menu must hold the app URL"
    assert REPO_URL in codes, "Copy menu must hold the repository URL"
    for tile in ("Status", "Storage", "Rows", "Columns", "KPIs", "File"):
        assert tile in md, f"status strip tile {tile!r} missing"
    assert "Your pipeline" in md, "infra diagram label missing"
    for node in ("Upload", "Clean", "KPIs", "Export"):
        assert node_count(md, node) == "—", \
            f"infra node {node!r} must show — with no data"
    assert "Rows processed" in md, "API metric Rows processed missing"
    assert "Success rate" in md, "API metric Success rate missing"
    assert "No data loaded yet" in md, "Advisor must say no data loaded yet"
    find_button(at, "Load a file", key="dashboard_advisor_go")
    find_button(at, "Ask Assistant", key="dashboard_advisor_ask")
    assert "Reports" in md, "Reports heading missing"
    assert "Build a custom report" in md, "Reports empty state missing"
    assert "Keep track of your most important metrics" in md
    find_button(at, "Add block", key="dashboard_reports_add")
    find_button(at, "Add your first block",
                key="dashboard_reports_first")
    assert "Free plan usage" not in md, \
        "no Free-plan usage panel on the Overview"
    assert "Nothing loaded yet" not in text, \
        "generic empty state must not hide the Dashboard Overview"
    print("overview with no data OK")


def test_overview_copy_menu(_tmp_env):
    """The Copy menu holds both real addresses as code blocks
    (st.code carries its own copy button). AppTest renders the
    popover's contents in the tree even while closed; opening the
    popover in the browser is covered by the real-DOM probe."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    goto_nav(at, "Dashboard", "dcs_nav_dashboard")
    codes = vals(at.code)
    assert APP_URL in codes, "Copy menu must show the app URL"
    assert REPO_URL in codes, "Copy menu must show the repository URL"
    print("overview Copy menu OK")


def test_overview_ask_assistant_jumps_to_tutorial(_tmp_env):
    """Ask Assistant opens the How to use guide — this app has no AI
    assistant panel, so the guide is the honest counterpart."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    goto_nav(at, "Dashboard", "dcs_nav_dashboard")
    find_button(at, "Ask Assistant",
                key="dashboard_advisor_ask").click().run()
    assert not at.exception, f"exception on Ask Assistant: {at.exception}"
    assert any("How to use Data Cleaner Studio" in v
               for v in vals(at.subheader)), \
        "Ask Assistant must land on the How to use guide"
    assert not any("No data loaded yet" in v for v in vals(at.markdown)), \
        "we must have left the Dashboard after Ask Assistant"
    print("overview Ask Assistant OK")


def test_overview_reports_add_block_no_data(_tmp_env):
    """With no data, "Add your first block" goes to Preview (load a
    file first) — the button's destination follows the real state."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    goto_nav(at, "Dashboard", "dcs_nav_dashboard")
    find_button(at, "Add your first block",
                key="dashboard_reports_first").click().run()
    assert not at.exception, f"exception on Add block: {at.exception}"
    assert any("Nothing loaded yet" in v for v in vals(at.markdown)), \
        "Add block with no data must land on the Preview empty state"
    print("overview Reports Add block (no data) OK")


# ---------------------------------------------------------------------------
# Loaded, not cleaned: live counts, Advisor points at cleaning
# ---------------------------------------------------------------------------

def test_overview_loaded_not_cleaned(_tmp_env):
    """Sample loaded (80 rows), not cleaned: the Upload node shows
    80 rows, the Clean node "—" / "Not cleaned yet", Rows processed
    is 80, Success rate is still "—", and the Advisor finds the
    sample's real issues."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    goto_section(at, "Dashboard")
    md = "\n".join(vals(at.markdown))
    assert node_count(md, "Upload") == "80 rows", \
        "Upload node must show the loaded row count"
    assert node_count(md, "Clean") == "—", \
        "Clean node must show — before any clean"
    assert "Not cleaned yet" in md, "Clean node sub must say Not cleaned yet"
    assert "Rows processed" in md
    assert "80" in md.split("Rows processed")[1].split("Success rate")[0], \
        "Rows processed must be the loaded row count"
    assert "Advisor found" in md, "Advisor must report the sample's issues"
    find_button(at, "Go to Clean", key="dashboard_advisor_go")
    find_button(at, "Ask Assistant", key="dashboard_advisor_ask")
    print("overview loaded-not-cleaned OK")


# ---------------------------------------------------------------------------
# Cleaned: the diagram and the API numbers follow the real clean
# ---------------------------------------------------------------------------

def test_overview_cleaned(_tmp_env):
    """Sample cleaned (80 → 77 rows): the Clean node shows 77 rows
    with its step count, Export reads Ready, Success rate is the
    real kept share (96.2%), and the Reports footer says the report
    is ready to build."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    goto_section(at, "Clean")
    clean_sample(at)
    goto_section(at, "Dashboard")
    md = "\n".join(vals(at.markdown))
    assert node_count(md, "Upload") == "80 rows"
    assert node_count(md, "Clean") == "77 rows", \
        "Clean node must show the cleaned row count"
    assert "cleaning steps" in md, \
        "Clean node sub must show the applied step count"
    assert node_count(md, "KPIs") != "—", \
        "KPIs node must show the auto-KPI count"
    assert node_count(md, "Export") == "Ready", \
        "Export node must read Ready once data is cleaned"
    assert "96.2%" in md.split("Success rate")[1].split("Advisor")[0], \
        "Success rate must be the real kept share (77/80)"
    assert "ready to build" in md, \
        "Reports footer must say the report is ready to build"
    print("overview cleaned OK")


def test_overview_reports_add_block_cleaned(_tmp_env):
    """With cleaned data, "Add block" lands on the Report tab."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    goto_section(at, "Clean")
    clean_sample(at)
    goto_section(at, "Dashboard")
    find_button(at, "Add block",
                key="dashboard_reports_add").click().run()
    assert not at.exception, f"exception on Add block: {at.exception}"
    assert any("Download PDF report" in b.label
               for b in at.download_button), \
        "Add block with cleaned data must land on the Report tab"
    print("overview Reports Add block (cleaned) OK")


# ---------------------------------------------------------------------------
# No issues: the Advisor's happy path has Ask Assistant only
# ---------------------------------------------------------------------------

def test_overview_no_issues(_tmp_env):
    """A file with no missing cells and no duplicates: the Advisor
    says it found no issues, and Ask Assistant is the only button
    (the old "How to use" button went to the same place)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_clean_file(at)
    goto_section(at, "Dashboard")
    md = "\n".join(vals(at.markdown))
    assert "Advisor found no issues" in md, \
        "Advisor must say it found no issues for a clean file"
    find_button(at, "Ask Assistant", key="dashboard_advisor_ask")
    # No state-action button in the no-issues state: the old
    # "How to use" button (key dashboard_advisor_go) went to the
    # same place as Ask Assistant, so it is gone. (A "How to use"
    # sidebar nav row still exists — that is navigation, not the
    # Advisor's button — so the check is key-scoped, not label.)
    assert not any(b.key == "dashboard_advisor_go" for b in at.button), \
        "no Advisor action button in the no-issues state"
    assert "Free plan usage" not in md, \
        "no Free-plan usage panel on the Overview"
    print("overview no-issues Advisor OK")

# ---------------------------------------------------------------------------
# Fix round (live check 2026-11-10): Advisor after a clean + Back
# ---------------------------------------------------------------------------

def test_overview_advisor_after_clean(_tmp_env):
    """After a real clean that fixed everything (80 -> 77 rows, the
    3 duplicates dropped, the 52 missing cells filled), the Advisor
    scores the CLEANED data and says it found no issues — it must
    not keep scoring the raw file (the live-check failure: it still
    said "Advisor found 136 issues" after the clean)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    goto_section(at, "Clean")
    clean_sample(at)
    goto_section(at, "Dashboard")
    md = "\n".join(vals(at.markdown))
    assert "Advisor found no issues" in md, \
        "Advisor must score the cleaned data after a clean"
    assert not any(b.label == "Go to Clean" for b in at.button), \
        "no Go to Clean button once the clean fixed everything"
    print("overview Advisor after clean OK")


def test_profile_back_goes_to_dashboard_with_data(_tmp_env):
    """With data loaded, Profile's "← Back to dashboard" lands on
    the Dashboard tab — not on Preview (the live-check failure:
    the button pointed at Preview in both branches)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    assert any("Profile information" in v for v in vals(at.markdown)), \
        "Profile view must render"
    find_button(at, "← Back to dashboard").click().run()
    assert not at.exception, f"exception going back: {at.exception}"
    # section_heading() HTML-escapes the sub (html.escape), so the
    # apostrophe reads &#x27; in the raw markdown value.
    assert any("Your data&#x27;s health, at a glance." in m.value
               for m in at.markdown), \
        "Back should land on the Dashboard tab, not Preview"
    assert not any("Profile information" in v for v in vals(at.markdown)), \
        "profile view should be gone after Back"
    print("profile Back goes to Dashboard (with data) OK")


def test_overview_reports_footer_every_state(_tmp_env):
    """Fix round (live check 2026-11-10, Dashboard A7): the Reports
    footer renders in every state — no data, loaded, cleaned — with
    copy and destination following the real state. The live check
    quoted a footer string ("You don't have any data loaded yet")
    that does not exist anywhere in the app, so the footer was
    misread, not missing; pin all three real copies here, and pin
    the phantom string absent, so a future check cannot misread it.
    (The footer is rendered unconditionally by the Dashboard strips
    — no session flag suppresses it after the first render.)"""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    goto_nav(at, "Dashboard", "dcs_nav_dashboard")
    md = "\n".join(vals(at.markdown))
    assert "No data loaded yet — load a file to start." in md, \
        "Reports footer must render with no data loaded"
    goto_nav(at, "Preview", "dcs_nav_preview")
    load_sample(at)
    goto_section(at, "Dashboard")
    md = "\n".join(vals(at.markdown))
    assert "Data loaded — clean it to unlock the report." in md, \
        "Reports footer must follow the loaded state"
    goto_section(at, "Clean")
    clean_sample(at)
    goto_section(at, "Dashboard")
    md = "\n".join(vals(at.markdown))
    assert ("Your data is cleaned — your one-page report "
            "is ready to build.") in md, \
        "Reports footer must follow the cleaned state"
    assert "You don't have any data loaded yet" not in md, \
        "the live check's footer string must not exist anywhere"
    print("overview Reports footer every state OK")


def test_overview_reports_help_button(_tmp_env):
    """Reports footer "?" button (user's call, 2026-11-10): a "?"
    icon button sits in the footer row beside the state copy in all
    three states, with a tooltip naming its destination, and it
    navigates by the same state logic as Add block — no data ->
    Preview, data -> Clean, cleaned -> Report. The card's footer is
    plain HTML, so the button lives in a columns row directly under
    the card, not inside the card's border."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice2")
    goto_nav(at, "Dashboard", "dcs_nav_dashboard")
    b = find_button(at, "", key="dashboard_reports_help")
    assert "Preview" in (b.help or ""), \
        "no-data tooltip must name Preview"
    b.click().run()
    assert not at.exception, f"exception on ? (no data): {at.exception}"
    assert any("Nothing loaded yet" in v for v in vals(at.markdown)), \
        "? with no data must land on the Preview empty state"
    load_sample(at)
    goto_section(at, "Dashboard")
    b = find_button(at, "", key="dashboard_reports_help")
    assert "Clean" in (b.help or ""), \
        "loaded tooltip must name Clean"
    b.click().run()
    assert not at.exception, f"exception on ? (loaded): {at.exception}"
    assert any(x.label == "Clean my data" for x in at.button), \
        "? with data loaded must land on the Clean tab"
    clean_sample(at)
    goto_section(at, "Dashboard")
    b = find_button(at, "", key="dashboard_reports_help")
    assert "Report" in (b.help or ""), \
        "cleaned tooltip must name Report"
    b.click().run()
    assert not at.exception, f"exception on ? (cleaned): {at.exception}"
    assert any("Download PDF report" in x.label
               for x in at.download_button), \
        "? with cleaned data must land on the Report tab"
    print("overview Reports footer ? button OK")

