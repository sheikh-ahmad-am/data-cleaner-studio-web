"""Supabase sidebar rail + theme-sync tests (rail rebuild, 2026-11-07).

The user asked for Supabase's real sidebar — a collapsed icon-only
rail (~60px, the dashboard's default) that expands to a labelled
sidebar (~260px) with a collapse toggle, no section headers, a hover
wash + tooltip per icon — and for the whole interface to match the
page-by-page study. This file pins what AppTest can pin:

  1. rail_css: the 60px / 260px widths, the 6px content padding, the
     36px icon squares (12 icons + toggle fit a 573px viewport), the
     hover wash and active highlight, in both themes, with no
     cross-theme hex leaking in.
  2. sidebar_nav: collapsed = icon-only buttons (empty label, icon
     set, help = "Go to <label>", active disabled), expanded = icon +
     label rows; grouped input still flattens but emits NO section
     headers; clicking a row reports its key.
  3. render_rail_toggle: chevron_right / "Expand sidebar" collapsed,
     "Collapse sidebar" / chevron_left expanded.
  4. Theme sync (the screenshot bug: dark page, dropdown reading
     "Light"): the login-screen toggle flip writes both widget keys;
     the full-app paths — login-toggle flip then signup, selectbox
     flip then logout then re-login, and a direct dcs_theme write —
     all land with the sidebar selectbox reading the active theme.
     (The avatar-radio flip and the direct write are also pinned in
     isolation by test_supabase_rebuild.py::test_theme_sync_both_directions.)
  5. The full app: the rail starts collapsed after signup (icon-only
     nav + toggle, no selectbox / uploader / sample button / section
     headers, sample still reachable via the empty-state CTA); the
     toggle expands and collapses it; the state persists across
     reruns; an icon-only nav click navigates; the top-bar Upload
     pill expands the rail; the Profile caption renders.

Run ONLY this file:  .test-venv-rebuild/bin/python -m pytest
tests/test_supabase_rail.py -q   (from project root)
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import ai_settings  # noqa: E402
import auth  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"

# The 12 rail pages in order — same pages, same order as before the
# rebuild; only the chrome changed.
NAV_ORDER = ["preview", "clean", "join", "kpis", "dashboard", "compare",
             "report", "tools", "tutorial", "settings", "profile",
             "status"]
NAV_LABELS = {"preview": "Preview", "clean": "Clean", "join": "Join",
              "kpis": "KPIs", "dashboard": "Dashboard",
              "compare": "Compare", "report": "Report", "tools": "Tools",
              "tutorial": "How to use", "settings": "Settings",
              "profile": "Profile", "status": "Status"}


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern test_status.py uses."""
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    _settings = ai_settings.SETTINGS_PATH
    _backup = None
    if _settings.is_file():
        _backup = _settings.read_bytes()
        _settings.unlink()
    try:
        yield tmp_path
    finally:
        if _backup is not None:
            _settings.write_bytes(_backup)
        elif _settings.is_file():
            _settings.unlink()


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def find_button(at, label, key=None):
    for b in at.button:
        if b.label == label and (key is None or b.key == key):
            return b
    raise AssertionError(f"button {label!r} (key={key!r}) missing")


def find_button_by_key(at, key):
    for b in at.button:
        if b.key == key:
            return b
    raise AssertionError(f"button key={key!r} missing")


def find_text_input(at, label):
    for t in at.text_input:
        if t.label == label:
            return t
    raise AssertionError(f"text input {label!r} missing")


def signup(at, username, password="password123"):
    """Sign up (auto-login); the app must show the data screen after.

    Leaves the rail in its default collapsed state — the rail tests
    assert on that state explicitly."""
    at.radio[0].set_value("Sign up").run()
    find_text_input(at, "Username").set_value(username).run()
    find_text_input(at, "Password").set_value(password).run()
    find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    assert at.session_state.get("current_user", {}).get("username") == username, \
        "signup must log the user straight in"
    assert any(b.label == "Try the sample data" for b in at.button), \
        "the empty state must offer the sample CTA after signup"


