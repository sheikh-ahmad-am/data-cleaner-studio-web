"""Fix-up round 5 — the five live-check gaps + sidebar motion/tooltip
chrome + the Supabase Preferences rebuild (2026-11-08).

The live check (browser task 501904e6, 878x573px) found five gaps in
the rail rebuild; the user then added the sidebar's motion + tooltip
chrome (from his Supabase screen recording) and a Preferences page
matching Supabase's account page. This file pins what AppTest can
pin — the CSS rules, the widget wiring, and the state that must
survive a collapse — and the live visual check afterwards is the
only proof of the look itself:

  Gap 1 — collapsed rail shows ONLY nav + toggle: a CSS safety net
  hides every non-button sidebar child (client-mode checkbox,
  auto-refresh expander, slicers, toasts) while the widgets stay
  mounted, so their values survive a collapse/expand cycle.
  Gap 2 — the toggle is pinned to the rail's bottom (flex column +
  margin-top:auto + sticky) and is the LAST sidebar button, in
  both states; the collapsed buttons are 36px so 12 icons + toggle
  fit a 573px viewport and the scroll offset clamps to ~0.
  Gap 3 — expanded nav rows are full-width rows (the old
  `button[kind="secondary"]` selector was dead — Streamlit renders
  no `kind` attribute).
  Gap 4 — the uploader's format line wraps instead of truncating.
  Gap 5 — the top bar's breadcrumb is the file name only (no
  duplicated workspace name), the columns give the Upload pill
  room, and the breadcrumb spans shrink + ellipsize instead of
  overlapping the search hint.
  Addition 1 — the rail animates on a 200ms ease; the tooltip is
  Supabase's dark rounded pill, white text, with NO shortcut chips
  (the app has no G-then-X shortcuts).
  Addition 2 — the Profile page is Supabase's Preferences page in
  layout: sub-nav + bordered cards, First/Last name + Save wired
  to the real display name, Sign-in methods, Appearance (Light/Dark
  only — no System row), and nothing the app does not have (no
  Access Tokens, no Audit Logs, no Upgrade to Pro).

Run ONLY this file:  .test-venv-rebuild/bin/python -m pytest
tests/test_fixup_round5.py -q   (from project root)
"""

import inspect
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import ai_settings  # noqa: E402
import auth  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_profile.py."""
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    yield tmp_path


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


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


def expand_rail(at):
    """Open the sidebar rail (it starts collapsed)."""
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert not at.exception, f"exception expanding rail: {at.exception}"


def signup(at, username, password="password123"):
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


def goto_profile(at):
    """Open the Profile section from the avatar menu's Account action."""
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    radio = next(r for r in at.radio if r.label == "Section")
    assert radio.value == "Profile", \
        f"section switcher should read Profile, got {radio.value!r}"


