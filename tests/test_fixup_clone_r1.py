"""Clone Round 1 (shell) tests — the Supabase-dashboard shell rebuild
(2026-11-08).

The user ordered a clone of the Supabase dashboard INTERFACE into his
app, his version: only button/page names change to his pages; the
chrome is cloned, not the database product. Round 1 is the SHELL
only: the top bar, the 12-item rail with Supabase's 3-way bottom
control (Expanded / Collapsed / Expand on hover), the account menu
with its System/Dark/Light theme section, the Profile page rebuilt
to the Preferences pattern, and Quick Jump unchanged (20 actions).

This file pins what AppTest can pin:

  1. The rail mode: constants, derivation from the old bool (a
     deploy never collapses a user's pinned rail), set_rail_mode
     writing the mode + the derived bool together, bogus values
     falling back to "hover".
  2. rail_css variants (collapsed/expanded x light/dark x hover
     on/off): NO :has() and NO :is() anywhere (the ban holds in
     every variant); hover rules present in hover mode, ABSENT in
     strict "collapsed" mode (no section:hover, no 260px overlay,
     hiding unconditional — the bare section selector, no
     :not(:hover)).
  3. The behavior menu: the popover renders with a radio of the
     three modes; picking one sets dcs_rail_mode + the derived
     bool; the old direct toggle is gone (no render_rail_toggle,
     no dcs_rail_toggle button anywhere).
  4. The theme preference: System/Dark/Light in the account menu
     (the avatar radio owns the PREFERENCE; the sidebar selectbox
     and the Profile radio own the RESOLVED theme); "System"
     resolves to Light; set_theme writes theme + preference
     together; sync_theme_widgets resolves the pref before syncing.
  5. The Profile Appearance card's Sidebar behavior radio: same
     three options, same setting as the rail menu; picking it sets
     the mode, and the rail menu's radio agrees on the next run.
  6. Quick Jump: still 20 actions, in order, filterable.
  7. The full app: the mode seeds to "hover" after signup; the
     top bar still renders (brand + Upload pill + Help).

The flyout-toggle-stays-closed proof (a real mouse click + a 10s
hold, both themes) is NOT an AppTest test — it is the real-DOM
probe's job (probe27), because AppTest cannot hover or hold a
pointer. The AppTest proof here is the mechanism that makes it
true: the mode is an explicit choice, so picking "Collapsed" in
the flyout collapses and STAYS collapsed (no state for hover to
flip back).

Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_fixup_clone_r1.py -q   (from project root)
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import feat_quickjump  # noqa: E402
import test_fixup_round6 as _r6  # noqa: E402  (helpers + AppTest setup)
from test_fixup_round9 import _tmp_env  # noqa: E402,F401  (reused fixture)
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")


# ---------------------------------------------------------------------------
# 1. The rail mode: constants, derivation, set_rail_mode
# ---------------------------------------------------------------------------

def test_clone_r1_mode_constants():
    assert ui_design.RAIL_MODES == ("expanded", "collapsed", "hover")
    assert ui_design.RAIL_MODE_DEFAULT == "hover"
    assert ui_design.RAIL_MODE_LABELS == {
        "expanded": "Expanded", "collapsed": "Collapsed",
        "hover": "Expand on hover"}
    assert ui_design.RAIL_MODE_KEY == "dcs_rail_mode"
    assert ui_design.RAIL_BEHAVIOR_KEY == "dcs_rail_behavior"
    assert ui_design.RAIL_BEHAVIOR_KEY_CLASS == "st-key-dcs_rail_behavior"
    print("clone r1 mode constants OK")


def test_clone_r1_normalize_rail_mode():
    for good in ("expanded", "collapsed", "hover"):
        assert ui_design.normalize_rail_mode(good) == good
    for bad in (None, "", "bogus", "EXPANDED", 0, True):
        assert ui_design.normalize_rail_mode(bad) == "hover", \
            f"normalize_rail_mode({bad!r}) must fall back to hover"
    print("clone r1 normalize rail mode OK")


def test_clone_r1_rail_mode_falls_back_to_old_bool():
    """A session with NO mode stored (pre-clone, or a deploy over
    one) derives the mode from the old dcs_rail_collapsed bool, so
    a deploy never collapses a user's pinned rail: pinned-expanded
    stays expanded; anything else becomes hover (the current
    behavior + Supabase's account default)."""
    script = (
        "import streamlit as st\n"
        "import ui_design\n"
        "st.write(f\"mode={ui_design.rail_mode()} "
        "collapsed={ui_design.rail_collapsed()}\")\n")
    at = AppTest.from_string(script)
    at.run()
    assert "mode=hover" in "\n".join(_r6.vals(at.markdown)), \
        "no stored state must default to hover"
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert "mode=expanded" in "\n".join(_r6.vals(at.markdown)), \
        "an old pinned-expanded bool must derive expanded"
    at.session_state["dcs_rail_collapsed"] = True
    at.run()
    assert "mode=hover" in "\n".join(_r6.vals(at.markdown)), \
        "an old collapsed bool must derive hover, not strict collapsed"
    print("clone r1 rail mode falls back to old bool OK")


def test_clone_r1_set_rail_mode_writes_both_keys():
    """set_rail_mode writes the mode AND the derived bool together,
    so the two can never disagree."""
    at = AppTest.from_string("import streamlit as st\nimport ui_design\n")
    at.run()
    ui_design.set_rail_mode(at, "collapsed")
    assert at.session_state["dcs_rail_mode"] == "collapsed"
    assert at.session_state["dcs_rail_collapsed"] is True
    ui_design.set_rail_mode(at, "expanded")
    assert at.session_state["dcs_rail_mode"] == "expanded"
    assert at.session_state["dcs_rail_collapsed"] is False
    ui_design.set_rail_mode(at, "hover")
    assert at.session_state["dcs_rail_mode"] == "hover"
    assert at.session_state["dcs_rail_collapsed"] is True
    ui_design.set_rail_mode(at, "bogus")
    assert at.session_state["dcs_rail_mode"] == "hover", \
        "a bogus mode must fall back to hover"
    print("clone r1 set rail mode writes both keys OK")


# ---------------------------------------------------------------------------
# 2. rail_css variants: the :has()/:is() ban + hover vs strict
# ---------------------------------------------------------------------------

def test_clone_r1_no_has_or_is_in_any_rail_css_variant():
    """The :has()/:is() ban holds in EVERY rail_css variant —
    collapsed/expanded x light/dark x hover on/off (the ban test
    in test_fixup_round9 only covers the hover=True default)."""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            for hover in (True, False):
                css = ui_design.rail_css(collapsed, theme, hover=hover)
                assert ":has(" not in css, \
                    f"rail CSS ({collapsed=}, {theme}, {hover=}) must not contain :has()"
                assert ":is(" not in css, \
                    f"rail CSS ({collapsed=}, {theme}, {hover=}) must not contain :is()"
    print("clone r1 no :has()/:is() in any rail CSS variant OK")


def test_clone_r1_hover_mode_has_overlay_strict_mode_has_none():
    """Hover mode (the default) carries the overlay: section:hover
    grows the rail to 260px as an overlay. Strict "collapsed" mode
    carries NO hover-overlay rule at all — no section:hover, no
    260px width — so a pointer resting on the rail cannot
    re-expand anything, whatever it does."""
    for theme in ("light", "dark"):
        hover_css = ui_design.rail_css(True, theme, hover=True)
        assert 'section[data-testid="stSidebar"]:hover' in hover_css, \
            f"hover {theme} rail must carry the hover-expand rule"
        assert "width: 260px !important" in hover_css, \
            f"hover {theme} rail must carry the 260px overlay width"
        strict_css = ui_design.rail_css(True, theme, hover=False)
        assert 'section[data-testid="stSidebar"]:hover' not in strict_css, \
            f"strict {theme} rail must carry NO hover-expand rule"
        assert "260px" not in strict_css, \
            f"strict {theme} rail must carry NO 260px width at all"
    # Expanded carries no hover rules in either mode (unchanged).
    for hover in (True, False):
        assert ":hover" not in ui_design.rail_css(False, "light", hover=hover), \
            f"expanded rail must carry no hover rules (hover={hover})"
    print("clone r1 hover vs strict overlay OK")


def test_clone_r1_strict_hiding_is_unconditional():
    """In strict "collapsed" mode the label-hiding rules use the
    BARE section selector (no :not(:hover)): the labels never
    show, whatever the pointer does. In hover mode the same
    rules are gated on :not(:hover), so the overlay can reveal
    them."""
    for theme in ("light", "dark"):
        strict_css = ui_design.rail_css(True, theme, hover=False)
        assert ":not(:hover)" not in strict_css, \
            f"strict {theme} rail must not gate anything on :not(:hover)"
        # The nav-label hiding rule is present, with the bare
        # section selector.
        assert ('section[data-testid="stSidebar"] '
                'div[data-testid="stButton"] button '
                'span[style*="display: contents"]' in strict_css), \
            f"strict {theme} rail must hide the nav labels unconditionally"
        hover_css = ui_design.rail_css(True, theme, hover=True)
        assert ":not(:hover)" in hover_css, \
            f"hover {theme} rail must gate the hiding on :not(:hover)"
    print("clone r1 strict hiding is unconditional OK")


# ---------------------------------------------------------------------------
# 3. The behavior menu (replaces the direct toggle)
# ---------------------------------------------------------------------------

def test_clone_r1_behavior_menu_renders_and_drives_mode():
    """The popover renders with a radio of the three modes; picking
    one sets dcs_rail_mode + the derived bool; the old direct
    toggle is gone entirely."""
    assert not hasattr(ui_design, "render_rail_toggle"), \
        "the direct toggle must be gone in clone Round 1"
    script = (
        "import streamlit as st\n"
        "import ui_design\n"
        "ui_design.render_rail_behavior_menu()\n"
        "st.write(f\"mode={ui_design.rail_mode()} "
        "collapsed={ui_design.rail_collapsed()}\")\n")
    at = AppTest.from_string(script)
    at.run()
    assert not at.exception, f"rail menu exception: {at.exception}"
    at.get_by_key("dcs_rail_behavior")
    assert not any((b.key or "") == "dcs_rail_toggle" for b in at.button), \
        "no dcs_rail_toggle button may render any more"
    menu = next(r for r in at.radio if r.key == "dcs_rail_mode_radio")
    assert list(menu.options) == ["Expanded", "Collapsed",
                                  "Expand on hover"], \
        f"menu radio must offer the three modes, got {list(menu.options)!r}"
    assert menu.value == "hover"
    # Pick Collapsed from hover: collapses and STAYS collapsed
    # across a rerun (the old toggle's flyout failure — the click
    # flipped back to pinned-expanded; the menu's explicit choice
    # cannot flip).
    menu.set_value("collapsed").run()
    assert ui_design.rail_mode(at) == "collapsed"
    assert at.session_state.get("dcs_rail_collapsed") is True
    at.run()
    assert ui_design.rail_mode(at) == "collapsed", \
        "Collapsed must survive a rerun"
    # Pick Expanded, then hover, and back: every transition lands.
    at.radio(key="dcs_rail_mode_radio").set_value("expanded").run()
    assert ui_design.rail_mode(at) == "expanded"
    assert at.session_state.get("dcs_rail_collapsed") is False
    at.radio(key="dcs_rail_mode_radio").set_value("hover").run()
    assert ui_design.rail_mode(at) == "hover"
    assert at.session_state.get("dcs_rail_collapsed") is True
    print("clone r1 behavior menu renders and drives mode OK")


def test_clone_r1_menu_button_css():
    """The menu button's key-scoped rules: a 36px square, centred,
    icon-only when collapsed; left-aligned with its label when
    expanded; Streamlit's expand_more chevron hidden (it would
    crowd the 36px square). The rules carry the FULL main-area
    chain (probe27d): Streamlit's own popover-button rule (44px
    !important, (0,2,2)) beats the bare key-class rule (0,2,1) —
    the full chain is (0,5,4) and wins. The container is a layout
    wrapper (probe27b)."""
    btn = (ui_design.RAIL_BEHAVIOR_CHAIN
           + ' button[data-testid="stPopoverButton"]')
    collapsed = ui_design.rail_css(True, "light")
    for frag in (
            btn + ' {',
            "  width: 36px !important; height: 36px !important;",
            "  min-width: 36px !important;",
            "  justify-content: center !important; }",
            btn + ' > div > div[aria-hidden="true"] {\n  display: none !important; }'):
        assert frag in collapsed, \
            f"collapsed rail must carry the menu button rule {frag!r}"
    expanded = ui_design.rail_css(False, "light")
    assert (btn + ' {'
            '\n  width: 236px !important;'
            '\n  height: 36px !important; min-height: 36px !important;'
            '\n  justify-content: flex-start !important;'
            '\n  min-width: 236px !important; }' in expanded), \
        "expanded rail must left-align the menu button"
    print("clone r1 menu button CSS OK")


# ---------------------------------------------------------------------------
# 4. The theme preference (System / Dark / Light)
# ---------------------------------------------------------------------------

def test_clone_r1_theme_pref_constants_and_resolution():
    assert ui_design.THEME_PREFS == ("system", "dark", "light")
    assert ui_design.THEME_PREF_LABELS == {
        "system": "System", "dark": "Dark", "light": "Light"}
    assert ui_design.resolve_theme_pref("system") == "light", \
        "System with no OS reading must resolve to Light"
    assert ui_design.resolve_theme_pref("dark") == "dark"
    assert ui_design.resolve_theme_pref("light") == "light"
    assert ui_design.normalize_theme_pref("bogus") == "light"
    print("clone r1 theme pref constants and resolution OK")


def test_clone_r1_set_theme_writes_pref_and_theme():
    """set_theme writes the resolved theme AND the preference
    together, so the account menu's radio and the resolved theme
    can never disagree."""
    at = AppTest.from_string("import streamlit as st\nimport ui_design\n")
    at.run()
    ui_design.set_theme(at, "dark")
    assert at.session_state["dcs_theme"] == "dark"
    assert at.session_state[ui_design.THEME_PREF_KEY] == "dark"
    ui_design.set_theme(at, "light")
    assert at.session_state["dcs_theme"] == "light"
    assert at.session_state[ui_design.THEME_PREF_KEY] == "light"
    print("clone r1 set theme writes pref and theme OK")


def test_clone_r1_avatar_menu_theme_radio_has_system():
    """The account menu's Theme section is System / Dark / Light
    (Supabase's three rows). The radio owns the PREFERENCE; a
    System pick resolves the theme to Light when no OS reading
    exists (AppTest has none — the Round 3 cookie bridge supplies
    it in the real app)."""
    script = (
        "import streamlit as st\n"
        "import ui_design\n"
        "st.session_state.setdefault('dcs_theme', 'light')\n"
        "ui_design.sync_theme_widgets()\n"
        "ui_design.render_avatar_menu(user={'username': 'alice1'})\n"
        "st.write(f\"theme={st.session_state.get('dcs_theme')} \"\n"
        "         f\"pref={st.session_state.get('dcs_theme_pref')}\")\n")
    at = AppTest.from_string(script)
    at.run()
    assert not at.exception, f"avatar menu exception: {at.exception}"
    radio = next(r for r in at.radio
                 if r.key.startswith("avatar_theme_radio"))
    assert list(radio.options) == ["System", "Dark", "Light"], \
        f"avatar theme radio must offer System/Dark/Light, got {list(radio.options)!r}"
    assert radio.value == "light"
    # Pick Dark: theme dark, pref dark.
    radio.set_value("dark").run()
    assert at.session_state.get("dcs_theme") == "dark"
    assert at.session_state.get("dcs_theme_pref") == "dark"
    # Pick System: theme light, pref system.
    radio = next(r for r in at.radio
                 if r.key.startswith("avatar_theme_radio"))
    radio.set_value("system").run()
    assert at.session_state.get("dcs_theme") == "light", \
        "System with no OS reading must resolve the theme to Light"
    assert at.session_state.get("dcs_theme_pref") == "system"
    print("clone r1 avatar menu theme radio has System OK")


def test_clone_r1_sync_theme_widgets_resolves_pref():
    """sync_theme_widgets resolves the stored preference BEFORE
    syncing: a stored "system" pref lands the resolved theme on
    Light, the avatar radio on "system", and the sidebar/Profile
    controls on the resolved "light"."""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "st.session_state.setdefault('dcs_theme_pref', 'system')\n"
        "ui_design.sync_theme_widgets()\n")
    at.run()
    assert at.session_state.get("dcs_theme") == "light"
    assert at.session_state.get(
        ui_design.theme_radio_key("system")) == "system"
    assert at.session_state.get("dcs_theme_select") == "light"
    assert at.session_state.get("profile_theme_radio") == "light"
    at.session_state["dcs_theme_pref"] = "dark"
    at.run()
    assert at.session_state.get("dcs_theme") == "dark"
    assert at.session_state.get(
        ui_design.theme_radio_key("dark")) == "dark"
    assert at.session_state.get("dcs_theme_select") == "dark"
    print("clone r1 sync theme widgets resolves pref OK")


