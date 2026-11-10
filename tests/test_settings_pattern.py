"""Settings pattern tests (Project Settings clone round).

The Settings tab renders Supabase's Project Settings, mapped to
this app's own settings: a left sub-nav (Back to dashboard, group
labels General / Connections / Automation / Setup, anchor links to
each section) and the sections as bordered cards in the Profile
page's row shape — Account (read-only, no Save/Cancel), Your brand
(rows + Save brand / Cancel), AI keys (row + Save API keys /
Cancel), Scheduled refresh jobs (list + add form with Add / Cancel),
Shared dashboard links (read-only list), Still needs your details
(read-only info).

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_settings_pattern.py -q   (from project root)
"""

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# NOTE: app.py is NOT imported here — it executes top-level
# Streamlit code at import (set_page_config, session state), so it
# cannot be imported in a plain pytest; the pattern is covered
# through AppTest below, like the Dashboard/Preview/KPIs rounds.
import auth  # noqa: E402
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


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def all_text(at):
    """Every visible string on the page (markdown + captions + headers
    + info/success/warning/error callouts)."""
    out = []
    out.extend(vals(at.markdown))
    out.extend(vals(at.caption))
    out.extend(e.value for e in at.subheader)
    out.extend(e.value for e in at.header)
    out.extend(vals(at.info))
    out.extend(vals(at.success))
    out.extend(vals(at.warning))
    out.extend(vals(at.error))
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


def goto_settings(at):
    goto_nav(at, "Settings", key="dcs_nav_settings")
    assert "Your account, keys, brand, and automations." in all_text(at), \
        "Settings heading sub-line missing"


# ---------------------------------------------------------------------------
# 1. Sub-nav: groups, anchor links, Back button
# ---------------------------------------------------------------------------

def test_settings_subnav_groups_and_links(_tmp_env):
    """The left sub-nav groups the sections (General / Connections /
    Automation / Setup), each row an anchor link to its section
    heading, with a Back to dashboard button on top."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "set1")
    goto_settings(at)
    md = all_text(at)
    for group in ("General", "Connections", "Automation", "Setup"):
        assert group in md, f"sub-nav group {group!r} missing"
    for anchor in ("settings-account", "settings-brand", "settings-ai-keys",
                   "settings-shares", "settings-jobs", "settings-setup"):
        assert f"#{anchor}" in md, f"sub-nav anchor #{anchor} missing"
    for section in ("Account", "Your brand", "AI keys",
                    "Shared dashboard links", "Scheduled refresh jobs",
                    "Still needs your details"):
        assert section in md, f"section {section!r} missing"
    find_button(at, "← Back to dashboard", key="settings_back_dashboard")
    print("settings sub-nav OK: 4 groups, 6 anchors, Back button")


def test_settings_back_goes_to_dashboard(_tmp_env):
    """Back to dashboard lands on the Dashboard tab (its strips render
    with no data, so the tab is reachable empty)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "set2")
    goto_settings(at)
    find_button(at, "← Back to dashboard").click().run()
    assert not at.exception, f"exception going back: {at.exception}"
    assert any("Your data&#x27;s health, at a glance." in m.value
               for m in at.markdown), "Back should land on the Dashboard tab"
    assert "Your account, keys, brand, and automations." not in all_text(at), \
        "settings view should be gone after Back"
    print("settings Back OK: lands on Dashboard")


# ---------------------------------------------------------------------------
# 2. Sections render with their real content
# ---------------------------------------------------------------------------

def test_settings_sections_render(_tmp_env):
    """Every section renders its real content: Account (signed-in
    row + Open Profile + cloud setup), AI keys (status + inputs +
    Save/Cancel), brand rows (name/accent/logo + Save/Cancel), jobs
    (empty list + add form), shares (empty list), setup info."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "set3")
    goto_settings(at)
    md = all_text(at)
    # Account — read-only: signed-in row, backend, cloud setup line.
    assert "Signed in as" in md, "Account signed-in row missing"
    assert "Cloud setup:" in md, "Account cloud-setup line missing"
    find_button(at, "Open Profile", key="settings_open_profile")
    # AI keys.
    assert "Groq key: not set" in md, "AI keys status line missing"
    find_text_input(at, "Groq API key")
    find_text_input(at, "Gemini API key")
    find_button(at, "Save API keys", key="settings_keys_save")
    find_button(at, "Cancel", key="settings_keys_cancel")
    # Brand rows.
    find_text_input(at, "Brand name")
    assert any("Brand name" in v for v in vals(at.markdown)), \
        "brand name row label missing"
    find_button(at, "Save brand", key="brand_save")
    find_button(at, "Cancel", key="brand_cancel")
    # Jobs / shares / setup.
    assert "No scheduled jobs yet." in md, "jobs empty state missing"
    find_button(at, "Add scheduled job", key="sched_new_add")
    find_button(at, "Cancel", key="sched_new_cancel")
    assert "No share links yet" in md, "shares empty state missing"
    assert "Email reports (SMTP)" in md, "setup info missing"
    print("settings sections OK: all six render with real content")


# ---------------------------------------------------------------------------
# 3. Save/Cancel behaviour
# ---------------------------------------------------------------------------

def test_settings_keys_save_persists(_tmp_env, tmp_path):
    """Save API keys writes the typed key to the user's settings.json
    and flips the status line to 'set'."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "set4")
    goto_settings(at)
    find_text_input(at, "Groq API key").set_value("gsk_test_key_123").run()
    assert not at.exception, f"exception typing key: {at.exception}"
    find_button(at, "Save API keys", key="settings_keys_save").click().run()
    assert not at.exception, f"exception saving keys: {at.exception}"
    assert "API keys saved in your folder." in all_text(at), \
        "save confirmation missing"
    assert "Groq key: set" in all_text(at), \
        "status line should read 'set' after saving"
    assert find_text_input(at, "Groq API key").value in ("", None), \
        "Save must clear the typed key from the field (the status line " \
        "now carries the set state)"
    saved = list(tmp_path.rglob("settings.json"))
    assert saved, "settings.json was not written"
    assert json.loads(saved[0].read_text()).get("groq_api_key") == \
        "gsk_test_key_123", "saved key mismatch"
    print("settings keys Save OK: persisted + status flipped")