def upload_sample(at, username):
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([("messy_sales.csv", SAMPLE.read_bytes(), "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert storage.list_files(username, "uploads") == ["messy_sales.csv"], \
        "upload must be saved in the user's uploads/"


def _app_literal():
    """The app.py DESIGN_SYSTEM_CSS literal (the pin tests' pattern)."""
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r'DESIGN_SYSTEM_CSS = """<style>(.*?)</style>"""', source, re.DOTALL)
    assert match, "DESIGN_SYSTEM_CSS block missing from app.py"
    return "<style>" + match.group(1) + "</style>"


# ---------------------------------------------------------------------------
# Gap 1 — collapsed rail shows ONLY nav + toggle
# ---------------------------------------------------------------------------

def test_gap1_collapsed_hides_non_nav_sidebar_content():
    """The denylist: in the collapsed rail every non-button direct
    child of the vertical block is hidden by an explicit testid
    list — the client-mode checkbox, the status pill, the banner,
    the uploader, the expanders, the slicers and any sidebar
    toast. Only the nav-button and toggle wrappers stay visible.
    The old :has() safety net is gone: it matched the nav buttons
    too (their direct child is the intermediate help-wrapper div,
    not another stButton div) and never took effect live. The rule
    is collapsed-only: the expanded rail shows every control."""
    denylisted = ("stCheckbox", "stMarkdown", "stMultiSelect",
                  "stDateInput", "stCaption", "stExpander",
                  "stFileUploader", "stSelectbox", "stAlert",
                  "stTextInput", "stRadio", "stNumberInput")
    for theme in ("light", "dark"):
        css = ui_design.rail_css(collapsed=True, theme=theme)
        assert ":has(" not in css, \
            f"collapsed {theme} rail CSS must not use :has() at all"
        for testid in denylisted:
            assert (f'div[data-testid="{testid}"]' in css), \
                f"collapsed {theme} rail CSS must hide {testid}"
        assert "display: none !important" in css, \
            f"collapsed {theme} rail denylist must hide its targets"
        # Nav + toggle wrappers are NOT denylisted: no display:none
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
    for theme in ("light", "dark"):
        css = ui_design.rail_css(collapsed=False, theme=theme)
        assert "display: none !important" not in css, \
            f"expanded {theme} rail must show every sidebar control"
    print("gap 1 collapsed denylist OK")


def test_gap1_client_mode_survives_collapse(_tmp_env):
    """The client-mode checkbox stays mounted when the rail
    collapses (the CSS hides it, the widget is not unmounted), so
    its value — and the client_mode data key — survive a
    collapse/expand cycle instead of resetting."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    cb = next(c for c in at.sidebar.checkbox
              if c.label == "Client mode (simple view)")
    cb.set_value(True).run()
    assert not at.exception, f"exception enabling client mode: {at.exception}"
    assert at.session_state.get("client_mode") is True, \
        "enabling the checkbox must set client_mode"
    at.session_state["dcs_rail_collapsed"] = True
    at.run()
    assert not at.exception, f"exception collapsing rail: {at.exception}"
    cb2 = next(c for c in at.sidebar.checkbox
               if c.label == "Client mode (simple view)")
    assert cb2.value is True, \
        "collapsing the rail must not reset the client-mode checkbox"
    assert at.session_state.get("client_mode") is True, \
        "collapsing the rail must not reset client_mode"
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    cb3 = next(c for c in at.sidebar.checkbox
               if c.label == "Client mode (simple view)")
    assert cb3.value is True, \
        "re-expanding the rail must restore the checkbox checked"
    print("gap 1 client mode survives collapse OK")


def test_gap1_slicer_survives_collapse(_tmp_env):
    """The slicers stay mounted when the rail collapses, so a
    picked filter value survives a collapse/expand cycle instead
    of resetting to all values."""
    import pandas as pd

    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    df = pd.read_csv(SAMPLE)
    at.session_state["raw"] = df
    at.session_state["clean"] = df
    at.session_state["actions"] = []
    at.session_state["kpis"] = []
    at.session_state["source_name"] = "messy_sales.csv"
    at.session_state["source_kind"] = "upload"
    at.run()
    assert not at.exception, f"exception loading data: {at.exception}"
    slicer = next(m for m in at.sidebar.multiselect
                  if m.label == "Category")
    slicer.set_value(["Electronics"]).run()
    assert not at.exception, f"exception picking a slice: {at.exception}"
    at.session_state["dcs_rail_collapsed"] = True
    at.run()
    assert not at.exception, f"exception collapsing rail: {at.exception}"
    slicer2 = next(m for m in at.sidebar.multiselect
                   if m.label == "Category")
    assert list(slicer2.value) == ["Electronics"], \
        "collapsing the rail must not reset the slicer"
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    slicer3 = next(m for m in at.sidebar.multiselect
                   if m.label == "Category")
    assert list(slicer3.value) == ["Electronics"], \
        "re-expanding the rail must restore the slicer value"
    print("gap 1 slicer survives collapse OK")


# ---------------------------------------------------------------------------
# Gap 2 — toggle pinned to the rail's bottom + scroll carryover
# ---------------------------------------------------------------------------

def test_gap2_toggle_pinned_to_rail_bottom():
    """The toggle pin is per-state. Collapsed-and-not-hovered keeps
    margin-top:auto + sticky (proven live — the collapsed rail is
    short, so the flex column has free space). Expanded and
    hover-expanded use an ABSOLUTE pin at the scroll container's
    bottom — margin-top:auto has no free space when the content
    overflows, and sticky did not hold live in the expanded state.
    The vertical block carries bottom padding so the last rows are
    not covered by the pinned toggle. The toggle wrapper carries
    the sidebar surface so scrolling rows never show through it."""
    for theme in ("light", "dark"):
        collapsed_css = ui_design.rail_css(True, theme)
        assert "margin-top: auto !important" in collapsed_css, \
            f"collapsed {theme} rail must pin the toggle with " \
            "margin-top:auto"
        assert "position: sticky !important" in collapsed_css, \
            f"collapsed {theme} rail must stick the toggle"
        assert "bottom: 0 !important" in collapsed_css, \
            f"collapsed {theme} rail must stick the toggle to the bottom"
        assert "position: absolute !important" in collapsed_css, \
            f"collapsed {theme} rail must carry the absolute pin for " \
            "the hover-expanded state"
        assert "padding-bottom: 56px !important" in collapsed_css, \
            f"collapsed {theme} rail must pad the vertical block for " \
            "the pinned toggle"
        expanded_css = ui_design.rail_css(False, theme)
        assert "position: absolute !important" in expanded_css, \
            f"expanded {theme} rail must pin the toggle absolutely"
        assert "bottom: 0 !important" in expanded_css, \
            f"expanded {theme} rail must pin the toggle to the bottom"
        assert "padding-bottom: 56px !important" in expanded_css, \
            f"expanded {theme} rail must pad the vertical block for " \
            "the pinned toggle"
    # The toggle wrapper carries the sidebar surface (light #fdfdfd,
    # dark #1b1d1c) so scrolling rows never show through it.
    assert "background: #fdfdfd !important" in ui_design.rail_css(
        True, "light")
    assert "background: #1b1d1c !important" in ui_design.rail_css(
        True, "dark")
    print("gap 2 toggle pinned OK")


def test_gap2_collapsed_fits_short_viewport():
    """12 icons + toggle at 36px with 4px gaps and 6px content
    padding fit a 573px viewport (13 x 36 + 12 x 4 + 12 = 528px),
    so collapsing from a scrolled-down expanded sidebar clamps the
    scroll offset to ~0 instead of reopening on the client-mode
    text."""
    css = ui_design.rail_css(collapsed=True, theme="light")
    assert "height: 36px !important" in css, \
        "collapsed rail buttons must be 36px"
    assert "gap: 4px !important" in css, "collapsed rail gap must be 4px"
    assert "padding-left: 6px !important" in css
    total = 13 * 36 + 12 * 4 + 12
    assert total <= 573, f"collapsed rail content ({total}px) must fit 573px"
    print("gap 2 collapsed fits short viewport OK")


def test_gap2_toggle_is_last_sidebar_button(_tmp_env):
    """The toggle renders after every other sidebar control (the
    slicers are last in script order before it), so the rail CSS's
    last-child pin targets the toggle — in both states."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    # Collapse (signup's helper expands the rail): nav + toggle only.
    at.session_state["dcs_rail_collapsed"] = True
    at.run()
    assert not at.exception, f"exception collapsing rail: {at.exception}"
    assert at.session_state.get("dcs_rail_collapsed") is True
    collapsed_buttons = list(at.sidebar.button)
    assert collapsed_buttons, "collapsed rail must have sidebar buttons"
    assert collapsed_buttons[-1].key == "dcs_rail_toggle", \
        "the toggle must be the last sidebar button (collapsed)"
    # Expanded: uploader, sample button and the rest render before it.
    expand_rail(at)
    expanded_buttons = list(at.sidebar.button)
    assert expanded_buttons[-1].key == "dcs_rail_toggle", \
        "the toggle must be the last sidebar button (expanded)"
    print("gap 2 toggle is last sidebar button OK")


# ---------------------------------------------------------------------------
# Gap 3 — expanded nav rows are full-width rows
# ---------------------------------------------------------------------------

def test_gap3_expanded_nav_rows_full_width():
    """The light sheet's full-width rule must use the selectors
    Streamlit 1.66.1 actually renders (the wrapper div + the button's
    data-testid) — the old `button[kind="secondary"]` selector was
    dead, because the rendered <button> carries no `kind` attribute,
    so the expanded nav rows rendered as compact pills. The dark
    sheet's plain-`button` rule already matched and stays."""
    css = ui_design.DESIGN_SYSTEM_CSS
    assert ('section[data-testid="stSidebar"] div[data-testid="stButton"] {\n'
            "  width: 100% !important; }" in css), \
        "light sheet must force the sidebar button wrapper full-width"
    # The button rule is merged into the sidebar base rule (one rule,
    # one selector — no duplicate): its body must carry the width
    # and the left alignment.
    rule = ('section[data-testid="stSidebar"] div[data-testid="stButton"]'
            ' button[data-testid="stBaseButton-secondary"]')
    body = re.search(re.escape(rule) + r"\s*\{([^}]*)\}", css)
    assert body, "light sheet must have the sidebar button rule"
    assert "width: 100% !important" in body.group(1), \
        "light sheet must force sidebar secondary buttons full-width"
    assert "justify-content: flex-start !important" in body.group(1), \
        "light sheet must left-align sidebar secondary buttons"
    assert ('section[data-testid="stSidebar"] div[data-testid="stButton"]'
            ' > button[data-testid="stBaseButton-secondary"] {' not in css), \
        "the child-combinator sidebar button rule must be gone — " \
        "it matched 0 buttons (the help-wrapper div sits between " \
        "the stButton div and the <button>)"
    assert ('section[data-testid="stSidebar"] div[data-testid="stButton"]'
            ' > button[kind="secondary"] {' not in css), \
        "the dead kind=\"secondary\" full-width rule must be gone"
    dark = ui_design.DARK_CSS
    assert ('section[data-testid="stSidebar"] div[data-testid="stButton"]'
            ' button {\n  width: 100%; justify-content: flex-start;'
            in dark), "dark sheet must keep its full-width sidebar rule"
    assert _app_literal() == ui_design.DESIGN_SYSTEM_CSS, \
        "app.py literal must stay the verbatim light stylesheet"
    print("gap 3 expanded nav rows full-width OK")


# ---------------------------------------------------------------------------
# Gap 4 — uploader format line wraps
# ---------------------------------------------------------------------------

def test_gap4_uploader_format_line_wraps():
    """The uploader's instructions element must wrap instead of
    truncating at the sidebar's right edge — in both themes, and in
    the app.py literal."""
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS),
                      ("app.py literal", _app_literal())):
        assert "stFileUploaderDropzoneInstructions" in css, \
            f"{name} sheet must style the uploader instructions element"
        assert "white-space: normal !important" in css, \
            f"{name} sheet must let the format line wrap"
        assert "overflow: visible !important" in css, \
            f"{name} sheet must not clip the wrapped format line"
    print("gap 4 uploader format line wraps OK")