# ---------------------------------------------------------------------------
# 5. Profile Appearance card: Sidebar behavior radio
# ---------------------------------------------------------------------------

def _goto_profile(at):
    _r6.find_button(at, "Profile", key="dcs_nav_profile").click().run()
    assert not at.exception, f"exception going to Profile: {at.exception}"


def test_clone_r1_profile_sidebar_behavior_radio(_tmp_env):
    """The Profile Appearance card carries a Sidebar behavior radio
    with the same three options as the rail menu — one setting,
    two controls. Picking it sets the mode, and the rail menu's
    radio agrees on the next run."""
    at = AppTest.from_file(APP)
    at.run()
    _r6.signup(at, "alice1")
    _r6.expand_rail(at)
    _goto_profile(at)
    radio = next(r for r in at.radio
                 if r.key == "profile_sidebar_behavior_radio")
    assert list(radio.options) == ["Expanded", "Collapsed",
                                   "Expand on hover"], \
        f"Profile sidebar radio must offer the three modes, got {list(radio.options)!r}"
    assert radio.value == "expanded", \
        "the Profile radio must read the current mode (expanded)"
    # Pick Collapsed in Profile: the mode flips, the bool follows,
    # and the rail menu's radio agrees after the rerun.
    radio.set_value("collapsed").run()
    assert not at.exception, f"exception picking Collapsed in Profile: {at.exception}"
    assert ui_design.rail_mode(at) == "collapsed"
    assert at.session_state.get("dcs_rail_collapsed") is True
    assert at.radio(key="dcs_rail_mode_radio").value == "collapsed", \
        "the rail menu radio must agree with the Profile pick"
    # And back to hover from Profile.
    at.radio(key="profile_sidebar_behavior_radio").set_value("hover").run()
    assert ui_design.rail_mode(at) == "hover"
    assert at.radio(key="dcs_rail_mode_radio").value == "hover"
    print("clone r1 Profile sidebar behavior radio OK")


