"""Data Cleaner Studio (web) — server-side refresh scheduler.

Runs as a SEPARATE process from the Streamlit app (never inside a user
session). On each tick it reads the job registry, refreshes every due job,
and writes the results back — atomically, so the app never reads a
half-written file.

Job registry: ``data/scheduler/jobs.json``

    {
      "version": 1,
      "jobs": [
        {
          "user": "alice",
          "source_type": "sheets",          // "sheets" | "db"
          "source": "https://docs.google.com/spreadsheets/d/...",
          "target": "uploads/sales.csv",    // relative INSIDE data/users/<user>/
          "interval_minutes": 60,
          "last_run": "2026-11-06T06:00:00+00:00",   // ISO 8601, nullable
          "next_run": "2026-11-06T07:00:00+00:00",   // ISO 8601, nullable = due now
          "enabled": true,
          "table": "orders"                 // db jobs only; else from connection file
        }
      ]
    }

How each source refreshes
--------------------------
* ``sheets`` — ``engine.load_sheets_url(source)`` (public "anyone with the
  link" Google Sheet) -> DataFrame -> written as CSV to ``target``.
* ``db`` — ``source`` is a SAVED CONNECTION NAME, not credentials. The
  connection params live in ``data/users/<user>/connections/<name>.json``
  (created by the app's Settings page; see README.md for the contract).
  The job's ``table`` field (or the connection file's ``table``) picks the
  table, loaded via ``feat_db.load_table``. If ``feat_db`` cannot be
  imported, or the DB driver for that engine is not installed, the job is
  marked failed with a clear reason — never retried silently, never
  crashing the pass.

Safety rules (do not weaken these)
----------------------------------
* A job may ONLY write inside ``data/users/<that job's user>/``. Every
  target path is resolved and checked; ``..``, absolute paths and
  symlink escapes are rejected and logged as failures.
* Usernames and connection names must match ``[A-Za-z0-9][A-Za-z0-9._-]*``.
* Registry and target files are written atomically (temp file in the same
  directory + ``os.replace``), so a concurrent app process never reads a
  half-written file.
* One bad job never stops the pass: every failure is caught, logged and
  recorded on the job, and the pass continues with the next job.
* No credentials are ever written to the log. DB log lines carry the
  connection NAME only.

Usage
-----
    python scheduler.py --once            # single pass (for cron / systemd timer)
    python scheduler.py --daemon          # loop forever; tick = smallest enabled
                                          # job interval, 60 s default, 30 s floor
    python scheduler.py --once --jobs data/scheduler/jobs.json
    python scheduler.py --daemon --interval 300   # fixed 5-minute tick

Exit code: 0 when the pass completed (even if individual jobs failed —
check the log / registry for those), 1 when the registry itself could not
be read.

Only the standard library plus the project's own engine is used.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
USERS_DIR = DATA_DIR / "users"
SCHED_DIR = DATA_DIR / "scheduler"
DEFAULT_JOBS_FILE = SCHED_DIR / "jobs.json"
DEFAULT_LOG_FILE = SCHED_DIR / "scheduler.log"

DEFAULT_INTERVAL_SECONDS = 60
MIN_TICK_SECONDS = 30
MAX_TICK_SECONDS = 3600
DEFAULT_JOB_INTERVAL_MINUTES = 60

# SUPABASE KEEP-ALIVE (free tier): a free Supabase project pauses after
# 1 week of inactivity, and the pause clock is reset by REAL database
# activity — actual queries (login, load, save, SELECT/INSERT), not by
# opening the app's page. So the scheduler runs one tiny real SELECT
# against the profiles table at most once every 3 days. That query
# doubles as the keep-alive and the project stays awake even if nobody
# opens the app for a week. Runs only when Supabase mode is active and
# credentials are configured; in local mode it is a no-op. The last
# successful run is tracked in data/scheduler/keepalive.json, and the
# keep-alive runs even when NO jobs are configured at all.
KEEPALIVE_INTERVAL_DAYS = 3
KEEPALIVE_STATE_FILENAME = "keepalive.json"

# Usernames / connection names: plain, no slashes, no leading dot.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


# --------------------------------------------------------------------------
# Engine import (project root first, documented fallbacks for local dev)
# --------------------------------------------------------------------------

def _import_engine():
    """Import the project's engine (engine.load_sheets_url)."""
    for candidate in (
        PROJECT_ROOT,
        Path(os.environ.get("DCS_ENGINE_DIR", "")) if os.environ.get("DCS_ENGINE_DIR") else None,
        PROJECT_ROOT.parent / "data-cleaner-studio",  # sibling .exe project, local dev
    ):
        if candidate is None:
            continue
        candidate = Path(candidate)
        if (candidate / "engine.py").is_file() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        try:
            import engine  # noqa: PLC0415  (import after sys.path fix-up)
            if hasattr(engine, "load_sheets_url"):
                return engine
        except ImportError:
            continue
    return None