def expand_rail(at):
    """Open the rail by its real toggle (the chevron), the way a user
    would — collapsed (icon-only) to expanded (icon + label). A no-op
    when the rail is already open: the state is session state and
    survives logout like the theme, so a re-login can land expanded."""
    toggle = find_button_by_key(at, "dcs_rail_toggle")
    if toggle.label == "Collapse sidebar":
        assert at.session_state.get("dcs_rail_collapsed") is False, \
            "an expanded toggle must mean an expanded rail"
        return
    assert toggle.label == "", "collapsed toggle must be icon-only"
    toggle.click().run()
    assert not at.exception, f"exception expanding rail: {at.exception}"
    assert at.session_state.get("dcs_rail_collapsed") is False, \
        "clicking the collapsed toggle must expand the rail"


def nav_buttons(at):
    """The rail's nav buttons, in render order (all dcs_nav_* keys)."""
    return [b for b in at.sidebar.button
            if (b.key or "").startswith("dcs_nav_")]


# ---------------------------------------------------------------------------
# 1. rail_css — widths, padding, icon squares, hover + active, both themes
# ---------------------------------------------------------------------------

def test_rail_css_collapsed_light():
    css = ui_design.rail_css(collapsed=True, theme="light")
    for width_rule in ("width: 60px !important",
                       "min-width: 60px !important",
                       "max-width: 60px !important",
                       "flex: 0 0 60px !important"):
        assert width_rule in css, f"collapsed rail CSS missing {width_rule!r}"
    assert "padding-left: 6px !important" in css, \
        "collapsed rail must shrink the sidebar content padding to 6px"
    assert "height: 36px !important" in css, \
        "collapsed rail buttons must be 36px squares (12 icons + " \
        "toggle fit a 573px viewport at 36px)"
    assert "border-radius: 8px !important" in css, \
        "collapsed rail buttons must be rounded squares, not pills"
    assert "background-color: #f8f8f8 !important" in css, \
        "collapsed hover wash must be the light hover token"
    assert "background-color: #f3f3f3 !important" in css, \
        "collapsed active highlight must be the light active token"
    assert "#030303" in css, "collapsed rail ink must be the light ink"
    for dark_hex in ("#1b1d1c", "#232625", "#2a2d2c", "#006338", "#4acd8b"):
        assert dark_hex not in css, \
            f"light rail CSS must not leak dark hex {dark_hex}"
    # 260px IS present in the collapsed sheet now — it is the HOVER
    # overlay width (hover expands the rail to 260px as an overlay).
    # The pinned base width must still be 60px.
    assert "width: 260px !important" in css, \
        "collapsed rail CSS must carry the 260px hover-overlay width"
    assert "section[data-testid=\"stSidebar\"]:hover" in css, \
        "collapsed rail CSS must carry the hover-expand rule"
    print("rail CSS collapsed light OK")


def test_rail_css_expanded_light():
    css = ui_design.rail_css(collapsed=False, theme="light")
    for width_rule in ("width: 260px !important",
                       "min-width: 260px !important",
                       "max-width: 260px !important",
                       "flex: 0 0 260px !important"):
        assert width_rule in css, f"expanded rail CSS missing {width_rule!r}"
    assert "width: 60px !important" not in css, \
        "expanded rail CSS must not set a 60px width"
    assert "min-width: 60px" not in css, \
        "expanded rail CSS must not set a 60px min-width"
    assert "height: 40px" not in css, \
        "expanded rail must keep the base sheet's row buttons, not squares"
    print("rail CSS expanded light OK")


def test_rail_css_collapsed_dark():
    css = ui_design.rail_css(collapsed=True, theme="dark")
    assert "width: 60px !important" in css, \
        "dark collapsed rail must still be 60px"
    assert "background-color: #262928 !important" in css, \
        "dark collapsed hover wash must be the dark hover token"
    assert "background-color: #343837 !important" in css, \
        "dark collapsed active highlight must be the dark active token"
    assert "#edefee" in css, "dark rail ink must be the dark ink"
    for light_hex in ("#fdfdfd", "#f3f3f3", "#117f50", "#f8f8f8"):
        assert light_hex not in css, \
            f"dark rail CSS must not leak light hex {light_hex}"
    print("rail CSS collapsed dark OK")


