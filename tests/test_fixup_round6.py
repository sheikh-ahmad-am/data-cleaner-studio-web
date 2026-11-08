"""Round-6 fix tests (2026-11-08): hover rail, live-DOM selectors,
breadcrumb, dark dropzone, dark disabled inputs, branded loader.

Why this file exists: the 5028aa3 fix passed its tests (454/9) but
several fixes did NOT take effect live — the same code-vs-live-DOM
mismatch as round 2. The live re-check (01:47–01:53 IST) found the
collapsed rail still leaking vertical text, the active icon with no
shaded background, expanded nav rows still compact pills, the toggle
below the fold, the breadcrumb still three segments, the dark
dropzone still white, dark disabled Profile fields unreadable, and
the branded loader unseen on sample load. Every selector/rule below
is verified against the REAL Streamlit 1.66.1 DOM (frontend chunks
in .test-venv-wave3 + the jsdom proof in hidden_files/dom-proof/,
22/22 green) — not just that a string exists in a stylesheet.

The hover model (the user's correction, 2026-11-08 ~12:17 IST): the
Supabase sidebar shows icons only; hovering it expands it
AUTOMATICALLY as an overlay (~260px, labels + controls appear,
~0.2s ease) floating above the page, and moving away shrinks it
back. The bottom toggle is the PINNED state (click = stays expanded,
click again = stays collapsed; hover is the temporary expand). The
hover expand is pure client-side CSS — :hover on the sidebar
container with a width transition — no server rerun, no remount, so
the 0.2s glide is genuinely achievable here, unlike the click-toggle
glide (which drives a full rerun and remounts at the new width).

That is why the labels AND the expanded-sidebar controls are IN THE
DOM while collapsed (CSS-hidden when collapsed-and-not-hovered,
revealed on hover): the 5028aa3 choice to leave labels empty and
skip rendering the controls when collapsed made the hover expand
impossible. The collapsed-mode guards in app.py are gone; the
rail CSS decides what shows.

Run ONLY this file:  .test-venv-wave3/bin/python -m pytest
tests/test_fixup_round6.py -q   (from project root)
"""

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai_settings  # noqa: E402
import auth  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
import test_fixup_five_gaps as _g5  # noqa: E402  (cascade simulator)
import test_fixup_round2 as _r2  # noqa: E402  (corrected DOM model)
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"

NAV_ORDER = ["preview", "clean", "join", "kpis", "dashboard", "compare",
             "report", "tools", "tutorial", "settings", "profile",
             "status"]
NAV_LABELS = {"preview": "Preview", "clean": "Clean", "join": "Join",
              "kpis": "KPIs", "dashboard": "Dashboard",
              "compare": "Compare", "report": "Report", "tools": "Tools",
              "tutorial": "How to use", "settings": "Settings",
              "profile": "Profile", "status": "Status"}


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_supabase_rail / test_fixup_round5.
    """
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


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def find_button(at, label, key=None):
    for b in at.button:
        if b.label == label and (key is None or b.key == key):
            return b
    raise AssertionError(f"button {label!r} (key={key!r}) missing")


def find_button_by_key(at, key):
    for b in at.button:
        if b.key == key:
            return b
    raise AssertionError(f"button key={key!r} missing")


def find_text_input(at, label):
    for t in at.text_input:
        if t.label == label:
            return t
    raise AssertionError(f"text input {label!r} missing")


def signup(at, username, password="password123"):
    """Sign up (auto-login); the app must show the data screen after.

    Leaves the rail in its default collapsed state — the round-6
    tests assert on that state explicitly."""
    at.radio[0].set_value("Sign up").run()
    find_text_input(at, "Username").set_value(username).run()
    find_text_input(at, "Password").set_value(password).run()
    find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    assert at.session_state.get("current_user", {}).get("username") == username, \
        "signup must log the user straight in"


def nav_buttons(at):
    """The rail's nav buttons, in render order (all dcs_nav_* keys)."""
    return [b for b in at.sidebar.button
            if (b.key or "").startswith("dcs_nav_")]


def expand_rail(at):
    """Pin the rail open (pick "Expanded" in the behavior menu):
    the non-nav sidebar controls only render when pinned open
    (round 7), so tests that need the sample button / uploader /
    slicers must expand first. (Clone Round 1: the direct toggle
    is gone; the menu's explicit mode choice is the control.)"""
    at.radio(key="dcs_rail_mode_radio").set_value("expanded").run()
    assert at.session_state.get("dcs_rail_collapsed") is False, \
        "the rail must be pinned open after picking Expanded"
    assert ui_design.rail_mode(at) == "expanded"


