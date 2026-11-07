"""Status + changelog tests (Worker C, Supabase-look refinement).

Covers, with no browser needed:
  1. get_status() honest states — local mode shows the mode only,
     cloud mode says "operational" only when auth's real health
     check passed, and "unavailable" with the plain-words warning
     when it failed (auth stubbed; the real RPC is auth's own code).
  2. The sidebar status pill renders the right label per state.
  3. The changelog: every entry is dated, newest-first, and has a
     real commit behind it (checked against git); CHANGELOG.md
     carries the same entries.
  4. AppTest: the Status tab renders (local mode, with and without
     data), the sidebar pill says "Local mode".
  5. Nit (a): the sidebar nav follows the client-mode toggle on the
     SAME run (no one-run lag).
  6. Nit (b): the top bar shows the newly selected language on the
     SAME run after a language switch (no one-run lag).

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler jobs
file are pointed at a temp dir, so the real data/ folder is untouched.
The language test also backs up the real settings.json (the picker
saves the chosen language there) and restores it afterwards.
Run ONLY this file:  .test-venv-refine-c/bin/python -m pytest
tests/test_status.py -q   (from project root)
"""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import ai_settings  # noqa: E402
import auth  # noqa: E402
import feat_status  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    The checkout's supabase_config.json holds real values, so local
    mode also needs the config path pointed at a nonexistent file in
    the temp dir — same redirection pattern test_profile.py uses.
    settings.json is backed up (if it exists) and removed for the
    run, so the language picker cannot change the real setting;
    it is restored afterwards.
    """
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    _settings = ai_settings.SETTINGS_PATH
    _backup = None
    if _settings.is_file():
        _backup = _settings.read_bytes()
        _settings.unlink()
    try:
        yield tmp_path
    finally:
        if _backup is not None:
            _settings.write_bytes(_backup)
        elif _settings.is_file():
            _settings.unlink()


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


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


def signup(at, username, password="password123"):
    """Sign up (auto-login); the app must show the data screen after."""
    at.radio[0].set_value("Sign up").run()
    find_text_input(at, "Username").set_value(username).run()
    find_text_input(at, "Password").set_value(password).run()
    find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "signup should log the user straight in"


def upload_sample(at, username):
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([("messy_sales.csv", SAMPLE.read_bytes(), "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert storage.list_files(username, "uploads") == ["messy_sales.csv"], \
        "upload must be saved in the user's uploads/"


def goto_section(at, label):
    """Pick a section in the sticky section switcher (radio 'Section')."""
    radio = next(r for r in at.radio if r.label == "Section")
    radio.set_value(label).run()
    assert not at.exception, f"exception going to {label}: {at.exception}"


def sidebar_nav_labels(at):
    """The sidebar nav's row labels (clickable icon buttons, keyed
    dcs_nav_<section>).

    Match the rendered buttons, not the stylesheet — the injected CSS
    also mentions dcs-nav rows."""
    return [b.label for b in at.button
            if (b.key or "").startswith("dcs_nav_")]


def topbar_markdown(at):
    """The top bar's left block (logo + workspace + current-section
    title).

    Match the rendered bar, not the stylesheet — the injected CSS
    also mentions dcs-topbar."""
    for m in at.markdown:
        if '<div class="dcs-topbar-left">' in m.value:
            return m.value
    raise AssertionError("top bar markdown missing")


class _FakeSt:
    """Minimal stand-in for Streamlit: records markdown calls only."""

    def __init__(self):
        self.markdown_calls = []
        self.session_state = {}

    def markdown(self, body, unsafe_allow_html=False):
        self.markdown_calls.append(str(body))


# ---------------------------------------------------------------------------
# 1. get_status() — the honest states (auth stubbed)
# ---------------------------------------------------------------------------

def test_get_status_local_mode_shows_mode_only(monkeypatch):
    monkeypatch.setattr(auth, "get_auth_backend", lambda: "local")
    status = feat_status.get_status()
    assert status == {"mode": "local", "state": "local", "detail": None}, \
        "local mode must not claim anything about a service it did not check"


def test_get_status_operational_only_when_health_check_passed(monkeypatch):
    monkeypatch.setattr(auth, "get_auth_backend", lambda: "supabase")
    monkeypatch.setattr(auth, "get_backend_warning", lambda: None)
    status = feat_status.get_status()
    assert status == {"mode": "cloud", "state": "operational",
                      "detail": None}, \
        "cloud + no warning is the only state that may say operational"


def test_get_status_unavailable_carries_warning_verbatim(monkeypatch):
    monkeypatch.setattr(auth, "get_auth_backend", lambda: "supabase")
    monkeypatch.setattr(
        auth, "get_backend_warning",
        lambda: "Project paused — restore it in the Supabase dashboard")
    status = feat_status.get_status()
    assert status["mode"] == "cloud"
    assert status["state"] == "unavailable"
    assert status["detail"] == (
        "Project paused — restore it in the Supabase dashboard")


def test_get_status_never_raises(monkeypatch):
    def _boom():
        raise RuntimeError("config unreadable")
    monkeypatch.setattr(auth, "get_auth_backend", _boom)
    status = feat_status.get_status()
    assert status["state"] == "unavailable"
    assert "config unreadable" in (status["detail"] or "")


# ---------------------------------------------------------------------------
# 2. The sidebar pill renders the right label per state
# ---------------------------------------------------------------------------

def test_status_pill_per_state(monkeypatch):
    cases = [
        ("local", None, "Local mode", "dcs-pill-grey"),
        ("supabase", None, "All systems operational", "dcs-pill-mint"),
        ("supabase", "Project paused — restore it in the Supabase "
         "dashboard", "Cloud unavailable", "dcs-pill-amber"),
    ]
    for backend, warning, label, pill_class in cases:
        monkeypatch.setattr(auth, "get_auth_backend", lambda b=backend: b)
        monkeypatch.setattr(auth, "get_backend_warning",
                            lambda w=warning: w)
        fake = _FakeSt()
        feat_status.render_status_pill(fake)
        assert len(fake.markdown_calls) == 1, "pill renders once"
        html = fake.markdown_calls[0]
        assert label in html, f"pill should read {label!r}, got {html!r}"
        assert pill_class in html, \
            f"pill should use {pill_class}, got {html!r}"
        assert "All systems operational" not in html \
            or label == "All systems operational", \
            "operational must only appear when genuinely verified"


# ---------------------------------------------------------------------------
# 3. The changelog — dated, newest-first, every entry real
# ---------------------------------------------------------------------------

def _git_commit_exists(commit):
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    return result.returncode == 0


def test_changelog_entries_dated_newest_first_and_real():
    entries = feat_status.CHANGELOG_ENTRIES
    assert len(entries) >= 5, "changelog should list the rebuild milestones"
    dates = []
    seen = set()
    for entry in entries:
        # Dated: a real YYYY-MM-DD date, not a free-text label.
        parsed = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        dates.append(parsed)
        assert entry["commit"] not in seen, \
            f"duplicate commit {entry['commit']}"
        seen.add(entry["commit"])
        assert len(entry["commit"]) == 40, "commit must be a full hash"
        assert entry["title"].strip(), "every entry needs a title"
        assert entry["user_action"].strip(), \
            "every entry must say what changed for the user"
        # Real: the commit exists in this repo's history.
        assert _git_commit_exists(entry["commit"]), \
            f"changelog commit {entry['commit']} is not in git history"
    assert dates == sorted(dates, reverse=True), \
        "changelog must be newest-first"


def test_changelog_md_matches_entries():
    text = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    for entry in feat_status.CHANGELOG_ENTRIES:
        assert entry["date"] in text, \
            f"CHANGELOG.md missing date {entry['date']}"
        assert entry["commit"][:7] in text, \
            f"CHANGELOG.md missing commit {entry['commit'][:7]}"
        assert entry["title"] in text, \
            f"CHANGELOG.md missing title {entry['title']!r}"
    rows = [line for line in text.splitlines()
            if line.startswith("| 20")]
    assert len(rows) == len(feat_status.CHANGELOG_ENTRIES), \
        "CHANGELOG.md row count must match the in-app entries"


# ---------------------------------------------------------------------------
# 4. AppTest: the Status tab renders (local mode), pill in the sidebar
# ---------------------------------------------------------------------------

def test_sidebar_status_pill_local_mode(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    signup(at, "alice1")
    # The pill itself (not the local-mode info banner): a markdown
    # element carrying the grey pill class and the "Local mode" label.
    pill = [m.value for m in at.markdown
            if "dcs-pill" in m.value and "Local mode" in m.value]
    assert pill, "sidebar should show the Local mode status pill"
    assert "dcs-pill-grey" in pill[0], \
        "local-mode pill should be the quiet grey one"
    assert "All systems operational" not in " ".join(vals(at.markdown)), \
        "local mode must never claim the cloud is operational"


def test_status_section_renders_with_data(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    upload_sample(at, "alice1")
    goto_section(at, "Status")
    # The section heading is ui_design.section_heading -> an <h2> in
    # markdown, not st.subheader.
    assert any("Status</h2>" in m.value for m in at.markdown), \
        "Status section heading should render"
    page = " ".join(vals(at.markdown))
    assert "Running in local mode." in page, \
        "local mode headline should say so plainly"
    assert "Local mode — on this server" in page, \
        "services table should name the local backend"
    assert "What's new" in " ".join(v.value for v in at.subheader), \
        "changelog heading missing"
    assert "6ce9c8a" in page and \
        "Rebuilt on the Supabase design system" in page, \
        "changelog must list the Supabase rebuild with its commit"
    assert "fa9aa3f" in page and "Profile section added" in page, \
        "changelog must list the Profile section with its commit"
    assert "No uptime percentages here" in " ".join(
        vals(at.caption)), \
        "the page must say plainly that no uptime is claimed"


def test_status_section_reachable_without_data(_tmp_env):
    at = AppTest.from_file(APP)
    at.session_state["pending_tab"] = "status"
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    signup(at, "alice1")
    # No file loaded: the app stops at the empty state unless the
    # user is heading to an info tab — Status is one, like Profile.
    assert any("Running in local mode." in m.value for m in at.markdown), \
        "Status should render with no data loaded"
    assert any("What's new" in s.value for s in at.subheader), \
        "changelog should render with no data loaded"
    find_button(at, "← Back to data", key="status_empty_back").click().run()
    assert not at.exception, f"exception going back: {at.exception}"
    assert any("Nothing loaded yet" in m.value for m in at.markdown), \
        "Back should return to the empty state"


# ---------------------------------------------------------------------------
# 5. Nit (a): sidebar nav follows the client-mode toggle, same run
# ---------------------------------------------------------------------------

def test_client_mode_toggle_nav_same_run(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    toggle = next(c for c in at.checkbox
                  if c.label == "Client mode (simple view)")
    assert toggle.value is False
    nav_before = sidebar_nav_labels(at)
    assert "Join" in nav_before and "Tools" in nav_before, \
        "full mode nav should list the advanced tabs"

    # Flip the toggle: the nav on THIS run must already show the
    # client set — before the fix it lagged one run behind.
    toggle.check().run()
    assert not at.exception, f"exception on toggle: {at.exception}"
    nav_client = sidebar_nav_labels(at)
    assert "Join" not in nav_client, \
        "client-mode nav must hide Join on the same run as the flip"
    assert "Tools" not in nav_client, \
        "client-mode nav must hide Tools on the same run as the flip"
    assert "Compare" not in nav_client, \
        "client-mode nav must hide Compare on the same run as the flip"
    assert "Status" in nav_client, \
        "client-mode nav must still list Status"
    assert "Preview" in nav_client, \
        "client-mode nav must still list Preview"

    # Flip it back: the full nav returns on the same run too.
    # (Re-find the checkbox — the element tree was rebuilt by .run().)
    toggle = next(c for c in at.checkbox
                  if c.label == "Client mode (simple view)")
    toggle.uncheck().run()
    assert not at.exception, f"exception on untoggle: {at.exception}"
    nav_back = sidebar_nav_labels(at)
    assert "Join" in nav_back and "Tools" in nav_back, \
        "untoggling must restore the full nav on the same run"


# ---------------------------------------------------------------------------
# 6. Nit (b): top bar shows the new language on the same run
# ---------------------------------------------------------------------------

def test_language_switch_topbar_same_run(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    assert "Preview" in topbar_markdown(at), \
        "top bar should start in English"
    picker = next(s for s in at.selectbox if s.label == "Language")
    assert picker.value == "English"

    # Switch to Hindi: the top bar on THIS run must already read
    # Hindi — before the fix it showed the previous language for
    # one run.
    picker.set_value("हिन्दी").run()
    assert not at.exception, f"exception on language switch: {at.exception}"
    topbar = topbar_markdown(at)
    assert "पूर्वावलोकन" in topbar, \
        f"top bar should read Hindi on the switch run, got {topbar!r}"
    assert "Preview</span>" not in topbar, \
        "top bar must not keep the English title on the switch run"
    nav = sidebar_nav_labels(at)
    assert "साफ़ करें" in nav, \
        "sidebar nav should also relabel on the switch run"
    # The choice is saved, so a later run stays in Hindi.
    assert ai_settings.load_settings().get("language") == "hi", \
        "switching language should save the setting"
