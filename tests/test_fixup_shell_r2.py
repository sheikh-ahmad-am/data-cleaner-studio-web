"""Clone Round 2 — shell fixes only (tests).

Covers the live-check FAILs from the clone-R1 verdict (browser
task 92f49b1f, 2026-11-09 00:23 IST) that have a code fix:
  FAIL 1  layout reflow / stuck offset — the rail's widths are
          fixed by design (60/260px) and the resize handle (the
          only control that writes a persisted sidebarWidth) is
          hidden in every variant, so nothing can park a stored
          width under the pins.
  FAIL 2  the "Sidebar behavior" control button widens to the
          labelled 236px row when the flyout is open, and its label
          span un-hides on container hover — hover mode only.
  FAIL 3  the Quick Jump palette is a popover in compact mode and
          a jump clears the query on the next render, so the panel
          never re-renders stale results after a jump.
  FAIL 4  flow_marker derives the "Your flow" marker from the
          actual active page, and ticks follow the data.
  FAIL 5  not reproduced in the real DOM (no such heading exists
          in the repo; no clipped element on any of the 12 pages) —
          no code fix, no test.

Run: .test-venv-brevo/bin/python -m pytest tests/test_fixup_shell_r2.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui_design
import feat_quickjump as fj


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rail_variants():
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            for hover in (True, False):
                yield (collapsed, theme, hover,
                       ui_design.rail_css(collapsed, theme, hover=hover))


# ---------------------------------------------------------------------------
# FAIL 1 — the resize handle is hidden in every rail variant
# ---------------------------------------------------------------------------

def test_r2_resize_handle_hidden_in_every_variant():
    """The sidebar resize handle is a dead control on a fixed-width
    rail: dragging it writes a persisted sidebarWidth while the
    pins hold the section at 60/260px, so the drag gives no
    feedback — and a stored width would surface the moment any pin
    weakened. It is hidden in collapsed/expanded x light/dark x
    hover on/off."""
    for collapsed, theme, hover, css in _rail_variants():
        assert ('div[data-testid="stSidebarResizeHandle"] {\n'
                '  display: none !important; }' in css), \
            f"resize handle must be hidden ({collapsed=}, {theme}, {hover=})"
    print("r2 resize handle hidden in every variant OK")


def test_r2_rail_widths_still_pinned_60_and_260():
    """The hardening changes nothing about the widths themselves:
    collapsed pins 60px, expanded pins 260px, in both themes."""
    for theme in ("light", "dark"):
        collapsed = ui_design.rail_css(True, theme)
        assert "width: 60px !important" in collapsed, \
            f"collapsed {theme} rail must still pin 60px"
        expanded = ui_design.rail_css(False, theme)
        assert "width: 260px !important" in expanded, \
            f"expanded {theme} rail must still pin 260px"
    print("r2 rail widths still pinned 60/260 OK")


# ---------------------------------------------------------------------------
# FAIL 2 — the flyout behavior button widens; its label un-hides
# ---------------------------------------------------------------------------

def test_r2_flyout_behavior_button_widens_in_hover_mode_only():
    """In hover mode the behavior control button widens to the
    labelled 236px row when the flyout is open (section hovered)
    or the pointer is on the control itself — the 36px collapsed
    pin would otherwise squeeze the label letter-by-letter. Strict
    mode gains no such rule (no hover widening at all), and the
    expanded rail needs none (its button is already 236px)."""
    for theme in ("light", "dark"):
        hover_css = ui_design.rail_css(True, theme, hover=True)
        assert ("width: 236px !important; "
                "min-width: 236px !important;" in hover_css), \
            f"hover {theme} rail must widen the flyout behavior button"
        assert ('button[data-testid="stPopoverButton"]' in hover_css), \
            f"hover {theme} widening must target the popover button"
        strict_css = ui_design.rail_css(True, theme, hover=False)
        assert "width: 236px !important" not in strict_css, \
            f"strict {theme} rail must carry NO 236px widening rule"
        assert ":hover" not in ui_design.rail_css(False, theme, hover=True), \
            f"expanded {theme} rail must carry no hover rules"
    print("r2 flyout behavior button widens in hover mode only OK")


def test_r2_flyout_behavior_label_unhides_on_container_hover():
    """The label span un-hides when the pointer is on the control's
    container — the hiding rule keys on section:not(:hover), and
    the pointer on the control is NOT on the section, so without
    this the wide button would show only the tune icon. Hover mode
    only; strict mode carries no container-hover rule."""
    for theme in ("light", "dark"):
        hover_css = ui_design.rail_css(True, theme, hover=True)
        assert (f'section[data-testid="stSidebar"] ~ div '
                f'{ui_design.RAIL_BEHAVIOR_CHAIN}:hover button '
                f'span[style*="display: contents"]' in hover_css), \
            f"hover {theme} rail must un-hide the label on container hover"
        strict_css = ui_design.rail_css(True, theme, hover=False)
        assert f'{ui_design.RAIL_BEHAVIOR_CHAIN}:hover button' \
            not in strict_css, \
            f"strict {theme} rail must carry NO container-hover rule"
    print("r2 flyout behavior label un-hides on container hover OK")


def test_r2_no_has_or_is_in_any_rail_css_variant():
    """The :has()/:is() ban holds in EVERY rail_css variant after
    the new rules (the ban test in test_fixup_clone_r1 covers the
    same ground; this one pins it for the Round 2 fragments)."""
    for collapsed, theme, hover, css in _rail_variants():
        assert ":has(" not in css, \
            f"rail CSS ({collapsed=}, {theme}, {hover=}) must not contain :has()"
        assert ":is(" not in css, \
            f"rail CSS ({collapsed=}, {theme}, {hover=}) must not contain :is()"
    print("r2 no :has()/:is() in any rail CSS variant OK")


# ---------------------------------------------------------------------------
# FAIL 3 — Quick Jump: popover in compact mode, clear after a jump
# ---------------------------------------------------------------------------

class _FakePopover:
    """Context manager standing in for st.popover: the with-block
    is entered (the body renders inside it, like Streamlit's
    current-block rule) and nothing is returned — the body is
    called with the module fake as its host."""

    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


class FakeSt:
    """Minimal stand-in for the streamlit module (same shape as the
    Group 1 tests and test_quickjump.py): widgets return preset
    values, display calls are recorded, ``sidebar`` is the stub
    itself — plus a popover that returns a context manager. The
    text input reads the session-state value first, like a real
    widget does: a value the widget wrote on an earlier run is
    what the next run sees."""

    def __init__(self, presets=None):
        self.session_state = {}
        self.presets = presets or {}
        self.calls = []
        self.sidebar = self

    def _rec(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            self._rec(name, *args, kwargs)
            return None
        return _call

    def text_input(self, label, key=None, **kwargs):
        self._rec("text_input", label, key)
        if key in self.session_state:
            return self.session_state[key]
        return self.presets.get(key, "")

    def button(self, label, key=None, **kwargs):
        self._rec("button", label, key)
        return bool(self.presets.get(key, False))

    def popover(self, label, **kwargs):
        self._rec("popover", label, key=kwargs.get("key"))
        return _FakePopover()


def _called(fake, name):
    return [c for c in fake.calls if c[0] == name]


def test_r2_quickjump_compact_renders_popover():
    """Compact mode (the top bar) renders the palette inside an
    st.popover labelled "Search…" — a real overlay, so the results
    float above the page instead of pushing content. The popover
    key is the module constant, so the design system can hide the
    trigger's chevron."""
    fake = FakeSt({"quickjump_query": ""})
    out = fj.render_quick_jump(fake, compact=True)
    assert out is None, "empty query jumps nowhere"
    pops = _called(fake, "popover")
    assert len(pops) == 1, f"compact mode must open exactly one popover, got {len(pops)}"
    assert pops[0][1][0] == "Search…", \
        f"popover label must be 'Search…', got {pops[0][1][0]!r}"
    assert pops[0][2].get("key") == f"{fj.QUICKJUMP_POPOVER_KEY}_0", \
        "popover key must be the base key + epoch 0 on a fresh session"
    assert _called(fake, "text_input"), \
        "the search input must render inside the popover"
    print("r2 quick jump compact renders a popover OK")