def test_clone_r1_profile_theme_radio_still_dark_light(_tmp_env):
    """The Profile Appearance card's Theme radio stays Dark/Light
    only — no System row (the app cannot follow the OS
    preference without a JS bridge). Picking Dark still applies
    at once and persists to the dashboard."""
    at = AppTest.from_file(APP)
    at.run()
    _r6.signup(at, "alice1")
    _r6.expand_rail(at)
    _goto_profile(at)
    radio = next(r for r in at.radio
                 if r.key == "profile_theme_radio")
    assert list(radio.options) == ["Light", "Dark"], \
        f"Profile theme radio must stay Light/Dark only, got {list(radio.options)!r}"
    radio.set_value("dark").run()
    assert at.session_state.get("dcs_theme") == "dark"
    assert at.session_state.get("dcs_theme_pref") == "dark", \
        "the Profile pick must also write the preference"
    print("clone r1 Profile theme radio still Dark/Light OK")


# ---------------------------------------------------------------------------
# 6. Quick Jump: still 20 actions
# ---------------------------------------------------------------------------

def test_clone_r1_quick_jump_still_twenty_actions():
    assert len(feat_quickjump.QUICK_ACTIONS) == 20, \
        f"Quick Jump must still have 20 actions, got {len(feat_quickjump.QUICK_ACTIONS)}"
    assert len(feat_quickjump.filter_actions("")) == 20, \
        "an empty Quick Jump query must return all 20 actions"
    labels = [a.get("label", a.get("title")) for a in feat_quickjump.QUICK_ACTIONS]
    assert labels[0] == "Upload & preview"
    assert "Profile" in labels and "Settings" in labels
    print("clone r1 Quick Jump still twenty actions OK")


