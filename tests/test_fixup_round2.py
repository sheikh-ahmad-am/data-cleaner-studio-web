"""Round-2 fix tests (2026-11-07): dark-mode buttons, loader, Get
connected label, Clean-my-data icon.

Why this file exists: the 705ca1f fix was "proven" by the cascade
simulation in tests/test_fixup_five_gaps.py and still failed live.
Two defects in that proof, both fixed here:

1. THE MODEL WAS WRONG. The old simulator put the stButton wrapper
   div as the <button>'s immediate parent. Streamlit 1.66.1 nests an
   intermediate plain div between them on the icon/help path (verified
   from the real frontend chunks in .test-venv-wave3 — Button chunk:
   stButton div -> intermediate element -> BaseButton -> <button>).
   Every failing button passes icon= and/or help= (icon_button(),
   sidebar_nav rows, topbar Help, connect-strip cells, Got it); the
   two buttons that worked live (plain primary "Clean my data", the
   download button) take the no-intermediate path. The corrected
   model below inserts that intermediate div for icon/help buttons
   and omits it for plain primary + download buttons.
2. THE MATCHER WAS WRONG. The old _matches read the combinator off
   the wrong token, so `A > B` silently behaved like `A B` — every
   `>`-chained rule "matched" in simulation and never matched live.
   Fixed in test_fixup_five_gaps._matches (round 2); the proof that
   the fix is real is test_round2_corrected_model_catches_the_old_fix
   below: the 705ca1f CSS FAILS this cascade (bg resolves to None —
   native white — exactly the live white pills), while the new CSS
   passes 9/9.

Run ONLY this file:  .test-venv-wave3/bin/python -m pytest
tests/test_fixup_round2.py -q   (from project root)
"""

import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import auth  # noqa: E402
import feat_brand  # noqa: E402
import feat_mobile  # noqa: E402
import storage  # noqa: E402
import scheduler  # noqa: E402
import test_fixup_five_gaps as _g5  # noqa: E402  (cascade simulator)
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_fixup_five_gaps / test_profile.
    """
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    yield tmp_path


def find_button(at, label, key=None):
    for b in at.button:
        if b.label == label and (key is None or b.key == key):
            return b
    raise AssertionError(f"button {label!r} (key={key!r}) missing")


def find_text_input(at, label):
    for t in at.text_input:
        if t.label == label:
            return t
    raise AssertionError(f"text input {label!r} missing")


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def expand_rail(at):
    """Open the sidebar rail (it starts collapsed — the dashboard's
    own default, icon-only) so the full sidebar is visible: theme
    selectbox, labelled nav rows, uploader, sample button. The rail
    tests in test_supabase_rail.py cover the collapsed state itself;
    the older helpers below need the expanded sidebar to do their
    jobs."""
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert not at.exception, f"exception expanding rail: {at.exception}"


def signup(at, username, password="<redacted>"):
    """Sign up (auto-login) and return the new user's id."""
    at.radio[0].set_value("Sign up").run()
    find_text_input(at, "Username").set_value(username).run()
    find_text_input(at, "Password").set_value(password).run()
    find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    expand_rail(at)
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "signup should log the user straight in"
    return at.session_state["current_user"]["id"]


