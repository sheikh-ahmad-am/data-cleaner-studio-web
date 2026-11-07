"""Round-3 fix tests (2026-11-07): the branded loader's mark must
actually paint during the sample load.

Why this file exists: round 2 "fixed" the loader by holding it
visible for 0.7s, on the theory that create + clear coalesced inside
one script run. The live check (20:10-20:18 IST) disproved that —
clicked twice, watched both times, a frame at ~0.7-0.85s still showed
only the normal Preview page. The sample loaded fine (80 rows), and
the plain text "Loading the sample file…" WAS visible — so the loader
element reached the DOM and painted its status, but the logo mark
never painted.

The proven cause (round-3 investigation): the mark was four empty
divs whose only image was a background-image carried on an inline
custom property (``--dcs-logo`` holding a 762KB data URI). Everything
else in the chain was verified with real evidence — the CSS parses
with 0 errors, the inline style survives the style parser AND the
full react-markdown + rehype-raw pipeline AND React sets the custom
property on the DOM element intact, Streamlit flushes deltas every
5ms, and the status text paints live — but the mark's
``background-image: var(--dcs-logo)`` resolution was the one link no
local check could prove, and it is the only mechanism unique to the
mark versus the status text that paints. The fix removes that
dependency entirely: the mark is now four <img> slices (the mechanism
the top-bar and console-header logos already use, and that paints
live), over small 192px loader files so the four-way duplication
stays light (~17KB each instead of 571KB/207KB).

Run ONLY this file:  .test-venv-wave3/bin/python -m pytest
tests/test_fixup_round3.py -q   (from project root)
"""

import ast
import contextlib
import re
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_fixup_round2 as _r2  # noqa: E402  (harness: signup, buttons)
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
_tmp_env = _r2._tmp_env


# ---------------------------------------------------------------------------
# 1 — the small loader logo files
# ---------------------------------------------------------------------------

def test_round3_loader_files_exist_and_small():
    """The 192px loader variants exist, are valid RGBA PNGs, and are
    an order of magnitude smaller than the full 1024px files — the
    four-slice mark inlines the small file, not the 571KB one."""
    for small_name, full_name in (("logo-loader.png", "logo.png"),
                                  ("logo-loader-dark.png", "logo-dark.png")):
        small = PROJECT_ROOT / "assets" / small_name
        full = PROJECT_ROOT / "assets" / full_name
        assert small.is_file(), f"{small_name} missing"
        from PIL import Image
        im = Image.open(small)
        im.load()
        assert im.format == "PNG" and im.size == (192, 192), \
            f"{small_name} must be a 192x192 PNG, got {im.format} {im.size}"
        assert im.mode == "RGBA", "loader logo must keep transparency"
        assert small.stat().st_size < 50_000, \
            f"{small_name} is {small.stat().st_size} bytes, must stay small"
        assert small.stat().st_size < full.stat().st_size // 5, \
            f"{small_name} must be far smaller than {full_name}"
    print("round 3 loader files exist and small OK")


def test_round3_loader_clip_windows_cover_small_file():
    """The four layer clip windows (parsed from the CSS) must cover
    the small loader file's actual ink — the resize must not have
    shifted the mark outside the windows the animation relies on."""
    from PIL import Image
    import numpy as np

    im = np.array(Image.open(
        PROJECT_ROOT / "assets" / "logo-loader.png").convert("RGBA"))
    cols = np.where((im[..., 3] > 20).any(axis=0))[0]
    ink_lo = cols.min() / 1.92  # percent of the 192px canvas
    ink_hi = cols.max() / 1.92
    css = ui_design.DESIGN_SYSTEM_CSS
    windows = []
    for layer in ("dcs-lm-bar1", "dcs-lm-bar2", "dcs-lm-bar3",
                  "dcs-lm-check"):
        m = re.search(re.escape("." + layer) +
                      r" \{ clip-path: inset\(0 (\d+)% 0 (\d+)%\)", css)
        assert m, f"no clip-path found for {layer}"
        right, left = int(m.group(1)), int(m.group(2))
        windows.append((left, 100 - right))
    merged = []
    for lo, hi in sorted(windows):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    assert len(merged) == 1, f"clip windows must merge to one span: {merged}"
    assert merged[0][0] <= ink_lo and merged[0][1] >= ink_hi, \
        f"merged span {merged} must cover the small file's ink " \
        f"{ink_lo:.1f}–{ink_hi:.1f}%"
    print("round 3 clip windows cover small file OK")


# ---------------------------------------------------------------------------
# 2 — CSS + source: img slices, no custom-property mechanism left
# ---------------------------------------------------------------------------

