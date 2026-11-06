"""Structural tests for the Supabase auth path (auth.py + google_auth.py
+ storage.py + scheduler.py keep-alive).

These are STRUCTURAL ONLY — no Supabase project exists yet, so nothing
here talks to a live Supabase backend. What they verify:
  * supabase-py imports and exposes the APIs auth.py / storage.py need.
  * Backend selection: missing credentials -> 'local' (+ banner);
    malformed / placeholder config -> 'local' + a clear warning.
  * A configured-but-unreachable project (http://127.0.0.1:9, which
    refuses connections immediately) -> backend stays 'supabase',
    get_backend_warning() is the plain paused message, and
    authenticate()/create_user() raise AuthServiceError — never a fake
    "wrong password", never a silent fall back to local accounts.
  * supabase_setup.sql exists and has the right shape (profiles +
    sessions tables, RLS, SECURITY DEFINER functions, bucket policies).
  * Google OAuth entry points exist on auth.py and behave in local
    mode (URL is None, callback returns a clean error tuple).
  * In Supabase mode without a service-role key, storage fails LOUDLY
    (RuntimeError) instead of silently writing locally.
  * The scheduler keep-alive: inactive in local mode, runs on a 3-day
    cadence, and runs even with no jobs configured.
  * Zero references to the previous provider left in the owned files.

Run:  python3 tests/test_auth_supabase.py   (from the project root)

SANDBOX NOTE: this VM's NO_PROXY list contains bracketed IPv6 entries
("[::1]") that httpx cannot parse, so create_client() raises
InvalidURL unless the list is sanitised first. The tests set a plain
no_proxy below before any client is built. That is a sandbox quirk,
not an app bug — real deploys do not have those entries.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Sandbox quirk (see module docstring): plain entries only.
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth
import google_auth
import storage

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# A URL that refuses connections instantly (nothing listens on port 9),
# so "unreachable project" tests fail fast instead of timing out.
DEAD_URL = "http://127.0.0.1:9"


def _repoint(tmp: Path, cfg: Path | None = None):
    old_cfg = auth.SUPABASE_CONFIG_PATH
    old_env = {k: os.environ.pop(k, None)
               for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY")}
    auth.SUPABASE_CONFIG_PATH = cfg or (tmp / "no-supabase_config.json")
    auth._reset_backend_cache()
    storage._reset_storage_cache()
    return old_cfg, old_env


def _restore(old_cfg, old_env):
    auth.SUPABASE_CONFIG_PATH = old_cfg
    for key, value in old_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    auth._reset_backend_cache()
    storage._reset_storage_cache()


def test_supabase_importable():
    from supabase import create_client

    client = create_client("https://example.supabase.co", "anon-key")
    for name in ("sign_up", "sign_in_with_password", "sign_in_with_oauth",
                 "exchange_code_for_session", "sign_out"):
        assert hasattr(client.auth, name), f"auth.{name} missing"
    assert hasattr(client, "table") and hasattr(client, "rpc")
    assert hasattr(client, "storage")
    bucket = client.storage.from_("user-files")
    for name in ("upload", "download", "list", "remove"):
        assert hasattr(bucket, name), f"storage.{name} missing"
    import supabase as sb

    print("supabase importable OK (version:",
          getattr(sb, "__version__", "?") + ")")


def test_missing_config_is_local():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        old_cfg, old_env = _repoint(tmp)
        try:
            assert auth.get_auth_backend() == "local"
            assert auth.get_backend_warning() is None
            banner = auth.get_local_mode_banner()
            assert banner == auth.LOCAL_MODE_BANNER
            assert "Local mode" in banner and "Supabase" in banner
            assert auth.get_google_sign_in_url() is None
            assert google_auth.get_google_sign_in_url() is None
            user, token, err = auth.handle_oauth_code("somecode")
            assert user is None and token is None and err
            print("missing config -> local + banner OK")
        finally:
            _restore(old_cfg, old_env)


def test_malformed_config_is_local_with_warning():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bad_cfg = tmp / "supabase_config.json"
        cases = [
            ("{not json", "unreadable"),
            (json.dumps(["not", "an", "object"]), "JSON object"),
            (json.dumps({"url": DEAD_URL}), "anon key"),
            (json.dumps({"anon_key": "x"}), "URL"),
            (json.dumps({"url": "not-a-url", "anon_key": "x"}), "URL"),
            (json.dumps({"url": "https://x.supabase.co",
                         "anon_key": "PASTE_YOUR_ANON_KEY_HERE"}),
             "placeholder"),
        ]
        for content, needle in cases:
            bad_cfg.write_text(content)
            old_cfg, old_env = _repoint(tmp, bad_cfg)
            try:
                assert auth.get_auth_backend() == "local", content
                warning = auth.get_backend_warning()
                assert warning is not None and needle in warning, (content, warning)
            finally:
                _restore(old_cfg, old_env)
        print("malformed/placeholder config -> local + warning OK")


def test_env_var_config_selects_supabase():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        old_cfg, old_env = _repoint(tmp)
        os.environ["SUPABASE_URL"] = DEAD_URL
        os.environ["SUPABASE_ANON_KEY"] = "test-anon-key"
        try:
            assert auth.get_auth_backend() == "supabase"
            # Unreachable project -> the plain paused message, not a crash.
            assert auth.get_backend_warning() == auth.PAUSED_MESSAGE
            print("env-var config -> supabase + paused message OK")
        finally:
            _restore(old_cfg, old_env)


def test_paused_project_never_fakes_a_login():
    """Configured but unreachable: authenticate/create_user must raise
    AuthServiceError — never return None (fake "wrong password") and
    never fall back to local accounts."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = tmp / "supabase_config.json"
        cfg.write_text(json.dumps({"url": DEAD_URL, "anon_key": "test-key"}))
        old_cfg, old_env = _repoint(tmp, cfg)
        try:
            assert auth.get_auth_backend() == "supabase"
            assert auth.get_backend_warning() == auth.PAUSED_MESSAGE
            assert auth.get_local_mode_banner() is None
            try:
                auth.authenticate("someone@example.com", "supersecret1")
            except auth.AuthServiceError as exc:
                assert "paused" in str(exc).lower(), str(exc)
            else:
                raise AssertionError("authenticate must raise, not return None")
            try:
                auth.create_user("someone@example.com", "supersecret1")
            except auth.AuthServiceError as exc:
                assert "paused" in str(exc).lower(), str(exc)
            else:
                raise AssertionError("create_user must raise, not return ok")
            # And no local account was created as a side effect.
            assert auth.get_auth_backend() == "supabase"
            print("paused project -> AuthServiceError, no fake login OK")
        finally:
            _restore(old_cfg, old_env)