def load_sample(at):
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([("messy_sales.csv", SAMPLE.read_bytes(), "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert at.session_state["raw"] is not None, "raw data not loaded"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"


def goto_section(at, label):
    radio = next(r for r in at.radio if r.label == "Section")
    radio.set_value(label).run()
    assert not at.exception, f"exception going to {label}: {at.exception}"
    assert radio.value == label, "section switcher did not stick"


def goto_nav(at, label, key):
    """Navigate via a sidebar nav row (the path that works with no data
    loaded, when the Section radio does not exist yet). The rail
    starts collapsed (icon-only, empty labels), so open it first —
    the rows carry their labels only when expanded."""
    expand_rail(at)
    find_button(at, label, key=key).click().run()
    assert not at.exception, f"exception going to {label}: {at.exception}"


# ---------------------------------------------------------------------------
# The CORRECTED DOM model (Streamlit 1.66.1, verified from the frontend
# chunks): on the icon/help path an intermediate plain div sits between
# the stButton wrapper and the <button>. Plain primary buttons and
# download buttons take the direct path (no intermediate div) — which
# is why "Clean my data" and "Download my data" rendered dark live
# while every icon/help button rendered white.
# ---------------------------------------------------------------------------
_INT = _g5._el("div")  # the intermediate wrapper on the icon/help path
_SIDEBAR = [_INT,
            _g5._el("div", ["stButton"], {"data-testid": "stButton"}),
            _g5._el("div"),
            _g5._el("section", [], {"data-testid": "stSidebar"}),
            _g5._el("div", ["stApp"])]
_MAIN = [_INT,
         _g5._el("div", ["stButton"], {"data-testid": "stButton"}),
         _g5._el("div"), _g5._el("div", ["stApp"])]
_PLAIN = [_g5._el("div", ["stButton"], {"data-testid": "stButton"}),
          _g5._el("div"), _g5._el("div", ["stApp"])]
_DL = [_g5._el("div", [], {"data-testid": "stDownloadButton"}),
       _g5._el("div"), _g5._el("div", ["stApp"])]
_DANGER = [_INT,
           _g5._el("div", ["stButton"], {"data-testid": "stButton"}),
           _g5._el("div"),
           _g5._el("div", [], {"data-testid": "stVerticalBlock"}),
           _g5._el("div", ["stApp"])]
_POPOVER = [_INT,
            _g5._el("div", ["stButton"], {"data-testid": "stButton"}),
            _g5._el("div"),
            _g5._el("div", [], {"data-testid": "stPopoverBody"}),
            _g5._el("div", ["stApp"])]

_SEC = _g5._el("button", [], {"data-testid": "stBaseButton-secondary"})
_PRI = _g5._el("button", [], {"data-testid": "stBaseButton-primary"})
_CASES = {
    "sidebar nav (enabled)": (_SEC, _SIDEBAR),
    "sidebar nav (active/disabled)": (
        _g5._el("button", [], {"data-testid": "stBaseButton-secondary"},
                disabled=True), _SIDEBAR),
    "Help button": (_SEC, _MAIN),
    "Log out": (_SEC, _MAIN),
    "Delete my account": (
        _g5._el("button", [], {"data-testid": "stBaseButton-secondary"},
                danger=True), _DANGER),
    "primary (Clean my data, plain)": (_PRI, _PLAIN),
    "primary with icon (Clean now)": (_PRI, _MAIN),
    "Download my data": (_SEC, _DL),
    "popover menu row": (_SEC, _POPOVER),
    "Got it": (_SEC, _MAIN),
    "Dashboard connect-strip cell": (_SEC, _MAIN),
}
_EXPECTED_DARK = {
    "sidebar nav (enabled)": ("#232625", "#edefee"),
    "sidebar nav (active/disabled)": ("#2a2d2c", "#edefee"),
    "Help button": ("#232625", "#edefee"),
    "Log out": ("#232625", "#edefee"),
    "Delete my account": ("#232625", "#ff6369"),
    "primary (Clean my data, plain)": ("#006338", "#ffffff"),
    "primary with icon (Clean now)": ("#006338", "#ffffff"),
    "Download my data": ("#232625", "#edefee"),
    "popover menu row": ("transparent", "#edefee"),
    "Got it": ("#232625", "#edefee"),
    "Dashboard connect-strip cell": ("#232625", "#edefee"),
}


def _dark_rules():
    """The stylesheets the app injects in dark mode, in DOM order."""
    return _g5._cascade_rules("dark")


# ---------------------------------------------------------------------------
# 1 — dark-mode buttons resolve dark under the CORRECTED model
# ---------------------------------------------------------------------------

def test_round2_dark_buttons_are_dark_panels_corrected_model():
    """Dark mode, corrected DOM model: every button the live check
    found white must resolve to a dark panel with bright text — the
    sidebar nav rows (enabled and the disabled active pill), Help,
    Log out, Delete, both primaries, Download, the popover menu row,
    Got it, and the Dashboard connect-strip cells. The inner label /
    icon colour (button *) must be bright too, or the icon reads as
    missing (the Got it check did)."""
    rules = _dark_rules()
    for name, (bg, color) in _EXPECTED_DARK.items():
        elm, anc = _CASES[name]
        got_bg = _g5._winning(rules, elm, anc, "background-color")
        got_color = _g5._winning(rules, elm, anc, "color")
        assert got_bg == bg, \
            f"dark {name}: background {got_bg!r}, want {bg!r}"
        assert got_color == color, \
            f"dark {name}: color {got_color!r}, want {color!r}"
        inner = _g5._el("span")
        got_inner = _g5._winning(rules, inner, [elm] + anc, "color")
        assert got_inner == color, \
            f"dark {name}: inner label/icon {got_inner!r}, want {color!r}"
    print("round 2 dark cascade (corrected model) OK")


def test_round2_dark_buttons_stay_dark_under_stale_light_mobile():
    """The dark rules must still win when the mobile sheet is a theme
    behind (light mobile CSS under the dark design system) — the
    stale-sheet case that made the pills white in round 1."""
    rules = []
    rules.extend(_g5._parse_rules(ui_design.theme_css("dark")))
    rules.extend(_g5._parse_rules(feat_mobile.mobile_css(theme="light")))
    rules.extend(_g5._parse_rules(
        feat_brand.brand_css(feat_brand.DEFAULT_ACCENT)))
    for name in ("sidebar nav (enabled)", "Help button", "Log out",
                 "Delete my account"):
        elm, anc = _CASES[name]
        bg = _g5._winning(rules, elm, anc, "background-color")
        color = _g5._winning(rules, elm, anc, "color")
        assert bg == _EXPECTED_DARK[name][0], \
            f"{name} must stay dark under a stale-light mobile sheet: {bg!r}"
        assert color == _EXPECTED_DARK[name][1], \
            f"{name} text must stay bright under a stale-light sheet: {color!r}"
    print("round 2 stale-mobile-sheet proof OK")


def test_round2_model_rejects_child_combinator_rules():
    """The model itself must reject `>`-chained button rules: a rule
    that only exists in `div[data-testid="stButton"] > button` form
    paints nothing under the corrected model, while the same rule in
    descendant form paints. If this test ever passes the `>` form,
    the matcher has regressed to the forgiving one."""
    elm, anc = _CASES["sidebar nav (enabled)"]
    child = _g5._parse_rules(
        'div[data-testid="stButton"] > button {'
        ' background-color: #232625; color: #edefee; }')
    assert _g5._winning(child, elm, anc, "background-color") is None, \
        "a `>`-chained rule must NOT match the icon/help button"
    desc = _g5._parse_rules(
        'div[data-testid="stButton"] button {'
        ' background-color: #232625; color: #edefee; }')
    assert _g5._winning(desc, elm, anc, "background-color") == "#232625"
    print("round 2 model rejects `>` rules OK")


def test_round2_corrected_model_catches_the_old_fix():
    """The 705ca1f CSS must FAIL the corrected-model cascade — the
    sidebar nav resolves to no background at all (native white shows
    through, exactly the live white pills). If this test ever passes
    against the old CSS, the model is still the forgiving one and the
    next fix could ship broken again."""
    proc = subprocess.run(
        ["git", "show", "705ca1f:ui_design.py"], cwd=PROJECT_ROOT,
        capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip("705ca1f not in this checkout's git history")
    m = re.search(r'DARK_CSS = """(.*?)"""', proc.stdout, re.S)
    if not m:
        pytest.skip("could not extract the old DARK_CSS from 705ca1f")
    rules = []
    for css in (m.group(1), feat_mobile.mobile_css(theme="dark"),
                feat_brand.brand_css(feat_brand.DEFAULT_ACCENT)):
        rules.extend(_g5._parse_rules(css))
    elm, anc = _CASES["sidebar nav (enabled)"]
    assert _g5._winning(rules, elm, anc, "background-color") is None, \
        "old CSS must NOT paint the sidebar nav under the corrected model"
    elm2, anc2 = _CASES["Help button"]
    assert _g5._winning(rules, elm2, anc2, "background-color") is None, \
        "old CSS must NOT paint the Help button under the corrected model"
    print("round 2 old-CSS regression proof OK")


# ---------------------------------------------------------------------------
# 2 — the dark sheet itself: descendant selectors, no dead hooks
# ---------------------------------------------------------------------------

def test_round2_dark_sheet_uses_descendant_selectors():
    """The dark stylesheet must use descendant button selectors and
    carry no `>`-chained stButton selector and no dead `[kind=...]`
    rule (Streamlit puts no `kind` attribute on the rendered button).
    Comments are stripped first — the round-2 note in the sheet quotes
    the old pattern as documentation."""
    dark = _g5._strip_comments(ui_design.DARK_CSS)
    assert 'div[data-testid="stButton"] button' in dark, \
        "dark sheet must carry the descendant stButton selector"
    assert 'div[data-testid="stButton"] > button' not in dark, \
        "no `>`-chained stButton selector may remain in the dark sheet"
    assert 'div[data-testid="stDownloadButton"] button' in dark
    assert 'div[data-testid="stDownloadButton"] > button' not in dark
    assert '.stButton > button' not in dark, \
        "no `>`-chained .stButton selector may remain in the dark sheet"
    assert 'button[kind="secondary"]' not in dark, \
        "dead [kind=secondary] rules must be gone from the dark sheet"
    assert 'button[kind="primary"]' not in dark, \
        "dead [kind=primary] rules must be gone from the dark sheet"
    # The blanket safety net covers the other button hosts too.
    for host in ("stFormSubmitButton", "stFileUploader"):
        assert f'div[data-testid="{host}"] button' in dark, \
            f"dark blanket must cover {host}"
    print("round 2 dark sheet descendant selectors OK")


def test_round2_strip_label_rule_in_both_themes():
    """The .dcs-strip-label rule (Dashboard 'Get connected' heading)
    must exist in both stylesheets and both sheets must stay
    brace-balanced — a missing `}` once swallowed every rule after it."""
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS)):
        depth = 0
        for line in css.splitlines():
            depth += line.count("{") - line.count("}")
        assert depth == 0, f"{name} stylesheet has unbalanced braces"
        assert ".dcs-strip-label" in css, \
            f"{name}: .dcs-strip-label rule missing"
    print("round 2 strip-label rule in both themes OK")


# ---------------------------------------------------------------------------
# 3 — loader: minimum visible time + sample-load path uses it
# ---------------------------------------------------------------------------

def _exec_branded_spinner():
    """Exec branded_spinner from app.py source against a fake `st`
    (same pattern as the gap-5 test) and return (spinner, rendered,
    cleared)."""
    import ast
    import contextlib

    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == "branded_spinner")
    rendered, cleared = [], []

    class _Placeholder:
        def markdown(self, html, **kw):
            rendered.append(html)

        def empty(self):
            cleared.append(True)

    class _FakeSt:
        def empty(self):
            return _Placeholder()

    ns = {"st": _FakeSt(), "ui_design": ui_design,
          "_loader_logo_path": lambda: str(PROJECT_ROOT / "assets" / "logo.png"),
          "contextlib": contextlib, "time": time,
          "_BRANDED_SPINNER_MIN_SECONDS": 0.7}
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 str(PROJECT_ROOT / "app.py"), "exec"), ns)
    return ns["branded_spinner"], rendered, cleared