def test_r2_quickjump_jump_sets_clear_flag_and_next_render_clears():
    """A jump sets the clear flag, and the NEXT render clears the
    query BEFORE the input mounts — so the panel never re-renders
    stale results after a jump (the clone-R1 live failure: the
    query survived the rerun and the same six results stayed
    open). The flag is consumed on that render."""
    # Run 1: type "clean", click the Clean result.
    fake = FakeSt({"quickjump_query": "clean",
                   "quickjump_go_clean": True})
    out = fj.render_quick_jump(fake)
    assert out == "clean", f"jump must return 'clean', got {out!r}"
    assert fake.session_state.get("pending_tab") == "clean", \
        "jump must set pending_tab"
    assert fake.session_state.get(fj._QUICKJUMP_CLEAR_KEY) is True, \
        "jump must set the clear flag"
    assert fake.session_state.get("quickjump_popover_epoch") == 1, \
        "jump must bump the popover epoch to 1"
    # Run 2: the widget state a real Streamlit run would hold —
    # the query still "clean" — plus the flag.
    fake.session_state["quickjump_query"] = "clean"
    fake.calls = []
    fake.presets = {}
    out2 = fj.render_quick_jump(fake)
    assert out2 is None, "the cleared render jumps nowhere"
    assert fake.session_state.get("quickjump_query") == "", \
        "the query must be cleared before the input mounts"
    assert fj._QUICKJUMP_CLEAR_KEY not in fake.session_state, \
        "the clear flag must be consumed on the clearing render"
    assert not [c for c in _called(fake, "button")
                if str(c[1][1]).startswith("quickjump_go_")], \
        "no result buttons may render after the clear"
    print("r2 quick jump clear-after-jump OK")


