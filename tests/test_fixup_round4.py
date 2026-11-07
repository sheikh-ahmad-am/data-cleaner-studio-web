"""Round-4 fix tests (2026-11-07): the branded loader must be VISIBLE
without scrolling whenever it appears.

Why this file exists: round 3 proved the loader paints live (the
<img>-slice mark), but the live check (21:09-21:19 IST) found it
renders directly below the "Try the sample data" button, which sits
at the very bottom edge of the empty state — so at 100% zoom the
loader is BELOW THE FOLD and invisible unless the user scrolls. The
first two loads the checker could not see it at all; only on the
third load, with the page scrolled so the button sat higher, was it
visible.

The fix is placement-only, CSS-only: the compact loader (the size
``branded_spinner`` renders for every wait — sample, sheet, table,
upload-open, login, cleaning, share link) is now a small fixed,
centred card on top of the page content, so it is in view wherever
the triggering button sits and whichever call site fired it. The
look is unchanged (same mark, status, shimmer, 0.7s hold); the large
loader on the login screen stays in-flow at the top of that screen,
where it is already visible. The card has ``pointer-events: none``
so it can never intercept a click, and being ``position: fixed`` it
is out of the document flow — it cannot shift the page layout when
it appears or disappears (no content jumping); clearing the
placeholder removes it entirely, exactly as before.

Run ONLY this file:  .test-venv-wave3/bin/python -m pytest
tests/test_fixup_round4.py -q   (from project root)
"""

import re
import sys
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


def _compact_rule(css):
    """The .dcs-loader--compact rule block (not its descendant rules)."""
    m = re.search(r"\.dcs-loader--compact \{([^}]*)\}", css, re.DOTALL)
    assert m, "no .dcs-loader--compact rule found"
    return m.group(1)


def _sheets():
    """(light sheet, dark sheet, app.py literal) — the literal must
    stay the verbatim light sheet."""
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r'DESIGN_SYSTEM_CSS = """<style>(.*?)</style>"""',
        source, re.DOTALL)
    assert match, "DESIGN_SYSTEM_CSS block missing from app.py"
    literal = "<style>" + match.group(1) + "</style>"
    assert literal == ui_design.DESIGN_SYSTEM_CSS, \
        "app.py literal must equal ui_design.DESIGN_SYSTEM_CSS verbatim"
    return (('light', ui_design.DESIGN_SYSTEM_CSS, '#ffffff'),
            ('dark', ui_design.DARK_CSS, '#232625'),
            ('app.py literal', literal, '#ffffff'))


# ---------------------------------------------------------------------------
# 1 — the compact loader is a fixed, centred, non-blocking card
# ---------------------------------------------------------------------------

def test_round4_compact_loader_is_fixed_centred_card():
    """The compact loader (the only size branded_spinner renders) is
    fixed to the centre of the viewport with a card background, so it
    is in view wherever the triggering button sits — including the
    empty-state CTA at the bottom of the page. It must never
    intercept clicks (pointer-events: none) and must stay above
    Streamlit's own chrome (z-index above 1000000). The card uses
    each theme's own tokens: white card on light, #232625 on dark."""
    for name, css, card_bg in _sheets():
        rule = _compact_rule(css)
        assert "position: fixed" in rule, \
            f"{name}: compact loader must be position: fixed"
        assert "top: 50%" in rule, f"{name}: card must be centred vertically"
        assert "left: 50%" in rule, f"{name}: card must be centred horizontally"
        assert "transform: translate(-50%, -50%)" in rule, \
            f"{name}: card must be offset back by half its own size"
        m = re.search(r"z-index: (\d+)", rule)
        assert m and int(m.group(1)) >= 1000000, \
            f"{name}: card z-index must sit above Streamlit chrome, got {rule!r}"
        assert "pointer-events: none" in rule, \
            f"{name}: card must never intercept clicks"
        assert f"background: {card_bg}" in rule, \
            f"{name}: card background must be the {name} card token {card_bg}"
        assert "border: 1px solid" in rule, \
            f"{name}: card needs a hairline border to read over page content"
        assert "border-radius: 12px" in rule, \
            f"{name}: card must be a rounded card, not a bare rectangle"
        assert "max-width: 90vw" in rule, \
            f"{name}: card must not blow out on a narrow viewport"
    # No dark token may leak into the light sheet.
    assert "#232625" not in ui_design.DESIGN_SYSTEM_CSS, \
        "light sheet must not carry the dark card token"
    print("round 4 compact loader is a fixed centred card OK")


