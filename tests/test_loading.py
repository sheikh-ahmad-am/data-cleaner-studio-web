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
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    print("ALL LOADING TESTS PASSED")