def test_rail_collapsed_default_true():
    """The rail starts collapsed — Supabase's own default, and the
    state the user asked for."""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "st.write(f'collapsed={ui_design.rail_collapsed()}')\n")
    at.run()
    assert not at.exception, f"rail_collapsed exception: {at.exception}"
    assert any("collapsed=True" in v for v in vals(at.markdown)), \
        "rail_collapsed must default to True on a fresh session"
    assert ui_design.RAIL_COLLAPSED_KEY == "dcs_rail_collapsed"
    assert ui_design.RAIL_WIDTH_COLLAPSED == "60px"
    assert ui_design.RAIL_WIDTH_EXPANDED == "260px"
    print("rail default collapsed OK")


# ---------------------------------------------------------------------------
# 2. sidebar_nav — icon-only collapsed, labelled expanded, no headers
# ---------------------------------------------------------------------------

def test_sidebar_nav_collapsed_icon_only():
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "clicked = ui_design.sidebar_nav([('preview', 'Preview'),\n"
        "                                ('clean', 'Clean'),\n"
        "                                ('join', 'Join')],\n"
        "                     active='preview', collapsed=True)\n"
        "st.write(f'clicked={clicked}')\n")
    at.run()
    assert not at.exception, f"sidebar_nav exception: {at.exception}"
    rows = [b for b in at.button if (b.key or "").startswith("dcs_nav_")]
    assert len(rows) == 3, f"collapsed nav must render 3 rows, got {len(rows)}"
    for b in rows:
        # Hover rail: the label IS in the DOM when collapsed (the rail
        # CSS hides it until hover) — the old empty-label behaviour
        # made the hover expand impossible.
        assert b.label in ("Preview", "Clean", "Join"), \
            f"collapsed nav row {b.key} must carry its label in the DOM, got {b.label!r}"
        assert b.proto.icon.startswith(":material/"), \
            f"collapsed nav row {b.key} must carry a Material icon"
        assert b.help, f"collapsed nav row {b.key} must carry its tooltip"
    preview = find_button_by_key(at, "dcs_nav_preview")
    clean = find_button_by_key(at, "dcs_nav_clean")
    assert preview.proto.icon == ui_design.icon_for("preview"), \
        "Preview icon must be the preview line icon"
    assert clean.proto.icon == ui_design.icon_for("clean"), \
        "Clean icon must be the clean line icon"
    assert preview.help == "Go to Preview", \
        "Preview tooltip must read 'Go to Preview'"
    assert clean.help == "Go to Clean", "Clean tooltip must read 'Go to Clean'"
    assert preview.disabled, "active nav row must be the disabled pill"
    assert not clean.disabled, "inactive nav row must stay clickable"
    assert not any("dcs-section-label" in v for v in vals(at.markdown)), \
        "the rail must not render section headers"
    clean.click().run()
    assert not at.exception, f"exception clicking nav: {at.exception}"
    assert any("clicked=clean" in v for v in vals(at.markdown)), \
        "clicking a collapsed nav icon must report its key"
    print("sidebar nav collapsed icon-only OK")


def test_sidebar_nav_expanded_labelled():
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "clicked = ui_design.sidebar_nav([('preview', 'Preview'),\n"
        "                                ('clean', 'Clean')],\n"
        "                     active='preview', collapsed=False)\n"
        "st.write(f'clicked={clicked}')\n")
    at.run()
    assert not at.exception, f"sidebar_nav exception: {at.exception}"
    preview = find_button(at, "Preview", key="dcs_nav_preview")
    clean = find_button(at, "Clean", key="dcs_nav_clean")
    assert preview.proto.icon.startswith(":material/"), \
        "expanded nav row must still carry its icon"
    assert preview.help == "Go to Preview", \
        "expanded nav row needs its 'Go to' tooltip"
    assert preview.disabled, "active nav row must be the disabled pill"
    assert not clean.disabled, "inactive nav row must stay clickable"
    assert not any("dcs-section-label" in v for v in vals(at.markdown)), \
        "the rail must not render section headers"
    clean.click().run()
    assert any("clicked=clean" in v for v in vals(at.markdown)), \
        "clicking an expanded nav row must report its key"
    print("sidebar nav expanded labelled OK")