# ---------------------------------------------------------------------------
# 2 — only the compact loader is fixed; the large one stays in-flow
# ---------------------------------------------------------------------------

def test_round4_large_loader_stays_in_flow():
    """Exactly one fixed element per sheet — the compact loader. The
    base .dcs-loader rule and the large loader (login screen, rendered
    at the top of that screen where it is already visible) must stay
    in normal flow: fixing the large one would yank the login screen's
    centred column out of place."""
    for name, css, _bg in _sheets():
        assert css.count("position: fixed") == 1, \
            f"{name}: exactly one fixed rule (the compact loader), " \
            f"got {css.count('position: fixed')}"
        base = re.search(r"\.dcs-loader \{([^}]*)\}", css, re.DOTALL)
        assert base, f"{name}: base .dcs-loader rule missing"
        assert "position" not in base.group(1), \
            f"{name}: base loader rule must stay in-flow"
        large = re.search(
            r"\.dcs-loader--large \.dcs-loader-mark \{([^}]*)\}",
            css, re.DOTALL)
        assert large, f"{name}: large loader mark rule missing"
        assert "position" not in large.group(1), \
            f"{name}: large loader mark must stay in-flow"
    print("round 4 large loader stays in-flow OK")


# ---------------------------------------------------------------------------
# 3 — the look is unchanged: same mark, status, shimmer, 0.7s hold
# ---------------------------------------------------------------------------

def test_round4_loader_look_unchanged():
    """Placement only — the mark slices, staggered rise/draw, shimmer
    and the 0.7s minimum hold are all untouched, in both themes, and
    the rendered compact HTML is the same structure round 3 proved
    paints live. The spinner must still clear its placeholder when
    the wait ends."""
    for name, css, _bg in _sheets():
        for rule in (".dcs-loader-mark > img", ".dcs-lm-bar1",
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
    html = ui_design.loader_block_html(
        PROJECT_ROOT / "assets" / "logo-loader.png",
        "Loading the sample file…", size="compact")
    assert 'class="dcs-loader dcs-loader--compact"' in html
    assert html.count('<img src="data:image/png;base64,') == 4, \
        "compact loader must still render four <img> slices"
    assert "Loading the sample file…" in html
    assert "dcs-loader-shimmer" in html
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert "_BRANDED_SPINNER_MIN_SECONDS = 0.7" in source, \
        "the 0.7s minimum hold must be unchanged"
    assert "_ph.empty()" in source, \
        "branded_spinner must still clear its placeholder on exit"
    print("round 4 loader look unchanged OK")


# ---------------------------------------------------------------------------
# 4 — the sample load still runs end to end through the spinner path
# ---------------------------------------------------------------------------

def test_round4_sample_cta_loads_through_the_spinner_path(_tmp_env):
    """Clicking the empty-state 'Try the sample data' CTA still loads
    the sample (80 rows) with no exception — the placement change is
    CSS-only and must not touch the load itself."""
    at = AppTest.from_file(APP)
    at.run()
    _r2.signup(at, "alice1")
    _r2.find_button(at, "Try the sample data").click().run()
    assert not at.exception, f"exception on sample CTA: {at.exception}"
    assert at.session_state["raw"] is not None, "sample did not load"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    print("round 4 sample CTA loads OK")


if __name__ == "__main__":
    # Pure tests only — the AppTest one needs the _tmp_env fixture,
    # so it runs under pytest, not here.
    test_round4_compact_loader_is_fixed_centred_card()
    test_round4_large_loader_stays_in_flow()
    test_round4_loader_look_unchanged()
    print("ALL ROUND 4 PURE TESTS PASSED")
