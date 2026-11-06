"""Data Cleaner Studio — daily auto-clean while the app is closed
(v1.4, Group B).

The app itself only cleans while it is open. This module is the
effortless way to get the cleaning done every morning anyway: it
registers one Windows scheduled task that runs morning_run.py daily,
even when the app is closed.

How it works (on your Windows PC only):
  * "Set up daily auto-clean" registers a daily task in Windows Task
    Scheduler — the same task setup_morning_run.bat creates, so the
    .bat file stays as the fallback for anyone who prefers it.
  * The task runs the portable package's own pythonw.exe (no console
    window pops up) with morning_run.py, so it works in the portable
    package without a system Python installed.
  * "Test it now" runs morning_run.py once, right now, and shows what
    it did — so you can check it works before trusting the morning run.
  * Put messy files in morning_in/ in the evening; find the cleaned
    files in morning_out/ each morning.

Nothing here works on a Mac, on Linux, or on the web — the task only
runs on his Windows PC, and every message in this module says so
plainly. On any other system the status call reports that plainly and
the buttons do nothing except explain it, so the app never crashes.

Contract:
  - TASK_NAME = "Data Cleaner Studio Morning Run"
  - build_daily_task_command(folder, recipe=None, time="08:00") -> str
  - task_status() -> (exists: bool, detail: str)
  - test_run_now(folder, recipe=None) -> (ok: bool, output: str)
  - render_schedule_section(st, folder=None, recipe=None)
    -> (exists: bool, detail: str)

Widget keys all start with "sched_".
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

TASK_NAME = "Data Cleaner Studio Morning Run"
DEFAULT_TIME = "08:00"

NON_WINDOWS_MSG = (
    "Auto-clean scheduling runs on your Windows PC — this computer is "
    "not Windows, so no scheduled task can be set up or checked here. "
    "Set it up on your Windows PC instead."
)

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

__all__ = [
    "TASK_NAME", "DEFAULT_TIME", "NON_WINDOWS_MSG",
    "build_daily_task_command", "task_status", "test_run_now",
    "render_schedule_section",
]


def _is_windows() -> bool:
    """True only on Windows (where Task Scheduler exists)."""
    return os.name == "nt" or sys.platform.startswith("win")


def _app_dir(folder=None) -> Path:
    return Path(folder) if folder is not None else Path(__file__).resolve().parent


def _win_path(folder, *parts) -> str:
    """A Windows-style path (backslashes) built from the app folder,
    so the scheduled task works in the portable package on Windows
    even when this string is built on another system."""
    base = str(folder).rstrip("/\\") or "."
    return "\\".join([base] + [str(p) for p in parts])


def _validate_time(time: str) -> str:
    """"HH:MM" (24-hour), or ValueError naming the problem."""
    if not isinstance(time, str) or not _TIME_RE.match(time.strip()):
        raise ValueError(
            f"time must look like '08:00' (24-hour HH:MM), got {time!r}")
    return time.strip()


def build_daily_task_command(folder, recipe=None, time=DEFAULT_TIME) -> str:
    """The exact schtasks command that registers the daily task.

    Runs the portable package's pythonw.exe (no console window) with
    morning_run.py, daily at ``time``. ``recipe`` (a saved recipe file)
    is passed with --recipe when given. Returns the command as one
    string — the app runs the same command as an argument list, never
    through a shell.
    """
    time = _validate_time(time)
    folder = _app_dir(folder)
    pythonw = _win_path(folder, "Data-Cleaner-Studio", "python", "pythonw.exe")
    script = _win_path(folder, "morning_run.py")
    tr_inner = f'\\"{pythonw}\\" \\"{script}\\"'
    if recipe is not None:
        tr_inner += f' --recipe \\"{recipe}\\"'
    return (f'schtasks /create /tn "{TASK_NAME}" /tr "{tr_inner}" '
            f'/sc daily /st {time} /f')


def _create_task_args(folder, recipe=None, time=DEFAULT_TIME) -> list:
    """The same command as build_daily_task_command(), as an argument
    list for subprocess (no shell, so no quoting surprises)."""
    time = _validate_time(time)
    folder = _app_dir(folder)
    pythonw = _win_path(folder, "Data-Cleaner-Studio", "python", "pythonw.exe")
    script = _win_path(folder, "morning_run.py")
    tr_value = f'"{pythonw}" "{script}"'
    if recipe is not None:
        tr_value += f' --recipe "{recipe}"'
    return ["schtasks", "/create", "/tn", TASK_NAME, "/tr", tr_value,
            "/sc", "daily", "/st", time, "/f"]


def task_status() -> tuple:
    """(exists, detail) for the daily task, via ``schtasks /query``.

    On a non-Windows computer this always returns (False, <the plain
    "runs on your Windows PC" message>) and never runs schtasks.
    On Windows, exists is True when the task is registered.
    """
    if not _is_windows():
        return False, NON_WINDOWS_MSG
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME],
            capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return (False, "Could not check the schedule — 'schtasks' was not "
                       "found on this Windows PC.")
    except Exception as e:  # noqa: BLE001 - a failed check must not crash
        return (False, f"Could not check the schedule on this Windows PC: {e}")
    if result.returncode == 0:
        detail = ("Daily auto-clean is set up on your Windows PC — "
                  "morning_run.py runs every morning.")
        next_run = ""
        for line in (result.stdout or "").splitlines():
            if "Next Run Time" in line and ":" in line:
                next_run = line.split(":", 1)[1].strip()
        if next_run:
            detail += f" Next run: {next_run}."
        return True, detail
    return (False, "No daily auto-clean is set up yet on this Windows PC. "
                   "Press 'Set up daily auto-clean' below to create it — "
                   "it takes one click.")


def test_run_now(folder, recipe=None) -> tuple:
    """Run morning_run.py once, right now, and report what happened.

    Returns (ok, output): ok is True when the script finished without
    an error, output is what it printed. Safe to call on Linux for
    testing — it just runs the Python script with this Python and
    reports the result. Never raises for a missing script or a failed
    run; those come back as (False, <plain explanation>).
    """
    folder = _app_dir(folder)
    script = folder / "morning_run.py"
    if not script.exists():
        return (False, f"morning_run.py was not found in {folder} — "
                       "the test run cannot start without it.")
    cmd = [sys.executable, str(script)]
    if recipe is not None:
        cmd += ["--recipe", str(recipe)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=120, cwd=str(folder))
    except Exception as e:  # noqa: BLE001 - report, don't crash
        return False, f"The test run could not start: {e}"
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if not output:
        output = "Morning run finished with no output."
    return result.returncode == 0, output


# --------------------------------------------------------------------------
# render function — thin Streamlit wrapper (st passed in, never imported)
# --------------------------------------------------------------------------

def render_schedule_section(st, folder=None, recipe=None) -> tuple:
    """Tools tab: set up the daily auto-clean, test it, see its status.

    All widget keys start with "sched_". Every Windows-only action is
    guarded: on a non-Windows computer the buttons only explain that
    the schedule runs on your Windows PC, and nothing is attempted.
    Returns task_status() — (exists, detail).
    """
    folder = _app_dir(folder)
    st.subheader("Daily auto-clean — while the app is closed")
    st.write("Want the cleaning done before you sit down? Put messy "
             "files in a `morning_in` folder in the evening and find "
             "the cleaned files in `morning_out` each morning — even "
             "when this app is closed.")
    st.write("This only works on your Windows PC: it creates a daily "
             "task in Windows Task Scheduler that runs `morning_run.py` "
             "every morning. It uses the recipe in `morning_recipe.json` "
             "next to the app when there is one (save one from the "
             "Clean tab and rename it), or the standard all-fixes "
             "cleaning when there is no recipe file. One bad file is "
             "logged and skipped; the rest still get cleaned.")
    run_time = st.time_input("Run every day at", value=datetime.time(8, 0),
                             key="sched_time",
                             help="The time the morning run starts, on "
                                  "your Windows PC.")
    time_str = run_time.strftime("%H:%M") if run_time else DEFAULT_TIME
    exists, detail = task_status()
    if exists:
        st.success(detail)
    else:
        st.info(detail)
    if st.button("Set up daily auto-clean", key="sched_setup", type="primary"):
        if not _is_windows():
            st.info(NON_WINDOWS_MSG)
        else:
            try:
                result = subprocess.run(
                    _create_task_args(folder, recipe, time_str),
                    capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    st.success(f"Done — the morning run is set for "
                               f"{time_str} every day on your Windows PC. "
                               f"Put messy files in morning_in and find "
                               f"the cleaned files in morning_out each "
                               f"morning.")
                    exists, detail = task_status()
                else:
                    st.error("Could not create the scheduled task on your "
                             "Windows PC. Try right-clicking "
                             "setup_morning_run.bat and choosing "
                             "'Run as administrator'. "
                             f"{(result.stderr or result.stdout or '').strip()}")
            except Exception as e:  # noqa: BLE001 - show, don't crash
                st.error(f"Could not create the scheduled task: {e}")
    if st.button("Test it now", key="sched_test_now"):
        ok, output = test_run_now(folder, recipe)
        if ok:
            st.success("Test run finished — the morning run works.")
        else:
            st.error("Test run did not finish cleanly.")
        st.write(output)
    st.write("Prefer the file instead? `setup_morning_run.bat` in the "
             "app folder does the same thing — double-click it on your "
             "Windows PC. To remove the daily run later, run: "
             f"`schtasks /delete /tn \"{TASK_NAME}\" /f`.")
    return exists, detail