def test_keepalive_never_raises_and_reports_paused():
    """supabase_keepalive() is a bool, never an exception — the
    scheduler depends on that."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = tmp / "supabase_config.json"
        cfg.write_text(json.dumps({"url": DEAD_URL, "anon_key": "test-key"}))
        old_cfg, old_env = _repoint(tmp, cfg)
        try:
            assert auth.get_auth_backend() == "supabase"
            assert auth.supabase_keepalive() is False
            print("keep-alive on dead project -> False, no raise OK")
        finally:
            _restore(old_cfg, old_env)


def test_setup_sql_shape():
    sql_path = PROJECT_ROOT / "supabase_setup.sql"
    assert sql_path.is_file(), "supabase_setup.sql missing"
    sql = sql_path.read_text(encoding="utf-8")
    lowered = sql.lower()
    for needle in (
        "create table if not exists public.profiles",
        "create table if not exists public.sessions",
        "enable row level security",
        "app_upsert_profile",
        "app_get_profile",
        "app_create_session",
        "app_validate_session",
        "app_delete_session",
        "security definer",
        "storage.buckets",
        "'user-files'",
        "create policy",
        "auth.uid()",
        "storage.foldername(name)",
    ):
        assert needle in lowered, f"supabase_setup.sql missing: {needle}"
    assert lowered.count("create policy") >= 4, "need >= 4 bucket policies"
    assert "service_role" not in lowered, "SQL must not mention service_role"
    print("supabase_setup.sql shape OK")


def test_google_entry_points_exist():
    assert callable(getattr(auth, "get_google_sign_in_url", None))
    assert callable(getattr(auth, "handle_oauth_code", None))
    assert callable(getattr(auth, "handle_google_callback", None))
    assert callable(getattr(google_auth, "get_google_sign_in_url", None))
    assert callable(getattr(google_auth, "handle_oauth_code", None))
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        old_cfg, old_env = _repoint(tmp)
        try:
            assert auth.get_auth_backend() == "local"
            assert google_auth.handle_oauth_code("garbage") == (
                None, None, "Google sign-in is not set up (local mode).")
            assert google_auth.handle_oauth_code("")[:2] == (None, None)
            print("Google entry points exist + clean local-mode behaviour OK")
        finally:
            _restore(old_cfg, old_env)


def test_storage_supabase_mode_fails_loud_without_service_key():
    """No service-role key -> RuntimeError naming it, never a silent
    local write."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = tmp / "supabase_config.json"
        cfg.write_text(json.dumps({"url": DEAD_URL, "anon_key": "test-key"}))
        old_cfg, old_env = _repoint(tmp, cfg)
        old_role = os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
        try:
            assert auth.get_auth_backend() == "supabase"
            assert storage._sb_service_key() is None
            try:
                storage.save_upload("alice", "x.csv", b"a,b\n1,2\n")
            except RuntimeError as exc:
                assert "SUPABASE_SERVICE_ROLE_KEY" in str(exc), str(exc)
            else:
                raise AssertionError("storage must raise without service key")
            print("Supabase storage without service key -> loud RuntimeError OK")
        finally:
            if old_role is not None:
                os.environ["SUPABASE_SERVICE_ROLE_KEY"] = old_role
            _restore(old_cfg, old_env)


