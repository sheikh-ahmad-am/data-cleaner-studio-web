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
import ui_design  # noqa: E402

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


# ---------------------------------------------------------------------------
# Dark theme (Worker A, refine/supabase-look): every token pinned in
# BOTH themes, motion + focus ring pinned, toggle default + switch.
# ---------------------------------------------------------------------------

def _hex_tokens(tokens):
    """The hex values of a token dict (sizes / radii are not colours)."""
    return [v for v in tokens.values()
            if isinstance(v, str) and v.startswith("#")]


def _luminance(hex_colour):
    """Relative luminance per WCAG 2.1 (sRGB)."""
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255
               for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = f(r), f(g), f(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg, bg):
    """WCAG contrast ratio between two hex colours."""
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_theme_css_light_and_dark():
    """ui_design.theme_css returns the light / dark stylesheets, and
    unknown names fall back to light — never to an unstyled app."""
    assert ui_design.theme_css("light") == ui_design.DESIGN_SYSTEM_CSS
    assert ui_design.theme_css("dark") == ui_design.DARK_CSS
    assert ui_design.theme_css("light") != ui_design.theme_css("dark")
    for unknown in (None, "", "Classic", "Dark green", "Nope"):
        assert ui_design.theme_css(unknown) == ui_design.DESIGN_SYSTEM_CSS, \
            f"theme_css({unknown!r}) must fall back to light"
    assert ui_design.normalize_theme("dark") == "dark"
    assert ui_design.normalize_theme("bogus") == "light"
    print("theme_css light/dark + fallback OK")


def test_all_tokens_pinned_both_themes():
    """EVERY token hex is asserted in the stylesheet that ships it:
    light tokens in theme_css('light'), dark tokens in
    theme_css('dark') — and no dark hex leaks into the light sheet.
    Three light tokens live outside CSS by design and are pinned here
    instead: #3ecf8e (brand green — logo mark only, not a CSS rule),
    #16b674 (icon green — dashboard node icons, not a CSS rule) and
    #4d4d4d (body token — the shipped CSS deliberately uses ink #030303
    for body text, so the token is record-only)."""
    light = ui_design.theme_css("light")
    dark = ui_design.theme_css("dark")
    non_css_light = {"#3ecf8e", "#16b674", "#4d4d4d"}
    for colour in _hex_tokens(ui_design.TOKENS):
        if colour in non_css_light:
            assert colour in ui_design.TOKENS.values(), colour
            continue
        assert colour in light, f"light token {colour} missing from light CSS"
    for colour in non_css_light:
        assert colour in ui_design.TOKENS.values(), \
            f"non-CSS token {colour} must stay in TOKENS"
        assert colour not in light, \
            f"non-CSS token {colour} must not appear in the light stylesheet"
    # #3ecf8e is the dark link-hover green, so it legitimately appears
    # in the dark sheet; the other two record-only tokens appear nowhere.
    assert "#16b674" not in dark and "#4d4d4d" not in dark
    for colour in _hex_tokens(ui_design.DARK_TOKENS):
        assert colour in dark, f"dark token {colour} missing from dark CSS"
    for colour in ("#1b1d1c", "#edefee", "#006338", "#4acd8b", "#232625",
                   "#2e2e2e", "#123527", "#2a2118", "#ff6369"):
        assert colour not in light, \
            f"dark hex {colour} leaked into the light stylesheet"
    assert "#fdfdfd" not in dark, \
        "light surface #fdfdfd must not appear in the dark stylesheet"
    print("all tokens pinned in both themes OK")


def test_dark_theme_contrast_aa():
    """Every dark text/background pair the theme ships passes WCAG AA
    (>= 4.5:1 for normal text). Dark hexes are secondary-sourced
    candidates, so the contrast — not the provenance — is the guarantee."""
    dark = ui_design.DARK_TOKENS
    pairs = [
        ("ink on surface", dark["ink"], dark["bg"]),
        ("body on surface", dark["body"], dark["bg"]),
        ("muted on surface", dark["muted"], dark["bg"]),
        ("link on surface", dark["link"], dark["bg"]),
        ("danger on surface", dark["danger"], dark["bg"]),
        ("ink on card", dark["ink"], dark["card"]),
        ("muted on card", dark["muted"], dark["card"]),
        ("white on primary fill", "#ffffff", dark["primary"]),
        ("white on primary hover", "#ffffff", dark["primary_hover"]),
        ("mint text on mint fill", dark["link"], dark["mint_pill"]),
        ("amber text on amber fill", dark["amber_text"], dark["amber_fill"]),
    ]
    for label, fg, bg in pairs:
        ratio = _contrast(fg, bg)
        assert ratio >= 4.5, f"{label}: {fg} on {bg} is {ratio:.2f}:1 (< 4.5)"
    print("dark theme WCAG AA contrast OK")