def test_sidebar_nav_grouped_input_flattens_no_headers():
    """The old grouped call shape still works (the rebuild test uses
    it) — but the section headers it used to render are gone."""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "clicked = ui_design.sidebar_nav([('Data', [('preview', 'Preview'),\n"
        "                                  ('clean', 'Clean')])],\n"
        "                     active='preview')\n"
        "st.write(f'clicked={clicked}')\n")
    at.run()
    assert not at.exception, f"sidebar_nav exception: {at.exception}"
    assert find_button(at, "Preview", key="dcs_nav_preview").disabled
    assert not any("dcs-section-label" in v for v in vals(at.markdown)), \
        "grouped input must not bring the section headers back"
    assert not any(">Data<" in v for v in vals(at.markdown)), \
        "the 'Data' header text must not render"
    print("sidebar nav grouped input flattens OK")


def test_render_rail_toggle_both_states():
    script = (
        "import streamlit as st\n"
        "import ui_design\n"
        "clicked = ui_design.render_rail_toggle()\n"
        "st.write(f'clicked={clicked} "
        "collapsed={ui_design.rail_collapsed()}')\n")
    at = AppTest.from_string(script)
    at.run()
    assert not at.exception, f"rail toggle exception: {at.exception}"
    toggle = find_button_by_key(at, "dcs_rail_toggle")
    assert toggle.label == "", "collapsed toggle must be icon-only"
    assert toggle.proto.icon == ":material/chevron_right:", \
        "collapsed toggle must be the right chevron (click to expand)"
    assert toggle.help == "Expand sidebar"
    toggle.click().run()
    assert any("clicked=True" in v for v in vals(at.markdown)), \
        "clicking the toggle must report the click"
    # Expanded state: the toggle becomes a labelled row.
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert not at.exception, f"rail toggle exception: {at.exception}"
    toggle = find_button(at, "Collapse sidebar", key="dcs_rail_toggle")
    assert toggle.proto.icon == ":material/chevron_left:", \
        "expanded toggle must be the left chevron (click to collapse)"
    assert toggle.help == "Collapse sidebar"
    print("rail toggle both states OK")


# ---------------------------------------------------------------------------
# 3. Theme sync — the screenshot bug (dark page, dropdown reading Light)
# ---------------------------------------------------------------------------

def test_theme_sync_login_toggle_writes_both_widget_keys():
    """The login-screen toggle flip must write BOTH widget keys, so
    the sidebar selectbox and the avatar radio already agree with
    the new theme before either widget is created on the next run."""
    script = (
        "import streamlit as st\n"
        "import ui_design\n"
        "st.session_state.setdefault('dcs_theme', 'light')\n"
        "ui_design.render_login_theme_toggle()\n"
        "ui_design.render_theme_toggle()\n"
        "ui_design.render_avatar_menu(user={'username': 'alice1'})\n"
        "st.write(f\"theme={st.session_state.get('dcs_theme')} \"\n"
        "         f\"select={st.session_state.get('dcs_theme_select')} \"\n"
        "         f\"radio={st.session_state.get('avatar_theme_radio')}\")\n")
    at = AppTest.from_string(script)
    at.run()
    assert not at.exception, f"login toggle exception: {at.exception}"
    assert any("theme=light select=light radio=light" in v
               for v in vals(at.markdown)), \
        f"login screen must start light, got {vals(at.markdown)!r}"
    find_button(at, "Switch to dark theme",
                key="dcs_theme_login_toggle").click().run()
    assert not at.exception, f"exception flipping login toggle: {at.exception}"
    assert at.session_state.get("dcs_theme") == "dark", \
        "login toggle must flip dcs_theme to dark"
    assert at.session_state.get("dcs_theme_select") == "dark", \
        "login toggle must write the selectbox key too"
    assert at.session_state.get("avatar_theme_radio") == "dark", \
        "login toggle must write the radio key too"
    assert any("theme=dark select=dark radio=dark" in v
               for v in vals(at.markdown)), \
        f"both widgets must read dark after the flip, got {vals(at.markdown)!r}"
    print("theme sync login toggle OK")