def test_settings_keys_cancel_discards(_tmp_env):
    """Cancel on the AI keys card drops what was typed: the inputs
    come back empty after the rerun."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "set5")
    goto_settings(at)
    find_text_input(at, "Groq API key").set_value("gsk_typed_not_saved").run()
    find_text_input(at, "Gemini API key").set_value("gem_typed_not_saved").run()
    find_button(at, "Cancel", key="settings_keys_cancel").click().run()
    assert not at.exception, f"exception on Cancel: {at.exception}"
    assert find_text_input(at, "Groq API key").value in ("", None), \
        "Cancel must clear the typed Groq key"
    assert find_text_input(at, "Gemini API key").value in ("", None), \
        "Cancel must clear the typed Gemini key"
    assert "Groq key: not set" in all_text(at), \
        "nothing was saved by Cancel"
    print("settings keys Cancel OK: typed keys discarded")


def test_settings_brand_cancel_discards(_tmp_env):
    """Cancel on the brand card reverts the name input to the saved
    brand (the default name, nothing saved yet)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "set6")
    goto_settings(at)
    find_text_input(at, "Brand name").set_value("Changed Name").run()
    find_button(at, "Cancel", key="brand_cancel").click().run()
    assert not at.exception, f"exception on brand Cancel: {at.exception}"
    assert find_text_input(at, "Brand name").value == "Data Cleaner Studio", \
        "Cancel must revert the brand name to the saved value"
    print("settings brand Cancel OK: name reverted to saved brand")


def test_settings_job_add_and_cancel(_tmp_env, tmp_path):
    """The jobs add form: Cancel clears it, Add creates the job in
    the registry and shows it in the list."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "set7")
    goto_settings(at)
    find_text_input(at, "Source (sheet link, or saved connection name)"
                    ).set_value("https://example.com/sheet").run()
    find_button(at, "Cancel", key="sched_new_cancel").click().run()
    assert not at.exception, f"exception on job Cancel: {at.exception}"
    assert find_text_input(
        at, "Source (sheet link, or saved connection name)").value == "", \
        "job Cancel must clear the source field"
    assert find_text_input(
        at, "Save refreshed data to (inside your folder)").value == \
        "uploads/refreshed.csv", "job Cancel must restore the target default"
    find_text_input(at, "Source (sheet link, or saved connection name)"
                    ).set_value("https://example.com/sheet").run()
    find_button(at, "Add scheduled job", key="sched_new_add").click().run()
    assert not at.exception, f"exception adding job: {at.exception}"
    assert "Job added." in all_text(at), "add confirmation missing"
    payload, err = scheduler.load_registry(scheduler.DEFAULT_JOBS_FILE)
    assert not err, f"registry unreadable: {err}"
    assert any(j.get("source") == "https://example.com/sheet"
               for j in payload.get("jobs", [])), "job missing from registry"
    assert "https://example.com/sheet" in all_text(at), \
        "added job should show in the list"
    print("settings jobs OK: Cancel clears, Add persists + lists")


# ---------------------------------------------------------------------------
# 4. Stylesheet: settings classes in both themes, no :has()
# ---------------------------------------------------------------------------

def test_settings_css_in_both_themes_no_has():
    """The Settings sub-nav/section classes exist in the light and
    dark stylesheets, and the new rules use no :has() selector
    (they do not take effect live — rounds 8–9)."""
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS)):
        for cls in ("dcs-settings-section", "dcs-settings-subnav-link",
                    "dcs-settings-subnav-active"):
            assert cls in css, f"{cls} missing from {name} stylesheet"
        block = css[css.find(".stApp .dcs-settings-section"):]
        block = block[:block.find("/* ---- avatar menu")]
        rules = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        assert ":has(" not in rules, \
            f":has() selector in {name} settings rules"
    print("settings CSS OK: classes in both themes, no :has()")