def test_motion_and_focus_ring_both_themes():
    """Honest motion only: the measured 0.2s cubic-bezier(0.22,1,0.36,1)
    colour transition on both themes, the shared focus ring (2px gap +
    4px translucent green halo) on both, primary hover darkening toward
    #007243 — and the ONLY keyframes/animation allowed are the branded
    loader's (approved loading motion, 2026-11-07: bars rising,
    checkmark drawing, gentle pulse, shimmer slide — functional, never
    decorative, per the Supabase rule). No scroll effects, no parallax,
    no other animation anywhere."""
    for theme in ("light", "dark"):
        css = ui_design.theme_css(theme)
        assert "0.2s cubic-bezier(0.22, 1, 0.36, 1)" in css, \
            f"{theme}: measured button transition missing"
        assert ("transition: background-color 0.2s cubic-bezier"
                "(0.22, 1, 0.36, 1)" in css.replace("\n", " ")
                or "background-color 0.2s cubic-bezier(0.22, 1, 0.36, 1)"
                in css), f"{theme}: transition must cover background-color"
        for prop in ("border-color 0.2s cubic-bezier(0.22, 1, 0.36, 1)",
                     "color 0.2s cubic-bezier(0.22, 1, 0.36, 1)"):
            assert prop in css, f"{theme}: transition must cover {prop}"
        assert "#30ba798c" in css, f"{theme}: focus halo missing"
        assert "0 0 0 2px" in css and "0 0 0 6px #30ba798c" in css, \
            f"{theme}: focus ring must be 2px gap + 4px halo"
        assert "#007243" in css, f"{theme}: primary hover #007243 missing"
        # Only the loader's keyframes may exist, and only the loader's
        # animations (plus `animation: none` under reduced motion).
        _allowed = {"dcs-lm-rise", "dcs-lm-drawcheck", "dcs-lm-breathe",
                    "dcs-lm-slide", "none"}
        for _m in re.finditer(r"@keyframes\s+([\w-]+)", css):
            assert _m.group(1) in _allowed, \
                f"{theme}: only the loader keyframes may ship, got {_m.group(1)}"
        for _m in re.finditer(r"animation:\s*([\w-]+)", css):
            assert _m.group(1) in _allowed, \
                f"{theme}: only the loader animations may ship, got {_m.group(1)}"
        for invented in ("scroll-behavior", "parallax"):
            assert invented not in css, \
                f"{theme}: invented motion {invented!r} must not ship"
        # The existing loading language survives: green spinner rule.
        assert 'div[data-testid="stSpinner"]' in css, \
            f"{theme}: green spinner rule missing"
    light = ui_design.theme_css("light")
    dark = ui_design.theme_css("dark")
    assert "0 0 0 2px #fdfdfd" in light, "light focus gap must be #fdfdfd"
    assert "0 0 0 2px #1b1d1c" in dark, "dark focus gap must be #1b1d1c"
    print("motion + focus ring in both themes OK")


def test_dark_stylesheet_covers_surfaces():
    """The dark stylesheet restyles every surface the light one does:
    sidebar, topbar, tables, KPI tiles, pills, code blocks and alerts."""
    dark = ui_design.theme_css("dark")
    for selector in ('section[data-testid="stSidebar"]', ".dcs-topbar",
                     'div[data-testid="stDataFrame"]', ".dcs-kpi",
                     ".dcs-pill-mint", ".dcs-pill-amber", ".dcs-pill-green",
                     ".dcs-pill-grey", ".dcs-pill-danger",
                     'div[data-testid="stCodeBlock"]',
                     'div[data-testid="stAlert"]',
                     ".dcs-empty", ".dcs-storage"):
        assert selector in dark, f"dark CSS missing {selector}"
    print("dark stylesheet covers all surfaces OK")


def test_theme_toggle_default_light_and_switch():
    """The toggle defaults to light, lives in app.py (sidebar + login
    switch), and switching themes changes the injected CSS."""
    assert ui_design.THEME_DEFAULT == "light"
    assert ui_design.normalize_theme(None) == "light"
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'setdefault("dcs_theme", "light")' in source, \
        "app.py must default st.session_state['dcs_theme'] to light"
    assert "ui_design.render_theme_toggle()" in source, \
        "sidebar theme toggle wiring missing from app.py"
    assert "ui_design.render_login_theme_toggle()" in source, \
        "login-screen theme switch wiring missing from app.py"
    assert "st.markdown(DESIGN_SYSTEM_CSS" in source, \
        "DESIGN_SYSTEM_CSS injection must stay (ui_polish pins it)"
    light = ui_design.theme_css("light")
    dark = ui_design.theme_css("dark")
    assert light != dark, "switching themes must change the injected CSS"
    assert "#fdfdfd" in light and "#1b1d1c" in dark
    assert "#117f50" in light and "#006338" in dark
    print("theme toggle default light + switch OK")


if __name__ == "__main__":
    test_config_theme_tokens()
    test_stylesheet_supabase_tokens()
    test_tab_bar_active_uses_f3f3f3()
    test_theme_css_and_legacy_migration()
    test_theme_css_light_and_dark()
    test_all_tokens_pinned_both_themes()
    test_dark_theme_contrast_aa()
    test_motion_and_focus_ring_both_themes()
    test_dark_stylesheet_covers_surfaces()
    test_theme_toggle_default_light_and_switch()
    print("ALL SUPABASE THEME TESTS PASSED")