def test_round2_branded_spinner_holds_the_loader_visible():
    """A fast wait must still show the branded loader: the spinner
    holds the placeholder for at least min_seconds even when the body
    finishes in milliseconds (the sample load is a local read — the
    live check saw no .dcs-loader element at any point because the
    create + clear coalesced inside one script run)."""
    spinner, rendered, cleared = _exec_branded_spinner()
    started = time.monotonic()
    with spinner("Loading the sample file…", min_seconds=0.15):
        assert rendered and "dcs-loader" in rendered[0], \
            "spinner must render the branded loader during the wait"
    elapsed = time.monotonic() - started
    assert elapsed >= 0.12, \
        f"spinner cleared after {elapsed:.2f}s, must hold >= ~0.15s"
    assert cleared, "spinner must clear the placeholder when the wait ends"
    print(f"round 2 spinner min-visible-time OK ({elapsed:.2f}s)")


def test_round2_spinner_default_is_point_seven_seconds():
    """The default minimum visible time is 0.7s — long enough for the
    browser to paint the loader, short enough that no real wait is
    noticeable."""
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert "_BRANDED_SPINNER_MIN_SECONDS = 0.7" in source, \
        "spinner default minimum must be 0.7s"
    assert 'with branded_spinner("Loading the sample file…")' in source, \
        "the sample-load path must go through branded_spinner"
    assert source.count('with branded_spinner("Loading the sample file…")') == 2, \
        "both sample-load sites (sidebar + empty-state CTA) must use it"
    print("round 2 spinner default + sample-load wiring OK")


