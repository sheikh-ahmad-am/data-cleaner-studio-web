"""Anti-layout-shift skeleton + section-rhythm tests for ui_loading.py.

Run: .test-venv-refine-b/bin/python tests/test_loading.py
       (from the project root)
Also pytest-collectable (plain asserts, no fixtures). No Streamlit
server needed — the HTML builders are pure functions, and the render
wrappers are exercised with a FakeSt stub.

Covers:
  (a) skeleton has fixed heights (20px title bar, 14px lines) and the
      same card padding as a loaded .dcs-card, so content does not jump
  (b) skeleton_table has a fixed 36px header and fixed 40px rows
  (c) skeleton_chart has a fixed height (320px default)
  (d) every skeleton carries its dcs-skeleton marker class, and the
      pulse is switched off under prefers-reduced-motion
  (e) rhythm CSS caps the container at 1280px and defines the
      section-gap spacers (48px / 64px)
  (f) render wrappers inject the HTML through Streamlit
  (g) tokens stay single-sourced: ui_loading re-uses ui_design.TOKENS,
      no hex is re-derived in its source
  (h) branded loader: the logo mark animating (bars rising staggered,
      checkmark drawing, gentle pulse) + shimmer — CSS in both themes
      and in the app.py literal, loader_block_html structure (one data
      URI, four layers, escaped status, missing-logo fallback), clip
      regions measured against the real logo ink, and the Supabase
      0.2s button/hover timing already in both themes
  (i) the app.py DESIGN_SYSTEM_CSS literal is the verbatim
      ui_design light stylesheet
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui_design
import ui_loading as ul
from ui_design import TOKENS

ROOT = Path(__file__).resolve().parent.parent


class FakeSt:
    """Minimal stand-in for the streamlit module: display calls are
    recorded."""

    def __init__(self):
        self.session_state = {}
        self.calls = []

    def markdown(self, text, **kwargs):
        self.calls.append(("markdown", text, kwargs))


def _markdown_texts(fake):
    return [c[1] for c in fake.calls if c[0] == "markdown"]


# --------------------------------------------------------------------------
# (a) skeleton: fixed heights + loaded-content padding
# --------------------------------------------------------------------------

def test_skeleton_fixed_heights():
    html = ul.skeleton_html(lines=3, title=True)
    assert "height: 20px" in html, "title bar must be a fixed 20px"
    assert html.count("height: 14px") == 3, \
        "three lines must each be a fixed 14px bar"
    # Same y-padding as the loaded .dcs-card (ui_design: 1rem 1.25rem)
    # — that shared padding is what stops the jump.
    assert "padding: 1rem 1.25rem" in html
    assert "border-radius: 12px" in html
    assert "dcs-skeleton" in html, "no layout-shift class missing"
    # The bar grey comes from the token, not a re-derived hex.
    assert TOKENS["active_nav"] in html
    # No height is content-driven: no auto heights on bars.
    assert "height: auto" not in html
    print("skeleton fixed heights OK")


def test_skeleton_variants():
    no_title = ul.skeleton_html(lines=2, title=False)
    assert "height: 20px" not in no_title, "title=False drops the bar"
    assert no_title.count("height: 14px") == 2
    one_line = ul.skeleton_html(lines=1, title=True)
    assert one_line.count("height: 14px") == 1
    # Clamped, never zero bars.
    assert ul.skeleton_html(lines=0).count("height: 14px") == 1
    assert ul.skeleton_html(lines=99).count("height: 14px") == 6
    print("skeleton variants OK")


# --------------------------------------------------------------------------
# (b) skeleton_table: fixed header + rows
# --------------------------------------------------------------------------

def test_skeleton_table_fixed_heights():
    html = ul.skeleton_table_html(rows=5, columns=4)
    assert "height: 36px" in html, "header row must be a fixed 36px"
    assert html.count("height: 40px") == 5, \
        "five rows must each be a fixed 40px"
    assert html.count("height: 14px") == 5 * 4 + 1, \
        "one 14px bar per column per row, plus the header bar"
    assert "dcs-skeleton-table" in html
    assert TOKENS["border"] in html, "hairline comes from the token"
    print("skeleton table fixed heights OK")


def test_skeleton_table_variants():
    html = ul.skeleton_table_html(rows=2, columns=2)
    assert html.count("height: 40px") == 2
    assert html.count("height: 14px") == 2 * 2 + 1
    print("skeleton table variants OK")


# --------------------------------------------------------------------------
# (c) skeleton_chart: fixed height
# --------------------------------------------------------------------------

def test_skeleton_chart_fixed_height():
    assert "height: 320px" in ul.skeleton_chart_html()
    assert "height: 200px" in ul.skeleton_chart_html(height=200)
    assert "height: 20px" in ul.skeleton_chart_html(), \
        "chart skeleton keeps the 20px title bar"
    assert "dcs-skeleton-chart" in ul.skeleton_chart_html()
    print("skeleton chart fixed height OK")


# --------------------------------------------------------------------------
# (d) marker classes + reduced motion
# --------------------------------------------------------------------------

def test_skeleton_reduced_motion():
    html = ul.skeleton_html()
    assert "prefers-reduced-motion" in html, \
        "the pulse must switch off for reduced-motion users"
    assert "dcs-skeleton-bar" in html
    assert "dcs-skeleton" in ul.skeleton_table_html()
    assert "dcs-skeleton" in ul.skeleton_chart_html()
    print("reduced motion OK")


# --------------------------------------------------------------------------
# (e) rhythm: 1280px cap + section gaps
# --------------------------------------------------------------------------

def test_rhythm_css():
    css = ul.rhythm_css()
    assert "1280px" in css, "container cap must be 1280px"
    assert ".block-container" in css
    assert "max-width: 1280px" in css
    assert ".dcs-section-gap" in css
    assert "48px" in css and "64px" in css
    assert ul.section_gap_html() .count("height: 48px") == 1
    assert "height: 64px" in ul.section_gap_html(px=64)
    assert "height: 128px" in ul.section_gap_html(px=999), \
        "gap clamps to 128px, never more"
    print("rhythm CSS OK")


# --------------------------------------------------------------------------
# (f) render wrappers inject through Streamlit
# --------------------------------------------------------------------------

def test_render_wrappers():
    fake = FakeSt()
    ul.skeleton(st_module=fake)
    ul.skeleton_table(rows=2, columns=2, st_module=fake)
    ul.skeleton_chart(height=200, st_module=fake)
    ul.inject_rhythm(st_module=fake)
    ul.section_gap(st_module=fake)
    texts = _markdown_texts(fake)
    assert len(texts) == 5, f"expected 5 markdown calls, got {len(texts)}"
    assert any("dcs-skeleton" in t and "height: 20px" in t for t in texts)
    assert any("dcs-skeleton-table" in t for t in texts)
    assert any("dcs-skeleton-chart" in t and "height: 200px" in t
               for t in texts)
    assert any("1280px" in t for t in texts), "rhythm CSS injected"
    assert any("dcs-section-gap" in t for t in texts)
    print("render wrappers OK")


# --------------------------------------------------------------------------
# (g) tokens single-sourced, no re-derived hex
# --------------------------------------------------------------------------

def test_tokens_single_sourced():
    src = (ROOT / "ui_loading.py").read_text(encoding="utf-8")
    assert "from ui_design import TOKENS" in src
    for hex_value in (TOKENS["active_nav"], TOKENS["panel_grey"],
                      TOKENS["border"], TOKENS["card"]):
        assert src.count(hex_value) == 0, \
            f"{hex_value} must come from TOKENS, not be re-derived"
    print("tokens single-sourced OK")


# --------------------------------------------------------------------------
# (h) branded loader: logo mark animating, Supabase-style
# --------------------------------------------------------------------------

_LOADER_SELECTORS = (
    ".dcs-loader",
    ".dcs-loader-mark",
    ".dcs-lm-bar1",
    ".dcs-lm-bar2",
    ".dcs-lm-bar3",
    ".dcs-lm-check",
    ".dcs-loader-name",
    ".dcs-loader-status",
    ".dcs-loader-shimmer",
    "@keyframes dcs-lm-rise",
    "@keyframes dcs-lm-drawcheck",
    "@keyframes dcs-lm-breathe",
    "@keyframes dcs-lm-slide",
)


def test_loader_css_in_both_themes():
    """Every loader rule + keyframe exists in the light stylesheet
    and has a dark twin (light/dark parity — switching themes never
    moves layout, only colour)."""
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS)):
        for sel in _LOADER_SELECTORS:
            assert sel in css, f"{name}: loader CSS missing {sel}"
        assert "prefers-reduced-motion" in css, \
            f"{name}: loader must switch off under reduced motion"
        # Supabase timing on the loader animations.
        assert "cubic-bezier(.22,1,.36,1)" in css, \
            f"{name}: loader must use the Supabase 0.2s easing"
        # The staggered rise + draw, pinned exactly.
        assert "animation: dcs-lm-rise .45s cubic-bezier(.22,1,.36,1) .13s both;" in css, \
            f"{name}: bar2 must rise .13s after bar1"
        assert "animation: dcs-lm-rise .45s cubic-bezier(.22,1,.36,1) .26s both;" in css, \
            f"{name}: bar3 must rise .26s after bar1"
        assert "animation: dcs-lm-drawcheck .6s cubic-bezier(.22,1,.36,1) .45s both;" in css, \
            f"{name}: checkmark must draw at .45s, after the bars"
        # The shimmer gradient uses theme tokens only: light runs the
        # primary gradient (#118050 -> #117f50); dark runs the brand
        # green to the dark link green (#3ecf8e is legitimately a dark
        # CSS token — the dark link-hover green — but it must never
        # appear in the light sheet, see test_supabase_theme.py).
        assert "linear-gradient(90deg, #118050, #117f50)" in \
            ui_design.DESIGN_SYSTEM_CSS, \
            "light shimmer must run #118050 -> #117f50"
        assert "linear-gradient(90deg, #3ecf8e, #4acd8b)" in \
            ui_design.DARK_CSS, \
            "dark shimmer must run #3ecf8e -> #4acd8b"
        assert "#3ecf8e" not in ui_design.DESIGN_SYSTEM_CSS, \
            "#3ecf8e is logo-only and must not appear in the light sheet"
    assert "#117f50" in ui_design.DESIGN_SYSTEM_CSS, \
        "light shimmer must end at the deep green #117f50"
    assert "#4acd8b" in ui_design.DARK_CSS, \
        "dark shimmer must end at the dark link green #4acd8b"
    # Button + hover timing (already in both themes): the Supabase
    # 0.2s ease on every interactive element, primary darkening
    # #0e7d4e -> #007243 on hover.
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS)):
        assert "transition: background-color 0.2s cubic-bezier(0.22, 1, 0.36, 1)" in css, \
            f"{name}: buttons must use the Supabase 0.2s transition"
    assert "#0e7d4e" in ui_design.DESIGN_SYSTEM_CSS
    assert "#007243" in ui_design.DESIGN_SYSTEM_CSS
    print("loader CSS in both themes OK")


def test_loader_block_html():
    """loader_block_html: large (centred, 96px, name + status +
    shimmer) and compact (row: 40px mark + status) share one data
    URI across four <img> slices; the status is escaped; a missing
    logo renders the status alone; an unknown size falls back to large.
    (Round 3: the mark is <img> slices, not empty divs over a
    background image on an inline custom property — that mechanism
    never painted live, two live checks saw the status text but never
    the mark, while <img> data URIs already paint everywhere else in
    this app.)"""
    logo = ROOT / "assets" / "logo.png"
    large = ui_design.loader_block_html(
        logo, "Waking up your workspace…")
    assert 'class="dcs-loader dcs-loader--large"' in large
    # One data-URI value, inlined once per slice (four slices share it).
    assert large.count("data:image/png;base64,") == 4, \
        "the logo must be inlined once per img slice (4 slices)"
    import re as _re
    uris = set(_re.findall(r'src="(data:image/png;base64,[^"]+)"', large))
    assert len(uris) == 1, "all four slices must share the same data URI"
    for layer in ("dcs-lm-bar1", "dcs-lm-bar2", "dcs-lm-bar3",
                  "dcs-lm-check"):
        assert f'<img src="data:image/png;base64,' in large, \
            "each layer must be an <img> with the data URI"
        assert layer in large, f"loader missing layer {layer}"
    assert "<div class=\"dcs-lm-bar1\">" not in large, \
        "layers must be <img> slices, not empty divs"
    assert "--dcs-logo" not in large, \
        "the inline custom-property mechanism is gone"
    assert "Data Cleaner Studio" in large
    assert "Waking up your workspace…" in large
    assert "dcs-loader-shimmer" in large
    compact = ui_design.loader_block_html(
        logo, "Cleaning your data…", size="compact")
    assert 'class="dcs-loader dcs-loader--compact"' in compact
    assert "dcs-loader-row" in compact
    assert "Cleaning your data…" in compact
    assert "Data Cleaner Studio" not in compact, \
        "compact loader has no app name (row: mark + status only)"
    assert compact.count("data:image/png;base64,") == 4
    assert 'dcs-loader--large' in ui_design.loader_block_html(
        logo, "x", size="huge"), "unknown size must fall back to large"
    escaped = ui_design.loader_block_html(logo, "<b>bold</b>")
    assert "<b>bold</b>" not in escaped, "status text must be escaped"
    assert "&lt;b&gt;bold&lt;/b&gt;" in escaped
    missing = ui_design.loader_block_html(
        ROOT / "assets" / "no-such-logo.png", "Loading…")
    assert "data:image" not in missing, \
        "a missing logo must not render a broken image"
    assert "dcs-lm-bar1" not in missing
    assert "Loading…" in missing, "status still shows without a logo"
    # The dark recolor inlines byte-identical to its asset file.
    import base64 as _b64
    dark = ui_design.loader_block_html(
        ROOT / "assets" / "logo-loader-dark.png", "Loading…")
    m = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", dark)
    assert m, "dark loader must inline the logo"
    assert _b64.b64decode(m.group(1)) == \
        (ROOT / "assets" / "logo-loader-dark.png").read_bytes(), \
        "dark loader must inline logo-loader-dark.png byte-identical"
    print("loader_block_html OK")


def test_loader_clip_regions_cover_logo():
    """The four layer clip windows (parsed from the CSS) must cover
    the logo's actual ink: the bars left to right, the checkmark
    sweeping the right side. Ink ranges are measured from logo.png,
    not guessed — if the mark ever changes, this test says so."""
    from PIL import Image
    import numpy as np

    im = np.array(Image.open(
        ROOT / "assets" / "logo.png").convert("RGBA"))
    cols = np.where((im[..., 3] > 20).any(axis=0))[0]
    ink_lo = cols.min() / 10.24  # percent of the 1024px canvas
    ink_hi = cols.max() / 10.24
    css = ui_design.DESIGN_SYSTEM_CSS
    windows = []
    for layer in ("dcs-lm-bar1", "dcs-lm-bar2", "dcs-lm-bar3",
                  "dcs-lm-check"):
        m = re.search(re.escape("." + layer) +
                      r" \{ clip-path: inset\(0 (\d+)% 0 (\d+)%\)", css)
        assert m, f"no clip-path found for {layer}"
        right, left = int(m.group(1)), int(m.group(2))
        windows.append((left, 100 - right))
    bars, check = windows[:3], windows[3]
    assert bars == sorted(bars), \
        f"bar windows must run left to right: {bars}"
    assert bars[0][1] <= bars[1][0] and bars[1][1] <= bars[2][0], \
        f"bar windows must not overlap: {bars}"
    assert check[1] >= ink_hi, \
        f"check window must reach the ink's right edge ({ink_hi:.1f}%)"
    # Merge the windows; the merged span must cover the whole ink
    # range with no gap (the check window bridges bar2/bar3).
    merged = []
    for lo, hi in sorted(windows):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    assert len(merged) == 1, f"clip windows must merge to one span: {merged}"
    assert merged[0][0] <= ink_lo and merged[0][1] >= ink_hi, \
        f"merged span {merged} must cover the ink {ink_lo:.1f}–{ink_hi:.1f}%"
    print("loader clip regions cover logo OK")


# --------------------------------------------------------------------------
# (i) app.py literal is the verbatim ui_design light stylesheet
# --------------------------------------------------------------------------

def test_app_literal_matches_ui_design():
    """The DESIGN_SYSTEM_CSS literal in app.py is the verbatim paste
    of ui_design.DESIGN_SYSTEM_CSS — the login screen would otherwise
    ship a stale stylesheet (see test_sidebar_avatar.py)."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r'DESIGN_SYSTEM_CSS = """<style>(.*?)</style>"""',
        source, re.DOTALL)
    assert match, "DESIGN_SYSTEM_CSS block missing from app.py"
    literal = "<style>" + match.group(1) + "</style>"
    assert literal == ui_design.DESIGN_SYSTEM_CSS, \
        "app.py literal must equal ui_design.DESIGN_SYSTEM_CSS verbatim"
    assert ".dcs-loader" in literal, \
        "app.py literal must carry the loader rules too"
    print("app.py literal matches ui_design OK")


if __name__ == "__main__":
    test_skeleton_fixed_heights()
    test_skeleton_variants()
    test_skeleton_table_fixed_heights()
    test_skeleton_table_variants()
    test_skeleton_chart_fixed_height()
    test_skeleton_reduced_motion()
    test_rhythm_css()
    test_render_wrappers()
    test_tokens_single_sourced()
    test_loader_css_in_both_themes()
    test_loader_block_html()
    test_loader_clip_regions_cover_logo()
    test_app_literal_matches_ui_design()
    print("ALL LOADING TESTS PASSED")