def _import_feat_db():
    """Import feat_db if present; None when the module is unavailable."""
    try:
        import feat_db  # noqa: PLC0415
        return feat_db
    except ImportError:
        return None


ENGINE = _import_engine()
FEAT_DB = _import_feat_db()


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value):
    """Parse an ISO-8601 timestamp; None on missing/invalid input."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def log_line(log_file: Path, message: str) -> None:
    """Append one timestamped line to the scheduler log (and stdout)."""
    line = f"{now_iso()} | {message}"
    print(line, flush=True)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:  # logging must never kill a pass
        print(f"{now_iso()} | WARNING: could not write log: {exc}", flush=True)


def atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically: temp file in the same dir + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_csv(df, path: Path) -> None:
    """Write a DataFrame to CSV atomically (temp file + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                    dir=str(path.parent))
    os.close(fd)
    try:
        df.to_csv(tmp_name, index=False)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

class _FileLock:
    """Best-effort exclusive lock (fcntl on POSIX; no-op elsewhere).

    Guards the read-modify-write of jobs.json against a concurrent writer
    (e.g. the Streamlit app adding a job while a pass is running).
    """

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._fh = None

    def __enter__(self):
        try:
            import fcntl  # noqa: PLC0415  (POSIX only)
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.lock_path, "a", encoding="utf-8")
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            self._fh = None
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            try:
                import fcntl  # noqa: PLC0415
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
                self._fh.close()
            except (ImportError, OSError):
                pass
        return False


