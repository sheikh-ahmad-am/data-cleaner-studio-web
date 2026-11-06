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
        self._rec("text_input", label, key)
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
    print("ALL QUICKJUMP TESTS PASSED")