# ---------------------------------------------------------------------------
# Gap 5 — top bar at narrow width
# ---------------------------------------------------------------------------

def test_gap5_topbar_breadcrumb_not_duplicated(_tmp_env):
    """The breadcrumb is the loaded file's name only: the top bar
    already renders the workspace name + the current screen, so the
    old crumb duplicated it ("Data Cleaner Studio / Data Cleaner
    Studio / Preview")."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    # The top-bar HTML is the markdown element carrying the
    # <div class="dcs-topbar-left"> — not the injected stylesheet,
    # which also mentions the class name.
    topbar0 = next(v for v in vals(at.markdown)
                   if '<div class="dcs-topbar-left">' in v)
    assert "dcs-topbar-crumb" not in topbar0, \
        "with no file loaded there is no breadcrumb crumb"
    upload_sample(at, "alice1")
    # The top bar renders before the uploader is processed in the
    # upload run, so its breadcrumb lags one run behind the file
    # name — one more run lets it catch up.
    at.run()
    assert not at.exception, f"exception after upload: {at.exception}"
    topbar = next(v for v in vals(at.markdown)
                  if '<div class="dcs-topbar-left">' in v)
    assert 'dcs-topbar-crumb"> / messy_sales.csv' in topbar, \
        "the breadcrumb must be the loaded file's name"
    assert "Data Cleaner Studio / Data Cleaner Studio" not in topbar, \
        "the workspace name must not be duplicated in the breadcrumb"
    assert topbar.count("Data Cleaner Studio") == 1, \
        "the workspace name must appear once (the brand)"
    print("gap 5 top-bar breadcrumb OK")


def test_gap5_topbar_columns_and_guards():
    """The top-bar columns give the Upload pill room (the old
    0.85-wide column truncated its label to "U…"), and the
    breadcrumb spans shrink + ellipsize instead of overflowing
    their column onto the search hint — in both themes."""
    source = inspect.getsource(ui_design.topbar)
    assert "[2.3, 1.9, 1.1, 0.35, 0.45]" in source, \
        "top-bar columns must be [2.3, 1.9, 1.1, 0.35, 0.45]"
    assert "[2.6, 2.0, 0.85, 0.4, 0.5]" not in source, \
        "the old cramped top-bar columns must be gone"
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS)):
        assert ".dcs-topbar-left > span { min-width: 0; overflow: hidden;" \
            in css, f"{name} sheet must let the breadcrumb spans shrink"
        assert "text-overflow: ellipsis" in css, \
            f"{name} sheet must ellipsize the breadcrumb instead of " \
            "overlapping the search hint"
    print("gap 5 top-bar columns and guards OK")


# ---------------------------------------------------------------------------
# Addition 1 — sidebar motion + tooltip chrome
# ---------------------------------------------------------------------------

def test_add1_rail_animates_200ms_ease():
    """The rail animates between 60px and 260px on a 200ms ease
    (the dashboard's ~0.2s slide), not a snap — in both states."""
    for collapsed in (True, False):
        css = ui_design.rail_css(collapsed, "light")
        assert "200ms cubic-bezier(0.22,1,0.36,1)" in css, \
            f"rail CSS ({collapsed=}) must animate on a 200ms ease"
        assert "300ms" not in css, \
            f"rail CSS ({collapsed=}) must not keep the old 300ms snap"
    print("addition 1 rail animates 200ms OK")


def test_add1_tooltip_chrome_dark_in_both_themes():
    """The tooltip is Supabase's dark rounded pill, white text, in
    both themes — in the sheets and in the app.py literal. The pill
    is dark in both themes by design, but each theme uses its own
    near-black (#030303 light ink in the light sheet + literal,
    #1b1d1c dark surface in the dark sheet) so no dark token leaks
    into the light stylesheet."""
    for name, css, bg in (("light", ui_design.DESIGN_SYSTEM_CSS, "#030303"),
                          ("dark", ui_design.DARK_CSS, "#1b1d1c"),
                          ("app.py literal", _app_literal(), "#030303")):
        assert 'div[data-testid="stTooltipContent"] {' in css, \
            f"{name} sheet must style the tooltip content"
        assert f"background-color: {bg} !important" in css, \
            f"{name} tooltip must be dark ({bg})"
        assert "color: #ffffff !important" in css, \
            f"{name} tooltip text must be white"
        assert "border-radius: 8px !important" in css, \
            f"{name} tooltip must be rounded"
    print("addition 1 tooltip chrome OK")


def test_add1_no_shortcut_chips():
    """No shortcut chips anywhere: the app has no G-then-X
    navigation shortcuts, so no tooltip may show one. The nav help
    text is "Go to <Page>" with no bracketed keys."""
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS)):
        assert "[G]" not in css and "kbd" not in css, \
            f"{name} sheet must not carry shortcut chips"
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "ui_design.sidebar_nav([('preview', 'Preview'),\n"
        "                       ('clean', 'Clean')], active='preview',\n"
        "                      collapsed=True)\n")
    at.run()
    assert not at.exception, f"sidebar_nav exception: {at.exception}"
    for b in at.button:
        if (b.key or "").startswith("dcs_nav_"):
            assert b.help.startswith("Go to "), \
                f"nav tooltip must read 'Go to <Page>', got {b.help!r}"
            assert "[" not in (b.help or ""), \
                f"nav tooltip must not carry a shortcut chip: {b.help!r}"
    print("addition 1 no shortcut chips OK")


