"""Sidebar Theme selector persistence (fix round 57).

Live-check find, 2026-11-12 (fix round 56 passed 5/6): picking Light
via the sidebar Theme selector reverted to Dark within ~6s, and
picking Dark reverted to Light on navigation. The probe (probe57,
runs 1+2) + a server-side trace pinned TWO root causes:

1. The cookie read is stale. ``_cookie_get`` returns the
   session-start request cookies first, so ``_ensure_one_pref_cookie``
   believes the browser already holds the picked value and SKIPS the
   write (trace: ENSURE desired='dark' browser='dark' SKIP
   already-equal, while document.cookie still said 'light'), and the
   verify cycle spins on a read that can never see the new value
   (trace: GAVE_UP desired='light'). A Dark pick therefore never
   reached the browser cookie, so a reload reverted it.
2. The avatar menu radio's ``on_change`` fires with a STALE frontend
   value. The radio lives inside a closed popover, so its frontend
   value does not follow script-driven sync writes: after a sidebar
   pick flips the preference, the next user-triggered rerun reports
   the radio's old value and the callback overwrites the preference
   with it (trace: AVATAR_ON_THEME radio='light' pref_before='dark'
   on the nav-click rerun).

The fix: (1) ``_cookie_get`` prefers the controller snapshot (the
freshest read) over the session-start request cookies; (2) the
avatar radio's widget key is namespaced by the preference in effect
(``ui_design.theme_radio_key``), so when the preference changes via
another control the radio REMOUNTS under a new key instead of
keeping the stale frontend value — a fresh key has no stale state,
so the menu always shows the preference in effect and no stale
echo can fire. The sidebar selectbox needs no such key: it does
not render while the rail is collapsed, so it is either visible
(and follows sync writes) or freshly created on expand.

A first attempt at (2) — a "last reported value" tracker updated
inside each theme callback, ignoring a callback that re-reports
it — was tried and REJECTED by probe57 run3: the tracker only
updates when the callback fires, so it holds the value from the
last callback invocation (T0's Dark), while the real echo carries
the frontend's most recent report (S1's Light). The tracker cannot
observe frontend reports that agree with the script value, so it
cannot tell the echo from a genuine pick-back. The remount does
not need to tell them apart: the stale state is gone entirely.
Do not reintroduce a callback-side tracker for this.

What the harness pins here: the remount (test 2) — after a sidebar
pick the radio lives under the new preference's key showing the
new value, and no radio exists under the old key, so nothing stale
can echo; plus genuine picks still applying through both controls
(tests 3+4). What it CANNOT pin (stated honestly): the cookie-read
precedence — AppTest has no session-start request cookies
(``st.context`` is empty in the harness), so the stale-read
divergence cannot be staged; that half is pinned by the probe,
which reads document.cookie directly and asserts the S2 nav
outcome (the Dark pick survives navigation only if its cookie
write landed). The end-to-end no-revert behaviour itself is also
probe-pinned (the harness frontend never goes stale the way a
closed popover's does).

Run: .test-venv-brevo/bin/python -m pytest tests/test_theme_sidebar_r57.py -v
"""

from streamlit.testing.v1 import AppTest

import ui_design


def _app_with_both_controls():
    """A script with the two theme controls in the real app's order:
    the avatar menu's radio (top bar) then the sidebar selectbox."""
    script = (
        "import streamlit as st\n"
        "import ui_design\n"
        "st.session_state.setdefault('dcs_theme', 'light')\n"
        "st.session_state.setdefault('dcs_theme_pref', 'light')\n"
        "ui_design.sync_theme_widgets()\n"
        "ui_design.render_avatar_menu(user={'email': 't@example.com'})\n"
        "ui_design.render_theme_toggle()\n")
    at = AppTest.from_string(script)
    at.run()
    assert not at.exception, f"controls exception: {at.exception}"
    return at


def _theme_radio(at):
    """The avatar radio, whatever preference-namespace key it
    currently lives under (fix round 57 remounts it on a flip)."""
    return next((r for r in at.radio
                 if r.key.startswith("avatar_theme_radio")), None)