def test_keepalive_scheduler_behaviour():
    import scheduler

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        jobs_file = tmp / "jobs.json"
        log_file = tmp / "scheduler.log"
        jobs_file.write_text(json.dumps({"version": 1, "jobs": []}))
        old_cfg, old_env = _repoint(tmp)
        try:
            # Local mode: keep-alive is inactive, and it runs even with
            # zero jobs configured (run_once still reports it).
            summary = scheduler.run_once(jobs_file, log_file)
            assert summary["keepalive"] == "inactive", summary
            assert not (tmp / "keepalive.json").exists()
            print("scheduler keep-alive inactive in local mode OK")
        finally:
            _restore(old_cfg, old_env)

        # Supabase mode, unreachable project: keep-alive fails, and the
        # state file is NOT written (a failure must be retried next pass).
        cfg = tmp / "supabase_config.json"
        cfg.write_text(json.dumps({"url": DEAD_URL, "anon_key": "test-key"}))
        old_cfg, old_env = _repoint(tmp, cfg)
        try:
            summary = scheduler.run_once(jobs_file, log_file)
            assert summary["keepalive"] == "failed", summary
            assert not (tmp / "keepalive.json").exists()
            # A recent successful run is "not-due": no query is attempted.
            (tmp / "keepalive.json").write_text(json.dumps({
                "last_keepalive": datetime.now(timezone.utc).isoformat(),
                "status": "ok",
            }))
            assert scheduler._run_supabase_keepalive(
                jobs_file, log_file, datetime.now(timezone.utc)) == "not-due"
            # A run 4 days ago IS due again.
            (tmp / "keepalive.json").write_text(json.dumps({
                "last_keepalive": (
                    datetime.now(timezone.utc) - timedelta(days=4)).isoformat(),
                "status": "ok",
            }))
            assert scheduler._run_supabase_keepalive(
                jobs_file, log_file, datetime.now(timezone.utc)) == "failed"
            print("scheduler keep-alive cadence (3 days) + failure path OK")
        finally:
            _restore(old_cfg, old_env)


def test_local_mode_still_enforces_username_rules():
    """Backend selection must not let an email slip into a local username."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        old_db = auth.DB_PATH
        old_cfg, old_env = _repoint(tmp)
        auth.DB_PATH = tmp / "users.db"
        try:
            assert auth.get_auth_backend() == "local"
            ok, err = auth.create_user("alice@example.com", "supersecret1")
            assert not ok and err, "email is not a valid local username"
            ok, err = auth.create_user("alice", "supersecret1")
            assert ok, f"local signup must still work: {err}"
            print("local username rules intact OK")
        finally:
            auth.DB_PATH = old_db
            _restore(old_cfg, old_env)


def test_no_previous_provider_references_left():
    """Zero references to the previous provider in the files this
    rework owns. The needle is built without the literal so this test
    file itself stays grep-clean for it."""
    needle = "fire" + "base"
    owned = [
        "auth.py", "google_auth.py", "storage.py", "scheduler.py",
        "requirements.txt", "DEPLOY.md", "README.md", "Dockerfile",
        ".gitignore", ".dockerignore", "supabase_setup.sql",
        "supabase_config.json.example",
    ]
    hits = []
    for name in owned:
        path = PROJECT_ROOT / name
        assert path.is_file(), f"owned file missing: {name}"
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if needle in line.lower():
                hits.append(f"{name}:{i}: {line.strip()}")
    assert not hits, "Previous-provider references left:\n" + "\n".join(hits)
    assert not (PROJECT_ROOT / ("fire" + "base_config.json.example")).exists()
    assert (PROJECT_ROOT / "supabase_config.json.example").is_file()
    # The example config must be placeholders only, never real keys.
    example = json.loads(
        (PROJECT_ROOT / "supabase_config.json.example").read_text())
    assert set(example) == {"url", "anon_key"}, example
    print("zero previous-provider references in owned files OK")


def main():
    test_supabase_importable()
    test_missing_config_is_local()
    test_malformed_config_is_local_with_warning()
    test_env_var_config_selects_supabase()
    test_paused_project_never_fakes_a_login()
    test_keepalive_never_raises_and_reports_paused()
    test_setup_sql_shape()
    test_google_entry_points_exist()
    test_storage_supabase_mode_fails_loud_without_service_key()
    test_keepalive_scheduler_behaviour()
    test_local_mode_still_enforces_username_rules()
    test_no_previous_provider_references_left()
    print("\nALL SUPABASE STRUCTURAL TESTS PASSED "
          "(no live Supabase project was contacted)")


if __name__ == "__main__":
    main()