def load_registry(jobs_file: Path):
    """Return (payload_dict, error_str|None). Missing file = empty registry."""
    if not jobs_file.is_file():
        return {"version": 1, "jobs": []}, None
    try:
        with open(jobs_file, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"cannot read registry {jobs_file}: {exc}"
    if isinstance(raw, list):  # tolerate a bare list of jobs
        return {"version": 1, "jobs": raw}, None
    if not isinstance(raw, dict) or not isinstance(raw.get("jobs"), list):
        return None, f"registry {jobs_file} is not {{'jobs': [...]}}"
    return raw, None


def save_registry(jobs_file: Path, payload: dict) -> None:
    with _FileLock(jobs_file.with_suffix(".lock")):
        atomic_write_json(jobs_file, payload)


# --------------------------------------------------------------------------
# Path safety — the one rule that matters most
# --------------------------------------------------------------------------

def resolve_user_target(user: str, target: str) -> Path:
    """Resolve ``target`` strictly inside ``data/users/<user>/``.

    Raises ValueError on: bad username, empty/absolute target, ``..``
    escapes, or a symlink that points outside the user's folder.
    """
    if not isinstance(user, str) or not SAFE_NAME.match(user):
        raise ValueError(f"unsafe username: {user!r}")
    if not isinstance(target, str) or not target.strip():
        raise ValueError("empty target path")
    if Path(target).is_absolute():
        raise ValueError(f"target must be relative, got: {target!r}")
    user_root = (USERS_DIR / user).resolve()
    resolved = (user_root / target).resolve()
    if not resolved.is_relative_to(user_root):
        raise ValueError(f"target escapes user folder: {target!r}")
    if resolved == user_root:
        raise ValueError("target must be a file inside the user folder")
    return resolved


def resolve_connection_file(user: str, name: str) -> Path:
    """Resolve data/users/<user>/connections/<name>.json, escape-checked."""
    if not SAFE_NAME.match(name or ""):
        raise ValueError(f"unsafe connection name: {name!r}")
    user_root = (USERS_DIR / user).resolve()
    resolved = (user_root / "connections" / f"{name}.json").resolve()
    if not resolved.is_relative_to(user_root):
        raise ValueError(f"connection path escapes user folder: {name!r}")
    return resolved


# --------------------------------------------------------------------------
# Job execution
# --------------------------------------------------------------------------

def refresh_sheets(job: dict, target_path: Path) -> tuple[int, str]:
    """Refresh a Google Sheets job. Returns (rows, detail)."""
    if ENGINE is None:
        raise RuntimeError(
            "engine.py not importable from the project root — "
            "copy engine.py into the web project (see README.md)"
        )
    url = job.get("source") or ""
    df = ENGINE.load_sheets_url(url)
    atomic_write_csv(df, target_path)
    return len(df), f"rows={len(df)} target={target_path.relative_to(USERS_DIR)}"


def refresh_db(job: dict, target_path: Path) -> tuple[int, str]:
    """Refresh a database job via a saved connection. Returns (rows, detail)."""
    if FEAT_DB is None:
        raise RuntimeError(
            "feat_db is not importable on this server — DB refresh "
            "unavailable (copy feat_db.py into the project)"
        )
    user = job["user"]
    conn_name = job.get("source") or ""
    conn_file = resolve_connection_file(user, conn_name)
    if not conn_file.is_file():
        raise RuntimeError(
            f"saved connection {conn_name!r} not found for user {user!r} "
            f"(expected data/users/{user}/connections/{conn_name}.json) — "
            "create it in the app's Settings page first"
        )
    try:
        with open(conn_file, encoding="utf-8") as fh:
            params = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"saved connection {conn_name!r} is unreadable: {exc}")
    if not isinstance(params, dict):
        raise RuntimeError(f"saved connection {conn_name!r} is not a JSON object")
    table = job.get("table") or params.get("table")
    if not table:
        raise RuntimeError(
            f"no table for DB job (set 'table' on the job or in connection {conn_name!r})"
        )
    df = FEAT_DB.load_table(
        engine=params.get("engine"),
        host=params.get("host"),
        port=params.get("port"),
        user=params.get("user"),
        password=params.get("password"),
        database=params.get("database"),
        table=table,
    )
    atomic_write_csv(df, target_path)
    return len(df), (
        f"rows={len(df)} connection={conn_name} table={table} "
        f"target={target_path.relative_to(USERS_DIR)}"
    )


def run_job(job: dict) -> tuple[bool, str]:
    """Run one job. Returns (ok, human-readable detail). Never raises."""
    user = job.get("user") or "?"
    source_type = job.get("source_type")
    try:
        target_path = resolve_user_target(user, job.get("target"))
        if source_type == "sheets":
            _, detail = refresh_sheets(job, target_path)
            return True, detail
        if source_type == "db":
            _, detail = refresh_db(job, target_path)
            return True, detail
        raise ValueError(f"unknown source_type: {source_type!r} (want 'sheets' or 'db')")
    except Exception as exc:  # one bad job must never stop the pass
        return False, f"{type(exc).__name__}: {exc}"


def job_interval_minutes(job: dict) -> int:
    try:
        minutes = int(job.get("interval_minutes") or DEFAULT_JOB_INTERVAL_MINUTES)
    except (TypeError, ValueError):
        return DEFAULT_JOB_INTERVAL_MINUTES
    return minutes if minutes > 0 else DEFAULT_JOB_INTERVAL_MINUTES