def test_theme_sync_screenshot_state_full_app(_tmp_env):
    """The exact screenshot state: dcs_theme written to dark (the way
    a flip from another control lands), the page dark — the sidebar
    selectbox must read dark, never light."""
    at = AppTest.from_file(APP)
    at.session_state["dcs_theme"] = "dark"
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    signup(at, "alice1")
    expand_rail(at)
    sel = next(s for s in at.sidebar.selectbox
               if s.key == "dcs_theme_select")
    assert sel.value == "dark", \
        f"selectbox must read dark when the page is dark, got {sel.value!r}"
    # The dark rail stylesheet is the one injected (dark active token).
    page = "\n".join(vals(at.markdown))
    assert "#343837" in page, "the dark rail sheet must be injected"
    print("theme sync screenshot state full app OK")


def test_theme_sync_login_toggle_then_signup(_tmp_env):
    """Flip the theme on the LOGIN screen, then sign up: the sidebar
    selectbox must read the flipped theme on first sight."""
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    find_button(at, "Switch to dark theme",
                key="dcs_theme_login_toggle").click().run()
    assert not at.exception, f"exception flipping login toggle: {at.exception}"
    assert at.session_state.get("dcs_theme") == "dark", \
        "login toggle must flip the theme before signup"
    signup(at, "alice1")
    expand_rail(at)
    sel = next(s for s in at.sidebar.selectbox
               if s.key == "dcs_theme_select")
    assert sel.value == "dark", \
        f"selectbox must read dark after a login-screen flip, got {sel.value!r}"
    print("theme sync login toggle then signup OK")


