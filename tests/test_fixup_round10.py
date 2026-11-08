"""Round-10 fix tests (2026-11-08): four leftovers from the round-9
live check (2026-11-08 18:28-18:43 IST, after a reboot — the app
served the OLD build first, stale-module trap again).

1. NAV ROWS 224px -> ~233px live (223px locally). Round 9's 8px
   padding + 8px scrollbar pin predicted ~234px live, but the live
   check measured 224px: the scrollbar pin is IGNORED by this
   Chromium (probe22c: ::-webkit-scrollbar 8px leaves clientWidth
   at 239; the classic scrollbar takes a fixed 20px). The padding
   carries the width alone: 259 - 3 - 3 - 20 = 233px. Round 10
   cuts the content padding to 3px a side (expanded + hover
   overlay); the collapsed rail keeps its 6px rest padding.
2. LIGHT PROFILE DISABLED FIELDS FAINT live (darkest pixel
   #A0A0A0, 2.61:1, vs 'Member since' #030303 at 20.62:1).
   Dark is FIXED (13.67:1 live). Round 10 mirrors the dark fill
   pin into the LIGHT sheet (fill #030303, bg #f3f3f3) — global,
   stTextInput-scoped, and per-key. This overturns the round-6/8/9
   premise "light passes, untouched": those three tests are
   updated in this round to pin the light fill instead.
3. FLYOUT TOGGLE CLICK SWALLOWED. Clicking the toggle while the
   sidebar is only HOVER-EXPANDED did nothing live (the checker
   read the overlay staying open as "pops back to 260px").
   Root cause, proven in the real DOM (probe22g/h): the pointer
   rests on the toggle (a main-area descendant), so
   ``section:hover`` drops the moment the press completes — and
   with no width transition the pin snapped 260px -> 60px
   instantly, the button shrank out from under the pointer
   (236px -> 36px), the mouseup landed on main, and no ``click``
   ever fired (no rerun, no state change; a JS .click() on the
   same button flips it fine, and a real click at (30,970) —
   inside the rail's own 60px footprint — flips it fine). The
   fix is an ASYMMETRIC width transition on the toggle pin:
   the base (rest) rule carries a 250ms delay, so on hover-loss
   the container holds 260px through the press-release and the
   click fires; the hover rule carries no delay, so the flyout
   still opens instantly. No :has() anywhere (the ban stands).
4. PROFILE APPEARANCE RADIO "DOESN'T PERSIST". Choosing Dark
   from the Profile radio reverted to Light on returning to the
   dashboard, live; switching via the avatar menu persisted.
   It does NOT reproduce locally — probe22b (empty state) and
   probe22c (data loaded) both show dark persisting on
   Dashboard +3-4s, and the code is symmetric (all three controls
   write dcs_theme; the top-of-run sync re-syncs every widget
   key on the next run). The one real gap: the Profile callback
   did NOT rerun, so the new theme only applied on the NEXT run
   (the stylesheet is injected at the top of the run, before the
   callback fires) — the Profile page sat light for a full run
   after picking Dark, the window the live check plausibly read
   as a revert. Round 10 adds ``st.rerun()`` to the callback
   (the login toggle's pattern), so the theme applies at once.
   The sibling keys cannot be written in the callback (the
   avatar radio + selectbox were already created this run),
   but the rerun re-syncs them from dcs_theme immediately.

Also: the probe server must be RESTARTED after every code edit
before measuring, or it serves stale CSS (round 8 reproduced
this locally). The live check after the push is the only proof;
a stale module needs a reboot first.

Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_fixup_round10.py -q   (from project root)
"""

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_fixup_round6 as _r6  # noqa: E402  (helpers + AppTest setup)
import test_fixup_round9 as _r9  # noqa: E402  (tmp-env fixture)
from test_fixup_round9 import _tmp_env  # noqa: E402,F401  (reused fixture)
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")

MAIN_PIN_CHAIN = ('main[data-testid="stMain"] '
                  'div[data-testid="stVerticalBlock"] '
                  'div[data-testid="stElementContainer"]'
                  '.st-key-dcs_rail_toggle')
HOVER_PIN_SEL = ('section[data-testid="stSidebar"]:hover ~ div '
                 + MAIN_PIN_CHAIN)
GLIDE = "250ms cubic-bezier(0.4,0,0.2,1)"


def _collapsed(theme="light"):
    return ui_design.rail_css(True, theme)


def _find_sidebar_button(at, key):
    for b in at.sidebar.button:
        if b.key == key:
            return b
    raise AssertionError(f"sidebar button key={key!r} missing")


def _find_radio(at, key):
    for r in at.radio:
        if r.key == key:
            return r
    raise AssertionError(f"radio key={key!r} missing")


# ---------------------------------------------------------------------------
# 1. Light Profile fill pin
# ---------------------------------------------------------------------------