# ---------------------------------------------------------------------------
# Addition 2 — Profile, same as Supabase, same place
# ---------------------------------------------------------------------------

def test_add2_profile_subnav_anchors_and_appearance(_tmp_env):
    """The Preferences page has the left sub-nav (Back + the
    sections this app genuinely has) with anchor links to the
    section headings, and an Appearance card whose theme radio is
    Light/Dark only — no System row, because the app cannot
    genuinely follow the OS preference."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    upload_sample(at, "alice1")
    goto_profile(at)
    md = " ".join(vals(at.markdown))
    for anchor in ("profile-information", "profile-signin",
                   "profile-appearance", "profile-storage",
                   "profile-download", "profile-logout", "profile-danger"):
        assert f'id="{anchor}"' in md, \
            f"Profile section heading {anchor!r} missing its id"
    # The sub-nav links to every section except Preferences itself:
    # that row is the current page (a highlighted span, not a link).
    for anchor in ("profile-signin", "profile-appearance",
                   "profile-storage", "profile-download",
                   "profile-logout", "profile-danger"):
        assert f'href="#{anchor}"' in md, \
            f"sub-nav must link to section {anchor!r}"
    assert ('<span class="dcs-profile-subnav-link '
            'dcs-profile-subnav-active">Preferences</span>' in md), \
        "Preferences must be the highlighted current page in the sub-nav"
    assert 'href="#profile-information"' not in md, \
        "Preferences must not link to itself"
    assert 'dcs-section-heading">Preferences<' in md, \
        "the page heading must be Preferences, not Profile"
    assert any(b.label == "← Back to dashboard" for b in at.button), \
        "sub-nav Back button missing"
    radios = [r for r in at.radio if r.key == "profile_theme_radio"]
    assert len(radios) == 1, "Appearance must have exactly one theme radio"
    # AppTest reports the radio's display labels (the format_func's
    # "Light" / "Dark"), not the raw values.
    assert list(radios[0].options) == ["Light", "Dark"], \
        "Appearance theme radio must be Light/Dark only (no System)"
    assert "System" not in list(radios[0].options), \
        "Appearance must not offer a System row"
    assert find_text_input(at, "Primary email").disabled, \
        "Primary email must be a disabled (read-only) field"
    assert find_text_input(at, "Username").disabled, \
        "Username must be a disabled (read-only) field"
    print("addition 2 Profile sub-nav and Appearance OK")


def test_add2_profile_first_last_name_split(_tmp_env):
    """First / Last name are the display name split on the first
    whitespace (there are no first/last-name columns); Save
    recombines them through the existing set_display_name."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    upload_sample(at, "alice1")
    # Seed a two-word display name, then reopen Profile: the split
    # must show First="Alice", Last="A".
    auth.set_display_name(at.session_state["current_user"]["id"], "Alice A")
    at.session_state["current_user"]["display_name"] = "Alice A"
    goto_profile(at)
    assert find_text_input(at, "First name").value == "Alice", \
        "First name must be the display name's first word"
    assert find_text_input(at, "Last name").value == "A", \
        "Last name must be the rest of the display name"
    # Editing Last name and saving recombines through set_display_name.
    find_text_input(at, "Last name").set_value("B").run()
    assert not at.exception, f"exception editing last name: {at.exception}"
    find_button(at, "Save").click().run()
    assert not at.exception, f"exception saving name: {at.exception}"
    assert at.session_state["current_user"].get("display_name") == "Alice B", \
        "Save must recombine First + Last into the display name"
    print("addition 2 Profile First/Last split OK")