def job_is_due(job: dict, now: datetime) -> bool:
    if not job.get("enabled", True):
        return False
    nxt = parse_iso(job.get("next_run"))
    return nxt is None or now >= nxt


# --------------------------------------------------------------------------
# One pass
# --------------------------------------------------------------------------

def _keepalive_state_path(jobs_file: Path) -> Path:
    """State file tracking the last keep-alive run (next to jobs.json)."""
    return jobs_file.parent / KEEPALIVE_STATE_FILENAME


def _run_supabase_keepalive(jobs_file: Path, log_file: Path,
                            now: datetime) -> str:
    """Run the Supabase keep-alive query if it is due.

    Returns "ok" | "failed" | "not-due" | "inactive". Never raises —
    a keep-alive failure must never break a refresh pass. Only runs
    when the auth backend is 'supabase' (credentials configured);
    in local mode it returns "inactive" without touching anything.
    The state file records the last SUCCESSFUL run only, so a failed
    attempt is retried on the next pass instead of waiting 3 days.
    """
    try:
        import auth
    except ImportError:
        return "inactive"
    try:
        if auth.get_auth_backend() != "supabase":
            return "inactive"
    except Exception:  # noqa: BLE001 - keep-alive must never break a pass
        return "inactive"

    state_file = _keepalive_state_path(jobs_file)
    try:
        last = None
        if state_file.is_file():
            state = json.loads(state_file.read_text(encoding="utf-8"))
            last = parse_iso(state.get("last_keepalive")) if isinstance(state, dict) else None
    except (OSError, ValueError):
        last = None
    if last is not None and (now - last) < timedelta(days=KEEPALIVE_INTERVAL_DAYS):
        return "not-due"

    ok = auth.supabase_keepalive()
    if ok:
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(state_file, {
                "last_keepalive": now_iso(),
                "status": "ok",
            })
        except OSError as exc:
            log_line(log_file, f"KEEP-ALIVE | ok but state file not saved: {exc}")
        log_line(log_file, "KEEP-ALIVE | ok | tiny SELECT on profiles ran")
        return "ok"
    log_line(
        log_file,
        "KEEP-ALIVE | FAILED | Supabase query did not run — check "
        "auth.get_backend_warning() (paused project or missing setup?)",
    )
    return "failed"


def run_once(jobs_file: Path, log_file: Path) -> dict:
    """Run a single pass over all due jobs. Returns a summary dict."""
    summary = {"ran": 0, "ok": 0, "failed": 0, "skipped": 0, "registry_error": None}
    payload, err = load_registry(jobs_file)
    if err is not None:
        summary["registry_error"] = err
        log_line(log_file, f"ERROR | {err}")
        return summary

    jobs = payload.get("jobs", [])
    now = datetime.now(timezone.utc)
    changed = False

    # Supabase keep-alive FIRST: it runs even when no jobs are due or
    # no jobs exist at all, and it must never break the pass.
    summary["keepalive"] = _run_supabase_keepalive(jobs_file, log_file, now)

    for job in jobs:
        if not isinstance(job, dict):
            summary["skipped"] += 1
            continue
        user = job.get("user") or "?"
        if not job.get("enabled", True):
            summary["skipped"] += 1
            continue
        if not job_is_due(job, now):
            summary["skipped"] += 1
            continue

        started = time.monotonic()
        ok, detail = run_job(job)
        elapsed = time.monotonic() - started
        minutes = job_interval_minutes(job)
        job["last_run"] = now_iso()
        job["next_run"] = (now + timedelta(minutes=minutes)).isoformat(timespec="seconds")
        job["last_status"] = "ok" if ok else "failed"
        job["last_error"] = None if ok else detail
        if ok:
            job["last_rows"] = int(detail.split("rows=", 1)[1].split()[0]) if "rows=" in detail else None
        changed = True

        status = "ok" if ok else "FAILED"
        summary["ran"] += 1
        summary["ok" if ok else "failed"] += 1
        log_line(
            log_file,
            f"{status} | user={user} | type={job.get('source_type')} | "
            f"source={job.get('source')} | {detail} | {elapsed:.1f}s",
        )

    if changed:
        try:
            save_registry(jobs_file, payload)
        except OSError as exc:
            summary["registry_error"] = f"cannot save registry: {exc}"
            log_line(log_file, f"ERROR | cannot save registry {jobs_file}: {exc}")

    log_line(
        log_file,
        f"PASS DONE | ran={summary['ran']} ok={summary['ok']} "
        f"failed={summary['failed']} skipped={summary['skipped']} "
        f"keepalive={summary.get('keepalive', 'n/a')}",
    )
    return summary


