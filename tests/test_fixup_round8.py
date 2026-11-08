"""Round-8 fix tests (2026-11-08): three live failures that survived
the round-7 reboot (the reboot proved the other eight items were a
stale module, not code). All three were verified live post-reboot
in the browser at 1920x1000, both themes, and reproduced against
the REAL Streamlit 1.66.1 DOM (Playwright + headless Chromium,
local app server — probes in ~/workspace/dcs-probe/, probe16*.py,
probe17*.py):

1. HOVER ONLY TRIGGERED ON A NARROW STRIP live (y≈150–170 of a
   ~460px rail; y≈133/210/250 dead even with ~600ms dwell). The
   local real-DOM probe could NOT reproduce it: the section is
   full-height (998px) and ``elementFromPoint`` returns sidebar
   elements at every y, with and without a file loaded, and the
   hover glides 60 -> 260 everywhere. So the trigger is HARDENED
   rather than root-caused further: the section carries a rest
   z-index (1000; the hover overlay lifts it to 1000000) so
   nothing painted above it can steal pointer events from the
   rail. The probe numbers are the evidence, not a guess.
2. PROFILE DARK DISABLED FIELDS STILL DIM live. Round 7's probe
   read computed ``color`` (#edefee, correct) and called the rule
   proven — WRONG: Chromium paints disabled input text with
   ``-webkit-text-fill-color``, which sat at rgba(3,3,3,0.4),
   so the values rendered dim dark-grey on the dark fields
   despite the correct ``color``. The fill pin is the fix
   (probe17: fill rgb(237,239,238) on rgb(42,45,44), and the
   screenshot shows the values as bright as "Member since").
3. COLLAPSE DID NOT STICK live: clicking "Collapse sidebar"
   returned the rail to 60px, but the rerun re-expanded it
   within a few seconds, sometimes into a hybrid 260px panel
   showing only the nav buttons. The round-8 probe proved the
   mechanism: the session state does NOT flip (the toggle still
   shows the right chevron = collapsed) — the re-expansion is
   the HOVER OVERLAY, because the pointer rests on the toggle
   after the click and the ungated ``:hover`` re-expanded it
   instantly. The fix gates the hover-expand on the toggle
   (``:not(:has(.st-key-dcs_rail_toggle:hover))``) and gives the
   hiding rules the matching ``:is()`` condition, so hovering
   the toggle leaves the rail collapsed and the mounted widgets
   stay hidden there (probe17: widths [60 x 17] over 8.5s with
   the mouse on the toggle; hovering a nav icon still glides
   to 260). The toggle strip (~52px at the bottom) is the one
   part of the rail that does not trigger the expand — it is a
   control, not rail content, and expanding from it would undo
   the click that just landed on it.
4. TOGGLE BAR PLACEMENT: the pinned "Collapse sidebar" row sat
   in a fixed FULL-WIDTH bottom bar (container 1920px wide,
   button 1896px) instead of inside the 260px sidebar column.
   Root cause, proven in the probe: the wide-state
   ``width: 100% !important`` container rule at specificity
   (0,3,3) beat the pin rule at (0,3,2), so the fixed toggle
   bar stretched to the viewport width. The pin selector now
   carries the full ancestor chain at (0,5,4) and the container
   rules exclude the toggle explicitly (probe17: expanded
   container 260px, button 236px at x=12; collapsed container
   60px, button 36px at x=12 — consistent on fresh load and
   after a collapse).

Also in this round: the local probe server itself taught a
lesson — the server was started BEFORE the code edits and kept
serving the OLD ui_design module (probe17's first run tested
the old build: gated selector absent from the served CSS), so
the probe must RESTART the local server after every code edit
before measuring. The live check after the push is the only
proof; a stale module needs a reboot first.

Run ONLY this file:  .test-venv-ui/bin/python -m pytest
tests/test_fixup_round8.py -q   (from project root)

Round 9 (2026-11-08) SUPERSEDED the :has() gate and the sidebar
pin below: the gate never took effect live (round 6 already proved
:has() never takes effect live), so the toggle moved OUT of the
sidebar into the main area and the gate was deleted — see
tests/test_fixup_round9.py for the new-mechanism tests. The three
round-8 tests that asserted the gate / the :is() hidden condition /
the sidebar pin chain were removed here and replaced there; the
tests that still hold (dark fill, no-selector-value, hover wash,
collapse survives a rerun) stay.

Clone Round 1 (2026-11-08) supersedes the toggle itself: the
direct toggle is gone, replaced by Supabase's 3-way bottom
control — a popover menu with the radio options Expanded /
Collapsed / Expand on hover. The mode is session state
``dcs_rail_mode``; ``dcs_rail_collapsed`` stays as the derived
bool. The collapse-survives-a-rerun test now picks "Collapsed"
in the menu radio instead of clicking the toggle.
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

# Round 9 superseded the :has() gate (GATE / HOVER constants) and
# the sidebar pin chain — see tests/test_fixup_round9.py.

# NOTE (round 9): the three tests that asserted the :has() gate, the
# :is() hidden condition and the sidebar pin chain lived here and
# were REMOVED — round 9 deleted the gate and moved the toggle to
# the main area (see tests/test_fixup_round9.py). Do not re-add
# a :has() gate: round 6 proved :has() never takes effect live.


def _collapsed(theme="light"):
    return ui_design.rail_css(True, theme)





def test_r8_dark_disabled_inputs_paint_bright():
    """The dark disabled-input rules pin BOTH ``color`` and
    ``-webkit-text-fill-color`` to #edefee: Chromium paints
    disabled input text with the fill, not the color, so the
    color pin alone left Profile's Primary email + Username dim
    live (fill rgba(3,3,3,0.4)). Both rules carry the fill pin.
    Round 10: the LIGHT sheet carries its own fill pin now
    (#030303 — the light Profile measured 2.61:1 live), so the
    light assertion below pins that instead of its absence."""
    assert ui_design.DARK_CSS.count(
        "-webkit-text-fill-color: #edefee !important") >= 2, \
        "dark sheet must pin the fill colour on both disabled-input rules"
    assert ui_design.DESIGN_SYSTEM_CSS.count(
        "-webkit-text-fill-color: #030303 !important") >= 2, \
        "light sheet must pin the fill colour on its disabled-input rules (round 10)"
    print("round 8 dark disabled inputs paint bright OK")


def test_r8_no_declaration_value_is_a_selector():
    """Regression pin for a round-8 self-inflicted bug: the
    collapsed branch redefines ``_hover`` from the hover-wash
    TOKEN to the gated hover SELECTOR, and one rule interpolated
    it as a VALUE — ``background-color:
    section[data-testid="stSidebar"]:hover:not(:has(...))`` —
    an invalid declaration the browser silently drops, so the
    nav-row hover wash vanished in both themes (caught by the
    supabase_rail token tests, not by the probe). No declaration
    value in any rail sheet may be a selector string."""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            css = ui_design.rail_css(collapsed, theme)
            assert "background-color: section[" not in css, \
                f"rail CSS ({collapsed=}, {theme}) must not carry " \
                "a selector as a background-color value"
            assert "color: section[" not in css, \
                f"rail CSS ({collapsed=}, {theme}) must not carry " \
                "a selector as a colour value"
    print("round 8 no declaration value is a selector OK")


def test_r8_expanded_nav_rows_have_a_hover_wash():
    """Pre-existing gap found while verifying the wash fix: the
    COLLAPSED sheet carried the nav-row hover wash (#f8f8f8 /
    #262928) but the PINNED-EXPANDED rail had no wash rule at
    all — the base button rule out-specified the generic hover
    wash, so hovering a row painted nothing (probe18: white in
    light, #232625 in dark). Both base sheets now carry the wash
    rule right after the button rule, before the :disabled rule,
    so a hovered non-active row washes and the active (disabled)
    row keeps its highlight."""
    assert ('section[data-testid="stSidebar"] '
            'div[data-testid="stButton"] '
            'button[data-testid="stBaseButton-secondary"]:hover {\n'
            '  background-color: #f8f8f8 !important; }'
            in ui_design.DESIGN_SYSTEM_CSS), \
        "light base sheet must wash a hovered nav row #f8f8f8"
    assert ('section[data-testid="stSidebar"] '
            'div[data-testid="stButton"] button:hover {\n'
            '  background-color: #262928 !important; }'
            in ui_design.DARK_CSS), \
        "dark base sheet must wash a hovered nav row #262928"
    for sheet in (ui_design.DESIGN_SYSTEM_CSS, ui_design.DARK_CSS):
        hover_at = sheet.find(":hover {\n  background-color: #")
        dis_at = sheet.find(":disabled {", hover_at)
        assert 0 < hover_at < dis_at, \
            "the wash rule must sit before the :disabled rule, so " \
            "the active row keeps its highlight"
    print("round 8 expanded nav rows have a hover wash OK")


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


def test_r8_collapse_survives_a_rerun(_tmp_env):
    """The collapse is session state, not a paint effect: expand
    the rail, pick "Collapsed" in the behavior menu, and the rail
    must read collapsed — and STILL read collapsed after a further
    rerun with no interaction (the live failure was the overlay
    re-expanding, which the round-8 CSS gate was meant to prevent
    and round 9's structural move + clone Round 1's explicit mode
    choice now prevent by construction: the mode is state, and
    in strict "collapsed" mode no hover rule exists to re-expand
    it). (Clone Round 1: the direct toggle is gone; the menu's
    radio is the control.)"""
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
    print("round 8 collapse survives a rerun OK")
