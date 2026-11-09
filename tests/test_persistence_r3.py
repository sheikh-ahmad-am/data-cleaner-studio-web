"""Round 3 — persistence (tests).

The theme preference + sidebar behavior survive a full browser
reload in cookies (``dcs_theme_pref`` / ``dcs_rail_mode``), and a
"System" theme preference follows the OS through the
``dcs_os_dark`` cookie the zero-height JS bridge writes.

Covered here (pytest, no browser):
  1. resolve_theme_pref with the OS reading (system follows it,
     explicit dark/light ignore it, no reading -> Light).
  2. restore_pref_values validation (valid values pass, unknown
     values are dropped, never defaulted here).
  3. The OS bridge snippet (matchMedia, writes only on change,
     Secure on https, writes nothing sensitive).
  4. sync_theme_widgets resolves System from the OS reading in
     session state.
  5. The full app restores theme + rail from the cookie snapshot
     (injected as session-state "cookies", the way the cookie
     component registers it) before first paint — dark +
     collapsed, system + os_dark, and invalid values ignored.
  6. The full app defaults (light / hover) with no cookies.

The write path itself (ensure: write on mismatch, survive a
rerun, re-issue a lost write) is covered end-to-end in
tests/test_auth_cookie.py, which drives the real controls through
the full app with the realistic fake cookie controller — tests
8–10 there cover the theme write, the rail write past the rerun,
and System following the OS cookie. Two guards found while
writing those tests are covered by test 10 there: (a) the ensure
never lets a session default overwrite a saved cookie before the
restore has seeded (``_prefs_from_cookies``), and (b) the
resolved-theme controls (sidebar selectbox, Profile radio)
ignore a value change the sync itself produced, so a late seed
cannot overwrite the "System" preference with the resolved
theme (``THEME_SYNCED_KEY``).

Run: .test-venv-brevo/bin/python -m pytest tests/test_persistence_r3.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui_design
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


# ---------------------------------------------------------------------------
# 1. System resolution follows the OS reading
# ---------------------------------------------------------------------------

def test_r3_resolve_theme_pref_os_dark():
    """System follows the OS reading when one exists; without one
    it falls back to Light; explicit Dark/Light ignore the OS."""
    assert ui_design.resolve_theme_pref("system", os_dark=True) == "dark"
    assert ui_design.resolve_theme_pref("system", os_dark=False) == "light"
    assert ui_design.resolve_theme_pref("system") == "light", \
        "no OS reading (the default) must still fall back to Light"
    assert ui_design.resolve_theme_pref("dark", os_dark=False) == "dark"
    assert ui_design.resolve_theme_pref("dark", os_dark=True) == "dark"
    assert ui_design.resolve_theme_pref("light", os_dark=True) == "light"
    assert ui_design.resolve_theme_pref("bogus", os_dark=True) == "light"
    print("r3 resolve theme pref OS dark OK")


# ---------------------------------------------------------------------------
# 2. restore_pref_values validation
# ---------------------------------------------------------------------------

def test_r3_restore_pref_values():
    """Valid cookies pass through; unknown values are dropped,
    never defaulted — the caller keeps its own defaults."""
    full = ui_design.restore_pref_values({
        "dcs_theme_pref": "dark", "dcs_rail_mode": "collapsed",
        "dcs_os_dark": "1"})
    assert full == {"theme_pref": "dark", "rail_mode": "collapsed",
                    "os_dark": True}, full
    assert ui_design.restore_pref_values({
        "dcs_theme_pref": "system", "dcs_rail_mode": "expanded",
        "dcs_os_dark": "0"}) == {
            "theme_pref": "system", "rail_mode": "expanded",
            "os_dark": False}
    assert ui_design.restore_pref_values({
        "dcs_theme_pref": "bogus", "dcs_rail_mode": "sideways",
        "dcs_os_dark": "maybe"}) == {}, \
        "unknown values must be dropped, not defaulted"
    assert ui_design.restore_pref_values({}) == {}
    assert ui_design.restore_pref_values(None) == {}
    assert ui_design.restore_pref_values({
        "dcs_theme_pref": "dark"}) == {"theme_pref": "dark"}, \
        "a partial cookie set restores only what is valid"
    # The cookie component JSON-parses numeric-looking values, so
    # a snapshot read can arrive as int 1/0 instead of "1"/"0" —
    # the OS reading must accept both.
    assert ui_design.restore_pref_values({
        "dcs_theme_pref": "system", "dcs_os_dark": 1}) == {
            "theme_pref": "system", "os_dark": True}
    assert ui_design.restore_pref_values({
        "dcs_theme_pref": "system", "dcs_os_dark": 0}) == {
            "theme_pref": "system", "os_dark": False}
    print("r3 restore pref values OK")


# ---------------------------------------------------------------------------
# 3. The OS bridge snippet
# ---------------------------------------------------------------------------

def test_r3_os_bridge_snippet():
    """The snippet evaluates prefers-color-scheme, mirrors it into
    the dcs_os_dark cookie only when it changed, adds Secure on
    https, and touches nothing sensitive."""
    html = ui_design.OS_DARK_BRIDGE_HTML
    assert "prefers-color-scheme: dark" in html
    assert "matchMedia" in html
    assert "dcs_os_dark" in html
    assert "max-age=31536000" in html
    assert "SameSite=Lax" in html
    assert "Secure" in html
    assert "password" not in html.lower()
    assert "token" not in html.lower()
    assert "auth" not in html.lower()
    print("r3 OS bridge snippet OK")


# ---------------------------------------------------------------------------
# 4. sync_theme_widgets resolves System from the OS reading
# ---------------------------------------------------------------------------

def test_r3_sync_theme_widgets_uses_os_dark():
    """A stored "system" pref lands on Dark when the OS reading
    says dark, Light when it says light or is unknown — and the
    avatar radio keeps showing "system" either way."""
    for os_dark, expected in ((True, "dark"), (False, "light"),
                              (None, "light")):
        script = (
            "import streamlit as st\n"
            "import ui_design\n"
            "st.session_state.setdefault('dcs_theme_pref', 'system')\n")
        if os_dark is not None:
            script += (
                "st.session_state['_dcs_os_dark'] = "
                + repr(os_dark) + "\n")
        script += "ui_design.sync_theme_widgets()\n"
        at = AppTest.from_string(script)
        at.run()
        assert not at.exception, f"os_dark={os_dark}: {at.exception}"
        assert at.session_state.get("dcs_theme") == expected, \
            f"os_dark={os_dark} must resolve System to {expected}"
        assert at.session_state.get("avatar_theme_radio") == "system"
    print("r3 sync theme widgets uses OS dark OK")


# ---------------------------------------------------------------------------
# 5-6. Full-app restore from the cookie snapshot
# ---------------------------------------------------------------------------

def _app_with_cookie_snapshot(snapshot):
    """A full-app AppTest whose session state already holds the
    cookie component's snapshot ("cookies"), the way the real
    component registers it after it mounts. The app's restore
    reads it before first paint."""
    at = AppTest.from_file(APP)
    if snapshot is not None:
        at.session_state["cookies"] = dict(snapshot)
    # The full app is slow on a cold start (Supabase client init):
    # the 3s AppTest default times out intermittently on the first
    # full-app run in the file. 30s is generous, still bounded.
    at.run(timeout=30)
    assert not at.exception, f"app exception: {at.exception}"
    return at


def test_r3_app_restores_dark_and_collapsed():
    """Dark pref + Collapsed rail in the cookies restore before
    first paint: the resolved theme is dark and the mode is
    collapsed, on the login screen itself."""
    at = _app_with_cookie_snapshot({
        "dcs_theme_pref": "dark", "dcs_rail_mode": "collapsed",
        "dcs_os_dark": "0"})
    assert at.session_state.get("dcs_theme") == "dark"
    assert at.session_state.get("dcs_rail_mode") == "collapsed"
    assert at.session_state.get("dcs_rail_collapsed") is True
    print("r3 app restores dark and collapsed OK")


def test_r3_app_restores_system_from_os_cookie():
    """A "system" pref restores from the OS cookie: dark when the
    OS reading is dark, light when it is light — and Light when
    there is no OS reading at all."""
    dark = _app_with_cookie_snapshot({
        "dcs_theme_pref": "system", "dcs_os_dark": "1"})
    assert dark.session_state.get("dcs_theme") == "dark"
    assert dark.session_state.get("dcs_theme_pref") == "system"
    light = _app_with_cookie_snapshot({
        "dcs_theme_pref": "system", "dcs_os_dark": "0"})
    assert light.session_state.get("dcs_theme") == "light"
    unknown = _app_with_cookie_snapshot({"dcs_theme_pref": "system"})
    assert unknown.session_state.get("dcs_theme") == "light", \
        "System with no OS reading must fall back to Light"
    print("r3 app restores system from OS cookie OK")


def test_r3_app_restores_system_from_int_os_cookie():
    """The controller's snapshot JSON-parses numeric-looking
    cookies, so ``dcs_os_dark`` can arrive as int 1/0 rather than
    "1"/"0" — the app must still resolve System from it (the
    merge coerces scalars back to cookie strings). This is the
    live System path: the bridge writes "1", the refresh re-reads
    it, and the restore must see dark, not the stale request
    cookie."""
    dark = _app_with_cookie_snapshot({
        "dcs_theme_pref": "system", "dcs_os_dark": 1})
    assert dark.session_state.get("dcs_theme") == "dark", \
        "System with an int os_dark=1 snapshot must resolve Dark"
    light = _app_with_cookie_snapshot({
        "dcs_theme_pref": "system", "dcs_os_dark": 0})
    assert light.session_state.get("dcs_theme") == "light", \
        "System with an int os_dark=0 snapshot must resolve Light"
    print("r3 app restores system from int OS cookie OK")


def test_r3_app_restores_light_and_expanded():
    """Light pref + Expanded rail restore the same way, and the
    derived collapsed bool agrees with the mode."""
    at = _app_with_cookie_snapshot({
        "dcs_theme_pref": "light", "dcs_rail_mode": "expanded"})
    assert at.session_state.get("dcs_theme") == "light"
    assert at.session_state.get("dcs_rail_mode") == "expanded"
    assert at.session_state.get("dcs_rail_collapsed") is False
    print("r3 app restores light and expanded OK")


def test_r3_app_ignores_invalid_cookies():
    """Unknown cookie values are ignored: the app defaults to
    light / hover instead of crashing or trusting them."""
    at = _app_with_cookie_snapshot({
        "dcs_theme_pref": "bogus", "dcs_rail_mode": "sideways",
        "dcs_os_dark": "maybe"})
    assert at.session_state.get("dcs_theme") == "light"
    assert at.session_state.get("dcs_rail_mode") == "hover"
    print("r3 app ignores invalid cookies OK")


def test_r3_app_restores_when_snapshot_arrives_late():
    """When the cookie snapshot only becomes visible on a later run
    (the component mounts after the restore on run 1), the values
    still seed — they were defaulted, not chosen, so the late
    arrival overwrites the defaults. Once seeded, a further run
    does not revert them."""
    at = AppTest.from_file(APP)
    at.run(timeout=30)
    assert not at.exception, f"app exception: {at.exception}"
    assert at.session_state.get("dcs_theme") == "light", \
        "run 1 with no cookies visible must default to light"
    at.session_state["cookies"] = {
        "dcs_theme_pref": "dark", "dcs_rail_mode": "collapsed"}
    at.run(timeout=30)
    assert not at.exception, f"app exception: {at.exception}"
    assert at.session_state.get("dcs_theme") == "dark"
    assert at.session_state.get("dcs_rail_mode") == "collapsed"
    at.run(timeout=30)
    assert at.session_state.get("dcs_theme") == "dark", \
        "a seeded value must not revert on a later run"
    assert at.session_state.get("dcs_rail_mode") == "collapsed"
    print("r3 app restores when snapshot arrives late OK")


def test_r3_app_defaults_without_cookies():
    """No cookies at all: light theme, hover rail, no exception —
    a fresh install behaves exactly as before Round 3."""
    at = _app_with_cookie_snapshot(None)
    assert at.session_state.get("dcs_theme") == "light"
    assert at.session_state.get("dcs_rail_mode") == "hover"
    print("r3 app defaults without cookies OK")


# ---------------------------------------------------------------------------
# Standalone run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_r3_resolve_theme_pref_os_dark()
    test_r3_restore_pref_values()
    test_r3_os_bridge_snippet()
    test_r3_sync_theme_widgets_uses_os_dark()
    test_r3_app_restores_dark_and_collapsed()
    test_r3_app_restores_system_from_os_cookie()
    test_r3_app_restores_system_from_int_os_cookie()
    test_r3_app_restores_light_and_expanded()
    test_r3_app_ignores_invalid_cookies()
    test_r3_app_restores_when_snapshot_arrives_late()
    test_r3_app_defaults_without_cookies()
    print("ALL R3 PERSISTENCE TESTS PASSED")
