"""Supabase faithful-rebuild tests (AppTest — no browser needed).

Covers the rebuild the user approved on 2026-11-07 ("Rebuild the whole
look"): icon buttons everywhere, the real top bar, clickable icon nav,
the avatar menu rebuilt to the dashboard's real menu, the theme sync
fix (the sidebar dropdown showed "Light" while the page was dark),
the Profile caption + cards fix (both were in code but did not render
live), the Dashboard status / Get-connected / metric strips, the
Preview toolbar + footer, Quick jump in the top bar, and the
stylesheet rules the rebuild pins (primary pill, micro table headers,
brace balance — the soul-pass transition rule once missed its closing
brace, which swallowed every rule after it).

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler jobs
file are pointed at a temp dir, so the real data/ folder is untouched.
Run ONLY this file:  .test-venv-wave3/bin/python -m pytest
tests/test_supabase_rebuild.py -q   (from project root)
"""

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import auth  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
import ui_design  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_profile.py: the checkout's
    supabase_config.json holds real values, so local mode also needs
    the config path pointed at a nonexistent file in the temp dir.
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


def expand_rail(at):
    """Open the sidebar rail (it starts collapsed — the dashboard's
    own default, icon-only) so the full sidebar is visible: theme
    selectbox, labelled nav rows, uploader, sample button. The rail
    tests in test_supabase_rail.py cover the collapsed state itself;
    the older helpers below need the expanded sidebar to do their
    jobs."""
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert not at.exception, f"exception expanding rail: {at.exception}"


def signup(at, username, password="password123"):
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


# ---------------------------------------------------------------------------
# 1. Icon buttons: the whole icon map renders, no bad Material name
# ---------------------------------------------------------------------------

def test_icon_map_renders():
    """Every icon the app uses must be a real Material icon — a bad
    name raises StreamlitAPIException at render time, never silently,
    so render one button per icon and prove none of them blows up."""
    names = sorted(ui_design.MATERIAL_ICONS)
    assert len(names) >= 50, f"icon map too small: {len(names)}"
    lines = ["import streamlit as st", "import ui_design"]
    for i, name in enumerate(names):
        lines.append(
            f"ui_design.icon_button('B{i}', {name!r}, key='ic_{i}')")
    at = AppTest.from_string("\n".join(lines))
    at.run()
    assert not at.exception, f"icon render exception: {at.exception}"
    assert len(at.button) == len(names), \
        f"expected {len(names)} icon buttons, got {len(at.button)}"
    # Unknown names fall back to the diamond, never raise.
    assert ui_design.icon_for("not-a-real-icon") == ":material/diamond:"
    print(f"icon map OK: {len(names)} buttons render")


# ---------------------------------------------------------------------------
# 2. Top bar: Upload / Help / avatar actions report back
# ---------------------------------------------------------------------------

def test_topbar_actions():
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "actions = ui_design.topbar('Preview', breadcrumb='Workspace',\n"
        "                           user={'username': 'alice1'})\n"
        "st.write(f\"upload={actions['upload']} help={actions['help']} \"\n"
        "         f\"avatar={actions['avatar']})\")\n")
    at.run()
    assert not at.exception, f"topbar exception: {at.exception}"
    # The bar carries the logo slot + workspace + screen title.
    assert any("dcs-topbar-left" in v for v in vals(at.markdown)), \
        "top bar must render its left block (logo + workspace + title)"
    # A breadcrumb is passed here ('Workspace'), so the breadcrumb
    # renders INSTEAD of the title span (round 6, item 6: the
    # breadcrumb is the file name only when one is loaded, the page
    # name only when none is — never both). The title-shows case is
    # pinned by test_fixup_round6::test_r6_breadcrumb_file_only_or_page_only.
    assert any("Workspace" in v for v in vals(at.markdown)), \
        "top bar must show the breadcrumb when one is passed"
    assert not any("dcs-topbar-title" in v for v in vals(at.markdown)), \
        "top bar must not render the title span when a breadcrumb is present"
    # The green primary pill + the icon-only Help button.
    find_button(at, "Upload", key="topbar_upload")
    help_btn = find_button(at, "", key="topbar_help")
    assert help_btn.help, "Help must be an icon-only button with a tooltip"
    # The avatar menu rows are all there.
    for label, key in (("Account", "avatar_account_btn"),
                       ("Feature previews", "avatar_previews_btn"),
                       ("Changelog", "avatar_changelog_btn"),
                       ("Sign out", "avatar_logout_btn")):
        find_button(at, label, key=key)
    # Clicking Upload reports upload=True; Help reports help=True.
    find_button(at, "Upload", key="topbar_upload").click().run()
    assert not at.exception, f"exception on Upload: {at.exception}"
    assert any("upload=True" in v for v in vals(at.markdown)), \
        "Upload click must report upload=True"
    find_button(at, "", key="topbar_help").click().run()
    assert not at.exception, f"exception on Help: {at.exception}"
    assert any("help=True" in v for v in vals(at.markdown)), \
        "Help click must report help=True"
    # Avatar rows report their actions.
    find_button(at, "Changelog", key="avatar_changelog_btn").click().run()
    assert any("avatar=status" in v for v in vals(at.markdown)), \
        "Changelog must report avatar=status"
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert any("avatar=profile" in v for v in vals(at.markdown)), \
        "Account must report avatar=profile"
    print("top bar actions OK")