def test_theme_sync_selectbox_flip_survives_logout_login(_tmp_env):
    """Flip the theme from the sidebar selectbox, log out from
    Profile, log back in: the selectbox must still read the flipped
    theme (dcs_theme survives logout; the widgets re-sync from it)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    expand_rail(at)
    sel = next(s for s in at.sidebar.selectbox
               if s.key == "dcs_theme_select")
    assert sel.value == "light", "selectbox must start light"
    sel.set_value("dark").run()
    assert not at.exception, f"exception flipping selectbox: {at.exception}"
    assert at.session_state.get("dcs_theme") == "dark", \
        "selectbox flip must write dcs_theme"
    # Log out via Profile's own Log out button.
    find_button(at, "Profile", key="dcs_nav_profile").click().run()
    assert not at.exception, f"exception going to Profile: {at.exception}"
    find_button(at, "Log out", key="profile_logout_btn").click().run()
    assert not at.exception, f"exception logging out: {at.exception}"
    assert any(b.label == "Log in" for b in at.button), \
        "logout must return to the login screen"
    # Log back in with the same credentials.
    find_text_input(at, "Username").set_value("alice1").run()
    find_text_input(at, "Password").set_value("password123").run()
    find_button(at, "Log in").click().run()
    assert not at.exception, f"exception logging back in: {at.exception}"
    assert at.session_state.get("dcs_theme") == "dark", \
        "the theme must survive logout"
    expand_rail(at)
    sel = next(s for s in at.sidebar.selectbox
               if s.key == "dcs_theme_select")
    assert sel.value == "dark", \
        f"selectbox must read dark after re-login, got {sel.value!r}"
    print("theme sync survives logout + login OK")


# ---------------------------------------------------------------------------
# 4. The full app rail — default collapsed, toggle, persistence, nav
# ---------------------------------------------------------------------------

def test_rail_default_collapsed_after_signup(_tmp_env):
    """After signup the rail is collapsed: 12 icon-only nav rows +
    the toggle, and NO theme selectbox / uploader / sample button /
    section headers in the sidebar. The sample stays reachable via
    the empty state's CTA in the main area."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    assert at.session_state.get("dcs_rail_collapsed") is True, \
        "the rail must start collapsed after signup"
    rows = nav_buttons(at)
    assert [b.key for b in rows] == [f"dcs_nav_{k}" for k in NAV_ORDER], \
        f"collapsed rail must list the 12 pages in order, got {[b.key for b in rows]!r}"
    for b in rows:
        # Hover rail: the label is in the DOM when collapsed (CSS hides
        # it until hover); the icon and tooltip are still the rail's
        # visible face.
        assert b.label == NAV_LABELS[b.key.removeprefix("dcs_nav_")], \
            f"collapsed nav row {b.key} must carry its label in the DOM, got {b.label!r}"
        assert b.proto.icon.startswith(":material/"), \
            f"collapsed nav row {b.key} must carry its icon"
        assert b.help == "Go to " + NAV_LABELS[b.key.removeprefix("dcs_nav_")], \
            f"collapsed nav row {b.key} tooltip must be its label"
    preview = find_button_by_key(at, "dcs_nav_preview")
    assert preview.disabled, "Preview (active) must be the disabled row"
    toggle = find_button_by_key(at, "dcs_rail_toggle")
    assert toggle.label == "" and toggle.help == "Expand sidebar", \
        "collapsed rail must show the expand toggle"
    # Round 7 reversal: the controls are NOT in the DOM when
    # collapsed (do-not-render — what is not in the DOM cannot
    # render as vertical one-letter text). The round-5 hover-rail
    # kept them mounted and CSS-hidden, which is what failed
    # live. They reappear when the rail is pinned open.
    assert not list(at.sidebar.selectbox), \
        "collapsed rail must not render the theme selectbox"
    assert not list(at.sidebar.file_uploader), \
        "collapsed rail must not render the file uploader"
    assert not any(b.label == "Try the messy sample" for b in at.button), \
        "collapsed rail must not render the sidebar sample button"
    assert not any('<div class="dcs-section-label"' in v
                   for v in vals(at.sidebar.markdown)), \
        "the rail must not render section headers"
    assert not any('<div class="dcs-section-label"' in v
                   for v in vals(at.markdown)), \
        "no section-header div may render anywhere"
    assert any(b.label == "Try the sample data" for b in at.button), \
        "the sample must stay reachable via the empty-state CTA"
    page = "\n".join(vals(at.markdown))
    assert "width: 60px !important" in page, \
        "the collapsed rail stylesheet must be injected"
    print("rail default collapsed full app OK")