def test_round3_loader_css_uses_img_slices():
    """Both stylesheets (and the app.py literal, which must stay the
    verbatim light sheet) size the mark's slices as <img>, not divs,
    and carry no trace of the custom-property background image. The
    keyframes and staggered animations are unchanged."""
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r'DESIGN_SYSTEM_CSS = """<style>(.*?)</style>"""',
        source, re.DOTALL)
    assert match, "DESIGN_SYSTEM_CSS block missing from app.py"
    literal = "<style>" + match.group(1) + "</style>"
    assert literal == ui_design.DESIGN_SYSTEM_CSS, \
        "app.py literal must equal ui_design.DESIGN_SYSTEM_CSS verbatim"
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS),
                      ("app.py literal", literal)):
        assert ".dcs-loader-mark > img" in css, \
            f"{name}: mark slices must be styled as <img>"
        assert ".dcs-loader-mark > div" not in css, \
            f"{name}: the div-slice rule must be gone"
        assert "var(--dcs-logo)" not in css, \
            f"{name}: the custom-property background image must be gone"
        for rule in (".dcs-loader", ".dcs-loader-mark", ".dcs-lm-bar1",
                     ".dcs-lm-bar2", ".dcs-lm-bar3", ".dcs-lm-check",
                     ".dcs-loader-status", ".dcs-loader-shimmer",
                     "@keyframes dcs-lm-rise",
                     "@keyframes dcs-lm-drawcheck",
                     "@keyframes dcs-lm-breathe",
                     "@keyframes dcs-lm-slide"):
            assert rule in css, f"{name}: loader rule {rule!r} missing"
        assert "animation: dcs-lm-rise .45s cubic-bezier(.22,1,.36,1) .13s both;" in css, \
            f"{name}: bar2 stagger must be unchanged"
        assert "animation: dcs-lm-drawcheck .6s cubic-bezier(.22,1,.36,1) .45s both;" in css, \
            f"{name}: checkmark draw must be unchanged"
    print("round 3 loader CSS uses img slices OK")


def test_round3_no_custom_property_loader_anywhere():
    """Neither source file may carry the old mechanism at all — not
    even in a comment or a leftover style attribute — so it cannot
    silently come back."""
    for fname in ("ui_design.py", "app.py"):
        src = (PROJECT_ROOT / fname).read_text(encoding="utf-8")
        for bad in ("var(--dcs-logo)", "--dcs-logo: url(",
                    ".dcs-loader-mark > div"):
            assert bad not in src, f"{fname}: still contains {bad!r}"
    print("round 3 no custom-property loader anywhere OK")


def test_round3_loader_logo_path_points_at_small_files():
    """_loader_logo_path must return the 192px loader variants, not
    the full 1024px files — the top bar reuses the same path, so it
    gets the diet too (24px display, visually identical)."""
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == "_loader_logo_path")
    fn_src = ast.get_source_segment(source, node)
    assert '"logo-loader.png"' in fn_src, \
        "_loader_logo_path must return logo-loader.png (light)"
    assert '"logo-loader-dark.png"' in fn_src, \
        "_loader_logo_path must return logo-loader-dark.png (dark)"
    assert '"logo.png"' not in fn_src and '"logo-dark.png"' not in fn_src, \
        "the full-size files must not be the loader path any more"
    print("round 3 loader logo path points at small files OK")


# ---------------------------------------------------------------------------
# 3 — branded_spinner renders the img-slice loader during the wait
# ---------------------------------------------------------------------------

def _exec_branded_spinner_with_loader_file():
    """Exec branded_spinner from app.py source against a fake `st`,
    with _loader_logo_path pointing at the real small loader file."""
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
          "_loader_logo_path": lambda: str(
              PROJECT_ROOT / "assets" / "logo-loader.png"),
          "contextlib": contextlib, "time": time,
          "_BRANDED_SPINNER_MIN_SECONDS": 0.7}
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 str(PROJECT_ROOT / "app.py"), "exec"), ns)
    return ns["branded_spinner"], rendered, cleared


def test_round3_branded_spinner_renders_img_slices():
    """During the wait the spinner must render the branded loader as
    four <img> slices over the small data URI — the mechanism that
    paints live — plus the status, and it must clear afterwards. The
    rendered HTML must be small: the old full-file mark would have
    been ~3MB of HTML per wait."""
    spinner, rendered, cleared = _exec_branded_spinner_with_loader_file()
    with spinner("Loading the sample file…", min_seconds=0.15):
        assert rendered, "spinner must render the loader during the wait"
        html = rendered[0]
        assert "dcs-loader" in html and "dcs-loader--compact" in html
        assert html.count('<img src="data:image/png;base64,') == 4, \
            "loader must render four <img> slices"
        for layer in ("dcs-lm-bar1", "dcs-lm-bar2", "dcs-lm-bar3",
                      "dcs-lm-check"):
            assert f'class="{layer}"' in html, \
                f"loader missing img slice {layer}"
        assert "Loading the sample file…" in html
        assert "dcs-loader-shimmer" in html
        assert "--dcs-logo" not in html, \
            "rendered loader must not use the custom property"
        assert len(html) < 200_000, \
            f"rendered loader is {len(html)} bytes, must stay small"
    assert cleared, "spinner must clear the placeholder when the wait ends"
    print(f"round 3 spinner renders img slices OK "
          f"({len(rendered[0])} bytes)")


# ---------------------------------------------------------------------------
# 4 — the sample load still runs end to end through the spinner path
# ---------------------------------------------------------------------------

def test_round3_sample_cta_loads_through_the_spinner_path(_tmp_env):
    """Clicking the empty-state 'Try the sample data' CTA still loads
    the sample (80 rows) with no exception — the loader restructure
    must not touch the load itself."""
    at = AppTest.from_file(APP)
    at.run()
    _r2.signup(at, "alice1")
    _r2.find_button(at, "Try the sample data").click().run()
    assert not at.exception, f"exception on sample CTA: {at.exception}"
    assert at.session_state["raw"] is not None, "sample did not load"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    print("round 3 sample CTA loads OK")


if __name__ == "__main__":
    # Pure tests only — the AppTest one needs the _tmp_env fixture,
    # so it runs under pytest, not here.
    test_round3_loader_files_exist_and_small()
    test_round3_loader_clip_windows_cover_small_file()
    test_round3_loader_css_uses_img_slices()
    test_round3_no_custom_property_loader_anywhere()
    test_round3_loader_logo_path_points_at_small_files()
    test_round3_branded_spinner_renders_img_slices()
    print("ALL ROUND 3 PURE TESTS PASSED")
