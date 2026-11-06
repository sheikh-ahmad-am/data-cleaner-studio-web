"""Sidebar avatar tests (AppTest — no browser needed).

The sidebar profile block is a single green circle with the user's
initial; the email, Profile, and Log out live ONLY inside the avatar
menu (st.popover). Covers: the initial logic, the avatar CSS pinned
in both themes + the app.py literal, the old card/buttons being gone,
the menu contents and actions (local user: no email; a user dict with
an email: the caption shows it), and the initial following a saved
display name.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler jobs
file are pointed at a temp dir, so the real data/ folder is untouched.
Run ONLY this file:  .test-venv-avatar/bin/python -m pytest
tests/test_sidebar_avatar.py -q   (from project root)
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


def find_text_input(at, label):
    for t in at.text_input:
        if t.label == label:
            return t
    raise AssertionError(f"text input {label!r} missing")


# ---------------------------------------------------------------------------
# 1. Initial logic (pure unit tests)
# ---------------------------------------------------------------------------

def test_avatar_initial():
    assert ui_design.avatar_initial({"display_name": "Md Ahmad"}) == "M"
    assert ui_design.avatar_initial({"display_name": "md ahmad"}) == "M"
    assert ui_design.avatar_initial({"display_name": "  Alice A "}) == "A"
    assert ui_design.avatar_initial({"username": "alice1"}) == "A"
    assert ui_design.avatar_initial({"email": "hamza@example.com"}) == "H"
    assert ui_design.avatar_initial({}) == "?"
    assert ui_design.avatar_initial(None) == "?"
    assert ui_design.avatar_initial({"display_name": ""}) == "?"
    assert ui_design.avatar_initial(
        {"display_name": None, "username": "bob"}) == "B"


# ---------------------------------------------------------------------------
# 2. Avatar CSS pinned in both themes + the app.py literal
# ---------------------------------------------------------------------------

def _app_literal_css() -> str:
    """The DESIGN_SYSTEM_CSS block out of app.py, read as source text
    (importing app.py would boot Streamlit)."""
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r'DESIGN_SYSTEM_CSS = """<style>(.*?)</style>"""',
        source, re.DOTALL)
    assert match, "DESIGN_SYSTEM_CSS block missing from app.py"
    return match.group(1)


def test_avatar_css_pinned_both_themes():
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS)):
        assert 'button[data-testid="stPopoverButton"]' in css, \
            f"{name}: avatar trigger rule missing"
        rule = re.search(
            r'stPopoverButton"\] \{(.*?)\}', css, re.DOTALL)
        assert rule, f"{name}: avatar trigger rule body missing"
        body = rule.group(1)
        assert "border-radius: 50%" in body, \
            f"{name}: avatar must be a circle: {body!r}"
        assert "#117f50" in body, \
            f"{name}: avatar must be Supabase green: {body!r}"
        assert "color: #ffffff" in body, \
            f"{name}: avatar initial must be white: {body!r}"
        assert 'stPopoverButton"] svg' in css, \
            f"{name}: avatar trigger chevron must be hidden"
        assert 'div[data-testid="stPopoverBody"]' in css, \
            f"{name}: avatar menu body rule missing"
    assert "#ffffff" in ui_design.DESIGN_SYSTEM_CSS, \
        "light avatar menu body must be white"
    assert "#232625" in ui_design.DARK_CSS, \
        "dark avatar menu body must be the dark card colour"
    # The app.py literal is the verbatim light paste — the avatar
    # rules must be there too, or the login screen would ship the
    # old stylesheet.
    literal = _app_literal_css()
    assert 'button[data-testid="stPopoverButton"]' in literal, \
        "app.py literal missing the avatar trigger rule"
    assert 'div[data-testid="stPopoverBody"]' in literal, \
        "app.py literal missing the avatar menu body rule"
    # The stale sidebar .dcs-card override (written for the removed
    # profile card) must be gone from the dark stylesheet.
    assert 'stSidebar"] .dcs-card' not in ui_design.DARK_CSS, \
        "stale sidebar .dcs-card override must be gone from DARK_CSS"


# ---------------------------------------------------------------------------
# 3. Sidebar: avatar menu for a local user (no email), actions work
# ---------------------------------------------------------------------------

def test_sidebar_avatar_menu_local_user(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    signup(at, "alice1")

    # The old standalone buttons are gone from the sidebar.
    assert not any(b.key == "profile_btn" for b in at.sidebar.button), \
        "old standalone sidebar Profile button should be gone"
    assert not any(b.key == "logout_btn" for b in at.sidebar.button), \
        "old standalone sidebar Log out button should be gone"
    # The avatar menu (popover) holds the Profile + Log out actions.
    find_button(at, "Profile", key="avatar_profile_btn")
    find_button(at, "Log out", key="avatar_logout_btn")
    # The username/email must not appear as sidebar markdown (the
    # card is gone); local users have no email, so no email caption
    # shows anywhere in the sidebar either.
    assert not any("alice1" in v for v in vals(at.sidebar.markdown)), \
        "sidebar must not show the username as markdown (card gone)"
    assert not any("@" in v for v in vals(at.sidebar.markdown)), \
        "sidebar must not show the email as markdown (card gone)"
    assert not any("@" in c.value for c in at.sidebar.caption), \
        "sidebar must not show an email caption for a local user"

    # The menu's Profile action opens the Profile view (no data
    # needed for an account page — the empty-state branch handles it).
    find_button(at, "Profile", key="avatar_profile_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    assert any(s.value == "Account info" for s in at.subheader), \
        "avatar menu Profile should open the Profile view"

    # Back to the sidebar, the menu's Log out logs out.
    find_button(at, "Log out", key="avatar_logout_btn").click().run()
    assert not at.exception, f"exception on avatar logout: {at.exception}"
    assert any(b.label == "Log in" for b in at.button), \
        "avatar menu Log out should return to the login screen"
    assert not any(b.label == "Try the messy sample" for b in at.button), \
        "avatar menu Log out must log the user out"


# ---------------------------------------------------------------------------
# 4. Avatar menu with an email (cloud-style user): caption shows it
# ---------------------------------------------------------------------------

def test_sidebar_avatar_menu_with_email():
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "user = {'display_name': 'Md Ahmad', 'username': 'ahmad',\n"
        "        'email': 'ahmadfed966@gmail.com'}\n"
        "action = ui_design.render_sidebar_avatar(user=user)\n"
        "st.write(f'action={action}')\n")
    at.run()
    assert not at.exception, f"avatar render exception: {at.exception}"
    # The menu shows the email (and only the menu does — there is no
    # other sidebar element carrying it).
    assert any("ahmadfed966@gmail.com" in c.value
               for c in at.sidebar.caption), \
        "avatar menu should show the email as a caption"
    assert not any("ahmadfed966@gmail.com" in v
                   for v in vals(at.sidebar.markdown)), \
        "email must not appear as sidebar markdown (menu only)"
    find_button(at, "Profile", key="avatar_profile_btn")
    find_button(at, "Log out", key="avatar_logout_btn")

    # The menu actions report back through the helper's return value.
    find_button(at, "Profile", key="avatar_profile_btn").click().run()
    assert not at.exception, f"exception on menu Profile: {at.exception}"
    assert any("action=profile" in v for v in vals(at.markdown)), \
        "menu Profile should return 'profile'"
    find_button(at, "Log out", key="avatar_logout_btn").click().run()
    assert not at.exception, f"exception on menu Log out: {at.exception}"
    assert any("action=logout" in v for v in vals(at.markdown)), \
        "menu Log out should return 'logout'"


# ---------------------------------------------------------------------------
# 5. The initial follows a saved display name
# ---------------------------------------------------------------------------

def test_avatar_initial_follows_display_name(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    # Open the Profile view from the avatar menu (no data needed).
    find_button(at, "Profile", key="avatar_profile_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    find_text_input(at, "Display name").set_value("Bob B").run()
    find_button(at, "Save display name").click().run()
    assert not at.exception, f"exception saving display name: {at.exception}"
    user = at.session_state["current_user"]
    assert user.get("display_name") == "Bob B", \
        "saved display name should land in the session user"
    assert ui_design.avatar_initial(user) == "B", \
        "avatar initial should follow the saved display name"
