"""Round-9 fix tests (2026-11-08): four live failures that survived
round 8 (verified live 2026-11-08 16:40-16:51 IST, 1920x1000, both
themes, no reboot needed — the new build WAS live, so these are NOT
a stale build). The local Supabase-mode probe (probe19/20, real
supabase_config.json, real login, Playwright + headless Chromium)
could NOT reproduce items 1, 2 and 4 — they pass locally, so the
live check is the final proof for them; item 3 reproduced (nav
rows 199px locally, 219px live, both short of ~233px).

1. PROFILE DARK DISABLED FIELDS STILL DIM live (max luminance 44
   on a ~29-37 field, ~1.3:1, vs "Member since" at 239). The global
   fill pin (round 8) already paints bright locally — probe19/20:
   computed fill rgb(237,239,238) on rgb(42,45,44), opacity 1,
   and the screenshot pixels max 238 — in BOTH themes, empty and
   data-loaded. The live cause does not reproduce locally, so
   round 9 adds a per-key fill pin (later in the sheet, naming
   the exact Profile widgets) as belt-and-braces.
2. COLLAPSE STICKS + TOGGLE BAR: after a collapse click with the
   pointer on the toggle, the sidebar sat at ~260px for 10s live
   (the hover overlay re-expanded because the pointer rests on
   the toggle), and the toggle bar was still full-width (text
   centred x~965) in both themes. The round-8 :has() gate worked
   locally but never took effect live (round 6 already proved
   :has() never takes effect live). Round 9 DELETES the gate and
   replaces it with a STRUCTURAL mechanism: the toggle renders
   in the MAIN area (app.py, one render), outside the sidebar
   section entirely, so ``section:hover`` can never fire from
   hovering the toggle — no :has() anywhere in rail_css. The pin
   chain targets the main area, and the hover pin (toggle widens
   to 260px when the rail overlay is open) is a sibling selector
   from the section to main[stMain]. The live check is the final
   proof that the collapse sticks and the bar sits in the column.
3. NAV ROWS 219px -> ~233px live (199px locally): the rows were
   14px short of the ~233px expectation. Root cause: the sidebar
   content's default padding left a 30px inset locally. The fix
   is an explicit 12px side padding on the content (expanded and
   hover-expanded), so the rows are 236px wide at x=12 — matching
   the toggle exactly (236px at x=12) and within 3px of ~233px.
4. TOOLTIP LINGER (cosmetic): "Expand sidebar" / nav tooltips
   stayed visible long after the pointer moved away, reappearing
   after reruns. Locally the tooltip is gone within 2s (probe19),
   so it does not reproduce — and a CSS-only fix would need
   :has() (the tooltip lives in a portal outside the section) or
   JS (not available in Streamlit markdown), so round 9 leaves
   it out deliberately. No test: nothing cheap to pin.

Also: the probe server must be RESTARTED after every code edit
before measuring, or it serves stale CSS (round 8 reproduced
this locally). The live check after the push is the only proof;
a stale module needs a reboot first.

Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_fixup_round9.py -q   (from project root)
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_fixup_round6 as _r6  # noqa: E402  (helpers + AppTest setup)
import test_fixup_round7 as _r7  # noqa: E402  (denylist constant)
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")

MAIN_PIN_CHAIN = ('main[data-testid="stMain"] '
                  'div[data-testid="stVerticalBlock"] '
                  'div[data-testid="stLayoutWrapper"]'
                  '.st-key-dcs_rail_behavior')
HOVER_PIN_SEL = ('section[data-testid="stSidebar"]:hover ~ div '
                 + MAIN_PIN_CHAIN)


def _collapsed(theme="light"):
    return ui_design.rail_css(True, theme)


def test_r9_no_has_in_rail_css():
    """The :has() ban is REINSTATED (round 8 wrongly relaxed it for
    its gate): NO :has() anywhere in the rail stylesheet, in either
    state or theme. The gate that used it worked locally (Chromium
    supports :has()) but never took effect live — round 6 proved
    that — and the round-8 live check saw the collapse not stick
    because of it. (The pre-existing :has() rules in the design-
    system sheets are out of scope here; this test pins the rail
    sheet, which is what round 9 rewrote.)"""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            css = ui_design.rail_css(collapsed, theme)
            assert ":has(" not in css, \
                f"rail CSS ({collapsed=}, {theme}) must not contain :has()"
            assert ":is(" not in css, \
                f"rail CSS ({collapsed=}, {theme}) must not contain :is()"
    print("round 9 no :has() in rail CSS OK")


def test_r9_hover_trigger_is_ungated():
    """The collapsed hover-expand trigger is the plain section
    hover — UNGATED. The gate is unnecessary now: the control is
    not a descendant of the section (it renders in the main
    area), so hovering it can never fire ``section:hover``. Every
    hover-expand rule carries the plain trigger, and no gated
    variant may remain."""
    for theme in ("light", "dark"):
        css = _collapsed(theme)
        for frag in (
                'section[data-testid="stSidebar"]:hover '
                'div[data-testid="stSidebarContent"]',
                'section[data-testid="stSidebar"]:hover '
                'div[data-testid="stVerticalBlock"]'):
            assert frag in css, \
                f"collapsed {theme} rail must expand on plain {frag!r}"
        assert ":not(:has(" not in css, \
            f"collapsed {theme} rail must not carry a :has() gate"
        # The section still sits above the main area at rest.
        assert "z-index: 1000 !important" in css, \
            f"collapsed {theme} rail section must carry a rest z-index"
    print("round 9 hover trigger ungated OK")


def test_r9_hidden_condition_is_plain_not_hover():
    """The hiding rules (denylist, no-help buttons, nav label
    spans) apply whenever the rail LOOKS collapsed: pointer away
    from the rail — the plain ``:not(:hover)`` condition. The
    round-8 :is() condition (which also covered "pointer on the
    toggle") is gone with the gate: the toggle is outside the
    section, so that case no longer exists. All 12 denylisted
    testids still appear under the plain condition, still as
    descendant selectors (no ``>`` — the 8b4dd04 lesson)."""
    for theme in ("light", "dark"):
        css = _collapsed(theme)
        hidden = 'section[data-testid="stSidebar"]:not(:hover)'
        assert hidden in css, \
            f"collapsed {theme} rail must carry the plain hidden condition"
        for testid in _r7.DENYLISTED:
            assert (f'{hidden} div[data-testid="stVerticalBlock"] '
                    f'div[data-testid="{testid}"]' in css), \
                f"collapsed {theme} rail must hide {testid} by a " \
                "descendant selector"
        assert (f'{hidden} div[data-testid="stButton"] button '
                'span[style*="display: contents"]' in css), \
            f"collapsed {theme} rail must hide nav labels under " \
            "the same condition"
    print("round 9 hidden condition is plain :not(:hover) OK")


def test_r9_toggle_pin_targets_main_area():
    """The toggle pin's width must be the only width its container
    ever gets — and the container is in the MAIN area now, not the
    sidebar. The pin selector carries the main-area ancestor
    chain (main > vertical block > element container, all
    descendant combinators); the hover variant is a SIBLING
    selector from the hovered section to main[stMain] (both are
    children of stAppViewContainer — verified in the real DOM),
    so the control widens to 260px when the rail overlay is open.
    Widths stay 60px collapsed / 260px expanded. The sidebar
    container rules still exclude the control explicitly.
    (Clone Round 1: the control is the 3-way menu, key
    dcs_rail_behavior — the old toggle's key was
    dcs_rail_toggle.)"""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            css = ui_design.rail_css(collapsed, theme)
            assert MAIN_PIN_CHAIN in css, \
                f"rail CSS ({collapsed=}, {theme}) must pin the " \
                "control in the main area"
            assert ('div[data-testid="stElementContainer"]'
                    ':not(.st-key-dcs_rail_behavior)' in css), \
                f"rail CSS ({collapsed=}, {theme}) must exclude " \
                "the control from the sidebar full-width container rules"
    assert "width: 60px" in ui_design.rail_css(True, "light"), \
        "collapsed rail control pin must be 60px wide"
    assert "width: 260px" in ui_design.rail_css(False, "light"), \
        "expanded rail control pin must be 260px wide"
    # The hover pin: section hovered -> control 260px, via the
    # sibling selector (no :has() gate).
    assert HOVER_PIN_SEL in _collapsed("light"), \
        "collapsed rail must widen the control to 260px on section hover"
    assert HOVER_PIN_SEL in _collapsed("dark"), \
        "collapsed dark rail must widen the control to 260px on section hover"
    print("round 9 control pin targets the main area OK")


def test_r9_behavior_menu_renders_once_in_main_area():
    """app.py renders the rail behavior menu exactly ONCE, at the
    top level (main area) — not inside a ``with st.sidebar:``
    block. The old two sidebar renders (empty state + data-loaded)
    are gone: a single main-area render covers both states, and it
    must sit before any st.stop() so the menu exists on every
    logged-in page. The render call must be a top-level
    ``ui_design.render_rail_behavior_menu()`` (not indented inside
    a ``with`` block, and NOT an ``if`` — the menu radio's
    on_change does the work). (Clone Round 1: the direct toggle
    is gone; this replaces test_r9_toggle_renders_once_in_main_area.)"""
    src = Path(APP).read_text()
    calls = [i for i, line in enumerate(src.splitlines(), 1)
             if "render_rail_behavior_menu()" in line
             and not line.strip().startswith("#")
             and "def " not in line]
    assert len(calls) == 1, \
        f"app.py must call render_rail_behavior_menu() exactly once, found {calls}"
    assert "render_rail_toggle()" not in src, \
        "app.py must not call the old render_rail_toggle() any more"
    line_no = calls[0]
    lines = src.splitlines()
    call_line = lines[line_no - 1]
    assert call_line.startswith("ui_design.render_rail_behavior_menu()"), \
        "the menu render must be a top-level statement (main area)"
    # It must come before the first st.stop() AFTER it in the
    # logged-in flow (the Profile empty-state branch) so it exists
    # on every page. (Earlier st.stop() calls are in the login /
    # share flows, before the menu's logged-in position.)
    stops_after = [i for i, line in enumerate(lines, 1)
                   if "st.stop()" in line and i > line_no]
    assert stops_after, "there must be a st.stop() after the menu render"
    assert line_no < stops_after[0], \
        "the menu render must precede the first st.stop() after it"
    print("round 9 behavior menu renders once in the main area OK")


def test_r9_behavior_menu_button_rules_in_main_area():
    """The menu button needs its own key-scoped rules now that it
    lives in the main area (the sidebar-scoped button rules do
    not reach it): 36px tall, borderless, transparent, icon-only
    centred when collapsed, left-aligned with its label when
    expanded — the same geometry the pin gave the old toggle in
    the sidebar (36px square collapsed, 236px row expanded).
    The trigger is a popover button (stPopoverButton, not
    stBaseButton-secondary), and Streamlit's expand_more chevron
    on it is hidden (it would crowd the 36px square). The rules
    carry the FULL main-area chain (probe27d): Streamlit's own
    popover-button rule (44px !important, (0,2,2)) beats the bare
    key-class rule (0,2,1) — the full chain is (0,5,4) and wins.
    The container is a layout wrapper (probe27b)."""
    btn = MAIN_PIN_CHAIN + ' button[data-testid="stPopoverButton"]'
    collapsed = _collapsed("light")
    for frag in (
            btn + ' {',
            "  width: 36px !important; height: 36px !important;",
            "  min-width: 36px !important;",
            "  justify-content: center !important; }",
            btn + ':hover {',
            btn + ' > div > div[aria-hidden="true"] {\n  display: none !important; }'):
        assert frag in collapsed, \
            f"collapsed rail must carry the main-area menu button rule {frag!r}"
    assert '.st-key-dcs_rail_toggle' not in collapsed, \
        "the collapsed rail must not carry the old toggle key class"
    expanded = ui_design.rail_css(False, "light")
    assert (btn + ' {'
            '\n  width: 236px !important;'
            '\n  height: 36px !important; min-height: 36px !important;'
            '\n  justify-content: flex-start !important;'
            '\n  min-width: 236px !important; }' in expanded), \
        "expanded rail must left-align the menu button (icon + label)"
    print("round 9 behavior menu button rules in the main area OK")


def test_r9_nav_rows_236px():
    """The nav rows are widened to ~233px: an explicit 3px side
    padding on the sidebar content — expanded and hover-expanded
    — PLUS an explicit width:100% on the user content + vertical
    block, PLUS the scrollbar pinned to 8px wide. Round 9 used
    8px padding and predicted ~234px live, but the live check
    measured 224px: the scrollbar pin is IGNORED by this
    Chromium (probe22c: it takes a fixed 20px whatever the pin
    says), so the padding carries the width alone — 259 - 3 - 3
    - 20 = 233px at x=3, matching the 236px toggle at x=12.
    Measured locally (Supabase mode, probe22c): 223px at x=18
    with 8px padding. The collapsed rail keeps its 6px padding."""
    for theme in ("light", "dark"):
        expanded = ui_design.rail_css(False, theme)
        assert ('section[data-testid="stSidebar"] '
                'div[data-testid="stSidebarContent"] {\n'
                '  padding-left: 3px !important; '
                'padding-right: 3px !important; }' in expanded), \
            f"expanded {theme} rail must pad the content 3px a side"
        assert ('section[data-testid="stSidebar"] '
                'div[data-testid="stSidebarContent"]'
                '::-webkit-scrollbar {\n'
                '  width: 8px !important; }' in expanded), \
            f"expanded {theme} rail must pin the scrollbar to 8px"
        assert ('section[data-testid="stSidebar"] '
                'div[data-testid="stSidebarUserContent"],\n'
                'section[data-testid="stSidebar"] '
                'div[data-testid="stSidebarUserContent"] '
                'div[data-testid="stVerticalBlock"] {\n'
                '  width: 100% !important; }' in expanded), \
            f"expanded {theme} rail must pin the user content width"
        collapsed = _collapsed(theme)
        assert ('section[data-testid="stSidebar"]:hover '
                'div[data-testid="stSidebarContent"] {' in collapsed), \
            f"collapsed {theme} rail must keep the hover overlay rule"
        assert ("  padding-left: 3px !important; "
                "padding-right: 3px !important;" in collapsed), \
            f"collapsed {theme} rail must pad the hover overlay 3px a side"
        assert ('section[data-testid="stSidebar"]:hover '
                'div[data-testid="stSidebarContent"]'
                '::-webkit-scrollbar {' in collapsed), \
            f"collapsed {theme} rail must pin the hover scrollbar to 8px"
        assert ('section[data-testid="stSidebar"]:hover '
                'div[data-testid="stSidebarUserContent"],' in collapsed), \
            f"collapsed {theme} rail must pin the hover user content width"
        assert ('section[data-testid="stSidebar"] '
                'div[data-testid="stSidebarContent"] {\n'
                '  padding-left: 6px !important; '
                'padding-right: 6px !important;' in collapsed), \
            f"collapsed {theme} rail must keep its 6px rest padding"
    print("round 9 nav rows 235px OK")


def test_r9_dark_profile_per_key_fill():
    """The dark sheet pins the fill on the two Profile fields BY
    KEY, on top of the global disabled-input rules (round 8):
    ``.st-key-profile_primary_email`` and
    ``.st-key-profile_username`` inputs pin BOTH ``color`` and
    ``-webkit-text-fill-color`` to #edefee. The rule sits after
    the global rules in the sheet, so it wins over any competing
    rule that could be dimming them live. Round 10: the LIGHT
    sheet carries the same per-key pin now (#030303 — the light
    Profile measured 2.61:1 live), so the light assertion below
    pins that instead of the old "light untouched" premise."""
    dark = ui_design.DARK_CSS
    assert (".st-key-profile_primary_email input:disabled," in dark
            and ".st-key-profile_username input:disabled {" in dark), \
        "dark sheet must pin the fill on the two Profile fields by key"
    key_at = dark.find(".st-key-profile_primary_email input:disabled,")
    global_at = dark.find(".stApp input:disabled, .stApp textarea:disabled")
    assert 0 < global_at < key_at, \
        "the per-key fill pin must sit after the global disabled rule"
    light = ui_design.DESIGN_SYSTEM_CSS
    assert (".st-key-profile_primary_email input:disabled," in light
            and ".st-key-profile_username input:disabled {" in light), \
        "light sheet must pin the fill on the two Profile fields by key (round 10)"
    key_at = light.find(".st-key-profile_primary_email input:disabled,")
    global_at = light.find(".stApp input:disabled, .stApp textarea:disabled")
    assert 0 < global_at < key_at, \
        "the light per-key fill pin must sit after the global disabled rule"
    print("round 9 dark Profile per-key fill OK")


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_fixup_round6 — redirect the
    module-level paths directly (there is no DCS_TEST_TMP env var;
    an earlier version of this fixture set one and silently tested
    against the real data/users.db, where a re-run then failed
    signup on the already-taken username)."""
    import ai_settings
    import auth
    import scheduler
    import storage
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


def test_r9_collapse_survives_a_rerun(_tmp_env):
    """The collapse is session state, not a paint effect: expand
    the rail, pick "Collapsed" in the behavior menu (now in the
    main area — the menu radio is drivable by key, so the move
    does not change it), and the rail must read collapsed — and
    STILL read collapsed after a further rerun with no
    interaction. (The live failure was the overlay re-expanding,
    which the structural move now prevents: the control is
    outside the section, so hovering it cannot fire
    section:hover.) (Clone Round 1: the direct toggle is gone;
    the menu's radio is the control.)"""
    at = AppTest.from_file(APP)
    at.run()
    _r6.signup(at, "alice5")
    assert at.session_state.get("dcs_rail_collapsed") is True
    _r6.expand_rail(at)
    assert at.session_state.get("dcs_rail_collapsed") is False
    at.radio(key="dcs_rail_mode_radio").set_value("collapsed").run()
    assert at.session_state.get("dcs_rail_collapsed") is True
    assert ui_design.rail_mode(at) == "collapsed"
    at.run()
    assert at.session_state.get("dcs_rail_collapsed") is True, \
        "the collapse must survive a further rerun with no interaction"
    assert ui_design.rail_mode(at) == "collapsed", \
        "the mode must survive a further rerun with no interaction"
    print("round 9 collapse survives a rerun OK")