def test_r10_light_profile_fill_pin():
    """The LIGHT sheet pins the fill on the two Profile fields
    (global + stTextInput-scoped + per-key), mirroring the dark
    pin: fill #030303 on #f3f3f3. The per-key rule sits after the
    global rule so it wins. Dark keeps its pin (regression guard:
    fill #edefee on #2a2d2c)."""
    light = ui_design.DESIGN_SYSTEM_CSS
    assert ".stApp input:disabled" in light, \
        "light sheet must carry a disabled-input rule"
    m = re.search(r"\.stApp input:disabled[^{]*\{([^}]*)\}", light)
    assert m, "light disabled-input rule must have a body"
    assert "-webkit-text-fill-color: #030303 !important" in m.group(1), \
        f"light disabled inputs must pin the fill dark, got {m.group(1)!r}"
    assert "background-color: #f3f3f3 !important" in m.group(1), \
        f"light disabled inputs must sit on #f3f3f3, got {m.group(1)!r}"
    assert (".st-key-profile_primary_email input:disabled," in light
            and ".st-key-profile_username input:disabled {" in light), \
        "light sheet must pin the fill on the two Profile fields by key"
    key_at = light.find(".st-key-profile_primary_email input:disabled,")
    global_at = light.find(".stApp input:disabled, .stApp textarea:disabled")
    assert 0 < global_at < key_at, \
        "the light per-key fill pin must sit after the global disabled rule"
    dark = ui_design.DARK_CSS
    assert "-webkit-text-fill-color: #edefee !important" in dark, \
        "dark sheet must keep its fill pin"
    print("round 10 light Profile fill pin OK")


# ---------------------------------------------------------------------------
# 2. Nav rows 233px (3px padding)
# ---------------------------------------------------------------------------

def test_r10_nav_rows_233px():
    """The nav rows are 233px: the content padding is 3px a side
    (expanded + hover overlay), because the scrollbar pin is
    ignored by this Chromium and the padding carries the width
    alone (259 - 3 - 3 - 20 = 233). The collapsed rail keeps its
    6px rest padding; the scrollbar pin stays (harmless where
    honoured)."""
    for theme in ("light", "dark"):
        expanded = ui_design.rail_css(False, theme)
        assert ('section[data-testid="stSidebar"] '
                'div[data-testid="stSidebarContent"] {\n'
                '  padding-left: 3px !important; '
                'padding-right: 3px !important; }' in expanded), \
            f"expanded {theme} rail must pad the content 3px a side"
        assert ("  padding-left: 8px !important; "
                "padding-right: 8px !important;" not in expanded), \
            f"expanded {theme} rail must not keep the round-9 8px padding"
        collapsed = _collapsed(theme)
        assert ("  padding-left: 3px !important; "
                "padding-right: 3px !important;" in collapsed), \
            f"collapsed {theme} rail must pad the hover overlay 3px a side"
        assert ('section[data-testid="stSidebar"] '
                'div[data-testid="stSidebarContent"] {\n'
                '  padding-left: 6px !important; '
                'padding-right: 6px !important;' in collapsed), \
            f"collapsed {theme} rail must keep its 6px rest padding"
    print("round 10 nav rows 233px OK")


# ---------------------------------------------------------------------------
# 3. Flyout toggle click — delayed-shrink pin transition
# ---------------------------------------------------------------------------

def test_r10_toggle_pin_delayed_shrink():
    """The toggle pin's width TRANSITIONS, asymmetrically: the
    base (rest) rule carries a 250ms delay, so on hover-loss the
    container holds 260px through a press-release and the click
    fires; the hover rule carries no delay, so the flyout still
    opens instantly. The transition governs the change via the
    AFTER-change style, so the delay applies to the shrink only.
    Both themes, collapsed state (the hover pin only exists
    there)."""
    for theme in ("light", "dark"):
        collapsed = _collapsed(theme)
        base_at = collapsed.find(MAIN_PIN_CHAIN + " {")
        assert base_at > 0, \
            f"collapsed {theme} rail must carry the base toggle pin"
        base_rule = collapsed[base_at:base_at + 600]
        assert (f"transition: width {GLIDE} 250ms !important;"
                in base_rule), \
            f"base toggle pin ({theme}) must delay the shrink 250ms, " \
            f"got {base_rule!r}"
        hover_at = collapsed.find(HOVER_PIN_SEL + " {")
        assert hover_at > 0, \
            f"collapsed {theme} rail must carry the hover toggle pin"
        hover_rule = collapsed[hover_at:hover_at + 600]
        assert (f"transition: width {GLIDE} 0ms !important;"
                in hover_rule), \
            f"hover toggle pin ({theme}) must expand with no delay, " \
            f"got {hover_rule!r}"
        # Second half (probe23): the container ALSO holds 260px
        # while the pointer is on IT — a :hover on the container
        # itself, no :has(). section:hover can drop the moment
        # the pointer arrives on the toggle (the toggle is a
        # main-area descendant), closing the flyout before the
        # click lands; the container :hover holds the width
        # regardless, so the button stays under the pointer.
        self_at = collapsed.find(MAIN_PIN_CHAIN + ":hover {")
        assert self_at > 0, \
            f"collapsed {theme} rail must carry the toggle self-hover rule"
        self_rule = collapsed[self_at:self_at + 500]
        assert "position: fixed !important;" in self_rule, \
            f"toggle self-hover ({theme}) must restate the fixed pin, " \
            f"got {self_rule!r}"
        assert "width: 260px !important;" in self_rule, \
            f"toggle self-hover ({theme}) must hold 260px, got {self_rule!r}"
        assert (f"transition: width {GLIDE} 0ms !important;"
                in self_rule), \
            f"toggle self-hover ({theme}) must expand with no delay"
    print("round 10 toggle pin delayed shrink OK")