def topbar_left(at):
    """The top-bar left markdown element (the brand + title/crumb)."""
    return next(v for v in vals(at.markdown)
                if '<div class="dcs-topbar-left">' in v)


# ---------------------------------------------------------------------------
# 1. Hover expand — the overlay model (the user's correction)
# ---------------------------------------------------------------------------

def test_r6_hover_expands_as_overlay():
    """Collapsed rail CSS carries the hover-expand overlay: hovering
    the sidebar section grows the content to 260px as an ABSOLUTE
    overlay (position + z-index + shadow) floating above the page —
    the page is not pushed/reflowed. The expanded (pinned) sheet
    carries NO hover rules: when pinned-expanded, hover changes
    nothing."""
    for theme in ("light", "dark"):
        css = ui_design.rail_css(collapsed=True, theme=theme)
        assert 'section[data-testid="stSidebar"]:hover' in css, \
            f"collapsed {theme} rail CSS must carry the hover rule"
        assert "width: 260px !important" in css, \
            f"collapsed {theme} rail CSS must expand to 260px on hover"
        assert "position: absolute !important" in css, \
            f"collapsed {theme} rail CSS must overlay the content"
        assert "z-index: 1000000" in css, \
            f"collapsed {theme} rail CSS must float above the page"
        assert "box-shadow:" in css, \
            f"collapsed {theme} rail CSS must shadow the overlay"
        # No overflow:hidden on the section: the hover overlay is
        # absolute content 260px wide inside a 60px section, so it
        # relies on overflowing the section's bounds. Hiding is by
        # display:none (the denylist), not by clipping.
    for theme in ("light", "dark"):
        css = ui_design.rail_css(collapsed=False, theme=theme)
        assert ":hover" not in css, \
            f"expanded {theme} rail CSS must carry no hover rules"
    print("round 6 hover overlay OK")


def test_r6_hover_glide_is_client_side():
    """The hover glide is pure client-side CSS, so it sidesteps the
    rerun problem: the collapsed sheet carries a 200ms ease width
    transition on the sidebar (including flex-basis, the property
    Streamlit's flex-row layout actually renders), and the hover
    rule is present regardless of the pinned state — no server round
    trip, no remount, so the 0.2s glide is genuinely achievable.
    The click-toggle glide is NOT claimed here: the toggle drives a
    full server rerun and the sidebar remounts at the new width, so
    a CSS transition cannot interpolate across it."""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            css = ui_design.rail_css(collapsed, theme)
            assert "200ms cubic-bezier(0.22,1,0.36,1)" in css, \
                f"rail CSS ({collapsed=}, {theme}) must animate on a " \
                "200ms ease"
            assert "flex-basis" in css, \
                f"rail CSS ({collapsed=}, {theme}) must transition " \
                "flex-basis (the rendered width in the flex row)"
    # The hover rule lives in the collapsed sheet only — it is a
    # client-side rule, not a session-state one.
    assert 'section[data-testid="stSidebar"]:hover' in \
        ui_design.rail_css(True, "light")
    assert 'section[data-testid="stSidebar"]:hover' not in \
        ui_design.rail_css(False, "light")
    print("round 6 hover glide is client-side OK")


# ---------------------------------------------------------------------------
# 2. Labels + controls are IN THE DOM when collapsed (hover model)
# ---------------------------------------------------------------------------

