"""Group C (v1.4) tests — GAP 8: mobile-friendly layout (feat_mobile).

Run: .test-venv-mobile/bin/python tests/test_feat_mobile.py  (from project root)
Also pytest-collectable (plain asserts, no fixtures).

Checks the CSS string itself (media query + key rules, nothing outside
the query, nothing unsafe to inject) and that a real Streamlit app still
renders with it injected, via streamlit.testing AppTest.
"""

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feat_mobile as fm

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_css_is_a_style_block():
    css = fm.mobile_css()
    assert isinstance(css, str) and css.strip().startswith("<style>")
    assert css.strip().endswith("</style>")
    assert css.count("<style>") == 1 and css.count("</style>") == 1
    print("style block OK")


def test_media_query_present():
    css = fm.mobile_css()
    assert "@media (max-width: 768px)" in css
    assert css.count("@media") == 1, "exactly one media query — desktop untouched"
    # Nothing but comments sits before the media query: no rule can leak
    # onto desktop.
    before = css.split("@media")[0]
    assert "{" not in before, "a CSS rule outside the media query!"
    print("media query OK: single @media (max-width: 768px), nothing outside it")


def test_key_rules_present():
    css = fm.mobile_css()
    # Stack multi-column layouts full-width.
    assert "stHorizontalBlock" in css
    assert "flex-direction: column" in css
    assert 'div[data-testid="column"]' in css
    assert "width: 100% !important" in css
    # Full-width buttons, finger-sized.
    assert ".stButton > button" in css
    assert ".stDownloadButton > button" in css
    assert "min-height: 44px" in css
    # Smaller headings.
    assert ".stApp h1" in css and "font-size: 1.6rem" in css
    assert ".stApp h2" in css and "font-size: 1.3rem" in css
    assert ".stApp h3" in css
    # Tighter padding.
    assert ".block-container" in css
    assert "padding-left: 0.75rem" in css
    # Sidebar stays usable.
    assert 'section[data-testid="stSidebar"]' in css
    assert "max-width: 85vw" in css
    assert "min-width: 200px" in css
    # Wide tables scroll instead of breaking the page.
    assert ".stDataFrame" in css and "overflow-x: auto" in css
    print("key rules OK: stack / full-width buttons / headings / padding / sidebar / tables")


def test_css_is_safe_to_inject():
    """No JavaScript, no external URLs, no Streamlit-breaking tricks —
    a plain <style> string is all st.markdown(unsafe_allow_html=True)
    ever receives."""
    css = fm.mobile_css()
    lowered = css.lower()
    assert "<script" not in lowered
    assert "javascript:" not in lowered
    assert "http://" not in lowered and "https://" not in lowered
    assert "@import" not in lowered
    assert "url(" not in lowered
    # Balanced braces — a typo here would silently kill the whole block.
    assert css.count("{") == css.count("}"), "unbalanced braces"
    print("injection safety OK: no scripts, no URLs, balanced braces")


def test_apply_mobile_css_uses_markdown():
    """apply_mobile_css(st) injects exactly mobile_css() via markdown."""
    calls = []

    class FakeSt:
        def markdown(self, text, unsafe_allow_html=False):
            calls.append((text, unsafe_allow_html))

    fm.apply_mobile_css(FakeSt())
    assert len(calls) == 1
    assert calls[0][0] == fm.mobile_css()
    assert calls[0][1] is True
    print("apply_mobile_css OK: st.markdown(mobile_css(), unsafe_allow_html=True)")


def test_supabase_palette():
    """The base theme is the Supabase palette — near-white page, white
    cards, near-black ink, one deep-green accent — and no retired
    Classic colour survives in the CSS or the constants."""
    css = fm.mobile_css()
    for token in ("#FDFDFD", "#FFFFFF", "#E8E8E8", "#030303", "#696969",
                  "#117F50", "#0E7D4E", "#E5E5E5", "#B91C1C"):
        assert token in css, f"{token} missing from mobile CSS"
    for retired in ("#FAF7F2", "#23272E", "#2F5D5A", "#264845", "#F3EFE8",
                    "#EFEDE8", "#E5E0D8", "#D9D4C9", "#6E6A61", "#121212",
                    "#9A4A38", "#8A6D3B"):
        assert retired not in css, f"retired Classic colour {retired} in CSS"
    assert fm.PAGE_BG == "#FDFDFD" and fm.ACCENT == "#117F50"
    assert fm.ACCENT_HOVER == "#0E7D4E" and fm.INK == "#030303"
    assert fm.DANGER == "#B91C1C" and fm.WARNING == "#E69344"
    print("Supabase palette OK: tokens in CSS, no Classic colours left")


def test_app_renders_with_css_injected():
    """A small AppTest run: the app renders with the CSS injected and
    raises no exception — the mobile stylesheet does not break the app."""
    from streamlit.testing.v1 import AppTest

    script = (
        "import sys\n"
        "sys.path.insert(0, r'" + str(PROJECT_ROOT) + "')\n"
        "import streamlit as st\n"
        "import feat_mobile\n"
        "st.markdown(feat_mobile.mobile_css(), unsafe_allow_html=True)\n"
        "st.title('Mobile test')\n"
        "c1, c2 = st.columns(2)\n"
        "c1.write('left')\n"
        "c2.write('right')\n"
        "st.button('Tap me')\n"
    )
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as tmp:
        path = Path(tmp) / "mobile_apptest_app.py"
        path.write_text(script, encoding="utf-8")
        at = AppTest(str(path), default_timeout=30).run()
    assert len(at.exception) == 0, list(at.exception)
    assert at.title[0].value == "Mobile test"
    assert at.markdown[0].value == fm.mobile_css()
    assert at.button[0].label == "Tap me"
    print("AppTest render OK: app runs with mobile CSS injected, no exception")


if __name__ == "__main__":
    test_css_is_a_style_block()
    test_media_query_present()
    test_key_rules_present()
    test_css_is_safe_to_inject()
    test_supabase_palette()
    test_apply_mobile_css_uses_markdown()
    test_app_renders_with_css_injected()
    print("ALL MOBILE TESTS PASSED")
