"""Wave-3 fixes (items 17-25 + overlap extras) — AppTest + unit checks.

Run from the project root, script mode (like the web smoke test):
    .test-venv-wave3/bin/python tests/test_wave3.py
or under pytest:
    .test-venv-wave3/bin/python -m pytest tests/test_wave3.py -q

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler jobs
file are pointed at a fresh temp dir per test, so the real data/
folder is untouched. Local mode only, except the #26 email-confirmation
tests, which force the Supabase backend with a mocked client (canned
sign_up / sign_in answers) — no live Supabase project, no network
calls, no test accounts in the live project.
"""

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TESTS_DIR))

import os
from types import SimpleNamespace

import auth  # noqa: E402
import engine  # noqa: E402
import feat_enrich  # noqa: E402
import feat_share  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"
LIVE_URL = "https://data-c-ak7dfcpvbzklkfn8gozels.streamlit.app"


def _fresh_backend():
    """Point all server-side state at a fresh temp dir. Returns the dir.

    Also repoints the Supabase config path at a nonexistent temp file
    and clears Supabase env vars, so the backend is deterministically
    'local' no matter what credential files exist in the project folder
    (same pattern as tests/test_auth_storage.py)."""
    tmp = Path(tempfile.mkdtemp(prefix="dcs-wave3-"))
    auth.DB_PATH = tmp / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp / "scheduler" / "jobs.json"
    auth.SUPABASE_CONFIG_PATH = tmp / "no-supabase_config.json"
    for _k in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
        os.environ.pop(_k, None)
    auth._reset_backend_cache()
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    return tmp


def _all_text(at):
    """Every user-visible string in the run (markdown — which is
    also where st.write text lands — captions, code and alerts)."""
    out = []
    for coll in (at.markdown, at.caption, at.info, at.success, at.warning,
                 at.error, at.code):
        try:
            out.extend(str(e.value) for e in coll)
        except Exception:  # noqa: BLE001 - a missing collection is not fatal
            pass
    return out


def _find_button(at, label):
    for b in at.button:
        if b.label == label:
            return b
    raise AssertionError(f"button {label!r} missing; have "
                         f"{[b.label for b in at.button]}")


def _find_text_input(at, label):
    for t in at.text_input:
        if t.label == label:
            return t
    raise AssertionError(f"text input {label!r} missing")


def _find_selectbox(at, label):
    for s in at.selectbox:
        if s.label == label:
            return s
    raise AssertionError(f"selectbox {label!r} missing")


def _goto_section(at, label):
    """Pick a section in the sticky section switcher (radio 'Section')."""
    radio = next((r for r in at.radio if r.label == "Section"), None)
    assert radio is not None, "Section switcher missing"
    assert label in list(radio.options), \
        f"section {label!r} not offered; have {list(radio.options)}"
    radio.set_value(label).run()
    assert not at.exception, f"exception going to {label}: {at.exception}"
    assert radio.value == label, "section switcher did not stick"
    return at


def _signup_and_login(at, username="alice1", password="password123"):
    """Sign up (auto-login now) and assert the app opens straight away."""
    _find_text_input(at, "Username").set_value(username).run()
    _find_text_input(at, "Password").set_value(password).run()
    at.radio[0].set_value("Sign up").run()
    _find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "signup must log the user straight in (no manual login step)"
    assert at.session_state.get("current_user", {}).get("username") == username
    return at


def _login(at, username="alice1", password="password123"):
    _find_text_input(at, "Username").set_value(username).run()
    _find_text_input(at, "Password").set_value(password).run()
    _find_button(at, "Log in").click().run()
    assert not at.exception, f"exception on login: {at.exception}"
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "login should open the app"
    return at