def test_r6_labels_and_controls_in_dom_when_collapsed(_tmp_env):
    """Round 7 REVERSED this test's round-6 expectation. The hover
    expand needs only the NAV labels in the DOM while collapsed —
    the rail CSS hides them when collapsed-and-not-hovered and
    reveals them on hover. The non-nav controls (theme selectbox,
    file uploader, sample button, client-mode checkbox) are NOT
    rendered while collapsed: app.py guards them on the rail state,
    because what is not in the DOM cannot render as vertical
    one-letter text (the 8b4dd04 live failure — "Theme", the status
    pill, the uploader and the checkbox all squeezed into
    single-letter columns despite a CSS denylist). They reappear
    when the rail is pinned open; their values persist in session
    state across the collapse."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    assert at.session_state.get("dcs_rail_collapsed") is True, \
        "the rail must start collapsed after signup"
    rows = nav_buttons(at)
    assert [b.label for b in rows] == [NAV_LABELS[k] for k in NAV_ORDER], \
        "collapsed rail must carry all 12 nav labels in the DOM"
    assert not list(at.sidebar.selectbox), \
        "collapsed rail must NOT render the theme selectbox"
    assert not list(at.sidebar.file_uploader), \
        "collapsed rail must NOT render the file uploader"
    assert not any(b.label == "Try the messy sample" for b in at.button), \
        "collapsed rail must NOT render the sidebar sample button"
    assert not any(c.label == "Client mode (simple view)"
                   for c in at.sidebar.checkbox), \
        "collapsed rail must NOT render the client-mode checkbox"
    # Clone Round 1: the direct toggle is gone. The bottom control
    # is the behavior menu, not a button: its popover renders and
    # its radio reads the current mode.
    at.get_by_key("dcs_rail_behavior")
    assert at.radio(key="dcs_rail_mode_radio").value == "hover", \
        "collapsed rail's menu radio must read Expand on hover"
    # Pin it open: the controls come back.
    expand_rail(at)
    assert list(at.sidebar.selectbox), \
        "pinned-open rail must render the theme selectbox"
    assert list(at.sidebar.file_uploader), \
        "pinned-open rail must render the file uploader"
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "pinned-open rail must render the sidebar sample button"
    assert any(c.label == "Client mode (simple view)"
               for c in at.sidebar.checkbox), \
        "pinned-open rail must render the client-mode checkbox"
    print("round 6/7 collapsed rail: nav only in DOM, controls on expand OK")


def test_r6_denylist_hides_controls_not_nav():
    """Collapsed rail CSS hides every non-button sidebar child with
    an explicit testid denylist. :has() is banned outright — round
    6 banned it, round 8 reintroduced it for ONE purpose (the
    toggle gate), round 9 DELETED the gate (it never took effect
    live) and the ban is reinstated: the collapsed sheet must
    contain NO :has() at all. The denylist itself still hides by
    explicit testids, never by :has(). The expanded rail shows
    every control."""
    denylisted = ("stCheckbox", "stMarkdown", "stMultiSelect",
                  "stDateInput", "stCaption", "stExpander",
                  "stFileUploader", "stSelectbox", "stAlert",
                  "stTextInput", "stRadio", "stNumberInput")
    for theme in ("light", "dark"):
        css = ui_design.rail_css(collapsed=True, theme=theme)
        assert ":has(" not in css, \
            f"collapsed {theme} rail CSS must contain no :has() at all " \
            "(round 9 deleted the toggle gate; the ban is reinstated)"
        assert ":is(" not in css, \
            f"collapsed {theme} rail CSS must contain no :is() either"
        for testid in denylisted:
            assert f'div[data-testid="{testid}"]' in css, \
                f"collapsed {theme} rail CSS must hide {testid}"
        assert "display: none !important" in css, \
            f"collapsed {theme} rail denylist must hide its targets"
        # Nav + toggle wrappers are never hidden: no display:none
        # selector may END with the stButton wrapper. (The no-help
        # rule ends with `> button` — it hides the <button> inside
        # the wrapper, not the wrapper itself.)
        for rule in css.split("}"):
            if "display: none !important" in rule:
                selector = rule.split("{")[0]
                for sel in selector.split(","):
                    assert not sel.strip().endswith(
                        'div[data-testid="stButton"]'), \
                        f"collapsed {theme} rail must never hide the " \
                        f"stButton wrapper: {sel.strip()!r}"
        # No-help buttons (the sample button) are hidden: a
        # display:none rule whose selector ends with `> button`.
        assert any(
            "display: none !important" in rule
            and rule.split("{")[0].strip().endswith("> button")
            for rule in css.split("}")), \
            f"collapsed {theme} rail CSS must hide no-help buttons"
    for theme in ("light", "dark"):
        css = ui_design.rail_css(collapsed=False, theme=theme)
        # The expanded rail hides none of the denylisted controls —
        # but it DOES hide Streamlit's native top "«" collapse
        # control (round 7: the rail collapses to the 60px icon
        # rail, never to 0px) and the menu button's expand_more
        # chevron (clone Round 1 — Streamlit's own chevron inside
        # the behavior-menu trigger). So the only display:none
        # allowed in the expanded sheet is those two.
        for rule in css.split("}"):
            if "display: none !important" in rule:
                selector = rule.split("{")[0]
                for testid in denylisted:
                    assert f'div[data-testid="{testid}"]' not in selector, \
                        f"expanded {theme} rail must not hide {testid}"
                assert ("stSidebarCollapseButton" in selector
                        or ("st-key-dcs_rail_behavior" in selector
                            and "aria-hidden" in selector)), \
                    f"expanded {theme} rail must only hide the native " \
                    f"collapse control or the menu chevron: {selector!r}"
    print("round 6 denylist OK")


# ---------------------------------------------------------------------------
# 3. Descendant button rules match the REAL 1.66.1 DOM (cascade proof)
# ---------------------------------------------------------------------------

def test_r6_descendant_rules_match_real_dom():
    """The light sheet's sidebar button rules are descendant selectors
    now, and under the CORRECTED DOM model (intermediate plain div
    between the stButton wrapper and the <button> on the icon/help
    path — verified from the real 1.66.1 frontend chunks, the same
    model test_fixup_round2 pins) the nav rows resolve to a real
    background in both themes: enabled #ffffff / #232625, active
    #f3f3f3 / #343837 — the active row's shaded background the live
    check found missing. The `>` form matched 0 buttons live."""
    expected = {
        "light": {
            "sidebar nav (enabled)": ("#ffffff", "#030303"),
            "sidebar nav (active/disabled)": ("#f3f3f3", "#030303"),
        },
        "dark": {
            "sidebar nav (enabled)": ("#232625", "#edefee"),
            "sidebar nav (active/disabled)": ("#343837", "#edefee"),
        },
    }
    for theme in ("light", "dark"):
        rules = _g5._cascade_rules(theme)
        for name, (bg, color) in expected[theme].items():
            elm, anc = _r2._CASES[name]
            got_bg = _g5._winning(rules, elm, anc, "background-color")
            got_color = _g5._winning(rules, elm, anc, "color")
            assert got_bg == bg, \
                f"{theme} {name}: background {got_bg!r}, want {bg!r}"
            assert got_color == color, \
                f"{theme} {name}: color {got_color!r}, want {color!r}"
    # The light sheet carries no `>`-chained LIVE (data-testid)
    # stButton rule (the dark sheet was fixed in round 2). The
    # [kind=...] rules are knowingly dead — the sheet's own comment
    # says Streamlit puts no kind attribute on the button — and are
    # kept as documentation, so they are not asserted away here.
    light = _g5._strip_comments(ui_design.DESIGN_SYSTEM_CSS)
    assert 'div[data-testid="stButton"] > button[data-testid=' not in light, \
        "no `>`-chained live stButton selector may remain in the " \
        "light sheet"
    assert 'div[data-testid="stButton"] > button:hover' not in light, \
        "no `>`-chained live stButton hover may remain in the light sheet"
    print("round 6 descendant rules match real DOM OK")


# ---------------------------------------------------------------------------
# 4. Dark dropzone + dark disabled inputs
# ---------------------------------------------------------------------------

def test_r6_dark_dropzone_is_dark():
    """The dropzone element is a <section>, not a <div> — the
    div-qualified rule never matched live, so the dark dropzone
    stayed Streamlit's light secondaryBg (white) with near-white
    text on it. The rule is unqualified now, with !important, in
    both themes and in the app.py literal."""
    dark = ui_design.DARK_CSS
    m = re.search(r'\[data-testid="stFileUploaderDropzone"\]\s*\{([^}]*)\}',
                  dark)
    assert m, "dark sheet must style the dropzone by unqualified testid"
    assert "background-color: #232625 !important" in m.group(1), \
        f"dark dropzone must be #232625, got {m.group(1)!r}"
    assert 'div[data-testid="stFileUploaderDropzone"] {' not in dark, \
        "the div-qualified dropzone rule must be gone from the dark sheet"
    light = ui_design.DESIGN_SYSTEM_CSS
    m = re.search(r'\[data-testid="stFileUploaderDropzone"\]\s*\{([^}]*)\}',
                  light)
    assert m, "light sheet must style the dropzone by unqualified testid"
    assert "background-color: #ffffff !important" in m.group(1), \
        f"light dropzone must stay #ffffff, got {m.group(1)!r}"
    print("round 6 dark dropzone OK")


def test_r6_dark_disabled_inputs_readable():
    """Dark mode: disabled inputs (Profile's Primary email +
    Username) render bright text on a dark panel, not very dark
    grey on dark. Round 10: the LIGHT sheet carries the same
    pin now (the light Profile measured 2.61:1 live — the old
    "light passes, untouched" premise was wrong), so the light
    assertion below pins the light fill instead of its absence."""
    dark = ui_design.DARK_CSS
    assert ".stApp input:disabled" in dark, \
        "dark sheet must carry a disabled-input rule"
    m = re.search(r"\.stApp input:disabled[^{]*\{([^}]*)\}", dark)
    assert m, "dark disabled-input rule must have a body"
    assert "color: #edefee !important" in m.group(1), \
        f"dark disabled inputs must be bright, got {m.group(1)!r}"
    assert "background-color: #2a2d2c !important" in m.group(1), \
        f"dark disabled inputs must sit on #2a2d2c, got {m.group(1)!r}"
    light = ui_design.DESIGN_SYSTEM_CSS
    assert ".stApp input:disabled" in light, \
        "light sheet must carry a disabled-input rule (round 10)"
    m = re.search(r"\.stApp input:disabled[^{]*\{([^}]*)\}", light)
    assert m, "light disabled-input rule must have a body"
    assert "-webkit-text-fill-color: #030303 !important" in m.group(1), \
        f"light disabled inputs must pin the fill dark, got {m.group(1)!r}"
    assert "background-color: #f3f3f3 !important" in m.group(1), \
        f"light disabled inputs must sit on #f3f3f3, got {m.group(1)!r}"
    print("round 6 dark disabled inputs OK")


# ---------------------------------------------------------------------------
# 5. Breadcrumb — file name only, or page name only
# ---------------------------------------------------------------------------

def test_r6_breadcrumb_file_only_or_page_only(_tmp_env):
    """The breadcrumb is the file name only when a file is loaded,
    and the page name only when none is loaded — never both. The
    5028aa3 change did not take effect live because the title span
    rendered unconditionally alongside the crumb (three segments:
    "Data Cleaner Studio / Prev... / messy_sales.csv (sa...").
    The brand span already says the workspace name."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    expand_rail(at)  # round 7: the sample button only renders pinned open
    # No file: title (page name) only, no crumb.
    left0 = topbar_left(at)
    assert "dcs-topbar-crumb" not in left0, \
        "with no file loaded there is no breadcrumb crumb"
    assert "dcs-topbar-title" in left0, \
        "with no file loaded the title span shows the page name"
    assert "Preview" in left0, \
        "with no file loaded the title must be the page name"
    assert left0.count("Data Cleaner Studio") == 1, \
        "the workspace name must appear once (the brand)"
    # Load the sample: crumb (file name) only, no title span.
    find_button(at, "Try the messy sample", key="sample_btn").click().run()
    assert not at.exception, f"exception loading sample: {at.exception}"
    at.run()  # the top bar lags one run behind the load
    left = topbar_left(at)
    assert 'dcs-topbar-crumb"> / messy_sales.csv (sample)' in left, \
        "the breadcrumb must be the loaded file's name"
    assert "dcs-topbar-title" not in left, \
        "with a file loaded the title span must not render"
    assert "Data Cleaner Studio / Data Cleaner Studio" not in left, \
        "the workspace name must not be duplicated in the breadcrumb"
    assert left.count("Data Cleaner Studio") == 1, \
        "the workspace name must appear once (the brand)"
    print("round 6 breadcrumb OK")