def daemon_tick_seconds(jobs_file: Path) -> int:
    """Sleep between daemon ticks: smallest enabled job interval, else 60 s."""
    payload, _ = load_registry(jobs_file)
    if payload is None:
        return DEFAULT_INTERVAL_SECONDS
    intervals = [
        job_interval_minutes(job) * 60
        for job in payload.get("jobs", [])
        if isinstance(job, dict) and job.get("enabled", True)
    ]
    if not intervals:
        return DEFAULT_INTERVAL_SECONDS
    return max(MIN_TICK_SECONDS, min(min(intervals), MAX_TICK_SECONDS))


def run_daemon(jobs_file: Path, log_file: Path, fixed_interval: int | None) -> None:
    log_line(log_file, "DAEMON START | scheduler.py --daemon")
    try:
        while True:
            run_once(jobs_file, log_file)
            sleep_s = fixed_interval if fixed_interval else daemon_tick_seconds(jobs_file)
            log_line(log_file, f"DAEMON SLEEP | next tick in {sleep_s}s")
            time.sleep(sleep_s)
    except KeyboardInterrupt:
        log_line(log_file, "DAEMON STOP | interrupted (Ctrl+C)")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Data Cleaner Studio (web) — server-side refresh scheduler."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true",
                      help="single pass over due jobs, then exit (for cron)")
    mode.add_argument("--daemon", action="store_true",
                      help="loop forever, sleeping between passes")
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS_FILE),
                        help="path to jobs.json (default: data/scheduler/jobs.json)")
    parser.add_argument("--log", default=str(DEFAULT_LOG_FILE),
                        help="path to scheduler.log (default: data/scheduler/scheduler.log)")
    parser.add_argument("--interval", type=int, default=None,
                        help="daemon tick in seconds (overrides job-derived interval)")
    parser.add_argument("--data-dir", default=None,
                        help="override the data/ directory (tests / alternate layouts)")
    args = parser.parse_args(argv)

    global DATA_DIR, USERS_DIR, SCHED_DIR  # noqa: PLW0603  (CLI override only)
    if args.data_dir:
        DATA_DIR = Path(args.data_dir).resolve()
        USERS_DIR = DATA_DIR / "users"
        SCHED_DIR = DATA_DIR / "scheduler"

    jobs_file = Path(args.jobs)
    log_file = Path(args.log)
    if args.data_dir and args.jobs == str(DEFAULT_JOBS_FILE):
        jobs_file = SCHED_DIR / "jobs.json"
    if args.data_dir and args.log == str(DEFAULT_LOG_FILE):
        log_file = SCHED_DIR / "scheduler.log"

    if args.daemon:
        run_daemon(jobs_file, log_file, args.interval)
        return 0
    # Default mode is a single pass (safe for cron; --once is explicit).
    summary = run_once(jobs_file, log_file)
    print(
        f"pass done: ran={summary['ran']} ok={summary['ok']} "
        f"failed={summary['failed']} skipped={summary['skipped']} "
        f"keepalive={summary.get('keepalive', 'n/a')}"
        + (f" | REGISTRY ERROR: {summary['registry_error']}" if summary["registry_error"] else ""),
        flush=True,
    )
    return 1 if summary["registry_error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