# ---------------------------------------------------------------------------
# 3. Avatar menu: theme radio flips dcs_theme (the live-check failure)
# ---------------------------------------------------------------------------

def test_avatar_menu_theme_radio_flips_theme():
    """The avatar menu's theme switch exists AND renders: a radio
    whose rows flip dcs_theme. (The old button existed in code but
    never appeared on screen — this test clicks the rendered radio,
    not the source.)"""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import ui_design\n"
        "st.session_state.setdefault('dcs_theme', 'light')\n"
        "ui_design.sync_theme_widgets()\n"
        "action = ui_design.render_avatar_menu(\n"
        "    user={'display_name': 'Md Ahmad', 'email': 'a@example.com'})\n"
        "st.write(f'action={action}')\n")
    at.run()
    assert not at.exception, f"avatar menu exception: {at.exception}"
    # The email is bold plain text at the top — never a link.
    assert any("dcs-menu-email" in v and "a@example.com" in v
               for v in vals(at.markdown)), \
        "avatar menu must show the email bold at the top"
    assert not any("<a " in v and "a@example.com" in v
                   for v in vals(at.markdown)), \
        "avatar menu email must not be a link"
    theme = next(r for r in at.radio if r.key == "avatar_theme_radio")
    assert theme.value == "light", \
        f"theme radio should start light, got {theme.value!r}"
    theme.set_value("dark").run()
    assert not at.exception, f"exception flipping theme: {at.exception}"
    assert at.session_state.get("dcs_theme") == "dark", \
        "avatar theme radio must flip dcs_theme to dark"
    theme = next(r for r in at.radio if r.key == "avatar_theme_radio")
    assert theme.value == "dark", "radio must follow the flip to dark"
    theme.set_value("light").run()
    assert at.session_state.get("dcs_theme") == "light", \
        "avatar theme radio must flip dcs_theme back to light"
    print("avatar menu theme radio OK")


# ---------------------------------------------------------------------------
# 4. Theme sync: selectbox and radio agree in both directions
# ---------------------------------------------------------------------------

def test_theme_sync_both_directions():
    """The live-check bug: the sidebar dropdown showed "Light" while
    the page was dark, because writing dcs_theme directly does not
    move a widget that already exists. sync_theme_widgets + the
    on_change callbacks must keep all three in agreement."""
    script = (
        "import streamlit as st\n"
        "import ui_design\n"
        "st.session_state.setdefault('dcs_theme', 'light')\n"
        "ui_design.sync_theme_widgets()\n"
        "ui_design.render_theme_toggle()\n"
        "ui_design.render_avatar_menu(user={'username': 'alice1'})\n"
        "sel = st.session_state.get('dcs_theme_select')\n"
        "rad = st.session_state.get('avatar_theme_radio')\n"
        "st.write(f\"theme={st.session_state.get('dcs_theme')} \"\n"
        "         f\"select={sel} radio={rad}\")\n")
    # Start dark: both widgets must read dark.
    at = AppTest.from_string(script)
    at.session_state["dcs_theme"] = "dark"
    at.run()
    assert not at.exception, f"theme sync exception: {at.exception}"
    assert any("theme=dark select=dark radio=dark" in v
               for v in vals(at.markdown)), \
        f"dark start must sync both widgets, got {vals(at.markdown)!r}"
    # Flip the selectbox to light: dcs_theme AND the radio follow.
    sel = next(s for s in at.selectbox if s.key == "dcs_theme_select")
    sel.set_value("light").run()
    assert at.session_state.get("dcs_theme") == "light", \
        "selectbox flip must write dcs_theme"
    assert any("theme=light select=light radio=light" in v
               for v in vals(at.markdown)), \
        "selectbox flip must sync the radio too"
    # Flip the radio to dark: dcs_theme AND the selectbox follow.
    rad = next(r for r in at.radio if r.key == "avatar_theme_radio")
    rad.set_value("dark").run()
    assert at.session_state.get("dcs_theme") == "dark", \
        "radio flip must write dcs_theme"
    assert any("theme=dark select=dark radio=dark" in v
               for v in vals(at.markdown)), \
        "radio flip must sync the selectbox too"
    print("theme sync both directions OK")