def test_r57_sidebar_pick_writes_same_preference():
    """The sidebar selectbox writes the SAME persisted preference as
    the avatar menu: the resolved theme, the preference and the
    user-picked flag all land on the pick."""
    script = (
        "import streamlit as st\n"
        "import ui_design\n"
        "st.session_state.setdefault('dcs_theme', 'dark')\n"
        "st.session_state.setdefault('dcs_theme_pref', 'dark')\n"
        "ui_design.sync_theme_widgets()\n"
        "ui_design.render_theme_toggle()\n")
    at = AppTest.from_string(script)
    at.run()
    assert not at.exception, f"toggle exception: {at.exception}"
    assert at.session_state.get("dcs_theme_select") == "dark"
    at.selectbox(key="dcs_theme_select").set_value("light").run()
    assert not at.exception, f"pick exception: {at.exception}"
    assert at.session_state.get("dcs_theme") == "light"
    assert at.session_state.get("dcs_theme_pref") == "light"
    assert at.session_state.get(
        ui_design.THEME_PREF_USER_SET_KEY) is True, \
        "a sidebar pick must mark the preference user-picked"
    assert at.session_state.get("dcs_theme_select") == "light"
    print("r57 sidebar pick writes same preference OK")


def test_r57_sidebar_pick_remounts_avatar_radio():
    """The live-check revert, pinned as a remount: a genuine Dark
    pick via the avatar radio, a flip to Light via the sidebar
    selectbox — the radio must then live under the Light key
    showing Light, with NO radio left under the Dark key, so no
    stale value exists to echo back on a later rerun. A further
    run keeps the preference Light, and a genuine radio pick
    through the new key still applies."""
    at = _app_with_both_controls()
    radio = _theme_radio(at)
    assert radio is not None, "avatar Theme radio missing"
    assert radio.key == ui_design.theme_radio_key("light")
    assert radio.value == "light"
    radio.set_value("dark").run()
    assert not at.exception, f"radio pick exception: {at.exception}"
    assert at.session_state.get("dcs_theme_pref") == "dark"
    radio = _theme_radio(at)
    assert radio is not None, "radio missing after Dark pick"
    assert radio.key == ui_design.theme_radio_key("dark")
    assert radio.value == "dark"
    at.selectbox(key="dcs_theme_select").set_value("light").run()
    assert not at.exception, f"selectbox pick exception: {at.exception}"
    assert at.session_state.get("dcs_theme_pref") == "light"
    assert at.session_state.get("dcs_theme") == "light"
    radio = _theme_radio(at)
    assert radio is not None, "radio missing after sidebar flip"
    assert radio.key == ui_design.theme_radio_key("light"), \
        "the radio must remount under the new preference's key"
    assert radio.value == "light", \
        "the remounted radio must show the preference in effect"
    assert not any(r.key == ui_design.theme_radio_key("dark")
                   for r in at.radio), \
        "no radio may remain under the old key to echo a stale value"
    at.run()
    assert at.session_state.get("dcs_theme_pref") == "light", \
        "a later run must not revert the sidebar pick"
    assert at.session_state.get("dcs_theme") == "light"
    _theme_radio(at).set_value("dark").run()
    assert at.session_state.get("dcs_theme_pref") == "dark", \
        "a genuine radio pick through the remounted key must apply"
    print("r57 sidebar pick remounts avatar radio OK")


def test_r57_avatar_radio_genuine_pick_still_applies():
    """The remount must never block a real pick: Dark, then Light,
    then System all apply through the avatar radio."""
    at = _app_with_both_controls()
    _theme_radio(at).set_value("dark").run()
    assert at.session_state.get("dcs_theme_pref") == "dark"
    assert at.session_state.get("dcs_theme") == "dark"
    _theme_radio(at).set_value("light").run()
    assert at.session_state.get("dcs_theme_pref") == "light"
    assert at.session_state.get("dcs_theme") == "light"
    _theme_radio(at).set_value("system").run()
    assert at.session_state.get("dcs_theme_pref") == "system"
    assert at.session_state.get("dcs_theme") == "light", \
        "System with no OS reading must resolve to Light"
    print("r57 avatar radio genuine pick still applies OK")


def test_r57_sidebar_genuine_pick_after_avatar_flip():
    """Dark via the avatar radio, Light via the sidebar, then Dark
    via the sidebar again — the re-pick applies."""
    at = _app_with_both_controls()
    _theme_radio(at).set_value("dark").run()
    assert at.session_state.get("dcs_theme_pref") == "dark"
    at.selectbox(key="dcs_theme_select").set_value("light").run()
    assert at.session_state.get("dcs_theme_pref") == "light"
    at.selectbox(key="dcs_theme_select").set_value("dark").run()
    assert not at.exception, f"re-pick exception: {at.exception}"
    assert at.session_state.get("dcs_theme_pref") == "dark", \
        "a genuine sidebar re-pick must apply"
    assert at.session_state.get("dcs_theme") == "dark"
    print("r57 sidebar genuine pick after avatar flip OK")
