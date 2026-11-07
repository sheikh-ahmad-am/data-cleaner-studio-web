"""Login-cookie tests for Data Cleaner Studio (item 16).

What is covered, with the cookie layer mocked (no real browser):
  1. Log in writes ONLY the random session token to a cookie
     (7-day expiry, Secure, SameSite=Lax — never a password).
  2. A simulated refresh (fresh AppTest = empty session state, cookie
     still present) restores the session without a login screen.
  3. An invalid/expired token in the cookie shows the login screen
     AND clears the cookie.
  4. Log out deletes the server session AND clears the cookie.
  5. NEW — the write must survive the post-login rerun: the cookie
     is issued in a run that completes normally, not in the login
     run that ends with an immediate st.rerun().
  6. NEW — the restore waits when the cookie layer has not
     answered yet on the first run after a refresh, instead of
     deciding "logged out" and showing the login screen.
  7. NEW — a cookie lost mid-session (blocked write, tab closed
     too fast) is re-issued while still logged in.

The mock is deliberately REALISTIC about browser timing, because
the bug this file guards was invisible to the old synchronous
mock: in a real browser a cookie write goes through a component
iframe, so a write issued in a run that ends with st.rerun() is
lost (the iframe is torn down before it mounts), while a write
issued in a run that completes normally lands. The fake models
that: set() only STAGES the write; it becomes visible to a fresh
session when the next script execution starts (the run's output
reached the browser) — unless a st.rerun() aborted the issuing
run, in which case the staged write is discarded. That is why the
test patches streamlit.rerun while it runs.

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
    import streamlit as st  # noqa: E402
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
    # REALISTIC timing (see the module docstring): set() stages the
    # write in `pending`; it only lands in `store` (visible to a
    # fresh session) when the next script execution starts — i.e.
    # the issuing run completed normally and its output reached the
    # browser. A run aborted by st.rerun() loses its staged writes:
    # the rerun hook below discards them.
    class RealisticFakeCookieController:
        """stand-in for streamlit_cookies_controller.CookieController."""
        store = {}
        pending = {}
        sets = []
        executions = 0
        delay_first_read = False

        def __init__(self, key="cookies"):
            cls = type(self)
            cls.executions += 1
            # A new execution: writes staged by an earlier execution
            # that completed normally have landed in the browser.
            cls.store.update(cls.pending)
            cls.pending.clear()
            if cls.delay_first_read and cls.executions == 1:
                # The component has not answered yet on the first
                # run after a refresh: no value registered, reads
                # return None until the next execution.
                return
            # Model the real component registering its value in
            # session state when it renders (the default on the
            # first run, the browser's cookies once it answers).
            try:
                st.session_state[key] = dict(cls.store)
            except Exception:  # noqa: BLE001 - no session state yet
                pass

        def _not_answered_yet(self):
            cls = type(self)
            return cls.delay_first_read and cls.executions == 1

        def get(self, name):
            if self._not_answered_yet():
                return None
            return type(self).store.get(name)

        def getAll(self):
            if self._not_answered_yet():
                return {}
            return dict(type(self).store)

        def set(self, name, value, **kwargs):
            type(self).sets.append((name, value, kwargs))
            # Staged only: lands in `store` at the next execution
            # (see __init__), never in the issuing run itself.
            type(self).pending[name] = value

        def remove(self, name, **kwargs):
            type(self).store.pop(name, None)
            type(self).pending.pop(name, None)

        def refresh(self):
            # In the fake a read already sees the committed store,
            # so a fresh browser read needs no action.
            return None

    streamlit_cookies_controller.CookieController = RealisticFakeCookieController

    # ---- Rerun hook: a rerun aborts its run, losing staged writes. ----
    _orig_rerun = st.rerun

    def _rerun_discarding_staged_writes(*args, **kwargs):
        RealisticFakeCookieController.pending.clear()
        return _orig_rerun(*args, **kwargs)

    st.rerun = _rerun_discarding_staged_writes

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

    def logged_in(at):
        return any(b.label == "Try the messy sample" for b in at.button)

    def login_screen(at):
        return any(b.label == "Log in" for b in at.button)

    try:
        # ---- 1. Fresh app: login screen, no cookie. ----
        at = AppTest.from_file(APP)
        at.run()
        assert not at.exception, f"startup exception: {at.exception}"
        assert login_screen(at) and not logged_in(at)
        assert COOKIE not in RealisticFakeCookieController.store
        print("1. fresh app: login screen, no cookie")

        # ---- 2. Sign up: auto-login writes the token to the cookie,
        # ----    and the write survives the post-login rerun. ----
        at.radio[0].set_value("Sign up").run()
        find_text_input(at, "Username").set_value("alice1").run()
        find_text_input(at, "Password").set_value("password123").run()
        find_button(at, "Create account").click().run()
        assert not at.exception, f"exception on signup: {at.exception}"
        # Signup logs the user straight in now (no separate Log in step).
        assert logged_in(at), "signup must log the user straight in"
        # The write is deferred past the login run (which ends with
        # an immediate st.rerun()): right after signup it has NOT
        # landed yet — it lands on the next run, which completes
        # normally. If the app wrote it in the login run, the rerun
        # hook above discarded it and this assertion fails.
        assert COOKIE not in RealisticFakeCookieController.store, \
            "the cookie must not be written in the rerun-aborted login run"
        assert RealisticFakeCookieController.sets, \
            "the login must stage a cookie write"
        at.run()
        assert not at.exception, f"exception on follow-up run: {at.exception}"
        assert logged_in(at), "the follow-up run must stay logged in"
        token = RealisticFakeCookieController.store.get(COOKIE)
        assert token, "login must write the session token to a cookie"
        assert token == at.session_state.get("auth_token"), \
            "cookie token must match the session token"
        assert auth.validate_session(token) is not None, \
            "cookie token must be a live server session"
        assert "password123" not in str(RealisticFakeCookieController.sets), \
            "a password must never be written to a cookie"
        _name, _value, kwargs = RealisticFakeCookieController.sets[-1]
        assert kwargs.get("max_age") == 7 * 24 * 3600, kwargs
        assert kwargs.get("secure") is True, kwargs
        assert kwargs.get("same_site") == "lax", kwargs
        print("2. signup auto-login writes the token cookie "
              "(7d, Secure, SameSite=Lax) past the post-login rerun")

        # ---- 3. Simulated refresh: new session state, cookie present. ----
        fresh = AppTest.from_file(APP)
        fresh.run()
        assert not fresh.exception, f"exception on refresh: {fresh.exception}"
        assert logged_in(fresh), "refresh with a live cookie must restore login"
        assert fresh.session_state.get("current_user", {}).get("username") == "alice1"
        print("3. refresh restores the session from the cookie")

        # ---- 4. A lost write is re-issued: delete the cookie mid-session
        # ----    (the browser blocked it, or the tab closed too fast)
        # ----    and the app writes it again on the next runs.
        assert RealisticFakeCookieController.store.get(COOKIE) == token, \
            "the cookie must be present before the re-issue test"
        sets_before = len(RealisticFakeCookieController.sets)
        RealisticFakeCookieController.store.pop(COOKIE, None)
        at.run()
        assert not at.exception, f"exception on re-issue run: {at.exception}"
        assert logged_in(at), "the re-issue run must stay logged in"
        at.run()
        assert not at.exception, f"exception on re-issue follow-up: {at.exception}"
        assert RealisticFakeCookieController.store.get(COOKIE) == token, \
            "a lost cookie must be re-issued while still logged in"
        assert len(RealisticFakeCookieController.sets) > sets_before, \
            "the re-issue must record a fresh cookie write"
        print("4. a lost cookie is re-issued while still logged in")

        # ---- 5. First-run delay: the restore WAITS instead of logging out.
        # ----    The cookie exists in the browser, but the component has
        # ----    not answered yet on the first run after a refresh. The
        # ----    app must show neither the login screen nor the main app
        # ----    on that run, and restore on the next run.
        RealisticFakeCookieController.delay_first_read = True
        RealisticFakeCookieController.executions = 0
        delayed = AppTest.from_file(APP)
        delayed.run()
        assert not delayed.exception, \
            f"exception on delayed first run: {delayed.exception}"
        assert not login_screen(delayed) and not logged_in(delayed), \
            "an unanswered cookie read must wait, not show the login screen"
        delayed.run()
        assert not delayed.exception, \
            f"exception on delayed second run: {delayed.exception}"
        assert logged_in(delayed), \
            "the next run must restore the session once the read answers"
        assert delayed.session_state.get("current_user", {}).get("username") == "alice1"
        RealisticFakeCookieController.delay_first_read = False
        print("5. first-run unanswered read waits, then restores")

        # ---- 6. Invalid token: login screen, cookie cleared. ----
        RealisticFakeCookieController.store[COOKIE] = "bogus-token"
        stale = AppTest.from_file(APP)
        stale.run()
        assert not stale.exception, f"exception on stale cookie: {stale.exception}"
        assert login_screen(stale) and not logged_in(stale), \
            "a dead cookie must show the login screen"
        assert COOKIE not in RealisticFakeCookieController.store, \
            "a dead cookie must be cleared"
        print("6. invalid token: login shown, cookie cleared")

        # ---- 7. Log out: server session deleted AND cookie cleared. ----
        RealisticFakeCookieController.store[COOKIE] = token
        again = AppTest.from_file(APP)
        again.run()
        assert not again.exception, f"exception on re-restore: {again.exception}"
        assert logged_in(again), "re-restore must log in before logout test"
        find_button(again, "Log out", key="avatar_logout_btn").click().run()
        assert not again.exception, f"exception on logout: {again.exception}"
        assert login_screen(again) and not logged_in(again), \
            "logout must return to the login screen"
        assert COOKIE not in RealisticFakeCookieController.store, \
            "logout must clear the cookie"
        assert auth.validate_session(token) is None, \
            "logout must delete the server session"
        print("7. logout deletes the server session and clears the cookie")
    finally:
        st.rerun = _orig_rerun

    print("ALL COOKIE TESTS PASSED")


if __name__ == "__main__":
    main()