# ---------------------------------------------------------------------------
# 5. Profile: caption renders + one card per section (live-check fix)
# ---------------------------------------------------------------------------

def test_profile_caption_and_cards(_tmp_env):
    """The caption existed in code (st.caption) but never appeared on
    screen. The rebuild fuses title + caption into one heading
    element and puts every section in a bordered card — prove the
    caption and all six cards actually render. (Round 5 rebuilt it
    as Supabase's Preferences page: caption "Manage your account,
    sign-in and data.", sections as headings above bordered cards.)"""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    assert any("Manage your account, sign-in and data." in v
               for v in vals(at.markdown)), \
        "Profile caption must render on screen"
    for section in ("Profile information", "Sign-in methods",
                    "Appearance", "Download my data", "Storage usage",
                    "Log out", "Danger zone"):
        assert any("dcs-profile-section" in v and section in v
                   for v in vals(at.markdown)), \
            f"Profile section {section!r} must be a settings card"
    # The section controls are all still there, keys unchanged.
    find_button(at, "Save")
    assert any(b.label == "Download my data" for b in at.download_button), \
        "download-my-data button missing"
    find_button(at, "Log out", key="profile_logout_btn")
    find_button(at, "Delete my account", key="profile_delete_reveal")
    # Preview content must NOT sit above Profile any more: the Recent
    # files section (a subheader) belongs to the Preview tab only.
    # (The What's-new changelog also mentions "Recent files" in prose
    # — that is not the section, so match the subheader exactly.)
    assert not any(s.value == "Recent files" for s in at.subheader), \
        "Profile must not show Preview's Recent files above it"
    print("Profile caption + cards OK")


# ---------------------------------------------------------------------------
# 6. Stylesheet rules the rebuild pins
# ---------------------------------------------------------------------------

def _brace_depth(css: str) -> int:
    depth = 0
    for line in css.splitlines():
        depth += line.count("{") - line.count("}")
    return depth


def test_stylesheet_rules_pinned():
    """Primary buttons are pills, table headers are 11px uppercase
    micro headers, both sheets are brace-balanced (the missing brace
    in the soul-pass transition rule once swallowed every rule after
    it), and the app.py literal is the verbatim light sheet."""
    for name, css in (("light", ui_design.DESIGN_SYSTEM_CSS),
                      ("dark", ui_design.DARK_CSS)):
        assert _brace_depth(css) == 0, \
            f"{name} stylesheet has unbalanced braces"
        # Primary-button rule: light uses the [kind=...] hook, dark the
        # testid hook (round 2 — [kind=...] never matches live).
        primary_sel = ('button[kind="primary"]' if name == "light"
                       else 'button[data-testid="stBaseButton-primary"]')
        assert primary_sel in css, \
            f"{name}: primary button rule missing"
        primary = re.search(
            re.escape(primary_sel) + r" \{(.*?)\}", css, re.DOTALL)
        assert primary and "border-radius: 999px" in primary.group(1), \
            f"{name}: primary buttons must be pills (999px)"
        assert "font-size: 11px" in css and "text-transform: uppercase" in css, \
            f"{name}: table headers must be 11px uppercase micro headers"
        assert "dcs-topbar-left" in css and "dcs-menu-email" in css, \
            f"{name}: top bar / avatar menu rules missing"
        assert "dcs-metric-card" in css and "dcs-settings-title" in css, \
            f"{name}: metric / settings-card rules missing"
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r'DESIGN_SYSTEM_CSS = """<style>(.*?)</style>"""',
        source, re.DOTALL)
    assert match, "DESIGN_SYSTEM_CSS block missing from app.py"
    assert "<style>" + match.group(1) + "</style>" == ui_design.DESIGN_SYSTEM_CSS, \
        "app.py literal must be the verbatim light stylesheet"
    assert _brace_depth(match.group(1)) == 0, \
        "app.py literal has unbalanced braces"
    print("stylesheet rules pinned OK")