def _load_sample(at):
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([("messy_sales.csv", SAMPLE.read_bytes(), "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert at.session_state["raw"] is not None, "raw data not loaded"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    return at


def _clean_sample(at):
    _goto_section(at, "Clean")
    _find_button(at, "Clean my data").click().run()
    assert not at.exception, f"exception after cleaning: {at.exception}"
    clean = at.session_state["clean"]
    assert clean is not None and len(clean) == 77, \
        "cleaned data should have 77 rows"
    return at


def _force_supabase_backend(tmp):
    """Point auth at a fake Supabase config (no live project) and
    return a restore function. Backend becomes 'supabase'."""
    import json

    cfg = tmp / "supabase_config.json"
    cfg.write_text(json.dumps(
        {"url": "https://example.supabase.co", "anon_key": "test-key"}))
    old_cfg = auth.SUPABASE_CONFIG_PATH
    old_env = {k: os.environ.pop(k, None)
               for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY")}
    old_client_fn = auth._get_client
    auth.SUPABASE_CONFIG_PATH = cfg
    auth._reset_backend_cache()
    storage._reset_storage_cache()
    assert auth.get_auth_backend() == "supabase", \
        "test must run in supabase mode"

    def _restore():
        auth._get_client = old_client_fn
        auth.SUPABASE_CONFIG_PATH = old_cfg
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        auth._reset_backend_cache()
        storage._reset_storage_cache()

    return _restore


class _FakeRpcResp:
    """Stand-in for a supabase-py RPC response (.data + .execute())."""

    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeSbAuth:
    """Stand-in for client.auth: canned sign_up / sign_in answers."""

    def __init__(self, signup_resp=None, signin_exc=None, signin_resp=None):
        self.signup_resp = signup_resp
        self.signin_exc = signin_exc
        self.signin_resp = signin_resp

    def sign_up(self, creds):
        return self.signup_resp

    def sign_in_with_password(self, creds):
        if self.signin_exc is not None:
            raise self.signin_exc
        return self.signin_resp


class _FakeSbClient:
    """Stand-in for the supabase-py client (auth + rpc only)."""

    def __init__(self, fake_auth):
        self.auth = fake_auth

    def rpc(self, function, params):
        # Profile upsert / health check: a usable profile row.
        return _FakeRpcResp({"id": "uuid-1", "email": "alice@example.com",
                             "created_at": "2026-11-06T00:00:00"})


def _fake_signup_resp(confirmed):
    """A supabase-py sign_up answer. Unconfirmed: no session and
    email_confirmed_at unset (what 'Confirm email' ON returns);
    confirmed: a session and a confirmed email."""
    user = SimpleNamespace(
        id="uuid-1",
        identities=[{"id": "identity-1"}],
        email_confirmed_at=("2026-11-06T00:00:00" if confirmed else None))
    session = SimpleNamespace(access_token="tok") if confirmed else None
    return SimpleNamespace(user=user, session=session)


# ------------------------------------------------------------------ unit
def test_enrich_dark_green_button_text():
    theme = feat_enrich.THEMES["Dark green"]
    assert theme["button_text"] == "#FFFFFF", theme
    css = feat_enrich.theme_css("Dark green")
    assert "#2F5D5A" in css and "#FFFFFF" in css
    print("enrich one-liner OK: Dark green button text #FFFFFF on #2F5D5A")


def test_backup_double_render_no_crash():
    """#17: render_backups twice in ONE run (Clean + Tools tabs) after
    a backup exists must not raise StreamlitDuplicateElementKey.
    The same call twice with one shared prefix DOES raise — that is
    the crash the key namespace fixes."""
    import textwrap

    tmp = _fresh_backend()
    raw = engine.load_file("messy_sales.csv", SAMPLE.read_bytes())
    mini = tmp / "mini_backups.py"
    mini.write_text(textwrap.dedent(f"""\
        import sys
        sys.path.insert(0, r"{PROJECT_ROOT}")
        import streamlit as st
        import feat_share, engine
        from pathlib import Path
        raw = engine.load_file("messy_sales.csv",
                               Path(r"{SAMPLE}").read_bytes())
        feat_share.backup_raw(raw, "messy_sales.csv", r"{tmp}")
        feat_share.render_backups(st, df=raw, source_name="messy_sales.csv",
                                  base_dir=r"{tmp}",
                                  key_prefix="s_backup_clean")
        feat_share.render_backups(st, base_dir=r"{tmp}",
                                  key_prefix="s_backup_tools")
        """), encoding="utf-8")
    at = AppTest.from_file(str(mini))
    at.run()
    assert not at.exception, f"double render crashed: {at.exception}"
    assert len([b for b in at.button if b.label == "Restore"]) == 2, \
        "both backup lists must render their own Restore button"
    # Negative control: the same prefix twice still collides.
    mini2 = tmp / "mini_backups_clash.py"
    mini2.write_text(textwrap.dedent(f"""\
        import sys
        sys.path.insert(0, r"{PROJECT_ROOT}")
        import streamlit as st
        import feat_share, engine
        from pathlib import Path
        raw = engine.load_file("messy_sales.csv",
                               Path(r"{SAMPLE}").read_bytes())
        feat_share.render_backups(st, df=raw, source_name="messy_sales.csv",
                                  base_dir=r"{tmp}")
        feat_share.render_backups(st, base_dir=r"{tmp}")
        """), encoding="utf-8")
    clash = AppTest.from_file(str(mini2))
    clash.run()
    assert len(clash.exception) > 0, \
        "same-prefix double render should still raise (negative control)"
    assert "same `key=" in str(clash.exception[0].message), clash.exception
    print("backup double-render OK: distinct prefixes render clean, "
          "shared prefix still collides (the fixed crash)")


def test_one_click_uses_spinner():
    """#25e: 'Run everything' shows progress feedback while it works."""
    import test_feat_share as tfs

    raw, clean, actions, kpis = tfs._sample_clean()
    with tempfile.TemporaryDirectory() as tmp:
        st = tfs.FakeSt(values={"s_oneclick_run": True})
        st.session_state["source_name"] = "messy_sales.csv"
        status = feat_share.render_one_click(st, raw, None, base_dir=tmp)
        assert status["status"] == "done", status
        assert any(c[0] == "spinner" for c in st.calls), \
            "one-click must show a spinner while it runs"
        assert "running everything" in " ".join(
            str(c[1]) for c in st.calls if c[0] == "spinner").lower()
    print("one-click spinner OK")


def test_signup_unconfirmed_marker():
    """#26 (auth): with 'Confirm email' ON, sign_up answers with no
    session and email_confirmed_at unset — create_user must return
    (True, SIGNUP_NEEDS_CONFIRMATION), not a plain (True, None)."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        restore = _force_supabase_backend(Path(td))
        try:
            auth._get_client = lambda: _FakeSbClient(
                _FakeSbAuth(signup_resp=_fake_signup_resp(confirmed=False)))
            ok, err = auth.create_user("alice@example.com", "password123")
            assert ok is True, err
            assert err == auth.SIGNUP_NEEDS_CONFIRMATION, err
        finally:
            restore()
    print("signup unconfirmed OK: (True, SIGNUP_NEEDS_CONFIRMATION)")


def test_signup_confirmed_no_marker():
    """#26 (auth): with confirmation OFF, sign_up comes back with a
    session and a confirmed email — create_user returns (True, None),
    the auto-login path."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        restore = _force_supabase_backend(Path(td))
        try:
            auth._get_client = lambda: _FakeSbClient(
                _FakeSbAuth(signup_resp=_fake_signup_resp(confirmed=True)))
            ok, err = auth.create_user("alice@example.com", "password123")
            assert (ok, err) == (True, None), (ok, err)
        finally:
            restore()
    print("signup confirmed OK: (True, None)")


def test_authenticate_unconfirmed_raises_distinct():
    """#26 (auth): 'Email not confirmed' on sign-in raises the distinct
    EmailNotConfirmedError (an AuthServiceError subclass) — never a
    silent None that the app would read as a wrong password."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        restore = _force_supabase_backend(Path(td))
        try:
            assert issubclass(auth.EmailNotConfirmedError,
                              auth.AuthServiceError)
            auth._get_client = lambda: _FakeSbClient(
                _FakeSbAuth(signin_exc=Exception("Email not confirmed")))
            try:
                auth.authenticate("alice@example.com", "password123")
            except auth.EmailNotConfirmedError as exc:
                assert "inbox" in str(exc).lower(), str(exc)
            else:
                raise AssertionError(
                    "unconfirmed sign-in must raise, not return None")
        finally:
            restore()
    print("unconfirmed sign-in OK: EmailNotConfirmedError (AuthServiceError)")


def test_authenticate_wrong_password_still_none():
    """#26 (auth): a genuinely wrong password still returns None —
    the unconfirmed path must not swallow it into an inbox message."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        restore = _force_supabase_backend(Path(td))
        try:
            auth._get_client = lambda: _FakeSbClient(
                _FakeSbAuth(
                    signin_exc=Exception("Invalid login credentials")))
            assert auth.authenticate("alice@example.com",
                                     "wrongpassword") is None
        finally:
            restore()
    print("wrong password OK: still None (not the inbox message)")


# ------------------------------------------------------------------ app
def test_signup_auto_login():
    """#18: creating an account logs the user straight in."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    assert any("Account created" in v for v in _all_text(at)), \
        "welcome note must confirm the account was created"
    print("signup auto-login OK: in the app right after Create account")


def test_signup_unconfirmed_no_autologin_no_cookie():
    """#26 (app): with 'Confirm email' ON, signup shows the inbox
    message, does NOT log the user in and writes NO session cookie;
    a login attempt then shows the inbox error, not wrong-password."""
    import streamlit_cookies_controller

    tmp = _fresh_backend()
    restore = _force_supabase_backend(tmp)
    orig_controller = streamlit_cookies_controller.CookieController

    class _RecordingCookies:
        """Cookie layer stand-in that records every write."""
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

    streamlit_cookies_controller.CookieController = _RecordingCookies
    try:
        auth._get_client = lambda: _FakeSbClient(
            _FakeSbAuth(
                signup_resp=_fake_signup_resp(confirmed=False),
                signin_exc=Exception("Email not confirmed")))
        at = AppTest.from_file(APP)
        at.run()
        assert not at.exception, f"startup exception: {at.exception}"
        assert any(b.label == "Log in" for b in at.button), \
            "supabase mode must still show the login screen"
        _find_text_input(at, "Email").set_value("alice@example.com").run()
        _find_text_input(at, "Password").set_value("password123").run()
        at.radio[0].set_value("Sign up").run()
        _find_button(at, "Create account").click().run()
        assert not at.exception, f"exception on signup: {at.exception}"
        assert any("check your inbox" in v.lower()
                   and "verification link" in v.lower()
                   for v in _all_text(at)), \
            "unconfirmed signup must tell the user to check their inbox"
        assert not any(b.label == "Try the messy sample" for b in at.button), \
            "unconfirmed signup must NOT log the user in"
        assert at.session_state.get("auth_token") is None, \
            "no session may be created for an unconfirmed user"
        assert _RecordingCookies.sets == [], \
            f"no session cookie may be written: {_RecordingCookies.sets}"
        # Now try to log in with the unconfirmed email.
        at.radio[0].set_value("Log in").run()
        _find_button(at, "Log in").click().run()
        assert not at.exception, f"exception on login: {at.exception}"
        assert any("Check your inbox" in v
                   and "verification link" in v for v in _all_text(at)), \
            "unconfirmed login must show the inbox message"
        assert not any("Wrong email/username or password" in v
                       for v in _all_text(at)), \
            "unconfirmed login must NOT show the wrong-password error"
        assert not any(b.label == "Try the messy sample" for b in at.button), \
            "unconfirmed login must stay on the login screen"
        assert at.session_state.get("auth_token") is None
        assert _RecordingCookies.sets == [], \
            "no session cookie may be written on a failed login either"
    finally:
        streamlit_cookies_controller.CookieController = orig_controller
        restore()
    print("unconfirmed signup/login OK: inbox message, no login, no cookie")


def test_tab_persists_across_reruns():
    """#19: the section stays put after an action that reruns the app."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _goto_section(at, "Settings")
    _find_button(at, "Save API keys").click().run()
    assert not at.exception, f"exception after save: {at.exception}"
    radio = next(r for r in at.radio if r.label == "Section")
    assert radio.value == "Settings", \
        f"tab reset to {radio.value!r} after the rerun"
    print("tab persistence OK: still on Settings after a rerun")


def test_backup_flow_no_crash_no_path_leak():
    """#17 + #20: back up, switch tabs, come back — no crash, and the
    backup message shows only the file name, never a server path."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _goto_section(at, "Clean")
    _find_button(at, "Back up the raw data now").click().run()
    assert not at.exception, f"exception after backup: {at.exception}"
    backed = [v for v in _all_text(at) if v.startswith("Backed up")]
    assert backed, "backup confirmation missing"
    assert all("/" not in v and "mount" not in v and "data/users" not in v
               for v in backed), f"server path leaked: {backed}"
    _goto_section(at, "Tools")
    assert not at.exception, f"exception on Tools tab: {at.exception}"
    assert any(b.label == "Restore" for b in at.button), \
        "Tools tab must list the backup with a Restore button"
    _goto_section(at, "Clean")
    assert not at.exception, f"exception back on Clean tab: {at.exception}"
    print("backup flow OK: no crash across tabs, file name only, no path")


def test_sheets_empty_link_validation():
    """#21b: 'Load sheet' with an empty link must say what is missing."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _find_button(at, "Load sheet").click().run()
    assert not at.exception, f"exception on empty sheet load: {at.exception}"
    assert any("Paste a Google Sheets link first" in v for v in _all_text(at)), \
        "empty sheet link must show a validation error"
    print("sheets validation OK: empty link shows an error")


def test_tutorial_got_it_visible():
    """#21c: the tutorial 'Got it' button always answers visibly."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _goto_section(at, "How to use")
    _find_button(at, "Got it — I know how this works").click().run()
    assert not at.exception, f"exception on tutorial Got it: {at.exception}"
    assert any("Got it" in v and "will not pop up" in v
               for v in _all_text(at)), "tutorial Got it must confirm"
    at.run()
    assert not at.exception
    assert (any("Got it" in v and "will not pop up" in v
                for v in _all_text(at))
            or any("already seen this guide" in v for v in _all_text(at))), \
        "confirmation (or the already-seen note) must survive the rerun"
    print("tutorial Got it OK: confirms, and the note survives a rerun")


def test_scheduled_job_empty_source():
    """#21a: 'Add scheduled job' with an empty Source must show an error."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _goto_section(at, "Settings")
    _find_button(at, "Add scheduled job").click().run()
    assert not at.exception, f"exception on empty job add: {at.exception}"
    assert any("Fill in the source and the target file first" in v
               for v in _all_text(at)), \
        "empty scheduled-job source must show a validation error"
    print("scheduled-job validation OK: empty source shows an error")


def test_schedule_notice_once_and_setup_disabled():
    """#22: the non-Windows notice appears exactly once, and 'Set up
    auto-clean' is disabled instead of stacking another copy."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _goto_section(at, "Tools")
    assert not at.exception, f"exception on Tools tab: {at.exception}"
    notices = [v for v in _all_text(at) if "not Windows" in v]
    assert len(notices) == 1, f"notice must appear once, got {notices}"
    setup = _find_button(at, "Set up auto-clean")
    assert getattr(setup, "disabled", False) is True, \
        "Set up auto-clean must be disabled off Windows"
    try:
        setup.click()
    except Exception:  # noqa: BLE001 - AppTest refuses disabled clicks
        pass  # AppTest refuses clicks on disabled widgets, as expected
    else:
        raise AssertionError("clicking a disabled Setup button must fail")
    print("schedule notice OK: shown once, Setup disabled off Windows")


def test_share_link_real_url():
    """#23: the share link shows the real deployed URL, not a placeholder."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _clean_sample(at)
    _goto_section(at, "Dashboard")
    _find_button(at, "Share dashboard").click().run()
    assert not at.exception, f"exception on share: {at.exception}"
    assert at.session_state.get("last_share_token"), "share token missing"
    full = [v for v in _all_text(at)
            if v.startswith(LIVE_URL) and "?share=" in v]
    assert full, f"full share link with the real URL missing: {_all_text(at)}"
    assert not any("<your-app>" in v for v in _all_text(at)), \
        "the <your-app> placeholder must be gone"
    print("share link OK: real deployed URL in the full link")


def test_reopen_restores_cleaned_state():
    """#24: reopening a saved file after logout/login restores the
    cleaned data and KPIs, not just the raw file."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _clean_sample(at)
    _find_button(at, "Log out").click().run()
    assert not at.exception, f"exception on logout: {at.exception}"
    _login(at)
    assert at.session_state.get("clean") is None, \
        "logout must clear the cleaned data from the session"
    pick = _find_selectbox(at, "Open a saved upload")
    pick.set_value("messy_sales.csv").run()
    _find_button(at, "Open").click().run()
    assert not at.exception, f"exception on reopen: {at.exception}"
    assert at.session_state.get("clean") is not None, \
        "reopen must restore the cleaned data"
    assert len(at.session_state["clean"]) == 77, \
        "restored cleaned data should have 77 rows"
    assert at.session_state.get("kpis"), "restored KPIs missing"
    assert any("cleaned data restored too" in v for v in _all_text(at)), \
        "reopen must say the cleaned data came back too"
    print("reopen OK: cleaned data (77 rows) + KPIs restored after relogin")


def test_saved_files_buttons_disabled_until_pick():
    """#25a: Open/Delete under 'Your saved files' stay disabled until
    a file is picked."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    open_btn = _find_button(at, "Open")
    delete_btn = _find_button(at, "Delete")
    assert getattr(open_btn, "disabled", False) is True, \
        "Open must be disabled with nothing selected"
    assert getattr(delete_btn, "disabled", False) is True, \
        "Delete must be disabled with nothing selected"
    pick = _find_selectbox(at, "Open a saved upload")
    pick.set_value("messy_sales.csv").run()
    assert getattr(_find_button(at, "Open"), "disabled", False) is False, \
        "Open must enable once a file is picked"
    assert getattr(_find_button(at, "Delete"), "disabled", False) is False, \
        "Delete must enable once a file is picked"
    print("saved-files buttons OK: disabled until a file is picked")


def test_keep_copy_pref_persists_across_login():
    """#25b: 'Keep a copy for quick reopen' stays ticked after
    logout/login (per-user storage, not just the session)."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    keep = next(c for c in at.checkbox
                if c.label == "Keep a copy for quick reopen")
    keep.check().run()
    assert not at.exception
    _find_button(at, "Log out").click().run()
    assert not at.exception
    # A FRESH AppTest instance: new session state, same stored backend.
    at2 = AppTest.from_file(APP)
    at2.run()
    _login(at2)
    _load_sample(at2)
    keep2 = next(c for c in at2.checkbox
                 if c.label == "Keep a copy for quick reopen")
    assert keep2.value is True, \
        "keep-a-copy must still be ticked after logout/login"
    print("keep-copy pref OK: still ticked in a fresh session after relogin")


def test_settings_no_internal_paths():
    """#25d: Settings shows plain words, no internal filenames/paths."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _goto_section(at, "Settings")
    text = _all_text(at)
    assert not any("supabase_config.json" in v for v in text), \
        "Settings must not show the internal config filename"
    assert not any("supabase_setup.sql" in v for v in text), \
        "Settings must not show the internal setup filename"
    assert any("Cloud setup:" in v for v in text), \
        "Settings must still show the cloud status in plain words"
    print("settings wording OK: plain-word cloud status, no filenames")


def test_save_view_appears_once():
    """Overlap (ii): 'Save this view' appears exactly once."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _clean_sample(at)
    _goto_section(at, "Dashboard")
    saves = [b for b in at.button if b.label == "Save this view"]
    assert len(saves) == 1, f"'Save this view' must appear once, got {len(saves)}"
    print("save-a-view OK: exactly one instance (Dashboard)")


def test_whats_new_per_user():
    """Overlap (iii): dismissing What's-new hides it for that user
    only — a second user still sees it."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at, "alice1")
    _load_sample(at)
    assert any("What's new" in v for v in _all_text(at)), \
        "fresh user must see What's-new"
    _find_button(at, "Got it — don't show this again").click().run()
    assert not at.exception
    at.run()
    assert not any("What's new" in v for v in _all_text(at)), \
        "dismissed What's-new must stay gone for alice"
    ok, err = auth.create_user("bob1", "password123")
    assert ok, f"could not create bob: {err}"
    bob = AppTest.from_file(APP)
    bob.run()
    _login(bob, "bob1")
    _load_sample(bob)
    assert any("What's new" in v for v in _all_text(bob)), \
        "bob must still see What's-new after alice dismissed it"
    print("whats-new per-user OK: alice dismissed, bob still sees it")


def test_google_button_hidden_by_default():
    """Overlap (iv): no 'Continue with Google' button unless the
    GOOGLE_OAUTH_ENABLED flag is on (it is off by default)."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception
    labels = [b.label for b in at.button]
    link_labels = [b.label for b in at.link_button]
    assert "Continue with Google" not in labels + link_labels, \
        "Google button must stay hidden by default"
    print("google button OK: still hidden by default")


def test_no_status_embed_iframe():
    """#25c: nothing in the app renders a 'Status embed' iframe or
    any iframe placeholder text."""
    _fresh_backend()
    at = AppTest.from_file(APP)
    at.run()
    _signup_and_login(at)
    _load_sample(at)
    _clean_sample(at)
    text = " ".join(_all_text(at))
    assert "Status embed" not in text, "status-embed placeholder text found"
    assert "iframe" not in text.lower(), "iframe text found in the app"
    print("status embed OK: no iframe / placeholder text rendered")


def main():
    test_enrich_dark_green_button_text()
    test_backup_double_render_no_crash()
    test_one_click_uses_spinner()
    test_signup_unconfirmed_marker()
    test_signup_confirmed_no_marker()
    test_authenticate_unconfirmed_raises_distinct()
    test_authenticate_wrong_password_still_none()
    test_signup_auto_login()
    test_signup_unconfirmed_no_autologin_no_cookie()
    test_tab_persists_across_reruns()
    test_backup_flow_no_crash_no_path_leak()
    test_sheets_empty_link_validation()
    test_tutorial_got_it_visible()
    test_scheduled_job_empty_source()
    test_schedule_notice_once_and_setup_disabled()
    test_share_link_real_url()
    test_reopen_restores_cleaned_state()
    test_saved_files_buttons_disabled_until_pick()
    test_keep_copy_pref_persists_across_login()
    test_settings_no_internal_paths()
    test_save_view_appears_once()
    test_whats_new_per_user()
    test_google_button_hidden_by_default()
    test_no_status_embed_iframe()
    print("ALL WAVE-3 TESTS PASSED")


if __name__ == "__main__":
    main()
