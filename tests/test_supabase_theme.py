"""Supabase theme tests for Data Cleaner Studio.

Pins the Supabase-look reskin (tokens measured off the live Supabase
dashboard — see supabase-design-study.md):
  (a) .streamlit/config.toml [theme] equals the Supabase tokens
  (b) the consolidated stylesheet (DESIGN_SYSTEM_CSS in app.py) carries
      the Supabase primary / background / border colours and contains
      NO Classic teal (#2F5D5A) or warm background (#FAF7F2)
  (c) the tab-bar active style uses the #f3f3f3 nav pill
  (d) theme_css("Supabase") carries the tokens; a stored legacy theme
      name ("Classic") still resolves to Supabase on load

Run: .test-venv-uipolish/bin/python tests/test_supabase_theme.py
Also pytest-collectable (plain asserts, no fixtures). No Streamlit
server needed — app.py is read as source text, never imported.
"""

import re
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai_settings  # noqa: E402
import feat_enrich as fe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

THEME_TOKENS = {
    "base": "light",
    "backgroundColor": "#fdfdfd",
    "secondaryBackgroundColor": "#fdfdfd",
    "textColor": "#030303",
    "primaryColor": "#117f50",
    "font": "sans serif",
}


def _design_system_css() -> str:
    """The DESIGN_SYSTEM_CSS block out of app.py, read as source text
    (importing app.py would boot Streamlit)."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r'DESIGN_SYSTEM_CSS = """<style>(.*?)</style>"""',
        source, re.DOTALL)
    assert match, "DESIGN_SYSTEM_CSS block missing from app.py"
    return match.group(1)


def test_config_theme_tokens():
    """(a) .streamlit/config.toml [theme] == the Supabase tokens."""
    cfg = tomllib.loads(
        (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    theme = cfg["theme"]
    for key, value in THEME_TOKENS.items():
        assert theme[key] == value, f"{key}: {theme.get(key)} != {value}"
    print("config theme tokens OK")


def test_stylesheet_supabase_tokens():
    """(b) The stylesheet has the Supabase palette, no Classic colours."""
    css = _design_system_css()
    for colour in ("#117f50", "#fdfdfd", "#e8e8e8", "#030303", "#696969"):
        assert colour in css, f"{colour} missing from DESIGN_SYSTEM_CSS"
    for retired in ("#2F5D5A", "#FAF7F2", "#264845", "#F3EFE8",
                    "#EFEDE8", "#23272E", "#6E6A61", "#D9D4C9",
                    "#E5E0D8", "#121212"):
        assert retired not in css, \
            f"{retired} must not be in DESIGN_SYSTEM_CSS"
    print("stylesheet Supabase tokens OK")


def test_tab_bar_active_uses_f3f3f3():
    """(c) The tab-bar active item is the #f3f3f3 nav pill."""
    css = _design_system_css()
    match = re.search(
        r"label:has\(input:checked\)\s*\{(.*?)\}", css, re.DOTALL)
    assert match, "tab-bar :checked rule missing from DESIGN_SYSTEM_CSS"
    rule = match.group(1)
    assert "#f3f3f3" in rule, f"active tab rule must use #f3f3f3: {rule!r}"
    assert "#2F5D5A" not in rule, "active tab must not be the old teal"
    print("tab-bar active #f3f3f3 OK")


def test_theme_css_and_legacy_migration():
    """(d) theme_css('Supabase') + legacy stored names resolve to it."""
    css = fe.theme_css("Supabase")
    for colour in ("#fdfdfd", "#030303", "#117f50"):
        assert colour in css, f"{colour} missing from theme_css('Supabase')"
    for retired in ("#2F5D5A", "#FAF7F2"):
        assert retired not in css, f"{retired} must not be in theme_css"
    # Any stored legacy theme name falls back to Supabase.
    assert fe.theme_css("Classic") == fe.theme_css("Supabase")
    assert fe.theme_css("Dark green") == fe.theme_css("Supabase")
    # ... and the settings migration does the same on load.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        path.write_text('{"theme": "Classic"}', encoding="utf-8")
        assert ai_settings.load_settings(path)["theme"] == "Supabase"
        path.write_text('{"theme": "Dark blue"}', encoding="utf-8")
        assert ai_settings.load_settings(path)["theme"] == "Supabase"
    print("theme_css + legacy migration OK")


if __name__ == "__main__":
    test_config_theme_tokens()
    test_stylesheet_supabase_tokens()
    test_tab_bar_active_uses_f3f3f3()
    test_theme_css_and_legacy_migration()
    print("ALL SUPABASE THEME TESTS PASSED")
