"""Login-cookie tests for Data Cleaner Studio (item 16).

What is covered, with the cookie layer mocked (no real browser):
  1. Log in writes ONLY the random session token to a cookie
     (7-day expiry, Secure, SameSite=Lax — never a password).
  2. A simulated refresh (fresh AppTest = empty session state, cookie
     still present) restores the session without a login screen.
  3. An invalid/expired token in the cookie shows the login screen
     AND clears the cookie.
  4. Log out deletes the server session AND clears the cookie.

Self-contained + safe: when run from the repo root this script first
copies the code (*.py only — no supabase_config.json, no data/) to a
temp dir and re-runs itself there, so the app under test always runs
in LOCAL mode and never touches the live Supabase project. The auth
DB, storage and scheduler state all point at a temp dir, like
test_web_smoke.py.

Run:  .test-venv-wave2/bin/python tests/test_auth_cookie.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _copy_code_only(dest: Path) -> None:
    """Copy the app's *.py files (no config, no data/) to dest."""
    dest.mkdir(parents=True, exist_ok=True)
    for py in PROJECT_ROOT.glob("*.py"):
        shutil.copy2(py, dest / py.name)
    # The Turnstile widget is a package, not a top-level .py file:
    # app.py imports it, so the copy needs it too.
    shutil.copytree(PROJECT_ROOT / "turnstile_component",
                    dest / "turnstile_component")
    tests_dir = dest / "tests"
    tests_dir.mkdir(exist_ok=True)
    shutil.copy2(Path(__file__).resolve(), tests_dir / "test_auth_cookie.py")


def main() -> None:
    # Re-exec inside a code-only copy when the repo config is present.
    if (PROJECT_ROOT / "supabase_config.json").exists():
        tmp = Path(tempfile.mkdtemp(prefix="dcs-cookie-test-"))
        copy_dir = tmp / "code"
        _copy_code_only(copy_dir)
        proc = subprocess.run(
            [sys.executable, str(copy_dir / "tests" / "test_auth_cookie.py")],
            cwd=str(copy_dir))
        raise SystemExit(proc.returncode)

    _run_flow()


# ---------------------------------------------------------------------------
# The flow below runs ONLY inside the code-only copy (no config present).
# ---------------------------------------------------------------------------

def _run_flow() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    import auth  # noqa: E402
    import scheduler  # noqa: E402
    import storage  # noqa: E402
    import streamlit_cookies_controller  # noqa: E402
    from streamlit.testing.v1 import AppTest  # noqa: E402

    APP = str(PROJECT_ROOT / "app.py")
    COOKIE = "dcs_auth_token"

    tmp = Path(tempfile.mkdtemp(prefix="dcs-cookie-test-"))
    auth.DB_PATH = tmp / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp / "users"
    scheduler.DEFAULT_JOBS_FILE = tmp / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"

    # ---- Mock cookie layer: a dict standing in for the browser. ----
    class FakeCookieController:
        """stand-in for streamlit_cookies_controller.CookieController."""
        store = {}
        sets = []

        def __init__(self, key="cookies"):
            pass

        def get(self, name):
            return type(self).store.get(name)

        def set(self, name, value, **kwargs):
            type(self).store[name] = value
            type(self).sets.append((name, value, kwargs))

        def remove(self, name, **kwargs):
            type(self).store.pop(name, None)

    streamlit_cookies_controller.CookieController = FakeCookieController

    def find_button(at, label):
        for b in at.button:
            if b.label == label:
                return b
        raise AssertionError(f"button {label!r} missing")

    def find_text_input(at, label):
        for t in at.text_input:
            if t.label == label:
                return t
        raise AssertionError(f"text input {label!r} missing")

    def logged_in(at):
        return any(b.label == "Try the messy sample" for b in at.button)

    def login_screen(at):
        return any(b.label == "Log in" for b in at.button)

    # ---- 1. Fresh app: login screen, no cookie. ----
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    assert login_screen(at) and not logged_in(at)
    assert COOKIE not in FakeCookieController.store
    print("1. fresh app: login screen, no cookie")

    # ---- 2. Sign up: auto-login writes the token to the cookie. ----
    at.radio[0].set_value("Sign up").run()
    find_text_input(at, "Username").set_value("alice1").run()
    find_text_input(at, "Password").set_value("password123").run()
    find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    # Signup logs the user straight in now (no separate Log in step).
    assert logged_in(at), "signup must log the user straight in"
    token = FakeCookieController.store.get(COOKIE)
    assert token, "login must write the session token to a cookie"
    assert token == at.session_state.get("auth_token"), \
        "cookie token must match the session token"
    assert auth.validate_session(token) is not None, \
        "cookie token must be a live server session"
    assert "password123" not in str(FakeCookieController.sets), \
        "a password must never be written to a cookie"
    _name, _value, kwargs = FakeCookieController.sets[-1]
    assert kwargs.get("max_age") == 7 * 24 * 3600, kwargs
    assert kwargs.get("secure") is True, kwargs
    assert kwargs.get("same_site") == "lax", kwargs
    print("2. signup auto-login writes the token cookie "
          "(7d, Secure, SameSite=Lax)")

    # ---- 3. Simulated refresh: new session state, cookie present. ----
    fresh = AppTest.from_file(APP)
    fresh.run()
    assert not fresh.exception, f"exception on refresh: {fresh.exception}"
    assert logged_in(fresh), "refresh with a live cookie must restore login"
    assert fresh.session_state.get("current_user", {}).get("username") == "alice1"
    print("3. refresh restores the session from the cookie")

    # ---- 4. Invalid token: login screen, cookie cleared. ----
    FakeCookieController.store[COOKIE] = "bogus-token"
    stale = AppTest.from_file(APP)
    stale.run()
    assert not stale.exception, f"exception on stale cookie: {stale.exception}"
    assert login_screen(stale) and not logged_in(stale), \
        "a dead cookie must show the login screen"
    assert COOKIE not in FakeCookieController.store, \
        "a dead cookie must be cleared"
    print("4. invalid token: login shown, cookie cleared")

    # ---- 5. Log out: server session deleted AND cookie cleared. ----
    FakeCookieController.store[COOKIE] = token
    again = AppTest.from_file(APP)
    again.run()
    assert not again.exception, f"exception on re-restore: {again.exception}"
    assert logged_in(again), "re-restore must log in before logout test"
    find_button(again, "Log out").click().run()
    assert not again.exception, f"exception on logout: {again.exception}"
    assert login_screen(again) and not logged_in(again), \
        "logout must return to the login screen"
    assert COOKIE not in FakeCookieController.store, \
        "logout must clear the cookie"
    assert auth.validate_session(token) is None, \
        "logout must delete the server session"
    print("5. logout deletes the server session and clears the cookie")

    print("ALL COOKIE TESTS PASSED")


if __name__ == "__main__":
    main()
