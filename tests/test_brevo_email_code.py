"""Brevo 6-digit email login code — unit + AppTest checks.

Replaces the old Cloudflare Turnstile check: every password login
(and every sign-up) now asks for a 6-digit code sent via Brevo, the
code is checked AFTER the password passes and BEFORE any session is
created, and Google OAuth is exempt. Covers:

  * the code is 6 digits and random
  * the plain code is never stored (salted SHA-256 hash only)
  * expiry (10 min), attempt limit (5 wrong tries), resend cooldown
    (60 s) and the per-hour cap (5) are all enforced
  * wrong codes are rejected; a correct code verifies exactly once
  * a failed Brevo send invalidates the stored code (retry at once)
  * the Brevo client sends the right payload (mocked transport —
    no real key, no real email ever leaves this test)
  * with Brevo unconfigured, logins are refused with the setup
    message — never bypassed
  * Turnstile is fully gone (no widget, no captcha_token anywhere)

Run from the project root, script mode (like the web smoke test):
    .test-venv-verify/bin/python tests/test_brevo_email_code.py
or under pytest:
    .test-venv-verify/bin/python -m pytest tests/test_brevo_email_code.py -q

Self-contained: auth.DB_PATH and the Supabase config path point at
a fresh temp dir per test, so the real data/ folder is untouched and
no live Supabase project is ever touched. The Supabase-mode tests
use a fake client + an in-memory stand-in for the code RPCs.
"""

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TESTS_DIR))

import hashlib
import inspect
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

import auth  # noqa: E402
import brevo_email  # noqa: E402
import httpx  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
EMAIL = "alice@example.com"
PASSWORD = "password123"


# ------------------------------------------------------------------ helpers
def _fresh_backend():
    """Point all server-side state at a fresh temp dir. Returns the dir.

    Also repoints the Supabase config path at a nonexistent temp file
    and clears Supabase env vars, so the backend is deterministically
    'local' no matter what credential files exist in the project folder
    (same pattern as tests/test_wave3.py)."""
    tmp = Path(tempfile.mkdtemp(prefix="dcs-brevo-"))
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


def _force_supabase_backend(tmp):
    """Point auth at a fake Supabase config (no live project) and
    return a restore function. Backend becomes 'supabase'."""
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


@contextmanager
def _brevo_configured(capture, fail_send=False):
    """Fake Brevo config + a capturing send_login_code.

    Sets BREVO_API_KEY / BREVO_SENDER_EMAIL in the environment and
    replaces brevo_email.send_login_code with a stub that records
    (email, code) into `capture` and returns True — or raises
    BrevoSendError when fail_send is set. Restores both afterwards.
    """
    old_key = os.environ.get("BREVO_API_KEY")
    old_sender = os.environ.get("BREVO_SENDER_EMAIL")
    old_send = brevo_email.send_login_code
    os.environ["BREVO_API_KEY"] = "xkeysib-test-key"
    os.environ["BREVO_SENDER_EMAIL"] = "sender@example.com"

    def _stub(email, code, client=None):
        if fail_send:
            raise brevo_email.BrevoSendError("simulated Brevo failure")
        capture.append((email, code))
        return True

    brevo_email.send_login_code = _stub
    try:
        yield
    finally:
        brevo_email.send_login_code = old_send
        if old_key is None:
            os.environ.pop("BREVO_API_KEY", None)
        else:
            os.environ["BREVO_API_KEY"] = old_key
        if old_sender is None:
            os.environ.pop("BREVO_SENDER_EMAIL", None)
        else:
            os.environ["BREVO_SENDER_EMAIL"] = old_sender


@contextmanager
def _brevo_missing():
    """No Brevo key/sender anywhere (env cleared; no secrets file in
    tests), so get_brevo_config() must return None."""
    old_key = os.environ.pop("BREVO_API_KEY", None)
    old_sender = os.environ.pop("BREVO_SENDER_EMAIL", None)
    try:
        yield
    finally:
        if old_key is not None:
            os.environ["BREVO_API_KEY"] = old_key
        if old_sender is not None:
            os.environ["BREVO_SENDER_EMAIL"] = old_sender


