"""Round 3b — the "Your flow" strip renders on EVERY flow page.

Round 2 built the pure helper (flow_marker derives the marker from
the actual page; ticks follow the data) but app.py rendered the
caption only inside the Preview block, so on Clean / KPIs / Report
the strip was never in the DOM at all (the Round 3 live failure:
"you are here" pinned to Upload, strip absent off Preview). The
fix moves the render to one shared site in the shell chrome, right
under the top bar. These tests prove the render site, not the
helper (the helper is covered by test_fixup_shell_r2.py):
  - the strip shows on Preview / Clean / KPIs / Report with
    "you are here" under the page you are actually on;
  - it shows on NO non-flow page (Dashboard, Settings, Profile);
  - ticks still track the data through the UI (load the sample,
    Clean ticks only after a real clean) while "you are here"
    still tracks the page, not the tick.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:
  .test-venv-brevo/bin/python -m pytest tests/test_flow_marker_r3b.py -q
(from project root)
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import auth  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_fixup_five_gaps.py.
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
    """Open the sidebar rail (it starts collapsed) so the full
    sidebar is visible: labelled nav rows, uploader, sample button."""
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
    """Navigate via a sidebar nav row (the path that works with no
    data loaded, when the Section radio does not exist yet)."""
    expand_rail(at)
    find_button(at, label, key=key).click().run()
    assert not at.exception, f"exception going to {label}: {at.exception}"


def flow_caption(at):
    """The rendered 'Your flow:' caption value, or None when the
    strip is not on the page."""
    for c in vals(at.caption):
        if "Your flow:" in c:
            return c
    return None


def assert_here(cap, step):
    assert cap is not None, "flow strip must render on a flow page"
    assert f"**{step}** — you are here" in cap, \
        f"'you are here' must sit under {step}: {cap!r}"


# ---------------------------------------------------------------------------
# The strip renders on every flow page, following the page
# ---------------------------------------------------------------------------

def test_r3b_strip_on_every_flow_page(_tmp_env):
    """Preview -> Upload, Clean -> Clean, KPIs -> KPIs, Report ->
    Export: the strip renders on each, with 'you are here' under
    the page you are actually on — never pinned to Upload."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "r3bflow")
    cap = flow_caption(at)
    assert_here(cap, "Upload")
    goto_nav(at, "Clean", "dcs_nav_clean")
    assert_here(flow_caption(at), "Clean")
    goto_nav(at, "KPIs", "dcs_nav_kpis")
    assert_here(flow_caption(at), "KPIs")
    goto_nav(at, "Report", "dcs_nav_report")
    assert_here(flow_caption(at), "Export")
    print("r3b strip on every flow page OK")


def test_r3b_no_strip_off_the_flow(_tmp_env):
    """Non-flow pages show no strip at all: Dashboard, Settings,
    Profile (via the avatar menu, as in gap 2)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "r3bofflow")
    goto_nav(at, "Dashboard", "dcs_nav_dashboard")
    assert flow_caption(at) is None, "no strip on Dashboard"
    goto_nav(at, "Settings", "dcs_nav_settings")
    assert flow_caption(at) is None, "no strip on Settings"
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    assert flow_caption(at) is None, "no strip on Profile"
    assert "Your flow:" not in all_text(at), \
        "no flow text anywhere on Profile"
    print("r3b no strip off the flow OK")


# ---------------------------------------------------------------------------
# Ticks still track the data through the UI
# ---------------------------------------------------------------------------

def test_r3b_ticks_track_data_and_page(_tmp_env):
    """Load the sample, go to Clean: Upload is ticked (its output
    exists) but 'you are here' stays under Clean. Clean the data
    for real, go to KPIs: Clean is ticked now, and 'you are here'
    is under KPIs — the marker tracks the page, not the tick."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "r3bticks")
    load_sample(at)
    goto_section(at, "Clean")
    cap = flow_caption(at)
    assert cap is not None, "strip must render on Clean with data"
    assert "Upload ✓" in cap, f"Upload ticks once a file is loaded: {cap!r}"
    assert_here(cap, "Clean")
    assert "Clean ✓" not in cap, \
        f"Clean must not tick before a real clean: {cap!r}"
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    assert at.session_state["clean"] is not None, "clean data must exist"
    goto_section(at, "KPIs")
    cap = flow_caption(at)
    assert cap is not None, "strip must render on KPIs with data"
    assert "Upload ✓" in cap and "Clean ✓" in cap, \
        f"both done steps tick on KPIs: {cap!r}"
    assert_here(cap, "KPIs")
    print("r3b ticks track data and page OK")


# ---------------------------------------------------------------------------
# Standalone run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as _td:
        _p = Path(_td)
        auth.SUPABASE_CONFIG_PATH = _p / "supabase_config.json"
        auth.DB_PATH = _p / "users.db"
        auth._reset_backend_cache()
        storage.BASE_DIR = _p / "users"
        storage._reset_storage_cache()
        scheduler.DEFAULT_JOBS_FILE = _p / "scheduler" / "jobs.json"
        test_r3b_strip_on_every_flow_page(_p)
        test_r3b_no_strip_off_the_flow(_p)
        test_r3b_ticks_track_data_and_page(_p)
    print("ALL R3B FLOW MARKER TESTS PASSED")