def test_r2_quickjump_jump_bumps_popover_epoch():
    """A jump bumps the popover epoch, so the next compact render
    mounts a FRESH popover (closed) instead of reusing the open
    one — the panel closes on selection. The key is base + epoch,
    so the design system's substring chevron rule still matches."""
    fake = FakeSt({"quickjump_query": "clean",
                   "quickjump_go_clean": True})
    fj.render_quick_jump(fake)
    assert fake.session_state.get("quickjump_popover_epoch") == 1
    fake2 = FakeSt({"quickjump_query": ""})
    fake2.session_state["quickjump_popover_epoch"] = 1
    fj.render_quick_jump(fake2, compact=True)
    pops = _called(fake2, "popover")
    assert len(pops) == 1
    assert pops[0][2].get("key") == f"{fj.QUICKJUMP_POPOVER_KEY}_1", \
        "the next compact render must use the bumped epoch key"
    print("r2 quick jump jump bumps popover epoch OK")


def test_r2_quickjump_action_list_still_20():
    """The rewrite changes no actions: the palette still lists
    the same 20 (eleven sections + nine key actions)."""
    assert len(fj.QUICK_ACTIONS) == 20, \
        f"action list must stay 20, got {len(fj.QUICK_ACTIONS)}"
    print("r2 quick jump action list still 20 OK")


def test_r2_quickjump_wrap_and_chevron_css_present_in_both_themes():
    """The design system wraps long result-button labels instead
    of truncating them, and hides the Search pill's expand_more
    chevron — in BOTH themes (the light and dark sheets are
    separate strings)."""
    for theme in ("light", "dark"):
        sheet = ui_design.theme_css(theme)
        assert ('div[class*="st-key-quickjump_go"] '
                'button[data-testid="stBaseButton-secondary"]' in sheet), \
            f"{theme} sheet must scope the wrap rule to quickjump buttons"
        assert "white-space: normal !important" in sheet, \
            f"{theme} sheet must wrap quickjump labels"
        assert ('div[data-testid="stLayoutWrapper"]'
                '[class*="st-key-quickjump_popover"] '
                'button[data-testid="stPopoverButton"]' in sheet), \
            f"{theme} sheet must scope the chevron rule to the quickjump popover"
    print("r2 quick jump wrap + chevron CSS in both themes OK")