def _code_rows():
    """All rows of the local email_login_codes table, as dicts.
    [] when the table was never created (no code was ever stored)."""
    conn = sqlite3.connect(str(auth.DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM email_login_codes ORDER BY created_at")]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _backdate_created(seconds):
    """Move every stored code's created_at back by `seconds` (so the
    60 s resend cooldown has passed without waiting)."""
    conn = sqlite3.connect(str(auth.DB_PATH))
    try:
        past = auth._iso(auth._utcnow() - timedelta(seconds=seconds))
        conn.execute("UPDATE email_login_codes SET created_at = ?", (past,))
        conn.commit()
    finally:
        conn.close()


def _backdate_expiry(seconds):
    """Move every stored code's expiry back by `seconds` (so the code
    is expired without waiting)."""
    conn = sqlite3.connect(str(auth.DB_PATH))
    try:
        past = auth._iso(auth._utcnow() - timedelta(seconds=seconds))
        conn.execute("UPDATE email_login_codes SET expires_at = ?", (past,))
        conn.commit()
    finally:
        conn.close()


def _all_text(at):
    """Every user-visible string in the run (markdown — which is
    also where st.write text lands — titles, captions, code and
    alerts)."""
    out = []
    for coll in (at.markdown, at.title, at.header, at.subheader,
                 at.caption, at.info, at.success, at.warning,
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


class _FakeRpc:
    """In-memory stand-in for the Supabase code RPCs (plus the
    profile/session RPCs the login path calls), with the same rules
    as the SQL: 60 s resend cooldown, 5/hour cap, 10 min expiry,
    5 wrong tries, one use."""

    def __init__(self):
        self.codes = {}   # email -> row dict
        self.history = []  # (email, created_at) for the hourly cap

    def __call__(self, function, params, action):
        now = auth._utcnow()
        if function == "app_request_login_code":
            email = params["p_email"]
            last = self.codes.get(email)
            if (last is not None and not last["used"]
                    and now - last["created_at"] < auth.CODE_RESEND_COOLDOWN):
                return "too_soon"
            hour_ago = now - timedelta(hours=1)
            count = sum(1 for e, t in self.history
                        if e == email and t >= hour_ago)
            if count >= auth.CODE_HOURLY_CAP:
                return "hourly_limit"
            if last is not None:
                last["used"] = True
            self.codes[email] = {
                "code_hash": params["p_code_hash"], "salt": params["p_salt"],
                "expires_at": auth._parse_iso(params["p_expires_at"]),
                "attempts": 0, "used": False, "created_at": now,
            }
            self.history.append((email, now))
            return "ok"
        if function == "app_verify_login_code":
            email = params["p_email"]
            row = self.codes.get(email)
            if row is None or row["used"]:
                return "not_found"
            if row["expires_at"] is None or row["expires_at"] <= now:
                row["used"] = True
                return "expired"
            if row["attempts"] >= auth.CODE_MAX_ATTEMPTS:
                row["used"] = True
                return "too_many"
            if auth._hash_login_code(params["p_code"], row["salt"]) \
                    == row["code_hash"]:
                row["used"] = True
                return "ok"
            row["attempts"] += 1
            if row["attempts"] >= auth.CODE_MAX_ATTEMPTS:
                row["used"] = True
                return "too_many"
            return "wrong"
        if function == "app_invalidate_login_code":
            row = self.codes.get(params["p_email"])
            if row is not None:
                row["used"] = True
            return None
        if function == "app_validate_session":
            # The session check answers with the user id (a string,
            # or a one-element list) — the fake session always
            # belongs to the one fake user.
            return "uuid-1"
        if function in ("app_upsert_profile", "app_get_user_by_id",
                        "app_get_profile"):
            return {"id": params.get("p_id", "uuid-1"),
                    "email": params.get("p_email", EMAIL),
                    "created_at": "2026-11-06T00:00:00"}
        return None


class _FakeSbAuth:
    """Stand-in for client.auth: a confirmed sign-in answer."""

    def __init__(self, signin_resp=None, signin_exc=None):
        self.signin_resp = signin_resp
        self.signin_exc = signin_exc

    def sign_in_with_password(self, creds):
        if self.signin_exc is not None:
            raise self.signin_exc
        return self.signin_resp


class _FakeRpcResp:
    """Stand-in for a supabase-py RPC response (.data + .execute())."""

    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeSbClient:
    """Stand-in for the supabase-py client (auth only; code RPCs go
    through auth._sb_rpc, patched separately)."""

    def __init__(self, fake_auth):
        self.auth = fake_auth

    def rpc(self, function, params):
        # Health check / profile lookups: a usable profile row (nil
        # UUID never matches a real user, so data None is also fine —
        # a row keeps the health check at "ok").
        return _FakeRpcResp({"id": "uuid-1", "email": EMAIL,
                             "created_at": "2026-11-06T00:00:00"})


def _fake_signin_resp():
    """A supabase-py sign_in answer: confirmed user + session."""
    user = SimpleNamespace(
        id="uuid-1",
        email=EMAIL,
        email_confirmed_at="2026-11-06T00:00:00")
    session = SimpleNamespace(access_token="tok")
    return SimpleNamespace(user=user, session=session)


# ------------------------------------------------------------------- unit
def test_code_is_six_digits_and_random():
    """generate_login_code: always 6 digits, never the same twice in
    a row of 200 (random, from `secrets`)."""
    codes = [auth.generate_login_code() for _ in range(200)]
    for code in codes:
        assert re.fullmatch(r"\d{6}", code), f"not 6 digits: {code!r}"
        assert 100000 <= int(code) <= 999999, f"out of range: {code!r}"
    assert len(set(codes)) > 190, \
        f"codes look non-random: {len(set(codes))} distinct of 200"
    print("code shape + randomness OK")


def test_plain_code_never_stored():
    """request_login_code stores only a salted SHA-256 hash — the
    plain code appears nowhere in the database."""
    _fresh_backend()
    capture = []
    with _brevo_configured(capture):
        ok, status = auth.request_login_code(EMAIL)
    assert (ok, status) == (True, "ok"), f"request failed: {status}"
    assert len(capture) == 1 and capture[0][0] == EMAIL
    code = capture[0][1]
    rows = _code_rows()
    assert len(rows) == 1, f"expected 1 stored code, got {len(rows)}"
    row = rows[0]
    assert row["email"] == EMAIL
    assert row["code_hash"] != code, "plain code stored as the hash"
    assert row["salt"], "no salt stored"
    assert row["code_hash"] == hashlib.sha256(
        (row["salt"] + code).encode("utf-8")).hexdigest(), \
        "stored hash is not SHA-256(salt + code)"
    dump = json.dumps(rows, default=str)
    assert code not in dump, "plain code leaked into the stored row"
    print("plain code never stored OK")


def test_correct_code_verifies_once():
    """A correct code verifies, then the same code is dead (used)."""
    _fresh_backend()
    capture = []
    with _brevo_configured(capture):
        assert auth.request_login_code(EMAIL) == (True, "ok")
    code = capture[0][1]
    assert auth.verify_login_code(EMAIL, code) == (True, "ok")
    assert auth.verify_login_code(EMAIL, code) == (False, "not_found"), \
        "a used code must not verify twice"
    print("correct code verifies once OK")


def test_wrong_code_rejected():
    """A wrong code is rejected — and the real code still works
    afterwards (a wrong try does not burn the code)."""
    _fresh_backend()
    capture = []
    with _brevo_configured(capture):
        assert auth.request_login_code(EMAIL) == (True, "ok")
    code = capture[0][1]
    wrong = "000000" if code != "000000" else "111111"
    assert auth.verify_login_code(EMAIL, wrong) == (False, "wrong")
    assert auth.verify_login_code(EMAIL, code) == (True, "ok")
    print("wrong code rejected OK")


def test_expiry_enforced():
    """A code past its 10-minute expiry is rejected as expired."""
    _fresh_backend()
    capture = []
    with _brevo_configured(capture):
        assert auth.request_login_code(EMAIL) == (True, "ok")
    code = capture[0][1]
    _backdate_expiry(seconds=601)
    assert auth.verify_login_code(EMAIL, code) == (False, "expired")
    print("expiry enforced OK")


def test_attempt_limit_enforced():
    """5 wrong tries invalidate the code: tries 1-4 'wrong', the
    5th 'too_many', and the real code is dead after that."""
    _fresh_backend()
    capture = []
    with _brevo_configured(capture):
        assert auth.request_login_code(EMAIL) == (True, "ok")
    code = capture[0][1]
    wrong = "000000" if code != "000000" else "111111"
    for i in range(4):
        assert auth.verify_login_code(EMAIL, wrong) == (False, "wrong"), \
            f"wrong try {i + 1} must be 'wrong'"
    assert auth.verify_login_code(EMAIL, wrong) == (False, "too_many"), \
        "5th wrong try must be 'too_many'"
    assert auth.verify_login_code(EMAIL, code) == (False, "not_found"), \
        "code must be dead after 5 wrong tries"
    print("attempt limit enforced OK")


def test_resend_cooldown_enforced():
    """A second code request inside 60 s is refused ('too_soon')."""
    _fresh_backend()
    capture = []
    with _brevo_configured(capture):
        assert auth.request_login_code(EMAIL) == (True, "ok")
        assert auth.request_login_code(EMAIL) == (False, "too_soon"), \
            "immediate resend must be 'too_soon'"
    assert len(capture) == 1, "no second email may be sent during cooldown"
    print("resend cooldown enforced OK")


def test_hourly_cap_enforced():
    """5 codes in an hour is the cap: the 6th request is refused
    ('hourly_limit'). The cooldown is side-stepped by backdating
    created_at — the cap itself is what is under test."""
    _fresh_backend()
    capture = []
    with _brevo_configured(capture):
        for i in range(5):
            assert auth.request_login_code(EMAIL) == (True, "ok"), \
                f"request {i + 1} must succeed"
            _backdate_created(seconds=61)
        assert auth.request_login_code(EMAIL) == (False, "hourly_limit"), \
            "6th code in an hour must be 'hourly_limit'"
    assert len(capture) == 5, "exactly 5 emails may be sent in the hour"
    print("hourly cap enforced OK")


def test_send_failure_invalidates_code():
    """When Brevo rejects the send, the stored code is invalidated
    so the user can retry at once (no 60 s cooldown on a code that
    never arrived)."""
    _fresh_backend()
    capture = []
    with _brevo_configured(capture, fail_send=True):
        assert auth.request_login_code(EMAIL) == (False, "send_failed")
    assert capture == [], "a failed send must not deliver a code"
    assert auth.verify_login_code(EMAIL, "123456") == (False, "not_found"), \
        "failed-send code must be invalidated"
    with _brevo_configured(capture):
        assert auth.request_login_code(EMAIL) == (True, "ok"), \
            "retry after a failed send must not hit the cooldown"
    print("send failure invalidates code OK")


def test_brevo_client_payload():
    """send_login_code posts the exact Brevo payload (mocked
    transport — no real key, no real email): URL, api-key header,
    sender, recipient, subject, and the code in both bodies. A
    non-201 answer raises BrevoSendError."""
    captured = []

    def _handler(request):
        captured.append(request)
        return httpx.Response(201, json={"messageId": "msg-1"})

    with _brevo_missing():
        os.environ["BREVO_API_KEY"] = "xkeysib-test-key"
        os.environ["BREVO_SENDER_EMAIL"] = "sender@example.com"
        try:
            client = httpx.Client(transport=httpx.MockTransport(_handler))
            assert brevo_email.send_login_code(
                "user@example.com", "123456", client=client) is True
        finally:
            os.environ.pop("BREVO_API_KEY", None)
            os.environ.pop("BREVO_SENDER_EMAIL", None)
    assert len(captured) == 1
    req = captured[0]
    assert str(req.url) == brevo_email.BREVO_API_URL
    assert req.headers["api-key"] == "xkeysib-test-key"
    assert req.headers["accept"] == "application/json"
    assert req.headers["content-type"] == "application/json"
    payload = json.loads(req.content.decode("utf-8"))
    assert payload["sender"] == {"name": "Data Cleaner Studio",
                                 "email": "sender@example.com"}
    assert payload["to"] == [{"email": "user@example.com"}]
    assert payload["subject"] == "Your Data Cleaner Studio login code"
    assert "123456" in payload["htmlContent"]
    assert "123456" in payload["textContent"]
    assert "10 minutes" in payload["textContent"]

    def _fail_handler(request):
        return httpx.Response(400, json={"message": "bad sender"})

    with _brevo_missing():
        os.environ["BREVO_API_KEY"] = "xkeysib-test-key"
        os.environ["BREVO_SENDER_EMAIL"] = "sender@example.com"
        try:
            client = httpx.Client(transport=httpx.MockTransport(_fail_handler))
            try:
                brevo_email.send_login_code(
                    "user@example.com", "123456", client=client)
            except brevo_email.BrevoSendError:
                pass
            else:
                raise AssertionError("400 from Brevo must raise BrevoSendError")
        finally:
            os.environ.pop("BREVO_API_KEY", None)
            os.environ.pop("BREVO_SENDER_EMAIL", None)
    print("Brevo client payload OK")


def test_login_code_email_carries_site_design():
    """The v2 login-code email (approved 2026-11-07): minimal,
    Supabase-email style — logo, welcome line, the code plain and
    large in the one green, one expiry line, one security line, tiny
    footer with a hairline. No card, no code box. The plain-text
    fallback matches. The logo is assets/logo-email.png (240x240,
    rendered from the user's logo) via the public raw URL."""
    payload = brevo_email.build_login_code_email(
        "sender@example.com", "user@example.com", "123456")
    assert payload["subject"] == "Your Data Cleaner Studio login code"
    html = payload["htmlContent"]
    text = payload["textContent"]
    # Logo: the public raw URL, alt text for blocked images.
    assert brevo_email.LOGO_EMAIL_URL in html
    assert brevo_email.LOGO_EMAIL_URL == (
        "https://raw.githubusercontent.com/sheikh-ahmad-am/"
        "data-cleaner-studio-web/main/assets/logo-email.png")
    assert 'alt="Data Cleaner Studio"' in html
    # Welcome line + code + theme tokens + tagline.
    welcome = ("Welcome to Data Cleaner Studio — here's your code "
               "to finish signing in.")
    assert welcome in html and welcome in text
    assert "123456" in html and "123456" in text
    for token in ("#fdfdfd", "#117f50", "#e8e8e8", "#030303",
                  "#696969", "#4d4d4d"):
        assert token in html, f"theme token {token} missing from the email"
    assert "letter-spacing: 8px" in html, "code must be letter-spaced"
    assert "font-size: 32px" in html, "code must be large"
    assert "monospace" in html, "code must be monospace"
    tagline = ("Put in a messy file. Get the cleaned file back, with "
               "its KPIs, charts and a one-page report.")
    assert tagline in html and tagline in text
    assert "It expires in 10 minutes." in html
    assert "It expires in 10 minutes." in text
    assert "If you didn't ask for this code, ignore this email." in html
    assert "If you didn't ask for this code, ignore this email." in text
    # v2 has NO card and NO code box (v1 had both).
    assert "border-radius: 12px" not in html, \
        "v2 must not have the v1 card"
    assert "border: 1px solid #117f50" not in html, \
        "v2 must not box the code in a green border"
    # The logo file itself: a valid 240x240 PNG rendered from the
    # user's mark (dark green #004E2C ink, same as assets/logo.png).
    from PIL import Image
    logo = Image.open(PROJECT_ROOT / "assets" / "logo-email.png")
    assert logo.size == (240, 240), "the email logo must be 240x240"
    assert logo.mode == "RGBA"
    px = logo.convert("RGBA").load()
    counts = {}
    for y in range(0, 240, 2):
        for x in range(0, 240, 2):
            r, g, b, a = px[x, y]
            if a > 200:
                counts[(r, g, b)] = counts.get((r, g, b), 0) + 1
    dominant = max(counts.items(), key=lambda kv: kv[1])[0]
    assert all(abs(a - b) <= 3 for a, b in zip(dominant, (0, 78, 44))), \
        f"the email logo must carry the user's dark green, got {dominant}"
    print("login-code email v2 design OK")


def test_brevo_missing_blocks_login():
    """With Brevo unconfigured: get_brevo_config() is None,
    request_login_code refuses with 'not_configured', the setup
    message names the Brevo API key, and nothing is stored — the
    code check is never bypassed."""
    _fresh_backend()
    with _brevo_missing():
        assert brevo_email.get_brevo_config() is None, \
            "no key/sender must mean no config"
        assert auth.request_login_code(EMAIL) == (False, "not_configured")
    assert "Brevo API key" in auth.BREVO_SETUP_MESSAGE
    assert _code_rows() == [], "no code may be stored when Brevo is missing"
    print("Brevo-missing blocks login OK")


def test_supabase_mode_code_flow_via_fake_rpc():
    """The Supabase path (auth._sb_*) wires through the RPCs: a code
    requested via the fake RPC verifies, a wrong one does not, and
    email_code_required() is True in Supabase mode."""
    tmp = _fresh_backend()
    restore = _force_supabase_backend(tmp)
    fake_rpc = _FakeRpc()
    old_rpc = auth._sb_rpc
    auth._sb_rpc = fake_rpc
    capture = []
    try:
        assert auth.email_code_required() is True
        with _brevo_configured(capture):
            assert auth.request_login_code(EMAIL) == (True, "ok")
        code = capture[0][1]
        assert auth.verify_login_code(EMAIL, "000000") == (False, "wrong")
        assert auth.verify_login_code(EMAIL, code) == (True, "ok")
        assert auth.verify_login_code(EMAIL, code) == (False, "not_found")
    finally:
        auth._sb_rpc = old_rpc
        restore()
    print("Supabase-mode code flow via fake RPC OK")


def test_turnstile_fully_gone():
    """No Turnstile reference survives in the app: no widget render,
    no captcha_token in the auth calls, no component directory, no
    Turnstile tests — and no 'Verify you are human' copy."""
    for name in ("app.py", "auth.py", "brevo_email.py", "ui_design.py",
                 "ui_loading.py", "google_auth.py", "storage.py",
                 "supabase_setup.sql"):
        text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
        assert "turnstile" not in text.lower(), \
            f"Turnstile reference left in {name}"
        assert "captcha" not in text.lower(), \
            f"captcha reference left in {name}"
    for name in ("feat_quickjump.py", "feat_status.py"):
        text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
        assert "turnstile" not in text.lower(), \
            f"Turnstile reference left in {name}"
    assert "captcha_token" not in inspect.signature(
        auth.authenticate).parameters, \
        "authenticate must not take captcha_token"
    assert "captcha_token" not in inspect.signature(
        auth.create_user).parameters, \
        "create_user must not take captcha_token"
    assert not (PROJECT_ROOT / "turnstile_component").exists(), \
        "turnstile_component/ must be deleted"
    assert not list((PROJECT_ROOT / "tests").glob("test_turnstile*.py")), \
        "Turnstile tests must be deleted"
    app_text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert "Verify you are human" not in app_text
    print("Turnstile fully gone OK")


# ----------------------------------------------------------------- AppTest
def _run_login_apptest(capture, fail_send=False):
    """Boot the app in Supabase mode with a fake sign-in + fake RPCs
    and a capturing Brevo send. Returns (at, fake_rpc, restore)."""
    import streamlit_cookies_controller

    tmp = _fresh_backend()
    restore = _force_supabase_backend(tmp)
    fake_rpc = _FakeRpc()
    old_rpc = auth._sb_rpc
    auth._sb_rpc = fake_rpc
    auth._get_client = lambda: _FakeSbClient(
        _FakeSbAuth(signin_resp=_fake_signin_resp()))
    orig_controller = streamlit_cookies_controller.CookieController

    class _RecordingCookies:
        """Cookie layer stand-in that records every write (same
        pattern as tests/test_wave3.py)."""
        store = {}
        sets = []

        def __init__(self, key="cookies"):
            try:
                import streamlit as st
                st.session_state[key] = dict(type(self).store)
            except Exception:  # noqa: BLE001 - no session state yet
                pass

        def get(self, name):
            return type(self).store.get(name)

        def set(self, name, value, **kwargs):
            type(self).store[name] = value
            type(self).sets.append((name, value, kwargs))

        def remove(self, name, **kwargs):
            type(self).store.pop(name, None)

        def refresh(self):
            return None

    streamlit_cookies_controller.CookieController = _RecordingCookies
    ctx = _brevo_configured(capture, fail_send=fail_send)
    ctx.__enter__()
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    assert any(b.label == "Log in" for b in at.button), \
        "supabase mode must still show the login screen"

    def _teardown():
        ctx.__exit__(None, None, None)
        streamlit_cookies_controller.CookieController = orig_controller
        auth._sb_rpc = old_rpc
        restore()

    return at, fake_rpc, _teardown


def test_apptest_login_shows_code_step_then_logs_in():
    """AppTest: a correct password shows the code screen (not the
    logged-in app), a wrong code is rejected, and the correct code
    completes the login through the normal session path."""
    capture = []
    at, _rpc, teardown = _run_login_apptest(capture)
    try:
        _find_text_input(at, "Email").set_value(EMAIL).run()
        _find_text_input(at, "Password").set_value(PASSWORD).run()
        _find_button(at, "Log in").click().run()
        assert not at.exception, f"exception on login: {at.exception}"
        assert len(capture) == 1, "login must send exactly one code"
        assert any("Check your email" in v for v in _all_text(at)), \
            "login must show the code screen after a correct password"
        assert at.session_state.get("auth_token") is None, \
            "no session may exist before the code passes"
        assert not any(b.label == "Try the messy sample"
                       for b in at.button), \
            "the app must not be logged in before the code passes"
        _find_text_input(at, "6-digit code").set_value("000000").run()
        _find_button(at, "Verify code").click().run()
        assert not at.exception, f"exception on wrong code: {at.exception}"
        assert any("Wrong code" in v for v in _all_text(at)), \
            "a wrong code must show a clear error"
        assert at.session_state.get("auth_token") is None, \
            "a wrong code must not log anyone in"
        code = capture[0][1]
        _find_text_input(at, "6-digit code").set_value(code).run()
        _find_button(at, "Verify code").click().run()
        assert not at.exception, f"exception on correct code: {at.exception}"
        assert at.session_state.get("auth_token") is not None, \
            "the correct code must create a session"
        # The rail starts collapsed (the dashboard's default) — open
        # it so the full sidebar's sample button is visible below.
        at.session_state["dcs_rail_collapsed"] = False
        at.run()
        assert not at.exception, f"exception expanding rail: {at.exception}"
        assert any(b.label == "Try the messy sample" for b in at.button), \
            "the correct code must log the user in"
    finally:
        teardown()
    print("AppTest login -> code step -> login OK")


def test_apptest_brevo_missing_shows_setup_message():
    """AppTest: with Brevo unconfigured, a correct password shows
    the setup message and logs nobody in — never a bypass."""
    import streamlit_cookies_controller

    tmp = _fresh_backend()
    restore = _force_supabase_backend(tmp)
    fake_rpc = _FakeRpc()
    old_rpc = auth._sb_rpc
    auth._sb_rpc = fake_rpc
    auth._get_client = lambda: _FakeSbClient(
        _FakeSbAuth(signin_resp=_fake_signin_resp()))
    orig_controller = streamlit_cookies_controller.CookieController

    class _RecordingCookies:
        store = {}
        sets = []

        def __init__(self, key="cookies"):
            try:
                import streamlit as st
                st.session_state[key] = dict(type(self).store)
            except Exception:  # noqa: BLE001 - no session state yet
                pass

        def get(self, name):
            return type(self).store.get(name)

        def set(self, name, value, **kwargs):
            type(self).store[name] = value
            type(self).sets.append((name, value, kwargs))

        def remove(self, name, **kwargs):
            type(self).store.pop(name, None)

        def refresh(self):
            return None

    streamlit_cookies_controller.CookieController = _RecordingCookies
    try:
        with _brevo_missing():
            at = AppTest.from_file(APP)
            at.run()
            assert not at.exception, f"startup exception: {at.exception}"
            _find_text_input(at, "Email").set_value(EMAIL).run()
            _find_text_input(at, "Password").set_value(PASSWORD).run()
            _find_button(at, "Log in").click().run()
            assert not at.exception, f"exception on login: {at.exception}"
            assert any("Email verification isn't set up yet" in v
                       for v in _all_text(at)), \
                "Brevo-missing login must show the setup message"
            assert at.session_state.get("auth_token") is None, \
                "Brevo-missing must log nobody in"
            assert not any(b.label == "Try the messy sample"
                           for b in at.button), \
                "Brevo-missing must not reach the logged-in app"
    finally:
        streamlit_cookies_controller.CookieController = orig_controller
        auth._sb_rpc = old_rpc
        restore()
    print("AppTest Brevo-missing setup message OK")


# -------------------------------------------------------------------- main
def main():
    test_code_is_six_digits_and_random()
    test_plain_code_never_stored()
    test_correct_code_verifies_once()
    test_wrong_code_rejected()
    test_expiry_enforced()
    test_attempt_limit_enforced()
    test_resend_cooldown_enforced()
    test_hourly_cap_enforced()
    test_send_failure_invalidates_code()
    test_brevo_client_payload()
    test_login_code_email_carries_site_design()
    test_brevo_missing_blocks_login()
    test_supabase_mode_code_flow_via_fake_rpc()
    test_turnstile_fully_gone()
    test_apptest_login_shows_code_step_then_logs_in()
    test_apptest_brevo_missing_shows_setup_message()
    print("ALL BREVO EMAIL CODE TESTS PASSED")


if __name__ == "__main__":
    main()