def test_round2_sample_cta_loads_through_the_spinner_path(_tmp_env):
    """Clicking the empty-state 'Try the sample data' CTA loads the
    sample (80 rows) — the path that goes through branded_spinner.
    (The loader's visibility itself is a browser-paint property; the
    min-time unit test above proves the hold, this test proves the
    path runs end to end.)"""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    find_button(at, "Try the sample data").click().run()
    assert not at.exception, f"exception on sample CTA: {at.exception}"
    assert at.session_state["raw"] is not None, "sample did not load"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    print("round 2 sample CTA loads OK")


# ---------------------------------------------------------------------------
# 4 — "Get connected" label renders on the Dashboard
# ---------------------------------------------------------------------------

def test_round2_dashboard_shows_get_connected_label(_tmp_env):
    """The Dashboard must show the literal text 'Get connected' above
    the six quick-action buttons — the strip rendered its cells with
    no visible heading (the label lived only in a docstring)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    goto_nav(at, "Dashboard", "dcs_nav_dashboard")
    md = "\n".join(vals(at.markdown))
    assert "Get connected" in md, \
        "'Get connected' label missing from the Dashboard"
    for cell in ("Upload", "Clean", "KPIs", "Charts", "Report", "Tools"):
        assert any(b.label == cell for b in at.button), \
            f"Get connected cell {cell!r} missing"
    print("round 2 Get connected label OK")


# ---------------------------------------------------------------------------
# 5 — "Clean my data" carries its icon
# ---------------------------------------------------------------------------

def test_round2_clean_my_data_has_icon(_tmp_env):
    """On the Clean page (sample loaded) the action button is 'Clean
    my data' — it must carry its cleaning-services icon, matching the
    other buttons (it was text-only; 'Clean now' is a different button
    that lives on Preview)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    goto_section(at, "Clean")
    btn = find_button(at, "Clean my data", key="clean_btn")
    assert btn.proto.icon == ":material/cleaning_services:", \
        f"Clean my data icon wrong: {btn.proto.icon!r}"
    print("round 2 Clean my data icon OK")