# ---------------------------------------------------------------------------
# 6. Branded loader on the sample path + transition coverage
# ---------------------------------------------------------------------------

def test_r6_branded_spinner_on_sample_path(_tmp_env, monkeypatch):
    """The sidebar sample button's load runs through
    branded_spinner — the loader HTML is produced on that path.
    (Round 4 proved the loader appears live; the last two checks
    saw only Streamlit's "Running..." — the code path is intact,
    and the 0.7s min hold is what makes it paint. This test pins
    the path, not the paint.)"""
    calls = []

    def _record(path, status, size="compact"):
        calls.append((str(path), status, size))
        return '<div class="dcs-loader">loader</div>'

    monkeypatch.setattr(ui_design, "loader_block_html", _record)
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    expand_rail(at)  # round 7: the sample button only renders pinned open
    find_button(at, "Try the messy sample", key="sample_btn").click().run()
    assert not at.exception, f"exception loading sample: {at.exception}"
    assert at.session_state.get("raw") is not None, \
        "the sample must load"
    assert calls, "branded_spinner must render the loader on the sample path"
    assert any(status == "Loading the sample file…"
               for _, status, _ in calls), \
        f"the sample loader must carry its status text, got {calls!r}"
    assert any("logo-loader" in path for path, _, _ in calls), \
        "the sample loader must use the loader logo variant"
    print("round 6 branded spinner on sample path OK")


def test_r6_transition_covers_flex_basis():
    """The rail transition list covers flex-basis — the property
    Streamlit's flex-row layout actually renders as the sidebar
    width — in both states and both themes. The old list covered
    only transform/min-width/max-width/width, so the width change
    never animated."""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            css = ui_design.rail_css(collapsed, theme)
            m = re.search(r"transition:\s*([^;]+);", css)
            assert m, f"rail CSS ({collapsed=}, {theme}) must transition"
            assert "flex-basis" in m.group(1), \
                f"rail CSS ({collapsed=}, {theme}) transition must cover " \
                f"flex-basis, got {m.group(1)!r}"
    print("round 6 transition covers flex-basis OK")
