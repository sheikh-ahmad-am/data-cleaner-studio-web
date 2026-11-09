"""Round 3c — the "Your flow" strip shows the tick AND the marker
on the active step, and Quick Jump gains keyboard selection.

Round 3b proved the strip follows the page, but the tick and the
marker were alternatives: on the Clean page after a real clean the
strip read "Upload ✓ → Clean — you are here" (no ✓ on Clean),
while the KPIs page correctly showed "Clean ✓" (the Round 3b live
failure). The fix makes them independent in flow_marker: a done
step that is also the current page shows BOTH
("Clean ✓ — you are here"). These tests prove that through the UI:
  - on Preview after loading, Upload reads "**Upload ✓** — you
    are here";
  - on Clean after a real clean, Clean reads "**Clean ✓** — you
    are here";
  - on KPIs after a clean, both ticks show and "you are here"
    stays under KPIs;
  - a step with unmet data still shows no tick (Clean before any
    clean).

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:
  .test-venv-brevo/bin/python -m pytest tests/test_flow_marker_r3c.py -q
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


def flow_caption(at):
    """The rendered 'Your flow:' caption value, or None when the
    strip is not on the page."""
    for c in vals(at.caption):
        if "Your flow:" in c:
            return c
    return None


def assert_both(cap, step):
    """The active step shows its tick AND the marker together:
    "**<step> ✓** — you are here"."""
    assert cap is not None, "flow strip must render on a flow page"
    assert f"**{step} ✓** — you are here" in cap, \
        f"done active step must show tick + marker: {cap!r}"


# ---------------------------------------------------------------------------
# The active step shows its tick AND "you are here"
# ---------------------------------------------------------------------------

def test_r3c_active_step_shows_tick_and_marker(_tmp_env):
    """Load the sample: on Preview, Upload reads
    "**Upload ✓** — you are here". Go to Clean (no clean yet):
    Upload stays ticked, Clean reads "**Clean** — you are here"
    with NO tick. Run a real clean: on Clean, Clean reads
    "**Clean ✓** — you are here". Go to KPIs: both ticks show
    and "you are here" stays under KPIs."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "r3cboth")
    load_sample(at)
    # Navigation drives every fresh run below (a bare at.run()
    # proved flaky): the strip renders before the sidebar upload
    # processing in script order, so the caption of the load run
    # itself is one run stale (pre-existing timing, not this fix
    # — the tick appears on the very next run, exactly as in the
    # live app after any interaction).
    goto_section(at, "Clean")
    cap = flow_caption(at)
    assert cap is not None, "strip must render on Clean with data"
    assert "Upload ✓" in cap, f"Upload ticks once a file is loaded: {cap!r}"
    assert "**Clean** — you are here" in cap, \
        f"marker stays under Clean: {cap!r}"
    assert "Clean ✓" not in cap, \
        f"Clean must not tick before a real clean: {cap!r}"
    goto_section(at, "Preview")
    cap = flow_caption(at)
    assert_both(cap, "Upload")
    assert "Clean ✓" not in cap, \
        f"Clean must not tick before a real clean: {cap!r}"
    goto_section(at, "Clean")
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    assert at.session_state["clean"] is not None, "clean data must exist"
    goto_section(at, "KPIs")
    cap = flow_caption(at)
    assert cap is not None, "strip must render on KPIs with data"
    assert "Upload ✓" in cap and "Clean ✓" in cap, \
        f"both done steps tick on KPIs: {cap!r}"
    assert "**KPIs** — you are here" in cap, \
        f"marker stays under KPIs: {cap!r}"
    goto_section(at, "Clean")
    cap = flow_caption(at)
    assert_both(cap, "Clean")
    assert "Upload ✓" in cap, f"Upload stays ticked: {cap!r}"
    print("r3c active step shows tick + marker OK")


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
        test_r3c_active_step_shows_tick_and_marker(_p)
    print("ALL R3C FLOW MARKER TESTS PASSED")
