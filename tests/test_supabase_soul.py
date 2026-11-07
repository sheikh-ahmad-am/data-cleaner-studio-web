"""Supabase-soul polish tests (AppTest where behaviour matters, CSS
pins where the stylesheet matters).

The app already looked like Supabase; this pass makes it feel like
it: hover + transitions on every interactive surface, a styled
sidebar collapse control, a real avatar account menu (email, Profile,
theme switch, Log out), tooltips on the nav rows, the status dot on
the sidebar pill, and hairline dividers between the Profile sections.
Covers: the new hover/transition/focus rules exist in BOTH themes
with the right tokens, the avatar menu theme switch flips the theme,
nav rows carry title tooltips, the status pill carries its dot, and
the Profile view is divided into sections. Presentation only — no
auth/session logic is re-tested here.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler jobs
file are pointed at a temp dir, so the real data/ folder is untouched.
Run ONLY this file:  .test-venv-soul/bin/python -m pytest
tests/test_supabase_soul.py -q   (from project root)
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

# Hover rules the soul pass adds, with the token each theme must use.
# (selector, light colour, dark colour)
_HOVER_RULES = (
    (".dcs-card:hover", "#d0d0d0", "#4a4d4c"),
    (".dcs-kpi:hover", "#d0d0d0", "#4a4d4c"),
    ('div[data-testid="stDownloadButton"] > button:hover',
     "#f8f8f8", "#2a2d2c"),
    ('div[data-testid="stExpander"]:hover', "#d0d0d0", "#4a4d4c"),
    ('div[data-testid="stPopoverBody"] .stButton > button'
     '[kind="secondary"]:hover', "#f8f8f8", "#262928"),
    ('div[data-testid="collapsedControl"]:hover', "#f8f8f8", "#262928"),
    ('div[data-baseweb="menu"] li[role="option"]:hover',
     "#f8f8f8", "#2a2d2c"),
    (".dcs-console-inside div:hover", "#030303", "#edefee"),
    (".dcs-menu-divider", "#e8e8e8", "#2e2e2e"),
    (".dcs-dot", "#117f50", "#4acd8b"),
    (".dcs-dot--warn", "#e69344", "#f3ba63"),
    (".dcs-dot--muted", "#696969", "#989a99"),
    ('div[data-testid="stFileUploaderDropzone"]:hover',
     "#d0d0d0", "#4a4d4c"),
    (".stApp input:hover", "#d0d0d0", "#4a4d4c"),
)

# Selectors that must ride the shared 0.2s transition (the "motion,
# honestly measured" block) in both themes.
_TRANSITION_SELECTORS = (
    ".dcs-card",
    ".dcs-kpi",
    ".dcs-console-inside div",
    'div[data-testid="stDownloadButton"] > button',
    'div[data-testid="stExpander"]',
    'div[data-testid="stFileUploaderDropzone"]',
    'div[data-testid="stPopoverBody"] .stButton > button',
    'div[data-testid="stPopover"] button[data-testid="stPopoverButton"]',
    'div[data-testid="collapsedControl"]',
    'section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"]',
    'section[data-testid="stSidebar"] button[kind="header"]',
    'div[data-baseweb="menu"] li[role="option"]',
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


def signup(at, username, password="password123"):
    """Sign up (auto-login) and return the new user's id."""
    at.radio[0].set_value("Sign up").run()
    for t in at.text_input:
        if t.label == "Username":
            t.set_value(username).run()
        elif t.label == "Password":
            t.set_value(password).run()
    find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "signup should log the user straight in"
    return at.session_state["current_user"]["id"]


def _transition_selectors(css: str) -> str:
    """The selector list of the shared transition rule, whitespace
    collapsed, so membership checks are exact."""
    m = re.search(r"motion, honestly measured.*?([\s\S]*?)\{\s*transition:",
                  css)
    assert m, "shared transition rule missing"
    return re.sub(r"\s+", " ", m.group(1))


# ---------------------------------------------------------------------------
# 1. Hover rules in both themes, with the right tokens
# ---------------------------------------------------------------------------

def test_soul_hover_rules_both_themes():
    """Every hover the soul pass adds exists in the light stylesheet
    with the light token and in the dark stylesheet with the dark
    twin — switching themes never drops a hover."""
    for theme, idx in (("light", 1), ("dark", 2)):
        css = ui_design.theme_css(theme)
        for selector, light, dark in _HOVER_RULES:
            assert selector in css, \
                f"{theme}: hover rule {selector} missing"
            colour = light if theme == "light" else dark
            # The colour must sit in the rule's own body, not just
            # anywhere in the file.
            body = re.search(re.escape(selector) + r"[^{]*\{([^}]*)\}",
                             css)
            assert body, f"{theme}: {selector} has no rule body"
            assert colour in body.group(1), \
                f"{theme}: {selector} must use {colour}, got {body.group(1)!r}"
    # Sidebar buttons are full-width rows in both themes.
    for theme in ("light", "dark"):
        css = ui_design.theme_css(theme)
        rule = ('section[data-testid="stSidebar"] '
                'div[data-testid="stButton"] > button[kind="secondary"]')
        assert rule in css, f"{theme}: sidebar row-button rule missing"
        body = re.search(re.escape(rule) + r"[^{]*\{([^}]*)\}", css)
        assert body and "width: 100%" in body.group(1), \
            f"{theme}: sidebar buttons must be full-width rows"
        assert "justify-content: flex-start" in body.group(1), \
            f"{theme}: sidebar buttons must be left-aligned rows"
    print("soul hover rules in both themes OK")


