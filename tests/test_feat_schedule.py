"""Group B (v1.4) — daily schedule + built-in tutorial tests.

Run from the project root:  .test-venv-brand/bin/python tests/test_feat_schedule.py
No Streamlit app needed — render functions run against a FakeSt.
No real scheduled task is ever created: task_status() is only read on
Linux (where it must report the plain non-Windows message), and the
command string is checked, never executed. The morning run itself is
tested by copying morning_run.py + engine.py + feat_automate.py into a
temp folder, so the real app folder is never touched.
No network call is ever made.
"""

import datetime
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feat_schedule
import feat_tutorial

APP_DIR = Path(__file__).resolve().parent.parent


class FakeSt:
    """Minimal stand-in for the Streamlit module for render tests."""

    def __init__(self, values=None):
        self.values = values or {}
        self.session_state = {}
        self.calls = []
        self.downloads = []

    def _rec(self, method, *args):
        self.calls.append((method,) + args)

    def subheader(self, text):
        self._rec("subheader", text)

    def write(self, text):
        self._rec("write", text)

    def info(self, text):
        self._rec("info", text)

    def warning(self, text):
        self._rec("warning", text)

    def success(self, text):
        self._rec("success", text)

    def error(self, text):
        self._rec("error", text)

    def time_input(self, label, key=None, value=None, help=None):
        self._rec("time_input", label, key)
        return self.values.get(key, value)

    def button(self, label, key=None, **kw):
        self._rec("button", label, key)
        return self.values.get(key, False)

    def messages(self, method):
        return [c[1] for c in self.calls if c[0] == method]

    def keys_used(self, prefix):
        return [c[2] for c in self.calls
                if len(c) > 2 and isinstance(c[2], str)
                and c[2].startswith(prefix)]


# -------------------------------------------------------------- schedule
def test_build_daily_task_command():
    cmd = feat_schedule.build_daily_task_command(r"C:\Apps\DCS")
    assert cmd.startswith("schtasks /create"), cmd
    assert f'/tn "{feat_schedule.TASK_NAME}"' in cmd, cmd
    assert feat_schedule.TASK_NAME == "Data Cleaner Studio Morning Run"
    assert "/sc daily" in cmd and "/st 08:00" in cmd and "/f" in cmd, cmd
    assert "pythonw.exe" in cmd, "must use pythonw (no console window)"
    assert r"Data-Cleaner-Studio\python\pythonw.exe" in cmd, cmd
    assert "morning_run.py" in cmd, cmd
    # A custom time and a recipe land in the command.
    cmd2 = feat_schedule.build_daily_task_command(
        r"C:\Apps\DCS", recipe=r"C:\Apps\DCS\morning_recipe.json",
        time="07:30")
    assert "/st 07:30" in cmd2 and "--recipe" in cmd2, cmd2
    assert "morning_recipe.json" in cmd2
    assert "/st 08:00" not in cmd2
    # No recipe -> no --recipe flag at all.
    assert "--recipe" not in feat_schedule.build_daily_task_command(r"C:\Apps\DCS")
    # Bad times are rejected, not silently scheduled wrong.
    for bad in ("8:00", "25:00", "08:60", "tomorrow", "", None):
        try:
            feat_schedule.build_daily_task_command(r"C:\Apps\DCS", time=bad)
        except ValueError as e:
            assert "08:00" in str(e)
        else:
            raise AssertionError(f"time {bad!r} must raise ValueError")
    print("schtasks command OK: task name, daily, 08:00, pythonw.exe path, "
          "recipe flag, bad times rejected")


def test_task_status_on_linux():
    # This test runs on Linux: no schtasks call, just the plain message.
    assert sys.platform != "win32", "this check is the Linux behaviour"
    exists, detail = feat_schedule.task_status()
    assert exists is False, (exists, detail)
    assert "Windows PC" in detail, detail
    assert "not Windows" in detail, detail
    print("task_status on Linux OK: (False, plain 'runs on your Windows PC' message)")


