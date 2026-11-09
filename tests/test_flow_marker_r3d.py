"""Round 3d — the Clean tick appears on the Clean page in the SAME
render as the clean's "Done" message, and the Quick Jump bridge
shows the matches after a plain Enter.

Fix 1 (the main item): Round 3c proved the tick and the marker
could show together, but the live check (2026-11-09 16:59 IST)
found the Clean tick ONE RENDER LATE on the Clean page itself —
no "Clean ✓" right after the clean, appearing only after the next
navigation — even though the tick state registered globally (the
KPIs page showed it). Root cause: the strip renders at the top of
the run, before the Clean section writes the cleaned-data state,
so the click run's caption is stale. The fix is a rerun at the end
of the Clean section when the tick flips (data cleaned for the
first time, or a restore/undo cleared it) — the "Done" line
re-renders from state on the rerun, so nothing is lost, and the
rerun fires only on the flip, so it cannot loop. These tests prove
that through the UI:
  - click "Clean my data" and, WITHOUT navigating anywhere, the
    strip on Clean reads "**Clean ✓** — you are here" in the same
    run, next to the "Done:" message;
  - clicking "Clean my data" again (re-clean, tick already on)
    does not rerun forever: no exception, tick still shown;
  - the Upload tick is untouched: Preview after loading still
    reads "**Upload ✓** — you are here".

Fix 2 (bridge, unit pins only — the live behaviour is proven by
the Playwright probe, AppTest runs no JS): the bridge no longer
auto-picks on a plain first Enter. Live-per-keystroke list
rendering is NOT feasible with stock Streamlit (a text input
submits on Enter/blur only, never per keystroke), so a plain
Enter only submits and the matches render in the still-open
popover for the user to see and pick; autoPick fires only when
the user already moved the highlight (ArrowDown/Up + Enter).
The pins live in tests/test_quickjump.py (``moved`` state and
the ``if(S.moved){S.autoPick=true;}`` gate).

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:
  .test-venv-brevo/bin/python -m pytest tests/test_flow_marker_r3d.py -q
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
# The Clean tick appears in the SAME render as the "Done" message
# ---------------------------------------------------------------------------

def test_r3d_clean_tick_same_run_as_done(_tmp_env):
    """Load the sample, go to Clean, click "Clean my data" — and
    WITHOUT navigating anywhere, the strip on Clean already reads
    "**Clean ✓** — you are here", in the same run as the "Done:"
    message. (Before this fix the caption read "Clean — you are
    here" with no tick until the next navigation.)"""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "r3dsame")
    load_sample(at)
    goto_section(at, "Clean")
    cap = flow_caption(at)
    assert cap is not None, "strip must render on Clean with data"
    assert "Clean ✓" not in cap, \
        f"Clean must not tick before a real clean: {cap!r}"
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception cleaning: {at.exception}"
    assert at.session_state["clean"] is not None, "clean data must exist"
    # Same run, no navigation in between: the tick is already there
    # AND the Done message is still visible next to it.
    cap = flow_caption(at)
    assert_both(cap, "Clean")
    assert "Upload ✓" in cap, f"Upload stays ticked: {cap!r}"
    done = [s for s in vals(at.success) if "Done:" in s]
    assert done, "the Done message must render in the same view as the tick"
    print("r3d clean tick in the same run as Done OK")


def test_r3d_reclean_does_not_loop(_tmp_env):
    """Cleaning when the tick is already on must not rerun forever:
    click "Clean my data" a second time — no exception, the tick
    still shows, the run terminates (the rerun fires only when
    the tick FLIPS, never on a re-clean)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "r3dloop")
    load_sample(at)
    goto_section(at, "Clean")
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception on first clean: {at.exception}"
    assert_both(flow_caption(at), "Clean")
    find_button(at, "Clean my data", key="clean_btn").click().run()
    assert not at.exception, f"exception on re-clean: {at.exception}"
    assert_both(flow_caption(at), "Clean")
    print("r3d re-clean does not loop OK")


def test_r3d_upload_tick_untouched(_tmp_env):
    """The Upload tick is untouched by the rerun fix: on Preview
    after loading, Upload reads "**Upload ✓** — you are here"
    (the load run itself is one run stale, pre-existing timing —
    the tick appears on the very next run, exactly as in the live
    app after any interaction)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "r3dupload")
    load_sample(at)
    goto_section(at, "Preview")
    cap = flow_caption(at)
    assert_both(cap, "Upload")
    assert "Clean ✓" not in cap, \
        f"Clean must not tick before a real clean: {cap!r}"
    print("r3d upload tick untouched OK")


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
        test_r3d_clean_tick_same_run_as_done(_p)
        test_r3d_reclean_does_not_loop(_p)
        test_r3d_upload_tick_untouched(_p)
    print("ALL R3D FLOW MARKER TESTS PASSED")