# ---------------------------------------------------------------------------
# 2. Transition + focus coverage for the new hover surfaces
# ---------------------------------------------------------------------------

def test_soul_transition_and_focus_both_themes():
    """The shared 0.2s cubic-bezier transition covers every new hover
    surface (so no hover snaps), and the focus ring reaches the avatar
    trigger and the sidebar collapse control."""
    for theme in ("light", "dark"):
        css = ui_design.theme_css(theme)
        selectors = _transition_selectors(css)
        for sel in _TRANSITION_SELECTORS:
            assert re.sub(r"\s+", " ", sel) in selectors, \
                f"{theme}: transition must cover {sel}"
        assert 'stPopoverButton"]:focus-visible' in css, \
            f"{theme}: focus ring must reach the avatar trigger"
        assert 'collapsedControl"] button:focus-visible' in css, \
            f"{theme}: focus ring must reach the collapse control"
        assert 'stSidebarCollapseButton"]:focus-visible' in css, \
            f"{theme}: focus ring must reach the sidebar collapse button"
    print("soul transition + focus in both themes OK")


# ---------------------------------------------------------------------------
# 3. Avatar menu: theme switch flips the theme, dividers separate
# ---------------------------------------------------------------------------

def test_avatar_menu_theme_switch():
    """The avatar menu carries the theme switch (same wording as the
    login-screen link); clicking it flips dcs_theme and the label
    flips with it. Profile and Log out are untouched."""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "user = {'display_name': 'Md Ahmad', 'username': 'ahmad',\n"
        "        'email': 'ahmadfed966@gmail.com'}\n"
        "action = ui_design.render_sidebar_avatar(user=user)\n"
        "st.write(f'action={action}')\n")
    at.run()
    assert not at.exception, f"avatar render exception: {at.exception}"
    find_button(at, "Profile", key="avatar_profile_btn")
    find_button(at, "Log out", key="avatar_logout_btn")
    # The menu is grouped by hairline dividers (email / actions / out).
    assert any("dcs-menu-divider" in v for v in vals(at.sidebar.markdown)), \
        "avatar menu must separate its groups with dividers"
    # Light by default: the switch offers dark.
    find_button(at, "Switch to dark theme", key="avatar_theme_btn")
    find_button(at, "Switch to dark theme",
                key="avatar_theme_btn").click().run()
    assert not at.exception, f"exception flipping theme: {at.exception}"
    assert at.session_state.get("dcs_theme") == "dark", \
        "avatar theme switch must flip dcs_theme to dark"
    find_button(at, "Switch to light theme", key="avatar_theme_btn")
    # And back again.
    find_button(at, "Switch to light theme",
                key="avatar_theme_btn").click().run()
    assert not at.exception, f"exception flipping theme back: {at.exception}"
    assert at.session_state.get("dcs_theme") == "light", \
        "avatar theme switch must flip dcs_theme back to light"
    # No paid-tier items: the menu never offers an upgrade.
    assert not any("Upgrade" in b.label for b in at.button), \
        "avatar menu must not offer an Upgrade to Pro"
    print("avatar menu theme switch OK")


# ---------------------------------------------------------------------------
# 4. Sidebar nav rows carry title tooltips
# ---------------------------------------------------------------------------

def test_sidebar_nav_tooltips():
    """Each nav row carries a title tooltip with its own label, and
    the active row keeps its pill."""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "ui_design.sidebar_nav([('Data', [('preview', 'Preview'),\n"
        "                                  ('clean', 'Clean')])],\n"
        "                     active='preview')\n")
    at.run()
    assert not at.exception, f"sidebar_nav exception: {at.exception}"
    html = "\n".join(vals(at.markdown))
    assert 'title="Preview"' in html, "Preview nav row needs its tooltip"
    assert 'title="Clean"' in html, "Clean nav row needs its tooltip"
    assert "dcs-nav-row dcs-nav-active" in html, \
        "active nav row must keep its pill"
    print("sidebar nav tooltips OK")


# ---------------------------------------------------------------------------
# 5. Status pill carries the dot
# ---------------------------------------------------------------------------

def test_status_pill_dot(_tmp_env):
    """The sidebar status pill is dot + pill (local mode: muted dot +
    'Local mode'), the login screen's 8px status dot, reused."""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import feat_status\n"
        "feat_status.render_status_pill(st)\n")
    at.run()
    assert not at.exception, f"status pill exception: {at.exception}"
    html = "\n".join(vals(at.markdown))
    assert "dcs-dot dcs-dot--muted" in html, \
        "local-mode status pill must carry the muted dot"
    assert "Local mode" in html, "local-mode pill text must stay"
    print("status pill dot OK")


# ---------------------------------------------------------------------------
# 6. Profile view: caption + dividers between sections
# ---------------------------------------------------------------------------

def test_profile_dividers_and_caption(_tmp_env):
    """The Profile view reads as a settings page: a one-line caption
    under the title and a hairline divider between every section,
    with the danger zone still separated and intact."""
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    signup(at, "alice1")
    find_button(at, "Profile", key="avatar_profile_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    assert any(c.value == "Your account, sign-in and data."
               for c in at.caption), \
        "Profile view needs its settings-page caption"
    assert len(at.divider) >= 5, \
        f"Profile view needs a divider between every section, got {len(at.divider)}"
    for section in ("Account info", "Change password", "Download my data",
                    "Storage usage", "Danger zone"):
        assert any(s.value == section for s in at.subheader), \
            f"Profile section {section!r} missing"
    find_button(at, "Delete my account", key="profile_delete_reveal")
    print("profile dividers + caption OK")