def _stage_morning_run(tmp):
    """Copy the three files morning_run.py needs into a temp folder."""
    for name in ("morning_run.py", "engine.py", "feat_automate.py"):
        shutil.copy(APP_DIR / name, Path(tmp) / name)
    in_dir = Path(tmp) / "morning_in"
    in_dir.mkdir()
    (in_dir / "messy.csv").write_text(
        "Name, Amount \n Alice , $1200 \n Bob,300\n Alice , $1200 \n",
        encoding="utf-8")
    return Path(tmp)


def test_run_now():
    with tempfile.TemporaryDirectory() as tmp:
        folder = _stage_morning_run(tmp)
        ok, output = feat_schedule.test_run_now(folder)
        assert ok is True, output
        assert "messy.csv" in output, output
        assert "cleaned" in output.lower(), output
        out_dir = folder / "morning_out"
        assert (out_dir / "messy_cleaned.csv").exists(), \
            "the run must write the cleaned file"
        assert (out_dir / "messy_log.txt").exists()
        assert (out_dir / "morning_run_summary.json").exists()
        cleaned = (out_dir / "messy_cleaned.csv").read_text()
        assert "Alice" in cleaned and "Bob" in cleaned
        summary = json.loads((out_dir / "morning_run_summary.json").read_text())
        assert summary[0]["status"] == "OK" and summary[0]["rows_in"] == 3, summary
        # A folder with no morning_run.py reports plainly, never raises.
        with tempfile.TemporaryDirectory() as empty:
            ok, output = feat_schedule.test_run_now(empty)
            assert ok is False and "morning_run.py" in output
            assert "not found" in output
    print("test_run_now OK: real morning_run.py runs, cleans messy.csv, "
          "writes morning_out + summary; missing script -> (False, plain message)")


def test_render_schedule_section():
    with tempfile.TemporaryDirectory() as tmp:
        folder = _stage_morning_run(tmp)
        # Nothing pressed: status line says Windows-only, no crash.
        st = FakeSt(values={"sched_time": datetime.time(8, 0)})
        exists, detail = feat_schedule.render_schedule_section(st, folder)
        assert exists is False and "Windows PC" in detail
        assert all(k.startswith("sched_") for k in st.keys_used("sched_"))
        assert "sched_time" in st.keys_used("sched_")
        assert "sched_setup" in st.keys_used("sched_")
        assert "sched_test_now" in st.keys_used("sched_")
        assert any("Set up auto-clean" in c[1]
                   for c in st.calls if c[0] == "button")
        assert any("Test it now" in c[1]
                   for c in st.calls if c[0] == "button")
        assert any("Windows PC" in m for m in st.messages("info")), \
            "status line must say plainly it runs on the Windows PC"
        assert any("setup_morning_run.bat" in m for m in st.messages("write")), \
            "the .bat fallback must still be mentioned"
        # "Set up" pressed on Linux: explains, attempts nothing, no crash.
        st = FakeSt(values={"sched_time": datetime.time(8, 0),
                            "sched_setup": True})
        exists, detail = feat_schedule.render_schedule_section(st, folder)
        assert exists is False
        assert any("not Windows" in m for m in st.messages("info"))
        # "Test it now" pressed: runs the real script, shows its output.
        st = FakeSt(values={"sched_time": datetime.time(8, 0),
                            "sched_test_now": True})
        exists, detail = feat_schedule.render_schedule_section(st, folder)
        assert any("Test run finished" in m for m in st.messages("success"))
        assert any("messy.csv" in m for m in st.messages("write")), st.calls
    print("render schedule OK: sched_* keys only, Windows-only text, "
          "setup guarded on Linux, Test-it-now runs + shows output")


# -------------------------------------------------------------- tutorial
def test_tutorial_steps():
    steps = feat_tutorial.TUTORIAL_STEPS
    assert isinstance(steps, list) and len(steps) >= 6, \
        f"need 6+ steps, got {len(steps)}"
    assert len(steps) <= 8, "keep it short: 6-8 steps"
    titles = [s["title"] for s in steps]
    assert "Load a file" in titles[0] or "load" in titles[0].lower()
    joined = " ".join(titles).lower()
    for word in ("health", "clean", "log", "kpi", "dashboard", "report"):
        assert word in joined, f"step flow must mention {word!r}: {titles}"
    for s in steps:
        assert set(s) >= {"title", "text"}, s
        assert isinstance(s["title"], str) and len(s["title"]) <= 40, s
        assert isinstance(s["text"], str) and len(s["text"]) > 20, s
        assert len(s["text"].split(". ")) <= 2 or s["text"].count(".") <= 2, \
            f"each step is 1-2 plain sentences: {s}"
    print(f"tutorial steps OK: {len(steps)} steps, load -> health -> clean "
          "-> log -> KPIs -> slicers -> report")


