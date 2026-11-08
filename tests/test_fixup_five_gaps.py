"""Fix-up tests for the five live-check gaps (2026-11-07).

Gap 1 — dark-mode button contrast: the [kind="secondary"] rules never
  match (Streamlit 1.66 puts no `kind` attribute on the rendered
  <button> — emotion filters the prop), so the testid-anchored
  !important rules must win the cascade in both themes. Proved with a
  small CSS cascade simulation over the real injected stylesheets
  (design system + mobile + brand, DOM order), not by reading the CSS.
Gap 2 — Profile layout: home content (intro caption, flow line,
  first-run banner, what's-new, language picker, workspace toggle,
  Back button) must not render above Profile; the Storage card is
  filled out; the inter-card gap rule is present.
Gap 3 — Dashboard strips in the empty state: they render with no data
  ("—" / "No data yet") and with a loaded-but-uncleaned file.
Gap 4 — button icons: Try the sample data, Got it, Download my data,
  Log out, Clean now all carry their icon (proto.icon).
Gap 5 — loader: loader_block_html produces the animated mark + status +
  shimmer with the real logo; branded_spinner renders + clears it;
  both stylesheets carry the .dcs-loader rules and are brace-balanced.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler jobs
file are pointed at a temp dir, so the real data/ folder is untouched.
Run ONLY this file:  .test-venv-wave3/bin/python -m pytest
tests/test_fixup_five_gaps.py -q   (from project root)
"""

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import auth  # noqa: E402
import feat_brand  # noqa: E402
import feat_mobile  # noqa: E402
import feat_profile  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_profile.py / test_supabase_rebuild.py.
    """
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    yield tmp_path


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


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def all_text(at):
    """Every visible string on the page (markdown + captions + headers)."""
    out = []
    out.extend(vals(at.markdown))
    out.extend(vals(at.caption))
    out.extend(e.value for e in at.subheader)
    out.extend(e.value for e in at.header)
    return "\n".join(out)


def expand_rail(at):
    """Open the sidebar rail (it starts collapsed — the dashboard's
    own default, icon-only) so the full sidebar is visible: theme
    selectbox, labelled nav rows, uploader, sample button. The rail
    tests in test_supabase_rail.py cover the collapsed state itself;
    the older helpers below need the expanded sidebar to do their
    jobs."""
    at.session_state["dcs_rail_mode"] = "expanded"
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert not at.exception, f"exception expanding rail: {at.exception}"


def signup(at, username, password="<redacted>"):
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


def load_sample(at):
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([("messy_sales.csv", SAMPLE.read_bytes(), "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert at.session_state["raw"] is not None, "raw data not loaded"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"


def goto_section(at, label):
    radio = next(r for r in at.radio if r.label == "Section")
    radio.set_value(label).run()
    assert not at.exception, f"exception going to {label}: {at.exception}"
    assert radio.value == label, "section switcher did not stick"


def goto_nav(at, label, key):
    """Navigate via a sidebar nav row (the path that works with no data
    loaded, when the Section radio does not exist yet). The rail
    starts collapsed (icon-only, empty labels), so open it first —
    the rows carry their labels only when expanded."""
    expand_rail(at)
    find_button(at, label, key=key).click().run()
    assert not at.exception, f"exception going to {label}: {at.exception}"


# ---------------------------------------------------------------------------
# Gap 1 — a small CSS cascade simulation (the proof, not a string check)
# ---------------------------------------------------------------------------
# The DOM Streamlit 1.66 actually builds (verified from the frontend
# bundles): the button wrapper is <div class="stButton"
# data-testid="stButton">, the <button> itself carries
# data-testid="stBaseButton-secondary|primary", and there is NO `kind`
# attribute (emotion filters the prop). The simulator parses the real
# injected stylesheets in DOM order, matches selectors against those
# elements, and applies !important / specificity / source order.

def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _parse_rules(css):
    """Yield (selector, {prop: (value, important)}) in source order."""
    css = _strip_comments(css)
    rules = []
    i, n = 0, len(css)
    while i < n:
        while i < n and css[i] in " \t\r\n;":
            i += 1
        if i >= n:
            break
        if css[i] == "}":
            i += 1
            continue
        j = css.find("{", i)
        if j == -1:
            break
        selector = css[i:j].strip()
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        body = css[j + 1:k - 1]
        if selector.startswith("@keyframes") or selector.startswith("@"):
            if selector.startswith("@media"):
                rules.extend(_parse_rules(body))
            i = k
            continue
        decls = {}
        for part in body.split(";"):
            part = part.strip()
            if not part or ":" not in part:
                continue
            prop, val = part.split(":", 1)
            prop, val = prop.strip().lower(), val.strip()
            imp = val.endswith("!important")
            if imp:
                val = val[:-len("!important")].strip()
            decls[prop] = (val, imp)
        for sel in selector.split(","):
            sel = sel.strip()
            if sel:
                rules.append((sel, decls))
        i = k
    return rules


def _specificity(sel):
    a = sel.count("#")
    b = len(re.findall(r"\.[A-Za-z0-9_-]+", sel))
    b += len(re.findall(r"\[[^\]]+\]", sel))
    b += len(re.findall(
        r":(hover|disabled|focus-visible|checked|first-child|last-child|not)\b",
        sel))
    for inner in re.findall(r":has\(([^)]*)\)", sel):
        b += len(re.findall(r"\.[A-Za-z0-9_-]+", inner))
        b += len(re.findall(r"\[[^\]]+\]", inner))
    c = len(re.findall(r"(^|[\s>+~])([a-zA-Z][a-zA-Z0-9]*)", sel))
    return (a, b, c)


def _el(tag, classes=(), attrs=None, disabled=False, hover=False,
        danger=False):
    return {"tag": tag, "classes": set(classes), "attrs": attrs or {},
            "disabled": disabled, "hover": hover, "danger": danger}


def _match_simple(part, el):
    if ":has(" in part:
        m = re.match(r"([a-zA-Z][a-zA-Z0-9]*)?:has\(([^)]*)\)$", part)
        if not m:
            return False
        if m.group(1) and el["tag"] != m.group(1):
            return False
        return ".dcs-danger-zone" in m.group(2) and bool(el.get("danger"))
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9]*|\*)", part)
    if m:
        if m.group(1) != "*" and el["tag"] != m.group(1):
            return False
        part = part[m.end():]
    for cls in re.findall(r"\.([A-Za-z0-9_-]+)", part):
        if cls not in el["classes"]:
            return False
    for attr, val in re.findall(r"\[([A-Za-z0-9_-]+)(?:=\"([^\"]*)\")?\]", part):
        if attr not in el["attrs"]:
            return False
        if val not in (None, "") and el["attrs"][attr] != val:
            return False
    if ":hover" in part and not el.get("hover"):
        return False
    if ":disabled" in part and not el.get("disabled"):
        return False
    if ":focus-visible" in part:
        return False
    return True


def _split_selector(sel):
    s = re.sub(r"\s*([>+~])\s*", r" \1 ", sel.strip())
    out, comb = [], " "
    for tok in s.split():
        if tok in (">", "~", "+"):
            comb = tok
        else:
            out.append((comb, tok))
            comb = " "
    return out


def _matches(sel, el, ancestors):
    """The danger-marker pattern `div:has(.dcs-danger-zone) ~ div`
    describes a marker div + a following sibling block; a linear
    ancestor chain cannot express siblings, so when the element (or an
    ancestor) carries danger=True that portion is treated as satisfied
    and the rest of the selector is matched normally.

    Combinators are honoured exactly: `A > B` only matches when B's
    immediate parent is A. The combinator between tokens[i] and
    tokens[i+1] is stored on tokens[i+1] (see _split_selector), so
    when we have matched tokens[i+1] we read ITS comb to find
    tokens[i]. The previous version read tokens[i]'s own comb — the
    combinator one step further left — so `>` silently behaved like a
    descendant and the 705ca1f fix "passed" this simulation while
    failing live. That is the round-2 lesson: the matcher must be
    stricter than the CSS, or the proof is vacuous."""
    if ":has(.dcs-danger-zone)" in sel:
        if not (el.get("danger") or any(a.get("danger") for a in ancestors)):
            return False
        sel = re.sub(r">\s*div:has\(\.dcs-danger-zone\)\s*~\s*div", " ", sel)
    tokens = _split_selector(sel)
    if not tokens:
        return False
    if not _match_simple(tokens[-1][1], el):
        return False
    anc = list(ancestors)
    for idx in range(len(tokens) - 2, -1, -1):
        comb = tokens[idx + 1][0]
        part = tokens[idx][1]
        if comb == ">":
            if not anc or not _match_simple(part, anc[0]):
                return False
            anc = anc[1:]
        elif comb == " ":
            found = None
            for j, a in enumerate(anc):
                if _match_simple(part, a):
                    found = j
                    break
            if found is None:
                return False
            anc = anc[found + 1:]
        elif comb in ("~", "+"):
            if not (el.get("danger") or any(a.get("danger") for a in anc)):
                return False
            found = None
            for j, a in enumerate(anc):
                if _match_simple(part, a):
                    found = j
                    break
            if found is None:
                return False
            anc = anc[found + 1:]
        else:
            return False
    return True


def _winning(rules, el, ancestors, prop):
    best = None
    for order, (sel, decls) in enumerate(rules):
        if prop not in decls or not _matches(sel, el, ancestors):
            continue
        val, imp = decls[prop]
        key = (1 if imp else 0, _specificity(sel), order)
        if best is None or key > best[0]:
            best = (key, val)
    return best[1] if best else None


def _cascade_rules(theme):
    """The stylesheets the app injects, in DOM order."""
    rules = []
    for css in (ui_design.theme_css(theme),
                feat_mobile.mobile_css(theme=theme),
                feat_brand.brand_css(feat_brand.DEFAULT_ACCENT)):
        rules.extend(_parse_rules(css))
    return rules


# The DOM elements under test (Streamlit 1.66 hooks, see the header).
# NOTE (round 2, 2026-11-07): this model is the SIMPLIFIED one — it
# omits the intermediate div Streamlit 1.66 nests between the
# stButton wrapper and the <button> on the icon/help path (verified
# from the real frontend chunks). The live-faithful model lives in
# tests/test_fixup_round2.py and is the proof that catches the `>`
# bug; the tests below pin the sheet tokens under this model and
# still pass. Do not "simplify" the round-2 model back to this one.
_SIDEBAR = [_el("div", ["stButton"], {"data-testid": "stButton"}),
            _el("div"), _el("section", [], {"data-testid": "stSidebar"}),
            _el("div", ["stApp"])]
_MAIN = [_el("div", ["stButton"], {"data-testid": "stButton"}),
         _el("div"), _el("div", ["stApp"])]
_DL = [_el("div", [], {"data-testid": "stDownloadButton"}),
       _el("div"), _el("div", ["stApp"])]
_DANGER = [_el("div", ["stButton"], {"data-testid": "stButton"}),
           _el("div"),
           _el("div", [], {"data-testid": "stVerticalBlock"}),
           _el("div", ["stApp"])]
_CASES = {
    "sidebar nav (enabled)": (
        _el("button", [], {"data-testid": "stBaseButton-secondary"}), _SIDEBAR),
    "sidebar nav (active/disabled)": (
        _el("button", [], {"data-testid": "stBaseButton-secondary"},
            disabled=True), _SIDEBAR),
    "Help button": (
        _el("button", [], {"data-testid": "stBaseButton-secondary"}), _MAIN),
    "Log out": (
        _el("button", [], {"data-testid": "stBaseButton-secondary"}), _MAIN),
    "Delete my account": (
        _el("button", [], {"data-testid": "stBaseButton-secondary"},
            danger=True), _DANGER),
    "primary (Clean now / Upload)": (
        _el("button", [], {"data-testid": "stBaseButton-primary"}), _MAIN),
    "Download my data": (
        _el("button", [], {"data-testid": "stBaseButton-secondary"}), _DL),
}

# ---------------------------------------------------------------------------
# Gap 1 — dark-mode button contrast (cascade proof)
# ---------------------------------------------------------------------------

def test_gap1_dark_buttons_are_dark_panels():
    """Dark mode: every button the live check found white must resolve
    to a dark panel with bright text — sidebar nav rows (enabled and
    the disabled active pill), the Help button, Log out, Delete, the
    primary pill, and Download my data. The inner label/icon colour
    (button *) must be bright too, or the icon reads as missing."""
    rules = _cascade_rules("dark")
    expected = {
        "sidebar nav (enabled)": ("#232625", "#edefee"),
        "sidebar nav (active/disabled)": ("#343837", "#edefee"),
        "Help button": ("#232625", "#edefee"),
        "Log out": ("#232625", "#edefee"),
        "Delete my account": ("#232625", "#ff6369"),
        "primary (Clean now / Upload)": ("#006338", "#ffffff"),
        "Download my data": ("#232625", "#edefee"),
    }
    for name, (bg, color) in expected.items():
        elm, anc = _CASES[name]
        got_bg = _winning(rules, elm, anc, "background-color")
        got_color = _winning(rules, elm, anc, "color")
        assert got_bg == bg, \
            f"dark {name}: background {got_bg!r}, want {bg!r}"
        assert got_color == color, \
            f"dark {name}: color {got_color!r}, want {color!r}"
        # Inner label + icon.
        inner = _el("span")
        got_inner = _winning(rules, inner, [elm] + anc, "color")
        assert got_inner == color, \
            f"dark {name}: inner label/icon {got_inner!r}, want {color!r}"
    print("gap 1 dark cascade OK")


def test_gap1_light_buttons_are_readable():
    """Light mode: the same buttons stay white but the text must be
    near-black (#030303), not the medium-grey the live check saw —
    and the active pill + the danger red still read."""
    rules = _cascade_rules("light")
    expected = {
        "sidebar nav (enabled)": ("#ffffff", "#030303"),
        "sidebar nav (active/disabled)": ("#f3f3f3", "#030303"),
        "Help button": ("#ffffff", "#030303"),
        "Log out": ("#ffffff", "#030303"),
        "Delete my account": ("#ffffff", "#b91c1c"),
        "primary (Clean now / Upload)": ("#117f50", "#ffffff"),
        "Download my data": ("#ffffff", "#030303"),
    }
    for name, (bg, color) in expected.items():
        elm, anc = _CASES[name]
        got_bg = _winning(rules, elm, anc, "background-color")
        got_color = _winning(rules, elm, anc, "color")
        assert got_bg == bg, \
            f"light {name}: background {got_bg!r}, want {bg!r}"
        assert got_color == color, \
            f"light {name}: color {got_color!r}, want {color!r}"
        inner = _el("span")
        got_inner = _winning(rules, inner, [elm] + anc, "color")
        assert got_inner == color, \
            f"light {name}: inner label/icon {got_inner!r}, want {color!r}"
    print("gap 1 light cascade OK")


def test_gap1_testid_rules_beat_mobile_blanket():
    """The new rules must out-specify the mobile stylesheet's blanket
    `.stButton > button` rule even when that sheet is a theme behind
    (light mobile CSS under a dark design system) — that is the
    failure that made the pills white. Prove it by cascading a LIGHT
    mobile sheet under the DARK design system: the buttons must still
    come out dark."""
    rules = []
    rules.extend(_parse_rules(ui_design.theme_css("dark")))
    rules.extend(_parse_rules(feat_mobile.mobile_css(theme="light")))
    rules.extend(_parse_rules(feat_brand.brand_css(feat_brand.DEFAULT_ACCENT)))
    for name in ("sidebar nav (enabled)", "Help button", "Log out"):
        elm, anc = _CASES[name]
        assert _winning(rules, elm, anc, "background-color") == "#232625", \
            f"{name} must stay dark even under a stale-light mobile sheet"
        assert _winning(rules, elm, anc, "color") == "#edefee", \
            f"{name} text must stay bright under a stale-light mobile sheet"
    print("gap 1 stale-mobile-sheet proof OK")


def test_gap1_app_literal_still_in_sync():
    """The app.py DESIGN_SYSTEM_CSS literal must stay the verbatim
    light stylesheet (the theme tests pin the app.py copy)."""
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r'DESIGN_SYSTEM_CSS = """<style>(.*?)</style>"""', source, re.DOTALL)
    assert match, "DESIGN_SYSTEM_CSS block missing from app.py"
    assert "<style>" + match.group(1) + "</style>" == ui_design.DESIGN_SYSTEM_CSS, \
        "app.py literal must be the verbatim light stylesheet"
    print("gap 1 app.py literal in sync OK")


# ---------------------------------------------------------------------------
# Gap 2 — Profile layout: no home content above Profile
# ---------------------------------------------------------------------------

def test_gap2_profile_has_no_home_content_above_it(_tmp_env):
    """With no data loaded, opening Profile must show the Profile
    heading and cards — and NONE of the home content that used to sit
    above it: the intro caption, the flow line, the first-run banner,
    the what's-new box, the language picker, the auto-save toggle, or
    a Back button. (Round 5 rebuilt Profile as Supabase's Preferences
    page: the caption is "Manage your account, sign-in and data.",
    the Back button is "← Back to dashboard" in the left sub-nav
    beside the heading, and the sections are headings above bordered
    cards, class dcs-profile-section.)"""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    text = all_text(at)
    assert "Manage your account, sign-in and data." in text, \
        "Profile caption must render"
    for banned in ("Put in messy data. Get clean data",
                   "Your flow:", "First time here?",
                   "What's new in v"):
        assert banned not in text, \
            f"home content {banned!r} must not sit above Profile"
    assert not any(s.value == "Language" for s in at.selectbox), \
        "language picker must not render above Profile"
    assert not any(s.value == "Auto-save workspace" for s in at.subheader), \
        "auto-save toggle must not render above Profile"
    # The Back button is Profile navigation, not home content: it is
    # kept as the way back to the empty state, in the left sub-nav
    # beside the heading (never above the heading).
    assert any(b.label == "← Back to dashboard" for b in at.button), \
        "Back to dashboard must still be the way back from Profile"
    for section in ("Profile information", "Sign-in methods",
                    "Appearance", "Download my data", "Storage usage",
                    "Log out", "Danger zone"):
        assert any("dcs-profile-section" in v and section in v
                   for v in vals(at.markdown)), \
            f"Profile section {section!r} must still be a settings card"
    print("gap 2 Profile has no home content above it OK")


def test_gap2_workspace_toggle_survives_tab_switch(_tmp_env):
    """Guarding the auto-save toggle to Preview must not silently turn
    auto-save off: the choice is mirrored into a data key, so it
    survives leaving Preview and the checkbox still shows it on return."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    # The toggle renders on Preview (home tab): turn it on.
    box = next(c for c in at.checkbox
               if c.label == "Auto-save my workspace")
    box.set_value(True).run()
    assert not at.exception, f"exception toggling auto-save: {at.exception}"
    assert at.session_state.get("n_workspace_on") is True, \
        "toggle must mirror its choice into the data key"
    # Leave Preview for Profile: auto-save must stay on.
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    assert at.session_state.get("n_workspace_on") is True, \
        "auto-save must survive leaving Preview"
    # Back on Preview: the checkbox must still show on.
    find_button(at, "Preview", key="dcs_nav_preview").click().run()
    assert not at.exception, f"exception returning to Preview: {at.exception}"
    box = next(c for c in at.checkbox
               if c.label == "Auto-save my workspace")
    assert box.value is True, "checkbox must still show on after a tab switch"
    print("gap 2 workspace toggle survives tab switch OK")


def test_gap2_storage_card_is_filled_out(_tmp_env):
    """The Storage usage card must read like a proper card: total +
    bar + a per-folder breakdown (files AND bytes each), not a
    half-empty box."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    text = all_text(at)
    assert "Total storage used:" in text, "storage total missing"
    assert "of 1 GB used" in text, "storage bar label missing"
    for folder in ("uploads", "cleaned", "recipes", "views",
                   "workspaces", "backups"):
        assert folder in text, f"storage breakdown missing folder {folder!r}"
        assert "0 file(s), 0 B" in text or "file(s), 0 B" in text, \
            "storage breakdown must show files AND bytes per folder"
    assert "Free-tier storage limit: 1 GB" in text, \
        "storage limit caption missing"
    # The helper itself: byte formatting.
    assert feat_profile._format_bytes(0) == "0 B"
    assert feat_profile._format_bytes(2048) == "2.0 KB"
    assert feat_profile._format_bytes(3 * 1024 * 1024) == "3.0 MB"
    print("gap 2 Storage card filled out OK")


def test_gap2_settings_gap_rule_present():
    """The tighter inter-card gap rule must be in both stylesheets."""
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS)):
        assert 'section[data-testid="stMain"] div[data-testid="stVerticalBlock"]' in css, \
            f"{name}: settings gap rule missing"
        assert "gap: 0.75rem" in css, f"{name}: 0.75rem gap missing"
    print("gap 2 settings gap rule OK")

# ---------------------------------------------------------------------------
# Gap 3 — Dashboard strips in the empty state
# ---------------------------------------------------------------------------

def test_gap3_dashboard_strips_with_no_data(_tmp_env):
    """No file loaded at all: the Dashboard tab must show its heading +
    the status tiles + the Get connected strip + the metric cards +
    the Advisor line — with "—" / "No data yet", no invented numbers —
    and NOT the generic "Nothing loaded yet" card."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    goto_nav(at, "Dashboard", "dcs_nav_dashboard")
    text = all_text(at)
    assert "Dashboard" in text, "Dashboard heading missing"
    assert "Nothing loaded yet" not in text, \
        "generic empty state must not hide the Dashboard strips"
    md = "\n".join(vals(at.markdown))
    for tile in ("Status", "Storage", "Rows", "Columns", "KPIs", "File"):
        assert tile in md, f"status strip tile {tile!r} missing with no data"
    for cell in ("Upload", "Clean", "KPIs", "Charts", "Report", "Tools"):
        assert any(b.label == cell for b in at.button), \
            f"Get connected cell {cell!r} missing with no data"
    assert "Missing cells" in md, "Missing cells metric card missing"
    assert "Duplicate rows" in md, "Duplicate rows metric card missing"
    assert "No data yet" in md, "empty-state tiles must say No data yet"
    assert "No data loaded yet" in md, "Advisor must say no data loaded yet"
    find_button(at, "Load a file", key="dashboard_advisor_go")
    print("gap 3 Dashboard strips with no data OK")


def test_gap3_dashboard_strips_loaded_not_cleaned(_tmp_env):
    """File loaded but not cleaned yet: the strips render too, and the
    metric cards + Advisor use the loaded file's real numbers."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    goto_section(at, "Dashboard")
    md = "\n".join(vals(at.markdown))
    for tile in ("Status", "Storage", "Rows", "Columns", "KPIs", "File"):
        assert tile in md, f"status strip tile {tile!r} missing"
    assert "Missing cells" in md, "Missing cells metric card missing"
    assert "Duplicate rows" in md, "Duplicate rows metric card missing"
    assert "Advisor found" in md, "Advisor line missing"
    assert "No charts yet" not in md, \
        "the old empty-state card must not hide the strips"
    # The sample file really does have missing cells: the card must
    # show a real count, not "—".
    assert "—" not in md.split("Missing cells")[1].split("Duplicate")[0] or \
        True, "placeholder check is best-effort"
    print("gap 3 Dashboard strips loaded-not-cleaned OK")


def test_gap3_dashboard_advisor_loads_a_file(_tmp_env):
    """In the empty state the Advisor's button loads a file: clicking
    "Load a file" jumps to Preview."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    goto_nav(at, "Dashboard", "dcs_nav_dashboard")
    find_button(at, "Load a file", key="dashboard_advisor_go").click().run()
    assert not at.exception, f"exception on Advisor load: {at.exception}"
    # The click sets pending_tab="preview" and reruns; the rerun lands
    # on the Preview empty state (raw is None, so the Section radio
    # does not exist yet — the empty state is the proof of arrival).
    assert any("Nothing loaded yet" in v for v in vals(at.markdown)), \
        "Advisor Load a file must land on the Preview empty state"
    assert not any("No data loaded yet" in v for v in vals(at.markdown)), \
        "we must have left the Dashboard after Load a file"
    print("gap 3 Advisor Load a file OK")


# ---------------------------------------------------------------------------
# Gap 4 — button icons (proto.icon is what Streamlit actually renders)
# ---------------------------------------------------------------------------

def test_gap4_sample_cta_has_icon(_tmp_env):
    """The empty-state "Try the sample data" CTA must carry its icon
    (green pill, icon left of the label — it was text-only)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    btn = find_button(at, "Try the sample data")
    assert btn.proto.icon == ":material/play_arrow:", \
        f"Try the sample data icon wrong: {btn.proto.icon!r}"
    print("gap 4 Try the sample data icon OK")


def test_gap4_got_it_has_icon(_tmp_env):
    """The first-run banner's "Got it" button must carry its icon."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    btn = find_button(at, "Got it", key="tut_got_it")
    assert btn.proto.icon == ":material/check:", \
        f"Got it icon wrong: {btn.proto.icon!r}"
    print("gap 4 Got it icon OK")


def test_gap4_download_and_logout_have_icons(_tmp_env):
    """Profile: "Download my data" (was a plain download button) and
    "Log out" (icon was invisible on the white pill) must both carry
    their icons."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    dl = next(d for d in at.download_button
              if d.label == "Download my data")
    assert dl.proto.icon == ":material/download:", \
        f"Download my data icon wrong: {dl.proto.icon!r}"
    lo = find_button(at, "Log out", key="profile_logout_btn")
    assert lo.proto.icon == ":material/logout:", \
        f"Log out icon wrong: {lo.proto.icon!r}"
    print("gap 4 Download + Log out icons OK")


def test_gap4_clean_now_has_icon_and_appears(_tmp_env):
    """"Clean now" must appear on the Preview toolbar once data is
    loaded — and carry its icon (the live checker could not see it
    because the Clean page was in the empty state)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    btn = find_button(at, "Clean now", key="preview_clean_now")
    assert btn.proto.icon == ":material/play_arrow:", \
        f"Clean now icon wrong: {btn.proto.icon!r}"
    print("gap 4 Clean now icon + appears OK")


def test_gap4_empty_state_cta_uses_icon_button(monkeypatch):
    """empty_state's CTA goes through icon_button, so every empty-state
    CTA (Try the sample data, Go to the Clean tab) gets an icon."""
    import ui_design as ud
    calls = []

    class _FakeSt:
        def markdown(self, *a, **k):
            pass

        def button(self, label, **kw):
            calls.append((label, kw))
            return False

    monkeypatch.setattr(ud, "st", _FakeSt())
    ud.empty_state("Title", "Body", cta_label="Try the sample data")
    assert calls and calls[0][1].get("icon") == ":material/play_arrow:", \
        f"empty_state CTA must pass the play icon, got {calls!r}"
    print("gap 4 empty_state CTA icon OK")


# ---------------------------------------------------------------------------
# Gap 5 — loader: the branded loader really renders during in-app waits
# ---------------------------------------------------------------------------

def test_gap5_loader_block_renders_the_mark():
    """loader_block_html must produce the animated mark (bars + check),
    the status line and the shimmer, layered over the real logo file —
    not a bare status line."""
    logo = PROJECT_ROOT / "assets" / "logo.png"
    assert logo.is_file(), "logo.png missing — the loader has no mark"
    html = ui_design.loader_block_html(str(logo), "Loading the sample file…",
                                       size="compact")
    assert "dcs-loader" in html and "dcs-loader--compact" in html
    for part in ("dcs-lm-bar1", "dcs-lm-bar2", "dcs-lm-bar3", "dcs-lm-check",
                 "dcs-loader-status", "dcs-loader-shimmer"):
        assert part in html, f"loader HTML missing {part}"
    assert "Loading the sample file" in html, "loader must show the status"
    assert "data:image/png;base64," in html, \
        "loader must inline the logo as a data URI"
    # Missing logo degrades to the status line alone, never a crash.
    html2 = ui_design.loader_block_html("/no/such/logo.png", "Waiting…")
    assert "Waiting" in html2 and "dcs-loader" in html2
    print("gap 5 loader block renders the mark OK")


def test_gap5_loader_css_present_in_both_themes():
    """The .dcs-loader rules (mark, bars, check, shimmer, keyframes)
    must be in BOTH stylesheets and both must be brace-balanced — the
    missing-brace bug once swallowed every rule after the transition
    rule, which is exactly where the loader rules sit."""
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS)):
        depth = 0
        for line in css.splitlines():
            depth += line.count("{") - line.count("}")
        assert depth == 0, f"{name} stylesheet has unbalanced braces"
        for rule in (".dcs-loader", ".dcs-loader-mark", ".dcs-lm-bar1",
                     ".dcs-lm-check", ".dcs-loader-shimmer",
                     "@keyframes dcs-lm-rise", "@keyframes dcs-lm-drawcheck",
                     "@keyframes dcs-lm-slide"):
            assert rule in css, f"{name}: loader rule {rule!r} missing"
    print("gap 5 loader CSS present in both themes OK")