# ---------------------------------------------------------------------------
# 7. Dashboard strips render with real data
# ---------------------------------------------------------------------------

def test_dashboard_strips_render(_tmp_env):
    """The Overview strips — six status tiles, the six-cell Get
    connected strip, the two metric cards, the Advisor line — all
    render from the app's own data once a file is cleaned."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    goto_section(at, "Clean")
    find_button(at, "Clean my data").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    goto_section(at, "Dashboard")
    md = "\n".join(vals(at.markdown))
    for tile in ("Status", "Storage", "Rows", "Columns", "KPIs", "File"):
        assert tile in md, f"status strip tile {tile!r} missing"
    for cell in ("Upload", "Clean", "KPIs", "Charts", "Report", "Tools"):
        assert any(b.label == cell for b in at.button), \
            f"Get connected cell {cell!r} missing"
    assert "Missing cells" in md, "Missing cells metric card missing"
    assert "Duplicate rows" in md, "Duplicate rows metric card missing"
    assert "Advisor found" in md, "Advisor line missing"
    print("Dashboard strips OK")


# ---------------------------------------------------------------------------
# 8. Preview toolbar + footer
# ---------------------------------------------------------------------------

def test_preview_toolbar_and_footer(_tmp_env):
    """The Preview table carries its own toolbar (search the preview,
    rows-per-page, green Clean now) and a footer counting the rows."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    load_sample(at)
    find_text_input(at, "Search the preview")
    rows = next(s for s in at.selectbox if s.label == "Rows")
    assert list(rows.options) == ["50", "100", "200"], \
        f"rows-per-page options wrong: {list(rows.options)!r}"
    find_button(at, "Clean now", key="preview_clean_now")
    assert any("Showing 80 of 80 rows" in v for v in vals(at.caption)), \
        "Preview footer must count the rows"
    # The toolbar search filters the shown rows.
    find_text_input(at, "Search the preview").set_value("2024").run()
    assert not at.exception, f"exception filtering preview: {at.exception}"
    assert any("Showing" in v and "of" in v and "rows" in v
               for v in vals(at.caption)), \
        "Preview footer must still count after filtering"
    # Clean now navigates to the Clean tab.
    find_button(at, "Clean now", key="preview_clean_now").click().run()
    radio = next(r for r in at.radio if r.label == "Section")
    assert radio.value == "Clean", \
        f"Clean now should open the Clean tab, got {radio.value!r}"
    print("Preview toolbar + footer OK")


# ---------------------------------------------------------------------------
# 9. Quick jump renders in a container (the top-bar search column)
# ---------------------------------------------------------------------------

def test_quickjump_in_container():
    """Quick jump is not sidebar-only any more: it renders in any
    container (the top bar's search column) with a collapsed label,
    and picking a match still jumps."""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "import feat_quickjump\n"
        "box = st.container()\n"
        "feat_quickjump.render_quick_jump(st, container=box, compact=True)\n"
        "st.write(f\"pending={st.session_state.get('pending_tab')}\")\n")
    at.run()
    assert not at.exception, f"quick jump exception: {at.exception}"
    box = find_text_input(at, "Quick jump ⌘K")
    box.set_value("clean").run()
    assert not at.exception, f"exception filtering quick jump: {at.exception}"
    find_button(at, "Clean — Fix duplicates, blanks and formats").click().run()
    assert not at.exception, f"exception jumping: {at.exception}"
    assert any("pending=clean" in v for v in vals(at.markdown)), \
        "quick jump must set pending_tab=clean"
    print("quick jump in container OK")
