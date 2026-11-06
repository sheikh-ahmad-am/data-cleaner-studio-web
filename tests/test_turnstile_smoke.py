"""Turnstile smoke test (AppTest on a fresh code-only copy).

Proves the login-screen wiring end to end without a browser and
without real credentials:
  1. No TURNSTILE_SITE_KEY -> no widget call; login proceeds as before.
  2. Key set, widget returns no token -> Log in is stopped with
     "Complete the security check above first." and no auth call.
  3. Key set, widget returns a token -> the token reaches Supabase
     Auth (the mocked client records options.captcha_token) and the
     login works.
  4. Key set, Supabase rejects with a captcha error -> the clear
     "Security check failed" message, not a raw error and not a
     wrong-password error.
  5. Key set, sign-up with a token -> create_user gets the token;
     the follow-up auto-login reuses the spent token and, when
     Supabase rejects it, the account-created message still shows
     (no crash, no raw error).

The copy has no data/, no supabase_config.json and no secrets: the
Supabase client is a fake, the backend is forced to "supabase"
through auth's cache, and the widget is a stub. The real app code
(login screen, handlers, auth.py) runs unmodified.

Run:  .test-venv/bin/python tests/test_turnstile_smoke.py
       (from the project root)
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The copy must NOT include the live config, live data, or venvs.
IGNORE = shutil.ignore_patterns(
    "data", ".git", "__pycache__", ".test-venv-*", "*.pyc",
    "supabase_config.json", ".streamlit",
)


class _FakeResp:
    def __init__(self, user=None, session=None):
        self.user = user
        self.session = session


class _FakeUser:
    def __init__(self, uid, email):
        self.id = uid
        self.email = email
        self.identities = ["email"]
        self.email_confirmed_at = "2026-11-06T00:00:00Z"


class _FakeRpc:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeAuth:
    """Records the exact credentials dicts; optionally fails captcha."""

    def __init__(self, calls, fail_captcha=False, fail_second_signin=False):
        self.calls = calls
        self.fail_captcha = fail_captcha
        self.fail_second_signin = fail_second_signin
        self.signin_count = 0
        self.signup_done = False

    def sign_up(self, credentials):
        self.calls.append(("sign_up", credentials))
        if self.fail_captcha:
            raise Exception("captcha verification failed")
        self.signup_done = True
        return _FakeResp(user=_FakeUser("uuid-1", credentials["email"]),
                         session=object())

    def sign_in_with_password(self, credentials):
        self.calls.append(("sign_in", credentials))
        self.signin_count += 1
        if self.fail_captcha:
            raise Exception("captcha verification failed")
        # The auto-login after a sign-up reuses the spent token.
        if self.fail_second_signin and self.signup_done:
            raise Exception("captcha verification failed")
        return _FakeResp(user=_FakeUser("uuid-1", credentials["email"]),
                         session=object())

    def sign_in_with_oauth(self, credentials):
        return _FakeResp()  # no .url -> Google URL is None


class _FakeClient:
    def __init__(self, auth):
        self.auth = auth

    def rpc(self, fn, params):
        if fn == "app_upsert_profile":
            return _FakeRpc({"id": "uuid-1",
                             "email": params.get("p_email"),
                             "created_at": "2026-11-06T00:00:00Z"})
        if fn in ("app_get_user_by_id", "app_get_profile"):
            return _FakeRpc({"id": "uuid-1", "email": "alice@example.com",
                             "created_at": "2026-11-06T00:00:00Z"})
        if fn == "app_create_session":
            return _FakeRpc({})
        if fn == "app_validate_session":
            return _FakeRpc("uuid-1")
        return _FakeRpc(None)


def _fresh_copy():
    tmp = Path(tempfile.mkdtemp(prefix="dcs-turnstile-smoke-"))
    dst = tmp / "app"
    shutil.copytree(PROJECT_ROOT, dst, ignore=IGNORE)
    assert not (dst / "supabase_config.json").exists(), \
        "copy must not carry the live Supabase config"
    assert not (dst / "data").exists(), "copy must not carry live data"
    return tmp, dst


def _vals(elements):
    return [e.value for e in elements]


def _find_button(at, label):
    for b in at.button:
        if b.label == label:
            return b
    raise AssertionError(f"button {label!r} missing")


def _find_text_input(at, label):
    for t in at.text_input:
        if t.label == label:
            return t
    raise AssertionError(f"text input {label!r} missing")


def main():
    tmp, dst = _fresh_copy()
    sys.path.insert(0, str(dst))
    import streamlit as st  # noqa: E402
    import auth  # noqa: E402
    import scheduler  # noqa: E402
    import storage  # noqa: E402
    import turnstile_component  # noqa: E402
    from streamlit.testing.v1 import AppTest  # noqa: E402

    # Secrets must never provide the key in this test: the key comes
    # from the environment only, per case. (st.secrets is process-wide
    # in AppTest, so patch it once and restore at the end.)
    _real_secrets = st.secrets
    st.secrets = {}
    try:
        _run(tmp, dst, auth, scheduler, storage, turnstile_component,
             AppTest)
    finally:
        st.secrets = _real_secrets
        shutil.rmtree(tmp, ignore_errors=True)


def _setup(dst, auth, scheduler, storage, calls, fail_captcha=False,
           fail_second_signin=False):
    """Point the COPY's modules at temp state + the fake client."""
    tmp = Path(tempfile.mkdtemp(prefix="dcs-turnstile-state-"))
    auth.DB_PATH = tmp / "users.db"
    auth._BACKEND = "supabase"
    auth._BACKEND_WARNING = None
    # ONE shared fake auth object: _get_client() is called fresh for
    # every auth call, and the fake's state (e.g. "a sign-up already
    # happened") must survive across those calls.
    _fake_auth = _FakeAuth(calls, fail_captcha, fail_second_signin)
    auth._get_client = lambda: _FakeClient(_fake_auth)
    storage.BASE_DIR = tmp / "users"
    scheduler.DEFAULT_JOBS_FILE = tmp / "scheduler" / "jobs.json"
    return tmp