def test_rail_toggle_expands_and_collapses(_tmp_env):
    """The toggle flips the rail both ways, and the expanded sidebar
    is the full sidebar: labelled nav rows, theme selectbox, status
    pill, uploader, sample button."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    expand_rail(at)
    rows = nav_buttons(at)
    assert [b.label for b in rows] == [NAV_LABELS[k] for k in NAV_ORDER], \
        "expanded rail must show the 12 labels in order"
    sel = next(s for s in at.sidebar.selectbox
               if s.key == "dcs_theme_select")
    assert sel.value == "light", "theme selectbox must read light"
    assert list(at.sidebar.file_uploader), \
        "expanded rail must render the file uploader"
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "expanded rail must render the sidebar sample button"
    assert any("Local mode" in v for v in vals(at.sidebar.markdown)), \
        "expanded rail must render the status pill"
    toggle = find_button(at, "Collapse sidebar", key="dcs_rail_toggle")
    assert toggle.proto.icon == ":material/chevron_left:"
    page = "\n".join(vals(at.markdown))
    assert "width: 260px !important" in page, \
        "the expanded rail stylesheet must be injected"
    # And back: the toggle collapses again.
    toggle.click().run()
    assert not at.exception, f"exception collapsing rail: {at.exception}"
    assert at.session_state.get("dcs_rail_collapsed") is True, \
        "clicking the expanded toggle must collapse the rail"
    # Round 7 reversal: collapsing removes the non-nav controls
    # from the DOM (do-not-render); only the nav labels + toggle
    # stay. They come back when the rail re-opens.
    assert [b.label for b in nav_buttons(at)] == \
        [NAV_LABELS[k] for k in NAV_ORDER], \
        "collapsed rail must keep its labels in the DOM"
    assert not list(at.sidebar.selectbox), \
        "collapsed rail must not render the theme selectbox"
    print("rail toggle expands and collapses OK")


def test_rail_persists_across_reruns(_tmp_env):
    """The rail state survives a rerun in both directions — it is
    session state, not a one-run flag."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    expand_rail(at)
    at.run()
    assert at.session_state.get("dcs_rail_collapsed") is False, \
        "expanded rail must stay expanded across a rerun"
    assert any(b.label == "Preview" for b in nav_buttons(at)), \
        "expanded rail must keep its labels across a rerun"
    find_button(at, "Collapse sidebar", key="dcs_rail_toggle").click().run()
    assert at.session_state.get("dcs_rail_collapsed") is True
    at.run()
    assert at.session_state.get("dcs_rail_collapsed") is True, \
        "collapsed rail must stay collapsed across a rerun"
    assert [b.label for b in nav_buttons(at)] == \
        [NAV_LABELS[k] for k in NAV_ORDER], \
        "collapsed rail must keep its labels in the DOM across a rerun"
    print("rail persists across reruns OK")


def test_rail_nav_click_collapsed_navigates(_tmp_env):
    """An icon-only nav click navigates: clicking the Clean icon
    (empty label, key only) lands on the Clean tab."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    assert at.session_state.get("dcs_rail_collapsed") is True
    clean = find_button_by_key(at, "dcs_nav_clean")
    assert clean.label == "Clean" and clean.help == "Go to Clean"
    clean.click().run()
    assert not at.exception, f"exception clicking Clean icon: {at.exception}"
    assert at.session_state.get("active_tab") == "Clean", \
        f"clicking the Clean icon must navigate, got active_tab={at.session_state.get('active_tab')!r}"
    print("rail nav click collapsed navigates OK")


def test_rail_upload_pill_expands(_tmp_env):
    """The top-bar Upload pill opens the rail as well as going to
    Preview, so the file uploader is visible when the user wants to
    upload (it lives in the expanded sidebar)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    assert at.session_state.get("dcs_rail_collapsed") is True
    find_button(at, "Upload", key="topbar_upload").click().run()
    assert not at.exception, f"exception clicking Upload pill: {at.exception}"
    assert at.session_state.get("dcs_rail_collapsed") is False, \
        "the Upload pill must expand the rail"
    assert list(at.sidebar.file_uploader), \
        "the uploader must be visible after the Upload pill"
    assert at.session_state.get("active_tab") == "Preview", \
        "the Upload pill must land on Preview"
    print("rail Upload pill expands OK")


def test_profile_caption_renders(_tmp_env):
    """Belt-and-braces for the study's §13.7 open item: the Profile
    caption must render on the Profile page."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    expand_rail(at)
    find_button(at, "Profile", key="dcs_nav_profile").click().run()
    assert not at.exception, f"exception going to Profile: {at.exception}"
    page = "\n".join(vals(at.markdown) + vals(at.caption))
    assert "Manage your account, sign-in and data." in page, \
        "the Profile caption must render"
    print("profile caption renders OK")


if __name__ == "__main__":
    test_rail_css_collapsed_light()
    test_rail_css_expanded_light()
    test_rail_css_collapsed_dark()
    test_rail_collapsed_default_true()
    test_sidebar_nav_collapsed_icon_only()
    test_sidebar_nav_expanded_labelled()
    test_sidebar_nav_grouped_input_flattens_no_headers()
    test_render_rail_toggle_both_states()
    test_theme_sync_login_toggle_writes_both_widget_keys()
    print("ALL SUPABASE RAIL TESTS PASSED (full-app tests need pytest)")