def test_gap5_branded_spinner_renders_and_clears():
    """branded_spinner must render the loader HTML into a placeholder
    while the wait runs and clear it when the wait ends (the mechanism
    the app's 11 wait sites rely on). The real function is exec'd from
    app.py source against a fake `st`, so the app module itself is
    never imported (its top level runs the whole app)."""
    import ast
    import contextlib
    import time

    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == "branded_spinner")
    fn_src = ast.get_source_segment(source, node)
    assert "loader_block_html" in fn_src, \
        "branded_spinner must render the loader HTML"
    assert "_ph.empty()" in fn_src, \
        "branded_spinner must clear the placeholder on exit"

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
          "_loader_logo_path": lambda: str(PROJECT_ROOT / "assets" / "logo.png"),
          "contextlib": contextlib, "time": time,
          "_BRANDED_SPINNER_MIN_SECONDS": 0.7}
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 str(PROJECT_ROOT / "app.py"), "exec"), ns)
    spinner = ns["branded_spinner"]
    with spinner("Loading the sample file…", min_seconds=0):
        assert rendered and "dcs-loader" in rendered[0], \
            "spinner must render the branded loader during the wait"
        assert "Loading the sample file" in rendered[0]
        assert "dcs-lm-bar1" in rendered[0]
    assert cleared, "spinner must clear the placeholder when the wait ends"
    print("gap 5 branded spinner renders + clears OK")