def _stub_widget(turnstile_component, calls, token):
    """Replace the widget with a stub that records calls."""

    def _stub(site_key, key="turnstile", reset=0):
        calls.append((site_key, key, reset))
        return token

    turnstile_component.turnstile_token = _stub


def _run(tmp, dst, auth, scheduler, storage, turnstile_component, AppTest):
    APP = str(dst / "app.py")

    # ---- 1. No key: no widget call, login proceeds as before. ----
    calls, widget_calls = [], []
    _setup(dst, auth, scheduler, storage, calls)
    _stub_widget(turnstile_component, widget_calls, "tok-123")
    os.environ.pop("TURNSTILE_SITE_KEY", None)
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    assert widget_calls == [], "widget must not render without a key"
    _find_text_input(at, "Email").set_value("alice@example.com").run()
    _find_text_input(at, "Password").set_value("password123").run()
    _find_button(at, "Log in").click().run()
    assert not at.exception, f"exception on login: {at.exception}"
    assert calls == [("sign_in", {"email": "alice@example.com",
                                  "password": "password123"})], \
        f"no-key login must send no options: {calls}"
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "login must reach the app"
    print("1. no key: widget hidden, login works, no token sent")

    # ---- 2. Key set, no token: submit is stopped, no auth call. ----
    calls, widget_calls = [], []
    _setup(dst, auth, scheduler, storage, calls)
    _stub_widget(turnstile_component, widget_calls, None)
    os.environ["TURNSTILE_SITE_KEY"] = "0xSITEKEY"
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    assert widget_calls, "widget must render when a key is set"
    assert widget_calls[0][0] == "0xSITEKEY"
    _find_text_input(at, "Email").set_value("alice@example.com").run()
    _find_text_input(at, "Password").set_value("password123").run()
    _find_button(at, "Log in").click().run()
    assert not at.exception, f"exception on blocked login: {at.exception}"
    assert any("Complete the security check above first." in v
               for v in _vals(at.error)), \
        "missing token must show the clear message"
    assert calls == [], f"blocked login must not call auth: {calls}"
    assert not any(b.label == "Try the messy sample" for b in at.button)
    print("2. key set, no token: login stopped with the clear message")

    # ---- 3. Key set, token present: token reaches Supabase, login ok. ----
    calls, widget_calls = [], []
    _setup(dst, auth, scheduler, storage, calls)
    _stub_widget(turnstile_component, widget_calls, "tok-123")
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception
    _find_text_input(at, "Email").set_value("alice@example.com").run()
    _find_text_input(at, "Password").set_value("password123").run()
    _find_button(at, "Log in").click().run()
    assert not at.exception, f"exception on login: {at.exception}"
    assert calls == [("sign_in", {
        "email": "alice@example.com", "password": "password123",
        "options": {"captcha_token": "tok-123"}})], f"calls: {calls}"
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "token login must reach the app"
    print("3. key set, token present: token reaches Supabase, login works")

    # ---- 4. Captcha rejected: clear message, no wrong-password error. ----
    calls, widget_calls = [], []
    _setup(dst, auth, scheduler, storage, calls, fail_captcha=True)
    _stub_widget(turnstile_component, widget_calls, "tok-bad")
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception
    _find_text_input(at, "Email").set_value("alice@example.com").run()
    _find_text_input(at, "Password").set_value("password123").run()
    _find_button(at, "Log in").click().run()
    assert not at.exception, f"exception on captcha failure: {at.exception}"
    assert any("Security check failed — please complete the check and "
               "try again." in v for v in _vals(at.error)), \
        f"captcha failure must show the clear message: {_vals(at.error)}"
    assert not any("Wrong email" in v for v in _vals(at.error)), \
        "captcha failure must not also claim a wrong password"
    assert not any("captcha verification failed" in v
                   for v in _vals(at.error)), "raw error must not leak"
    assert not any(b.label == "Try the messy sample" for b in at.button)
    print("4. captcha rejected: clear message only, no raw error")

    # ---- 5. Sign-up with a token: token sent; spent-token auto-login
    #      fails cleanly and the account-created message still shows. ----
    calls, widget_calls = [], []
    _setup(dst, auth, scheduler, storage, calls,
           fail_second_signin=True)
    _stub_widget(turnstile_component, widget_calls, "tok-456")
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception
    at.radio[0].set_value("Sign up").run()
    _find_text_input(at, "Email").set_value("alice@example.com").run()
    _find_text_input(at, "Password").set_value("password123").run()
    _find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    assert calls[0] == ("sign_up", {
        "email": "alice@example.com", "password": "password123",
        "options": {"captcha_token": "tok-456"}}), f"calls: {calls}"
    assert len(calls) == 2 and calls[1][0] == "sign_in", \
        "signup must attempt the auto-login with the same token"
    assert any("Account created — log in with your new account." in v
               for v in _vals(at.success)), \
        f"spent-token auto-login must end in the log-in message: " \
        f"{_vals(at.success)}"
    assert not any("captcha verification failed" in v
                   for v in _vals(at.error)), "raw error must not leak"
    print("5. signup: token sent; spent-token auto-login degrades cleanly")

    # ---- 6. The REAL component (not the stub) degrades gracefully
    #      in a headless run: declare_component resolves, no crash,
    #      and with no token yet the submit is still stopped. ----
    calls = []
    _setup(dst, auth, scheduler, storage, calls)
    # Restore the real wrapper (earlier cases replaced it with a stub).
    import importlib
    importlib.reload(turnstile_component)
    os.environ["TURNSTILE_SITE_KEY"] = "0xSITEKEY"
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"exception with real component: {at.exception}"
    _find_text_input(at, "Email").set_value("alice@example.com").run()
    _find_text_input(at, "Password").set_value("password123").run()
    _find_button(at, "Log in").click().run()
    assert not at.exception, f"exception on login: {at.exception}"
    assert any("Complete the security check above first." in v
               for v in _vals(at.error)), \
        "real component with no token must still stop the submit"
    assert calls == [], f"blocked login must not call auth: {calls}"
    print("6. real component: no crash headless, submit still gated")

    os.environ.pop("TURNSTILE_SITE_KEY", None)
    print("TURNSTILE SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
