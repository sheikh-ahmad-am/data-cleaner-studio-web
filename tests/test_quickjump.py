"""Quick-jump (Cmd+K-style quick actions) tests for feat_quickjump.py.

Run: .test-venv-refine-b/bin/python tests/test_quickjump.py
       (from the project root)
Also pytest-collectable (plain asserts, no fixtures). No Streamlit
server needed — the pure helpers (filter_actions, resolve_section)
are tested directly, and render_quick_jump is exercised with a
FakeSt stub (same shape as the Group 1 tests).

Covers:
  (a) empty query returns ALL actions, in defined order
  (b) search filters on label / hint / keywords, case-insensitive,
      every word must match; no match returns []
  (c) selecting an action resolves to the right section key;
      unknown keys resolve to None
  (d) every section key the palette can jump to is a real app.py
      section key, and every action key is unique
  (e) the render path: empty query shows the hint and jumps nowhere;
      a no-match query shows the guided empty state; clicking a
      result sets pending_tab and returns the section key
  (f) the honest Cmd+K limit is stated in the module docstring —
      a true overlay palette is not feasible in Streamlit, and the
      module must never claim otherwise
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feat_quickjump as fj

# The eleven section keys in app.py's _nav_labels. Quick jump may only
# ever set pending_tab to one of these.
APP_SECTION_KEYS = {"preview", "join", "clean", "kpis", "dashboard",
                    "compare", "report", "tools", "tutorial", "settings",
                    "profile"}


class FakeSt:
    """Minimal stand-in for the streamlit module (same shape as the
    Group 1 tests): widgets return preset values, display calls are
    recorded, ``sidebar`` is the stub itself."""

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
        self._rec("text_input", label, key, **kwargs)
        return self.presets.get(key, "")

    def button(self, label, key=None, **kwargs):
        self._rec("button", label, key)
        return bool(self.presets.get(key, False))


def _called(fake, name):
    return [c for c in fake.calls if c[0] == name]


def _called_text(fake, name):
    out = []
    for c in fake.calls:
        if c[0] == name:
            out.extend(str(a) for a in c[1])
    return " ".join(out)


# --------------------------------------------------------------------------
# (a) empty query shows all
# --------------------------------------------------------------------------

def test_empty_query_shows_all():
    all_actions = fj.filter_actions("")
    assert all_actions == fj.QUICK_ACTIONS, \
        "empty query must return every action, in defined order"
    assert fj.filter_actions("   ") == fj.QUICK_ACTIONS, \
        "a blank query is an empty query"
    assert fj.filter_actions(None) == fj.QUICK_ACTIONS
    # Every section is listed, plus the key actions.
    sections = {a["section"] for a in all_actions}
    assert sections == APP_SECTION_KEYS, \
        f"missing sections: {APP_SECTION_KEYS - sections}"
    print("empty query shows all OK:", len(all_actions), "actions")


# --------------------------------------------------------------------------
# (b) search filters
# --------------------------------------------------------------------------

def test_search_filters():
    clean = fj.filter_actions("clean")
    labels = [a["label"] for a in clean]
    assert "Clean" in labels and "Clean the data" in labels
    # Every returned action really mentions "clean" somewhere.
    for a in clean:
        hay = " ".join((a["label"], a["hint"], a["keywords"])).lower()
        assert "clean" in hay, f"{a['key']} does not mention 'clean'"
    # Case-insensitive, and multi-word queries need every word.
    assert fj.filter_actions("CLEAN") == clean
    assert [a["key"] for a in fj.filter_actions("sample file")] == ["sample"]
    assert [a["key"] for a in fj.filter_actions("download cleaned")] == \
        ["report", "export"]
    # No match -> empty, never an error.
    assert fj.filter_actions("zzzzqq") == []
    assert fj.filter_actions("clean zzzzqq") == []
    print("search filters OK")


# --------------------------------------------------------------------------
# (c) selecting one returns the right section key
# --------------------------------------------------------------------------

def test_resolve_section():
    assert fj.resolve_section("export") == "report"
    assert fj.resolve_section("profile") == "profile"
    assert fj.resolve_section("whats-new") == "preview"
    assert fj.resolve_section("ask") == "dashboard"
    assert fj.resolve_section("schedule") == "tools"
    assert fj.resolve_section("clean") == "clean"
    assert fj.resolve_section("no-such-action") is None
    assert fj.resolve_section("") is None
    print("resolve section OK")


# --------------------------------------------------------------------------
# (d) action list integrity
# --------------------------------------------------------------------------

def test_action_list_integrity():
    keys = [a["key"] for a in fj.QUICK_ACTIONS]
    assert len(keys) == len(set(keys)), "action keys must be unique"
    for a in fj.QUICK_ACTIONS:
        assert a["section"] in APP_SECTION_KEYS, \
            f"{a['key']} jumps to unknown section {a['section']!r}"
        assert a["label"] and a["hint"], f"{a['key']} needs label + hint"
    print("action list integrity OK")


# --------------------------------------------------------------------------
# (e) render path with FakeSt
# --------------------------------------------------------------------------

def test_render_empty_query_jumps_nowhere():
    fake = FakeSt(presets={"quickjump_query": ""})
    assert fj.render_quick_jump(fake) is None
    assert "pending_tab" not in fake.session_state
    assert _called(fake, "text_input"), "the search box must render"
    assert _called(fake, "caption"), "empty query shows the hint caption"
    assert not _called(fake, "button"), "no result buttons on empty query"
    print("render empty query OK")


def test_render_no_match_guided_empty_state():
    fake = FakeSt(presets={"quickjump_query": "zzzzqq"})
    assert fj.render_quick_jump(fake) is None
    assert "pending_tab" not in fake.session_state
    text = _called_text(fake, "info")
    assert "No matching section or action" in text
    assert "clean" in text and "export" in text and "profile" in text, \
        "empty state must offer the next step (words that do match)"
    print("render no-match OK")


def test_render_click_jumps_to_section():
    fake = FakeSt(presets={"quickjump_query": "profile",
                           "quickjump_go_profile": True})
    jumped = fj.render_quick_jump(fake)
    assert jumped == "profile", jumped
    assert fake.session_state.get("pending_tab") == "profile", \
        "clicking a result must set pending_tab"
    print("render click jumps OK")


def test_render_click_export_jumps_to_report():
    fake = FakeSt(presets={"quickjump_query": "download cleaned",
                           "quickjump_go_export": True})
    assert fj.render_quick_jump(fake) == "report"
    assert fake.session_state.get("pending_tab") == "report"
    print("render export -> report OK")


# --------------------------------------------------------------------------
# (f) the honest Cmd+K limit is stated, not faked
# --------------------------------------------------------------------------

def test_honest_cmdk_limit_stated():
    doc = fj.__doc__ or ""
    assert "NOT feasible" in doc, \
        "module must state plainly that a true overlay palette is " \
        "not feasible in Streamlit"
    assert "cannot be captured" in doc, \
        "module must state that Cmd+K cannot be captured"
    assert "pending_tab" in doc, \
        "module must document the pending_tab jump mechanism"
    # The render path never claims a keyboard shortcut exists.
    assert "⌘K" in doc or "Cmd+K" in doc
    print("honest Cmd+K limit OK")


# --------------------------------------------------------------------------
# (g) Round 3c — keyboard bridge: Enter / ArrowDown / ArrowUp pick a
# result while the search box is focused
# --------------------------------------------------------------------------

def test_keyboard_bridge_constant_exists():
    html = fj.QUICKJUMP_KEYS_BRIDGE_HTML
    assert isinstance(html, str) and "<script>" in html, \
        "the keyboard bridge must be an inline script constant"
    # It handles exactly the three keys, in the focused search box.
    for key in ("ArrowDown", "ArrowUp", "Enter"):
        assert f"'{key}'" in html or f'"{key}"' in html, \
            f"bridge must handle {key}"
    assert "Quick jump" in html, \
        "bridge must find the search box by its aria-label"
    assert "stPopoverBody" in html, \
        "bridge must scope results to the popover body"
    assert "quickjump_go_" in html, \
        "bridge must find result buttons by their widget keys"
    # Enter goes through the mouse path: the highlighted button is
    # clicked, never a separate jump mechanism.
    assert "target.click()" in html or ".click()" in html, \
        "Enter must click the highlighted result button"
    assert "preventDefault" in html, \
        "Enter must stop Streamlit's own submit when it clicks a " \
        "fresh result (a stale Enter lets the submit through)"
    assert "stopPropagation" in html, \
        "Enter must not reach Streamlit's key handler after the click"
    # A text input submits on Enter, never per keystroke — so while
    # the user is still typing there are no result buttons yet, and
    # live-per-keystroke list rendering is NOT feasible with stock
    # Streamlit. A plain first Enter therefore only submits, so the
    # matches render in the still-open popover for the user to see
    # and pick (second Enter, or a click). The bridge remembers a
    # pick (autoPick) ONLY when the user already moved the
    # highlight (ArrowDown/Up + Enter) — that is a choice, so it
    # jumps straight to it once the results render.
    assert "autoPick" in html, \
        "bridge must pick the result after the submit rerun"
    assert "moved:false" in html, \
        "bridge must track whether the highlight was moved"
    assert "S.moved" in html, \
        "bridge must remember the highlight move"
    assert "if(S.moved){S.autoPick=true;}" in html, \
        "autoPick must fire only when the highlight was moved"
    # ArrowDown pressed BEFORE the results render (the value is
    # still unsubmitted) must be remembered, not clamped away:
    # the highlight is only clamped once buttons exist.
    assert "if(btns.length&&S.highlight>=btns.length)" in html, \
        "bridge must not reset the highlight while no results exist"
    # ...and it must NEVER click a non-result button: the text
    # input itself renders a button with empty text, and the old
    # "any button in the body" fallback clicked that on Enter and
    # swallowed the submit (probe39).
    assert "root.querySelectorAll('button')" not in html, \
        "bridge must match ONLY st-key-quickjump_go_ result buttons"
    print("keyboard bridge constant OK")


def test_keyboard_bridge_never_listens_globally():
    html = fj.QUICKJUMP_KEYS_BRIDGE_HTML
    # No Cmd/Ctrl capture anywhere in the bridge: it only acts when
    # the keydown target IS the search box (the honest limit from
    # (f) still holds — Cmd+K global capture is NOT feasible).
    assert "metaKey" not in html and "ctrlKey" not in html, \
        "bridge must not listen for Cmd/Ctrl"
    assert "e.target" in html, \
        "bridge must check the keydown target is the search box"
    # One listener, installed once: a rerun that re-runs the script
    # must never stack a second one.
    assert "installed" in html, \
        "bridge install must be idempotent"
    print("keyboard bridge never listens globally OK")


def test_keyboard_bridge_injected_by_app():
    app_src = (Path(__file__).resolve().parent.parent / "app.py"
               ).read_text(encoding="utf-8")
    assert "QUICKJUMP_KEYS_BRIDGE_HTML" in app_src, \
        "app.py must inject the keyboard bridge"
    assert "components.v1.html" in app_src, \
        "bridge is injected as a zero-height components iframe"
    print("keyboard bridge injected by app OK")


# --------------------------------------------------------------------------
# (h) Round 3e — query clears on EVERY section change, and the
# placeholder is the rendered query (freshness)
# --------------------------------------------------------------------------

def _text_input_kwargs(fake):
    for c in fake.calls:
        if c[0] == "text_input":
            return c[2]
    return {}


def test_placeholder_is_the_rendered_query():
    # The bridge tells a fresh list from a stale one by comparing
    # the input's live value to its placeholder — so the server
    # must set the placeholder to the query the rendered buttons
    # were filtered for, and to the base text when the query is
    # blank (the placeholder only ever shows while the box is
    # empty, so a typed value never shows it).
    fake = FakeSt(presets={"quickjump_query": "clean"})
    fake.session_state["quickjump_query"] = "clean"
    fj.render_quick_jump(fake)
    assert _text_input_kwargs(fake).get("placeholder") == "clean", \
        "placeholder must be the rendered query"
    fake = FakeSt(presets={"quickjump_query": ""})
    fake.session_state["quickjump_query"] = ""
    fj.render_quick_jump(fake)
    assert _text_input_kwargs(fake).get("placeholder") == \
        "Search sections and actions…", \
        "blank query keeps the base placeholder"
    print("placeholder is the rendered query OK")


def test_render_section_change_clears_query():
    # Round 3d live failure, case (b)/(c): the old query survived
    # a section change because only the button-click handler set
    # the clear flag. A change of active_tab must clear the query
    # before the input mounts.
    fake = FakeSt(presets={"quickjump_query": "clean"})
    fake.session_state["active_tab"] = "KPIs"
    fake.session_state["quickjump_last_section"] = "Upload & preview"
    assert fj.render_quick_jump(fake) is None
    assert fake.session_state.get("quickjump_query") == "", \
        "query must clear when the section changes"
    assert fake.session_state.get("quickjump_last_section") == "KPIs", \
        "the new section must be remembered"
    # Same section: no clear (the jump flag covers same-section
    # jumps) — and a first run with nothing stored must not clear
    # either.
    fake = FakeSt(presets={"quickjump_query": "clean"})
    fake.session_state["quickjump_query"] = "clean"
    fake.session_state["active_tab"] = "Clean"
    fake.session_state["quickjump_last_section"] = "Clean"
    fj.render_quick_jump(fake)
    assert fake.session_state.get("quickjump_query") == "clean", \
        "same section must not clear the query"
    fake = FakeSt(presets={"quickjump_query": "clean"})
    fake.session_state["quickjump_query"] = "clean"
    fake.session_state["active_tab"] = "Upload & preview"
    fj.render_quick_jump(fake)
    assert fake.session_state.get("quickjump_query") == "clean", \
        "first run (nothing stored) must not clear the query"
    assert fake.session_state.get("quickjump_last_section") == \
        "Upload & preview"
    print("section-change clear OK")


def test_note_section_change_reruns_to_clear():
    # The radio-path half: app.py calls this AFTER the Section
    # radio is created, because the palette renders before the
    # radio exists on the run. A changed label with a typed query
    # sets the clear flag and reruns (the rerun clears before the
    # input mounts); an empty query costs no extra rerun.
    fake = FakeSt()
    fake.session_state["quickjump_last_section"] = "Upload & preview"
    fake.session_state["quickjump_query"] = "clean"
    fj.note_section_change(fake, "KPIs")
    assert fake.session_state.get("quickjump_clear_after_jump") is True, \
        "radio nav with a typed query must set the clear flag"
    assert fake.session_state.get("quickjump_last_section") == "KPIs"
    assert any(c[0] == "rerun" for c in fake.calls), \
        "radio nav with a typed query must rerun"
    fake = FakeSt()
    fake.session_state["quickjump_last_section"] = "Upload & preview"
    fake.session_state["quickjump_query"] = ""
    fj.note_section_change(fake, "KPIs")
    assert not any(c[0] == "rerun" for c in fake.calls), \
        "radio nav with an empty box must not rerun"
    assert fake.session_state.get("quickjump_last_section") == "KPIs"
    print("note_section_change OK")


def test_note_section_change_called_by_app():
    app_src = (Path(__file__).resolve().parent.parent / "app.py"
               ).read_text(encoding="utf-8")
    assert "note_section_change" in app_src, \
        "app.py must note a Section-radio change after the radio"
    print("note_section_change called by app OK")


def test_note_rail_nav_clears_same_section():
    # Fix round (live check 2026-11-10, R3e B3): a rail click on the
    # section the user is ALREADY on changes nothing, so the
    # palette's section tracking never fires — the query survived
    # a same-section rail click, and the clear flag (set only by a
    # result-button click) never fired on that path either. The
    # rail-click site must set the clear flag, so every rail click
    # clears on the next render, cross-section and same-section.
    fake = FakeSt(presets={"quickjump_query": "clean"})
    fake.session_state["quickjump_query"] = "clean"
    fake.session_state["active_tab"] = "KPIs"
    fake.session_state["quickjump_last_section"] = "KPIs"
    fj.note_rail_nav(fake)
    assert fake.session_state.get("quickjump_clear_after_jump") is True, \
        "a rail click must set the clear flag"
    # The next render pops the flag and clears before the input
    # mounts — even though the section did not change.
    assert fj.render_quick_jump(fake) is None
    assert fake.session_state.get("quickjump_query") == "", \
        "same-section rail nav must clear the query"
    assert fake.session_state.get("quickjump_clear_after_jump") is None, \
        "the flag must be consumed by the render"
    print("rail nav clear OK")


def test_note_rail_nav_called_by_app():
    app_src = (Path(__file__).resolve().parent.parent / "app.py"
               ).read_text(encoding="utf-8")
    assert "note_rail_nav" in app_src, \
        "app.py must note a rail click at the sidebar-nav site"
    print("note_rail_nav called by app OK")


def test_keyboard_bridge_freshness_gates():
    # Round 3e — the stale-highlight fix. Freshness is the input's
    # live value against its placeholder (the rendered query):
    # Enter clicks a highlighted result ONLY when fresh, Arrow
    # keys ignore the move while stale, autoPick only fires on a
    # fresh list, and a capture-phase click listener blocks a
    # mouse click on a stale result button.
    html = fj.QUICKJUMP_KEYS_BRIDGE_HTML
    assert "isFresh" in html, \
        "bridge must define a freshness check"
    assert "getAttribute('placeholder')" in html, \
        "freshness must compare against the placeholder"
    assert "input.value===ph" in html, \
        "fresh means the live value still equals the placeholder"
    assert "btns.length&&isFresh()" in html, \
        "Enter must click a result only when the list is fresh"
    assert "S.autoPick&&btns.length&&fresh" in html, \
        "autoPick must fire only on a fresh list"
    assert "addEventListener('click'" in html, \
        "bridge must intercept clicks on result buttons"
    assert "closest('[class*=\"st-key-quickjump_go_\"]')" in html, \
        "the click intercept must scope to result buttons only"
    # The old unconditional pins must NOT have survived: Enter no
    # longer clicks whenever buttons exist.
    assert "if(btns.length){" not in html, \
        "Enter must not click unconditionally when buttons exist"
    print("keyboard bridge freshness gates OK")


if __name__ == "__main__":
    test_empty_query_shows_all()
    test_search_filters()
    test_resolve_section()
    test_action_list_integrity()
    test_render_empty_query_jumps_nowhere()
    test_render_no_match_guided_empty_state()
    test_render_click_jumps_to_section()
    test_render_click_export_jumps_to_report()
    test_honest_cmdk_limit_stated()
    test_keyboard_bridge_constant_exists()
    test_keyboard_bridge_never_listens_globally()
    test_keyboard_bridge_injected_by_app()
    test_placeholder_is_the_rendered_query()
    test_render_section_change_clears_query()
    test_note_section_change_reruns_to_clear()
    test_note_section_change_called_by_app()
    test_note_rail_nav_clears_same_section()
    test_note_rail_nav_called_by_app()
    test_keyboard_bridge_freshness_gates()
    print("ALL QUICKJUMP TESTS PASSED")