# ---------------------------------------------------------------------------
# 7. Full app: mode seeds to hover; top bar still renders
# ---------------------------------------------------------------------------

def test_clone_r1_full_app_mode_seeds_to_hover(_tmp_env):
    """After signup the rail mode seeds to "hover" (the default —
    Supabase's account default) and the derived bool is True."""
    at = AppTest.from_file(APP)
    at.run()
    _r6.signup(at, "alice1")
    assert ui_design.rail_mode(at) == "hover", \
        f"the mode must seed to hover, got {ui_design.rail_mode(at)!r}"
    assert at.session_state.get("dcs_rail_collapsed") is True
    assert at.radio(key="dcs_rail_mode_radio").value == "hover"
    print("clone r1 full app mode seeds to hover OK")


def test_clone_r1_full_app_top_bar_renders(_tmp_env):
    """The top bar still renders: the brand + title/crumb on the
    left, the Upload pill, the Help icon, the avatar at the far
    right. (The avatar popover trigger itself is not exposed by
    AppTest — the real-DOM probe verifies it; the menu contents
    are pinned by the avatar-menu tests.)"""
    at = AppTest.from_file(APP)
    at.run()
    _r6.signup(at, "alice1")
    page = "\n".join(_r6.vals(at.markdown))
    assert '<div class="dcs-topbar-left">' in page, \
        "the top bar must render its left brand block"
    assert "Data Cleaner Studio" in page, \
        "the top bar must show the app title"
    _r6.find_button(at, "Upload", key="topbar_upload")
    # The Help button is icon-only (empty label, "?" icon) — match
    # by key, not by label.
    _r6.find_button(at, "", key="topbar_help")
    # The avatar menu renders (its Theme radio is in the tree).
    assert any(r.key.startswith("avatar_theme_radio") for r in at.radio), \
        "the avatar menu must render"
    print("clone r1 full app top bar renders OK")


if __name__ == "__main__":
    test_clone_r1_mode_constants()
    test_clone_r1_normalize_rail_mode()
    test_clone_r1_rail_mode_falls_back_to_old_bool()
    test_clone_r1_set_rail_mode_writes_both_keys()
    test_clone_r1_no_has_or_is_in_any_rail_css_variant()
    test_clone_r1_hover_mode_has_overlay_strict_mode_has_none()
    test_clone_r1_strict_hiding_is_unconditional()
    test_clone_r1_behavior_menu_renders_and_drives_mode()
    test_clone_r1_menu_button_css()
    test_clone_r1_theme_pref_constants_and_resolution()
    test_clone_r1_set_theme_writes_pref_and_theme()
    test_clone_r1_avatar_menu_theme_radio_has_system()
    test_clone_r1_sync_theme_widgets_resolves_pref()
    test_clone_r1_quick_jump_still_twenty_actions()
    print("ALL CLONE R1 TESTS PASSED (full-app tests need pytest)")
