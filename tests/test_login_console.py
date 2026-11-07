"""Login console layout tests (variant C — AppTest, no browser needed).

The login screen is the minimal console: header row (40px logo + title
left, theme switch as a text link right) over a narrow left-aligned
form column (~360px), no card, no panel, no tagline. The code screen
uses the same narrow column. Covers: the console CSS rules exist in
both themes (light/dark parity), console_head_html renders the logo +
title (and omits the img when the file is missing), the login screen
renders the console header + form with unchanged widget keys/labels,
the theme link flips the theme, and the code screen renders the
left-aligned heading + code input + Verify/Resend/Back with unchanged
keys. Presentation only — the auth/code flow itself is covered by
tests/test_brevo_email_code.py and is not re-tested here.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler jobs
file are pointed at a temp dir, so the real data/ folder is untouched.
Run ONLY this file:  .test-venv-loginfix/bin/python -m pytest
tests/test_login_console.py -q   (from project root)
"""

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
LOGO = PROJECT_ROOT / "assets" / "logo.svg"

_CONSOLE_SELECTORS = (
    ".dcs-console-head",
    ".dcs-console-h2",
    ".dcs-code-email",
    ".dcs-console-status",
    'input[maxlength="6"]',
    'button[kind="tertiary"]',
)


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_profile.py: the checkout's
    supabase_config.json holds real values, so local mode also needs
    the config path pointed at a nonexistent file in the temp dir.
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


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def test_console_css_in_both_themes():
    """Every console rule exists in the light stylesheet and has a dark
    twin (light/dark parity — switching themes never moves layout)."""
    for theme in ("light", "dark"):
        css = ui_design.theme_css(theme)
        for selector in _CONSOLE_SELECTORS:
            assert selector in css, f"{theme} CSS missing {selector}"
    light = ui_design.theme_css("light")
    dark = ui_design.theme_css("dark")
    assert "#117f50" in light and "#4acd8b" in dark, \
        "console link green must be the light/dark link token"
    print("console CSS in both themes OK")


def test_console_head_html():
    """The header row is the 40px logo + 22px title; a missing logo
    file renders the title alone (same guard as the old st.image)."""
    html = ui_design.console_head_html(LOGO)
    assert 'class="dcs-console-head"' in html
    assert "<h1>Data Cleaner Studio</h1>" in html
    assert "data:image/svg+xml;base64," in html, \
        "the logo must be inlined (Streamlit cannot put st.image in a row)"
    assert "width: 40px" in ui_design.theme_css("light") or \
        ".dcs-console-head img" in ui_design.theme_css("light")
    missing = ui_design.console_head_html(
        PROJECT_ROOT / "assets" / "no-such-logo.svg")
    assert "<img" not in missing, "a missing logo must not render an img"
    assert "<h1>Data Cleaner Studio</h1>" in missing
    print("console_head_html OK")


def test_login_screen_console_layout(_tmp_env):
    """AppTest: the login screen is the console — header row + narrow
    form, unchanged keys/labels, no tagline, theme link flips the theme."""
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    # Header row: logo + title as one markdown block, theme link right.
    assert any('class="dcs-console-head"' in v for v in vals(at.markdown)), \
        "login screen must render the console header row"
    assert any("Data Cleaner Studio" in v for v in vals(at.markdown)), \
        "console header must show the app name"
    # Theme switch is the text link (tertiary button, same key as before).
    toggle = find_button(at, "Switch to dark theme",
                         key="dcs_theme_login_toggle")
    toggle.click().run()
    assert not at.exception, f"exception flipping theme: {at.exception}"
    assert at.session_state.get("dcs_theme") == "dark", \
        "the theme link must flip the theme to dark"
    assert any(b.label == "Switch to light theme" for b in at.button), \
        "the theme link label must flip with the theme"
    # Form: unchanged keys/labels, in the narrow column.
    assert any(r.label == "Account" for r in at.radio), \
        "Account radio must still be on the login screen"
    assert any(t.label == "Username" for t in at.text_input), \
        "local-mode login must still have the Username field"
    assert any(t.label == "Password" for t in at.text_input), \
        "login must still have the Password field"
    find_button(at, "Log in", key="auth_login_btn")
    # Variant C drops the tagline (approved preview has none here).
    assert not any("Put in a messy file" in v
                   for v in vals(at.markdown)), \
        "variant C login screen must not show the tagline"
    print("login screen console layout OK")


def test_code_screen_console_layout(_tmp_env):
    """AppTest: with a pending code, the code screen renders in the
    same narrow column — left-aligned heading + code input +
    Verify/Resend/Back, unchanged keys, login form hidden."""
    at = AppTest.from_file(APP)
    at.session_state["pending_code"] = {
        "email": "a@b.com", "user": {}, "purpose": "login",
    }
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    assert any("Check your email" in v for v in vals(at.markdown)), \
        "code screen must show the 'Check your email' heading"
    assert any(t.label == "6-digit code" for t in at.text_input), \
        "code screen must have the 6-digit code input"
    find_button(at, "Verify code", key="email_code_verify_btn")
    find_button(at, "Resend code", key="email_code_resend_btn")
    find_button(at, "Back to login", key="email_code_cancel_btn")
    # The login form is replaced by the code screen, not shown with it.
    assert not any(b.label == "Log in" for b in at.button), \
        "code screen must hide the login form"
    assert not any(r.label == "Account" for r in at.radio), \
        "code screen must hide the Account radio"
    # The console header (logo + theme link) still shows above it.
    assert any('class="dcs-console-head"' in v for v in vals(at.markdown)), \
        "code screen must keep the console header row"
    print("code screen console layout OK")


if __name__ == "__main__":
    test_console_css_in_both_themes()
    test_console_head_html()
    print("login console tests OK (AppTest cases need pytest)")
