"""UI polish tests for Data Cleaner Studio (Supabase theme pass).

Pins the professional UI upgrade:
  (a) .streamlit/config.toml [theme] equals the Supabase palette
  (b) theme_css("Supabase") carries the palette and no retired colours
  (c) no destructive-labelled button (delete/clear/reset/remove) is primary
  (d) set_page_config carries the page title and a page_icon
  (e) assets/logo.png + assets/logo-dark.png + assets/favicon.png exist,
      PNGs are valid images
  (f) the consolidated stylesheet is injected before the login view

Run: .test-venv-uipolish/bin/python tests/test_ui_polish.py (from root)
Also pytest-collectable (plain asserts, no fixtures). No Streamlit
server needed — (b)/(c)/(d)/(f) are static source reads, (a) parses the
TOML file, (e) reads the asset files.
"""

import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feat_enrich as fe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

PALETTE = {
    "backgroundColor": "#fdfdfd",
    "secondaryBackgroundColor": "#fdfdfd",
    "textColor": "#030303",
    "primaryColor": "#117f50",
}
BANNED_COLOURS = ("#2F5D5A", "#FAF7F2", "#121212", "#0d1b2a", "#4da6ff",
                  "#1a7f37")
DESTRUCTIVE_WORDS = ("delete", "clear", "reset", "remove")


def test_config_theme_palette():
    """(a) .streamlit/config.toml parses and [theme] == the palette."""
    cfg = tomllib.loads(
        (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    theme = cfg["theme"]
    assert theme["base"] == "light", theme
    assert theme["font"] == "sans serif", theme
    for key, value in PALETTE.items():
        assert theme[key] == value, f"{key}: {theme.get(key)} != {value}"
    # The existing [server] settings survive untouched.
    assert cfg["server"]["port"] == 8501
    assert cfg["server"]["headless"] is True
    print("config theme palette OK")


def test_theme_css_supabase():
    """(b) theme_css('Supabase') has the palette, none of the old colours."""
    css = fe.theme_css("Supabase")
    assert set(fe.THEMES) == {"Supabase"}
    for colour in ("#fdfdfd", "#030303", "#117f50", "#FFFFFF"):
        assert colour in css, f"{colour} missing from theme_css('Supabase')"
    for banned in BANNED_COLOURS:
        assert banned not in css, f"{banned} must not be in Supabase CSS"
    assert fe.theme_css("Nope") == fe.theme_css("Supabase")
    assert fe.theme_css("Classic") == fe.theme_css("Supabase")
    assert fe.apply_theme.__doc__ is not None  # signature kept
    print("theme_css Supabase OK")


def _button_calls(source):
    """Yield the full text of each st.button()/c1.button() call in source,
    using paren counting so multi-line calls come out whole."""
    for match in re.finditer(r"\.button\(", source):
        depth = 0
        i = match.start()
        while i < len(source):
            if source[i] == "(":
                depth += 1
            elif source[i] == ")":
                depth -= 1
                if depth == 0:
                    yield source[match.start():i + 1]
                    break
            i += 1


def test_no_destructive_primary_button():
    """(c) No destructive-labelled button is type='primary' anywhere."""
    bad = []
    for path in sorted(ROOT.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for call in _button_calls(source):
            if 'type="primary"' not in call and "type='primary'" not in call:
                continue
            label = call.lower()
            hits = [w for w in DESTRUCTIVE_WORDS if w in label]
            if hits:
                bad.append(f"{path.name}: {call[:90]!r} ({hits})")
    assert not bad, "destructive primary button(s):\n" + "\n".join(bad)
    print("no destructive primary button OK")


def test_page_config_title_and_icon():
    """(d) set_page_config carries the page title and a page_icon."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.find("st.set_page_config(")
    assert start != -1, "set_page_config call missing from app.py"
    depth = 0
    end = None
    for i in range(start, len(source)):
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    assert end is not None, "set_page_config call never closes"
    call = source[start:end + 1]
    assert 'page_title="Data Cleaner Studio"' in call, call
    assert "page_icon" in call, call
    assert "favicon" in call, call
    print("page config title + icon OK")


def test_logo_and_favicon_assets():
    """(e) assets/logo.png + assets/logo-dark.png + assets/favicon.png
    exist; the PNGs are valid. The logo is the user's mark (dark-green
    bars + check, 1024x1024); the dark variant is the same mark in
    #4acd8b for the dark theme; the old checkmark logo.svg is gone."""
    from PIL import Image

    assert not (ROOT / "assets" / "logo.svg").exists(), \
        "the old checkmark logo.svg must be gone"
    logo = ROOT / "assets" / "logo.png"
    assert logo.is_file(), "assets/logo.png missing"
    with Image.open(logo) as img:
        img.load()
        assert img.format == "PNG" and img.mode == "RGBA"
        assert img.size == (1024, 1024), \
            f"logo is {img.size}, want the user's 1024x1024 mark"
    dark = ROOT / "assets" / "logo-dark.png"
    assert dark.is_file(), "assets/logo-dark.png missing"
    with Image.open(dark) as img:
        img.load()
        assert img.format == "PNG" and img.size == (1024, 1024)
    favicon = ROOT / "assets" / "favicon.png"
    assert favicon.is_file(), "assets/favicon.png missing"
    with Image.open(favicon) as img:
        img.load()
        assert img.size == (64, 64), f"favicon is {img.size}, want 64x64"
        assert img.format == "PNG"
    print("logo + favicon assets OK")


def test_stylesheet_before_login():
    """(f) The consolidated stylesheet is injected before the login view."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    inject = source.find("st.markdown(DESIGN_SYSTEM_CSS")
    assert inject != -1, "DESIGN_SYSTEM_CSS injection missing from app.py"
    login = source.find("if _current_user is None:")
    assert login != -1, "login view marker missing from app.py"
    assert inject < login, "stylesheet must be injected before the login view"
    # The old per-theme CSS block is gone: one stylesheet only.
    assert "render_theme_picker(st)" not in source, \
        "theme picker call site must be removed from app.py"
    print("stylesheet before login OK")


if __name__ == "__main__":
    test_config_theme_palette()
    test_theme_css_supabase()
    test_no_destructive_primary_button()
    test_page_config_title_and_icon()
    test_logo_and_favicon_assets()
    test_stylesheet_before_login()
    print("ALL UI POLISH TESTS PASSED")