def test_r2_quickjump_honest_cmdk_limit_still_stated():
    """The popover rewrite must not smuggle in a false claim: the
    docstring still states the honest limit — a true overlay
    palette is NOT feasible, Cmd+K cannot be captured, jumps go
    through pending_tab."""
    doc = fj.__doc__
    assert "NOT feasible" in doc, "docstring must still say NOT feasible"
    assert "cannot be captured" in doc, \
        "docstring must still say Cmd+K cannot be captured"
    assert "pending_tab" in doc, \
        "docstring must still name the pending_tab mechanism"
    print("r2 quick jump honest Cmd+K limit still stated OK")


# ---------------------------------------------------------------------------
# FAIL 4 — flow_marker derives the marker from the actual page
# ---------------------------------------------------------------------------

def test_r2_flow_marker_follows_the_page():
    """The current step is the page's step — Preview is Upload,
    Clean is Clean, KPIs is KPIs, Report is Export — never the
    data state. On Preview with nothing loaded there are no ticks
    at all (the old line ticked Upload before anything was
    uploaded)."""
    assert ui_design.flow_marker("preview") == [
        "**Upload** — you are here", "Clean", "KPIs", "Export"]
    assert ui_design.flow_marker("clean") == [
        "Upload", "**Clean** — you are here", "KPIs", "Export"]
    assert ui_design.flow_marker("kpis") == [
        "Upload", "Clean", "**KPIs** — you are here", "Export"]
    assert ui_design.flow_marker("report") == [
        "Upload", "Clean", "KPIs", "**Export** — you are here"]
    print("r2 flow marker follows the page OK")


def test_r2_flow_marker_ticks_follow_the_data():
    """A step before the current one is ticked only when its
    output exists. The current step wins over done: on Preview
    with a file loaded, Upload is still "you are here", not a
    tick — and Clean is ticked only once cleaned data exists."""
    assert ui_design.flow_marker("preview", raw_loaded=True) == [
        "**Upload** — you are here", "Clean", "KPIs", "Export"]
    assert ui_design.flow_marker("preview", clean_loaded=True) == [
        "**Upload** — you are here", "Clean ✓", "KPIs", "Export"]
    assert ui_design.flow_marker(
        "clean", raw_loaded=True) == [
        "Upload ✓", "**Clean** — you are here", "KPIs", "Export"]
    assert ui_design.flow_marker(
        "kpis", raw_loaded=True, clean_loaded=True) == [
        "Upload ✓", "Clean ✓", "**KPIs** — you are here", "Export"]
    assert ui_design.flow_marker(
        "report", raw_loaded=True, clean_loaded=True) == [
        "Upload ✓", "Clean ✓", "KPIs", "**Export** — you are here"]
    print("r2 flow marker ticks follow the data OK")


def test_r2_flow_marker_none_off_the_flow():
    """Pages that are not flow steps get no marker at all — the
    caption is not rendered there."""
    for section in ("dashboard", "join", "compare", "tools",
                    "tutorial", "settings", "profile", "status"):
        assert ui_design.flow_marker(section) is None, \
            f"flow_marker({section!r}) must be None"
    print("r2 flow marker None off the flow OK")


# ---------------------------------------------------------------------------
# Standalone run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_r2_resize_handle_hidden_in_every_variant()
    test_r2_rail_widths_still_pinned_60_and_260()
    test_r2_flyout_behavior_button_widens_in_hover_mode_only()
    test_r2_flyout_behavior_label_unhides_on_container_hover()
    test_r2_no_has_or_is_in_any_rail_css_variant()
    test_r2_quickjump_compact_renders_popover()
    test_r2_quickjump_jump_sets_clear_flag_and_next_render_clears()
    test_r2_quickjump_jump_bumps_popover_epoch()
    test_r2_quickjump_action_list_still_20()
    test_r2_quickjump_wrap_and_chevron_css_present_in_both_themes()
    test_r2_quickjump_honest_cmdk_limit_still_stated()
    test_r2_flow_marker_follows_the_page()
    test_r2_flow_marker_ticks_follow_the_data()
    test_r2_flow_marker_none_off_the_flow()
    print("ALL R2 SHELL TESTS PASSED")
