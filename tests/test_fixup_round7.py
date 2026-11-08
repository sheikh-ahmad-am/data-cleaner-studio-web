"""Round-7 fix tests (2026-11-08): make the round-6 fixes actually take
effect live.

Why this file exists: 8b4dd04 passed its tests (464/9) and the live
check confirmed the build WAS serving — yet the collapsed rail still
showed vertical one-letter text, the expanded rows were still compact
pills, the toggle was still below the fold, the hover glide still
snapped, the Profile dark fields were still unreadable, and the
loader was still unseen. The root cause, proven against the REAL
Streamlit 1.66.1 DOM (Playwright + headless Chromium, local app
server — probes in ~/workspace/dcs-dom-check/, probe_dom*.py):

* Every widget root is a GRANDCHILD of the vertical block (inside
  its element container), and an intermediate plain div sits between
  stSidebarUserContent and stVerticalBlock — so every rail_css
  selector using ``>`` matched ZERO elements live. Round 6's jsdom
  proof was against a hand-built synthetic DOM, so the combinator
  errors passed the proof and failed live.
* The element containers size to content, so the nav buttons'
  width:100% resolved against ~100px boxes (compact pills).
* The toggle's absolute pin scrolled away with the content; sticky
  stopped 56px short; only FIXED held at the viewport bottom.
* The hover glide snapped because the content's width was ``auto`` —
  a transition from auto never interpolates.
* The status pill overlapped "Load your data" because Streamlit's
  markdown container carries a -16px bottom margin and the pill row
  overflows its block by ~17px (hidden in local mode only by the
  banner's gap; in cloud mode it overlapped live).
* The Profile dark rule and the branded loader were PROVEN WORKING
  in the real DOM (disabled inputs #edefee on #2a2d2c; the loader
  visible ~0.5s with loaded images on both sample paths) — the live
  misses are the theme-flip transient and checker frame timing, not
  code defects. Those two get pinning tests, not code changes.

Round 7 reverses round 6's "controls stay in the DOM while
collapsed" choice: the non-nav sidebar widgets do NOT render while
collapsed (app.py guards them on the rail state) — what is not in
the DOM cannot render vertically — with the corrected descendant
denylist as a backstop. Hovering a collapsed rail shows the nav
labels + toggle; the uploader, theme, status and slicers appear
when the rail is pinned open. (The round-6 test file was updated
for the reversal.)

Also in round 7, at the user's ask: the sky-blue info boxes are
gone (plain Supabase-style cards; the blue lived on the alert
container, rgba(28,131,255,0.1), around a white inner box), and the
standalone "Language / भाषा / زبان" section moved into the avatar
menu as a small language row.

Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_fixup_round7.py -q   (from project root)
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai_settings  # noqa: E402
import auth  # noqa: E402
import feat_status  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
import test_fixup_round6 as _r6  # noqa: E402  (helpers + AppTest setup)
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_fixup_round6.
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

DENYLISTED = ("stCheckbox", "stMarkdown", "stMultiSelect",
              "stDateInput", "stCaption", "stExpander",
              "stFileUploader", "stSelectbox", "stAlert",
              "stTextInput", "stRadio", "stNumberInput")


# ---------------------------------------------------------------------------
# 1. The denylist uses DESCENDANT selectors (the round-6 root cause)
# ---------------------------------------------------------------------------

def test_r7_denylist_is_descendant_not_child():
    """No rail_css selector may use ``>`` to reach a widget from the
    vertical block: the real 1.66.1 DOM has an intermediate plain
    div between stSidebarUserContent and stVerticalBlock, and every
    widget root is a grandchild of the block — so ``>`` matched zero
    elements live (the 8b4dd04 failure). All 12 denylisted testids
    must appear in descendant form."""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            css = ui_design.rail_css(collapsed, theme)
            assert "stSidebarUserContent > div[data-testid=" not in css, \
                f"rail CSS ({collapsed=}, {theme}) must not use the " \
                "broken stSidebarUserContent > stVerticalBlock chain"
            assert "> div[data-testid=\"stCheckbox\"]" not in css, \
                f"rail CSS ({collapsed=}, {theme}) must not use > " \
                "to reach a widget"
    for theme in ("light", "dark"):
        css = ui_design.rail_css(True, theme)
        for testid in DENYLISTED:
            assert (f'div[data-testid="stVerticalBlock"] '
                    f'div[data-testid="{testid}"]' in css), \
                f"collapsed {theme} rail must hide {testid} by a " \
                "descendant selector"
    print("round 7 denylist is descendant OK")


# ---------------------------------------------------------------------------
# 2. Full-width rows, fixed toggle pin, visible glide, native hide
# ---------------------------------------------------------------------------

def test_r7_expanded_rows_are_full_width():
    """The element containers under the sidebar vertical block are
    forced full-width in the wide states (expanded + hover), so the
    nav buttons' width:100% resolves against the sidebar width
    (199px rows in the real-DOM probe) instead of a content-sized
    ~100px box (the compact pills live). Scoped to the wide states
    only — the collapsed rail keeps its content-sized 16px icons."""
    for theme in ("light", "dark"):
        expanded = ui_design.rail_css(False, theme)
        assert "align-self: stretch" in expanded, \
            f"expanded {theme} rail must stretch element containers"
        collapsed = ui_design.rail_css(True, theme)
        # The collapsed sheet stretches containers ONLY under :hover
        # (the overlay) — never in the plain collapsed state.
        plain = [r for r in collapsed.split("}")
                 if "align-self: stretch" in r]
        assert plain, f"collapsed {theme} rail must stretch on hover"
        assert all(":hover" in r.split("{")[0] for r in plain), \
            f"collapsed {theme} rail must stretch containers only " \
            "on hover, not in the plain rail"
    print("round 7 full-width rows OK")


def test_r7_toggle_pin_is_fixed():
    """The toggle pin is FIXED in every state (never absolute or
    sticky): absolute scrolled away with the content (toggle at
    1409px in a 998px viewport live) and sticky stopped 56px
    short; fixed held at the viewport bottom (998px) at every
    scroll offset in the real-DOM probe. Width matches the state
    (60px collapsed, 260px expanded / hover)."""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            css = ui_design.rail_css(collapsed, theme)
            assert "position: fixed !important" in css, \
                f"rail CSS ({collapsed=}, {theme}) must pin the " \
                "toggle with position: fixed"
            assert "position: absolute !important;\n  bottom: 0" not in css, \
                f"rail CSS ({collapsed=}, {theme}) must not use the " \
                "absolute pin that scrolled away live"
    assert "width: 60px" in ui_design.rail_css(True, "light"), \
        "collapsed rail toggle pin must be 60px wide"
    assert "width: 260px" in ui_design.rail_css(False, "light"), \
        "expanded rail toggle pin must be 260px wide"
    print("round 7 toggle pin is fixed OK")


def test_r7_toggle_pin_targets_only_the_toggle():
    """The toggle pin selector must target the toggle's element
    container ONLY (its Streamlit key class
    ``st-key-dcs_rail_toggle``). A plain ``div:last-child``
    descendant selector is a live bug: it matches every div that
    is a last child of its parent anywhere in the vertical block,
    so it fixed EVERY sidebar widget to the viewport bottom and
    the whole sidebar collapsed into one overlapping stack —
    the expanded sidebar rendered empty except for the toggle
    (caught by the round-7 real-DOM probe)."""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            css = ui_design.rail_css(collapsed, theme)
            assert 'div[data-testid="stElementContainer"].st-key-dcs_rail_toggle' in css, \
                f"rail CSS ({collapsed=}, {theme}) must pin the " \
                "toggle by its key class"
            assert 'div[data-testid="stVerticalBlock"] div:last-child' not in css, \
                f"rail CSS ({collapsed=}, {theme}) must not use the " \
                "broad div:last-child pin selector"
    print("round 7 toggle pin targets only the toggle OK")


def test_r7_hover_glide_is_visibly_gradual():
    """The hover glide has two definite widths to interpolate
    between: the collapsed content carries an explicit 60px base
    width (a transition from auto never interpolates — the 8b4dd04
    snap), the hover width is 260px, and the ease is 250ms
    (real-DOM probe: 60 -> 213 -> 252 -> 259 -> 260px across 40ms
    samples — visibly gradual, not a snap)."""
    for theme in ("light", "dark"):
        css = ui_design.rail_css(True, theme)
        assert "width: 60px" in css, \
            f"collapsed {theme} rail must carry an explicit 60px " \
            "content base width for the glide"
        assert "250ms cubic-bezier(0.4,0,0.2,1)" in css, \
            f"collapsed {theme} rail must glide on the proven " \
            "250ms ease"
        assert 'section[data-testid="stSidebar"]:hover ' \
            'div[data-testid="stSidebarContent"]' in css, \
            f"collapsed {theme} rail must carry the hover overlay rule"
        assert "width: 260px" in css, \
            f"collapsed {theme} rail must expand to 260px on hover"
    print("round 7 hover glide is gradual OK")


def test_r7_native_collapse_control_is_hidden():
    """Streamlit's native top "«" collapse control is suppressed in
    both states and both themes: it hides the sidebar entirely to
    0px ("»" to restore) instead of returning to the 60px rail, and
    it fought the bottom toggle live (the label flipped while the
    sidebar stayed 260px). Only the bottom toggle + hover govern
    the rail now."""
    for collapsed in (True, False):
        for theme in ("light", "dark"):
            css = ui_design.rail_css(collapsed, theme)
            assert 'div[data-testid="stSidebarCollapseButton"]' in css, \
                f"rail CSS ({collapsed=}, {theme}) must target the " \
                "native collapse control"
            rule = [r for r in css.split("}")
                    if "stSidebarCollapseButton" in r]
            assert rule and "display: none !important" in rule[0], \
                f"rail CSS ({collapsed=}, {theme}) must hide the " \
                "native collapse control"
    print("round 7 native collapse control hidden OK")


# ---------------------------------------------------------------------------
# 3. Status pill no longer overlaps "Load your data"
# ---------------------------------------------------------------------------

def test_r7_status_pill_wrapper_compensates_markdown_margin():
    """The status pill's two rows live in ONE flex-column wrapper
    with 16px bottom padding: Streamlit's markdown container
    carries a -16px bottom margin, so without the padding the pill
    row overflows its block by ~17px and the next sidebar element
    ("Load your data" — no banner between them in cloud mode) is
    pulled up into it. The local-mode banner used to hide this;
    in cloud mode it overlapped live."""
    import inspect
    src = inspect.getsource(feat_status.render_status_pill)
    assert "flex-direction: column" in src, \
        "the status pill must wrap both rows in one flex-column div"
    assert "padding-bottom: 16px" in src, \
        "the status wrapper must carry 16px bottom padding to " \
        "compensate Streamlit's -16px markdown margin"
    assert src.count("dcs-micro-label") == 1, \
        "the status block must render its label once"
    print("round 7 status pill wrapper OK")


# ---------------------------------------------------------------------------
# 4. No sky-blue info boxes anywhere
# ---------------------------------------------------------------------------

def test_r7_no_sky_blue_on_info_boxes():
    """Both stylesheets neutralise the info (blue) alert variant:
    the blue lived on the alert container (rgba(28,131,255,0.1))
    around a white inner box. The rule is scoped to alerts whose
    content is the Info variant (stAlertContentInfo) — success /
    warning / error keep their own colours. The container becomes
    a plain card (white / #e8e8e8 light, #232625 / #2e2e2e dark)
    and the inner box loses its own border, so there is exactly
    one hairline and no blue anywhere."""
    for theme, (bg, border) in (("light", ("#ffffff", "#e8e8e8")),
                                ("dark", ("#232625", "#2e2e2e"))):
        css = ui_design.theme_css(theme)
        assert "stAlertContentInfo" in css, \
            f"{theme} sheet must target the Info alert variant"
        assert f"background-color: {bg} !important" in css, \
            f"{theme} sheet must paint the info container {bg}"
        assert f"border: 1px solid {border} !important" in css, \
            f"{theme} sheet must give the info container a {border} " \
            "hairline"
        # The blue itself must not survive as an effective
        # background anywhere in the sheet.
        assert "rgba(28, 131, 255" not in css, \
            f"{theme} sheet must not carry the sky-blue alert fill"
    print("round 7 no sky-blue on info boxes OK")


def test_r7_info_card_renders_plain_card():
    """ui_design.info_card renders a plain .dcs-card (the
    Supabase-style card: white / #e8e8e8 light, #232625 / #2e2e2e
    dark) with the text escaped and no blue, no icon, no colour.
    (The docstring names the sky-blue it removes, so the pin is on
    the rendered markup, not on the word "sky".)"""
    import inspect
    src = inspect.getsource(ui_design.info_card)
    assert '<div class="dcs-card">' in src, \
        "info_card must render a plain .dcs-card div"
    assert "html.escape" in src, \
        "info_card must escape its text"
    # No inline style at all on the card: the colours come from the
    # .dcs-card class in the stylesheet, never an inline blue.
    body = src.split('"""', 2)[-1] if src.count('"""') >= 2 else src
    assert "style=" not in body, \
        "info_card must not carry any inline style (no inline blue)"
    print("round 7 info_card OK")


def test_r7_named_info_calls_use_plain_cards():
    """The four info boxes the user named (welcome banner, no
    recent files, shared-dashboard empty state, login-screen local
    banner) plus the sidebar local-mode banner no longer call
    st.info — they render plain cards. The text is unchanged."""
    app_src = (PROJECT_ROOT / "app.py").read_text()
    assert 'ui_design.info_card(\n            "This shared dashboard ' \
        'has no chart data saved in it.")' in app_src, \
        "the shared-dashboard empty state must use info_card"
    assert "ui_design.info_card(banner)" in app_src, \
        "the login-screen local banner must use info_card"
    assert "ui_design.info_card(_banner, st_module=st.sidebar)" in app_src, \
        "the sidebar local banner must use info_card"
    tut_src = (PROJECT_ROOT / "feat_tutorial.py").read_text()
    assert "ui_design.info_card(\"First time here?" in tut_src, \
        "the welcome banner must use info_card"
    assert "st.info(" not in tut_src, \
        "feat_tutorial must not call st.info anywhere"
    share_src = (PROJECT_ROOT / "feat_share.py").read_text()
    assert "_info_card(\"No recent files yet." in share_src, \
        "the no-recent-files box must use info_card"
    print("round 7 named info calls use plain cards OK")


# ---------------------------------------------------------------------------
# 5. Language lives in the avatar menu, not on the page
# ---------------------------------------------------------------------------

def test_r7_standalone_language_section_is_gone():
    """app.py no longer calls render_language_picker: the standalone
    "Language / भाषा / زبان" section (subheader + full-width
    dropdown on the Preview tab) is gone from the page."""
    app_src = (PROJECT_ROOT / "app.py").read_text()
    assert "render_language_picker" not in app_src, \
        "app.py must not call render_language_picker anywhere"
    # The heading string survives only in the removal comment above
    # the workspace toggle — it must not be rendered as a section.
    assert 'st.subheader("Language' not in app_src, \
        "app.py must not render a Language subheader"
    print("round 7 standalone Language section gone OK")


def test_r7_avatar_menu_carries_language_control():
    """The avatar menu carries the language control: a small
    "Language" row with the same selectbox (same key
    "n_lang_pick", same three options English / हिन्दी / اردو) and
    the same save (settings.json + "n_lang_data"), so selecting a
    language still changes the app language."""
    import inspect
    src = inspect.getsource(ui_design.render_avatar_menu)
    assert "Language" in src, \
        "the avatar menu must carry a Language row"
    assert "_render_language_menu_selectbox" in src, \
        "the avatar menu must render the language selectbox"
    helper = inspect.getsource(ui_design._render_language_menu_selectbox)
    assert '"n_lang_pick"' in helper, \
        "the menu language control must keep the n_lang_pick key"
    for label in ("English", "हिन्दी", "اردو"):
        assert label in helper, \
            f"the menu language control must keep the {label!r} option"
    assert "n_lang_data" in helper, \
        "the menu language control must keep writing n_lang_data"
    assert "save_settings" in helper, \
        "the menu language control must keep saving settings.json"
    print("round 7 avatar menu carries language OK")


def test_r7_language_switch_still_works(_tmp_env):
    """End to end: the avatar menu's language selectbox switches
    the app language — picking हिन्दी writes n_lang_data = "hi"
    (and settings.json), exactly as the standalone picker did."""
    at = AppTest.from_file(APP)
    at.run()
    _r6.signup(at, "alice2")
    lang = [s for s in at.selectbox if s.key == "n_lang_pick"]
    assert lang, "the avatar menu must render the n_lang_pick selectbox"
    assert [o for o in lang[0].options] == ["English", "हिन्दी", "اردو"], \
        "the menu language control must offer the same three options"
    lang[0].set_value("हिन्दी").run()
    assert not at.exception, f"exception switching language: {at.exception}"
    assert at.session_state.get("n_lang_data") == "hi", \
        "picking हिन्दी must set n_lang_data to 'hi'"
    assert ai_settings.load_settings().get("language") == "hi", \
        "picking हिन्दी must persist to settings.json"
    # And the standalone section is gone from the page itself.
    assert not any("Language / भाषा / زبان" in v for v in _r6.vals(at.markdown)), \
        "the Preview tab must not show the standalone Language section"
    print("round 7 language switch works OK")


# ---------------------------------------------------------------------------
# 6. Collapsed rail shows only nav + toggle (do-not-render, AppTest)
# ---------------------------------------------------------------------------

def test_r7_collapsed_rail_has_no_vertical_text_widgets(_tmp_env):
    """Collapsed, the sidebar carries ONLY the 12 nav icons + the
    toggle — no theme selectbox, status pill, banner, uploader,
    sample button, client-mode checkbox, expanders or slicers in
    the DOM at all. (The CSS denylist is the backstop; the guard
    is the fix.) Pinned open, they all come back."""
    at = AppTest.from_file(APP)
    at.run()
    _r6.signup(at, "alice3")
    assert at.session_state.get("dcs_rail_collapsed") is True
    assert not list(at.sidebar.selectbox)
    assert not list(at.sidebar.file_uploader)
    assert not list(at.sidebar.checkbox)
    assert not list(at.sidebar.expander)
    assert not list(at.sidebar.multiselect)
    assert not list(at.sidebar.text_input)
    assert not any(b.label == "Try the messy sample" for b in at.button)
    assert not any("Status" in v for v in _r6.vals(at.sidebar.markdown)
                   if "dcs-micro-label" in v), \
        "collapsed rail must not render the Status micro-label"
    _r6.expand_rail(at)
    assert list(at.sidebar.selectbox), "pinned open must show the theme"
    assert list(at.sidebar.file_uploader), "pinned open must show upload"
    assert list(at.sidebar.expander), "pinned open must show expanders"
    print("round 7 collapsed rail has no vertical-text widgets OK")


def test_r7_slicers_still_filter_when_collapsed(_tmp_env):
    """The slicers keep filtering while collapsed: the "FILTERS
    (SLICERS)" label and the widgets do not render when collapsed
    (no vertical letters), and the filtering reads the last-picked
    values from session state instead of rendering the widgets —
    so collapsing must not reset the filter to everything. (The
    multiselects themselves only exist once data is cleaned, so
    the label is the collapsed-rail pin here; the value read is
    pinned on the source.)"""
    at = AppTest.from_file(APP)
    at.run()
    _r6.signup(at, "alice4")
    _r6.expand_rail(at)
    _r6.find_button(at, "Try the messy sample", key="sample_btn").click().run()
    assert at.session_state.get("raw") is not None, "the sample must load"
    # The slicer label renders once data is loaded (expanded).
    assert any("Filters (slicers)" in v for v in _r6.vals(at.sidebar.markdown)), \
        "the slicer label must render when the rail is pinned open"
    # Collapse: the label (and any slicer widgets) must be gone.
    _r6.find_button_by_key(at, "dcs_rail_toggle").click().run()
    assert at.session_state.get("dcs_rail_collapsed") is True
    assert not any("Filters (slicers)" in v
                   for v in _r6.vals(at.sidebar.markdown)), \
        "collapsed rail must not render the slicer label"
    assert not list(at.sidebar.multiselect), \
        "collapsed rail must not render slicer widgets"
    # The filtering reads persisted values when collapsed.
    # (A plain non-widget key: the widget's own key is cleaned up
    # the moment the widget unmounts, so reading it would reset
    # the filter the run after a collapse.)
    app_src = (PROJECT_ROOT / "app.py").read_text()
    assert 'st.session_state.get(_persist_key, _all_vals)' in app_src, \
        "collapsed slicers must read the last-picked values from " \
        "a persistent session-state key"
    assert 'st.session_state.get(\n                    _dpersist_key' in app_src, \
        "the collapsed date slicer must read its persisted range"
    # Re-expand: the label comes back.
    _r6.expand_rail(at)
    assert any("Filters (slicers)" in v for v in _r6.vals(at.sidebar.markdown)), \
        "the slicer label must return when the rail re-opens"
    print("round 7 slicers still filter when collapsed OK")


# ---------------------------------------------------------------------------
# 7. Pins for the two items proven working live (no code change)
# ---------------------------------------------------------------------------

def test_r7_dark_disabled_inputs_rule_still_present():
    """Pin: the dark disabled-input rule (Profile's read-only
    Primary email + Username) is still in the dark sheet with the
    exact values the real-DOM probe measured live (#edefee text on
    #2a2d2c). The live miss was the theme-flip transient, not the
    rule — the rule must not regress."""
    assert ".stApp input:disabled" in ui_design.DARK_CSS, \
        "dark sheet must carry the disabled-input rule"
    assert "color: #edefee !important" in ui_design.DARK_CSS, \
        "dark disabled inputs must pin bright #edefee text"
    assert "background-color: #2a2d2c !important" in ui_design.DARK_CSS, \
        "dark disabled inputs must pin the #2a2d2c panel"
    print("round 7 dark disabled-input rule pinned OK")


def test_r7_branded_spinner_still_on_both_sample_paths():
    """Pin: branded_spinner is still entered on both sample paths
    (sidebar button + Dashboard empty-state CTA) — the loader was
    proven visible in the real DOM on both (~0.5s, images loaded),
    so the live miss was checker frame timing, not the path."""
    app_src = (PROJECT_ROOT / "app.py").read_text()
    assert app_src.count('with branded_spinner("Loading the sample file…")') >= 2, \
        "both sample paths must run through branded_spinner"
    print("round 7 branded spinner on both sample paths OK")