def test_first_run_flag():
    with tempfile.TemporaryDirectory() as tmp:
        settings_path = str(Path(tmp) / "settings.json")
        # Fresh: first run.
        assert feat_tutorial.is_first_run(settings_path) is True
        # Mark seen: flips, and the flag is stored under "tutorial_seen".
        assert feat_tutorial.mark_tutorial_seen(settings_path) is True
        assert feat_tutorial.is_first_run(settings_path) is False
        stored = json.loads(Path(settings_path).read_text())
        assert stored.get("tutorial_seen") is True
        # Marking again keeps it seen; other settings survive the write.
        stored["language"] = "en"
        Path(settings_path).write_text(json.dumps(stored), encoding="utf-8")
        feat_tutorial.mark_tutorial_seen(settings_path)
        kept = json.loads(Path(settings_path).read_text())
        assert kept["tutorial_seen"] is True and kept["language"] == "en"
        # A broken settings file still counts as a first run.
        Path(settings_path).write_text("{broken", encoding="utf-8")
        assert feat_tutorial.is_first_run(settings_path) is True
    print("first-run flag OK: True -> mark -> False, stored as 'tutorial_seen', "
          "other settings kept")


def test_render_tutorial_and_banner():
    with tempfile.TemporaryDirectory() as tmp:
        settings_path = str(Path(tmp) / "settings.json")
        # Tutorial page draws every step as a numbered section.
        st = FakeSt()
        feat_tutorial.render_tutorial(st)
        subs = st.messages("subheader")
        assert any("How to use" in s for s in subs)
        for i, step in enumerate(feat_tutorial.TUTORIAL_STEPS, start=1):
            assert any(f"{i}. {step['title']}" in s for s in subs), subs
        assert len(st.messages("write")) >= len(feat_tutorial.TUTORIAL_STEPS)
        # First-run banner shows on a first run, with a "Got it" button.
        st = FakeSt()
        shown = feat_tutorial.render_first_run_banner(st, settings_path)
        assert shown is True
        assert any("First time" in m for m in st.messages("info"))
        assert "tut_got_it" in st.keys_used("tut_")
        # Already seen: no banner at all.
        feat_tutorial.mark_tutorial_seen(settings_path)
        st = FakeSt()
        assert feat_tutorial.render_first_run_banner(st, settings_path) is False
        assert st.calls == [], "seen users get nothing drawn"
        # Pressing "Got it" marks seen.
        with tempfile.TemporaryDirectory() as tmp2:
            sp2 = str(Path(tmp2) / "settings.json")
            st = FakeSt(values={"tut_got_it": True})
            assert feat_tutorial.render_first_run_banner(st, sp2) is True
            assert feat_tutorial.is_first_run(sp2) is False
            assert any("Got it" in m for m in st.messages("success"))
        # The "How to use" page's own button marks seen too.
        with tempfile.TemporaryDirectory() as tmp3:
            sp3 = str(Path(tmp3) / "settings.json")
            st = FakeSt(values={"tut_page_seen": True})
            feat_tutorial.render_tutorial_page(st, sp3)
            assert feat_tutorial.is_first_run(sp3) is False
            assert "tut_page_seen" in st.keys_used("tut_")
    print("render tutorial OK: numbered sections, banner shows once, "
          "'Got it' (banner + page) flips the flag")


if __name__ == "__main__":
    test_build_daily_task_command()
    test_task_status_on_linux()
    test_run_now()
    test_render_schedule_section()
    test_tutorial_steps()
    test_first_run_flag()
    test_render_tutorial_and_banner()
    print("ALL SCHEDULE + TUTORIAL TESTS PASSED")