def test_r10_no_has_in_rail_css():
    """The :has() ban still holds in the rail stylesheet, in
    either state or theme — the round-10 pin transition uses no
    :has() (the fix is a transition delay, not a parent selector)."""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            css = ui_design.rail_css(collapsed, theme)
            assert ":has(" not in css, \
                f"rail CSS ({collapsed=}, {theme}) must not contain :has()"
            assert ":is(" not in css, \
                f"rail CSS ({collapsed=}, {theme}) must not contain :is()"
    print("round 10 no :has() in rail CSS OK")


def test_r10_collapse_survives_a_rerun(_tmp_env):
    """The collapse still survives a rerun after the pin-transition
    change (round-9 behaviour, re-pinned: the toggle click flips
    the session state once and it holds)."""
    at = AppTest.from_file(APP)
    at.run()
    _r6.signup(at, "alice10")
    assert at.session_state.get("dcs_rail_collapsed") is True
    _r6.expand_rail(at)
    assert at.session_state.get("dcs_rail_collapsed") is False
    _r6.find_button_by_key(at, "dcs_rail_toggle").click().run()
    assert at.session_state.get("dcs_rail_collapsed") is True
    at.run()
    assert at.session_state.get("dcs_rail_collapsed") is True, \
        "the collapse must survive a further rerun with no interaction"
    print("round 10 collapse survives a rerun OK")


# ---------------------------------------------------------------------------
# 4. Profile Appearance radio persists (rerun in the callback)
# ---------------------------------------------------------------------------

def test_r10_profile_radio_reruns():
    """The Profile theme callback writes dcs_theme AND reruns at
    once (the login toggle's pattern), so the new theme applies
    on the same interaction instead of lagging one run behind.
    The sibling keys are deliberately NOT written here — the
    avatar radio + selectbox were already created this run, so
    writing them would raise; the rerun re-syncs them from
    dcs_theme at the top of the next run."""
    src = (PROJECT_ROOT / "feat_profile.py").read_text()
    start = src.find("def _on_profile_theme():")
    assert start > 0, "feat_profile must define _on_profile_theme"
    body = src[start:src.find("st.radio(\"Theme\"", start)]
    assert 'st.session_state["dcs_theme"] = _new' in body, \
        "the Profile theme callback must write dcs_theme"
    assert "st.rerun()" in body, \
        "the Profile theme callback must rerun so the theme applies at once"
    print("round 10 Profile radio reruns OK")


def test_r10_profile_radio_persists_theme(_tmp_env):
    """End to end in AppTest: go to Profile, pick Dark on the
    Appearance radio, and dcs_theme must read dark — and STILL
    read dark after navigating to Dashboard and back to Profile.
    (The local probe could not reproduce the live revert; this
    pins the fixed path: callback + immediate rerun.)"""
    at = AppTest.from_file(APP)
    at.run()
    _r6.signup(at, "alice10")
    assert at.session_state.get("dcs_theme") == "light"
    _find_sidebar_button(at, "dcs_nav_profile").click().run()
    assert not at.exception, f"exception on Profile nav: {at.exception}"
    _find_radio(at, "profile_theme_radio").set_value("dark").run()
    assert not at.exception, \
        f"exception on Profile radio: {at.exception}"
    assert at.session_state.get("dcs_theme") == "dark", \
        "picking Dark on the Profile radio must set dcs_theme to dark"
    _find_sidebar_button(at, "dcs_nav_dashboard").click().run()
    assert at.session_state.get("dcs_theme") == "dark", \
        "dcs_theme must still be dark after returning to the dashboard"
    at.run()
    assert at.session_state.get("dcs_theme") == "dark", \
        "dcs_theme must survive a further rerun with no interaction"
    _find_sidebar_button(at, "dcs_nav_profile").click().run()
    assert _find_radio(at, "profile_theme_radio").value == "dark", \
        "the Profile radio must still show Dark when returning to Profile"
    print("round 10 Profile radio persists theme OK")
