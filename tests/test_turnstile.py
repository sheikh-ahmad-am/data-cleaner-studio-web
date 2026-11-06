"""Unit tests for the Cloudflare Turnstile integration.

Covers, with everything mocked (no live Supabase, no browser):
  * auth.py wiring: the token rides inside the credentials dict as
    options.captcha_token, and `options` is omitted entirely when
    there is no token. Captcha failures become CaptchaFailedError
    with the plain-word message, never a raw error.
  * turnstile_component.get_site_key(): Streamlit secrets first,
    then the environment; None when neither has it.
  * turnstile_component.turnstile_token(): no key -> None without
    touching the component; the component's args and return value
    pass through; non-string/empty values become None.
  * The frontend files exist and carry the protocol markers
    (Turnstile API URL, setComponentValue, componentReady).

Run:  python -m pytest tests/test_turnstile.py -q   (from project root)
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import auth  # noqa: E402
import turnstile_component  # noqa: E402


# ---------------------------------------------------------------------------
# Fake Supabase client (records the exact credentials dicts it receives)
# ---------------------------------------------------------------------------

class _FakeUser:
    def __init__(self, uid="uuid-1", email="alice@example.com"):
        self.id = uid
        self.email = email
        self.identities = ["email"]
        self.email_confirmed_at = "2026-11-06T00:00:00Z"


class _FakeResp:
    def __init__(self, user=None, session=None):
        self.user = user
        self.session = session


class _FakeAuth:
    def __init__(self, calls, exc=None):
        self.calls = calls  # list of ("sign_up"|"sign_in", credentials)
        self.exc = exc

    def sign_up(self, credentials):
        self.calls.append(("sign_up", credentials))
        if self.exc is not None:
            raise self.exc
        return _FakeResp(user=_FakeUser(), session=object())

    def sign_in_with_password(self, credentials):
        self.calls.append(("sign_in", credentials))
        if self.exc is not None:
            raise self.exc
        return _FakeResp(user=_FakeUser(), session=object())


class _FakeClient:
    def __init__(self, calls, exc=None):
        self.auth = _FakeAuth(calls, exc)


def _patch_client(monkeypatch, calls, exc=None):
    monkeypatch.setattr(auth, "_get_client",
                        lambda: _FakeClient(calls, exc))
    # Profile upsert is a separate RPC; keep it out of these tests.
    monkeypatch.setattr(
        auth, "_sb_upsert_profile",
        lambda user_id, email: {"id": user_id, "email": email,
                                "created_at": None})


# ---------------------------------------------------------------------------
# auth.py: token wiring
# ---------------------------------------------------------------------------

def test_create_user_sends_captcha_token_in_options(monkeypatch):
    calls = []
    _patch_client(monkeypatch, calls)
    ok, error = auth._sb_create_user("alice@example.com", "password123",
                                     captcha_token="tok-1")
    assert (ok, error) == (True, None)
    assert calls == [("sign_up", {
        "email": "alice@example.com",
        "password": "password123",
        "options": {"captcha_token": "tok-1"},
    })]


def test_create_user_omits_options_without_token(monkeypatch):
    calls = []
    _patch_client(monkeypatch, calls)
    ok, error = auth._sb_create_user("alice@example.com", "password123")
    assert (ok, error) == (True, None)
    assert calls == [("sign_up", {
        "email": "alice@example.com",
        "password": "password123",
    })]
    assert "options" not in calls[0][1]


def test_authenticate_sends_captcha_token_in_options(monkeypatch):
    calls = []
    _patch_client(monkeypatch, calls)
    user = auth._sb_authenticate("alice@example.com", "password123",
                                 captcha_token="tok-2")
    assert user == {"id": "uuid-1", "email": "alice@example.com",
                    "created_at": None}
    assert calls == [("sign_in", {
        "email": "alice@example.com",
        "password": "password123",
        "options": {"captcha_token": "tok-2"},
    })]


def test_authenticate_omits_options_without_token(monkeypatch):
    calls = []
    _patch_client(monkeypatch, calls)
    user = auth._sb_authenticate("alice@example.com", "password123")
    assert user is not None
    assert "options" not in calls[0][1]


def test_authenticate_captcha_failure_is_plain_word(monkeypatch):
    calls = []
    _patch_client(monkeypatch, calls,
                  exc=Exception("captcha verification failed"))
    with pytest.raises(auth.CaptchaFailedError) as excinfo:
        auth._sb_authenticate("alice@example.com", "password123",
                              captcha_token="tok-bad")
    assert str(excinfo.value) == auth.CAPTCHA_FAILED_MESSAGE
    assert "captcha verification failed" not in str(excinfo.value)


def test_create_user_captcha_failure_is_plain_word(monkeypatch):
    calls = []
    _patch_client(monkeypatch, calls,
                  exc=Exception("400: captcha required"))
    with pytest.raises(auth.CaptchaFailedError) as excinfo:
        auth._sb_create_user("alice@example.com", "password123",
                             captcha_token="tok-bad")
    assert str(excinfo.value) == auth.CAPTCHA_FAILED_MESSAGE


def test_public_wrappers_pass_the_token_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(auth, "get_auth_backend", lambda: "supabase")
    monkeypatch.setattr(
        auth, "_sb_create_user",
        lambda email, pw, captcha_token=None: seen.__setitem__(
            "create", (email, pw, captcha_token)) or (True, None))
    monkeypatch.setattr(
        auth, "_sb_authenticate",
        lambda email, pw, captcha_token=None: seen.__setitem__(
            "auth", (email, pw, captcha_token)) or {"id": "u"})
    assert auth.create_user("a@b.co", "password123",
                            captcha_token="tok-3") == (True, None)
    assert seen["create"] == ("a@b.co", "password123", "tok-3")
    assert auth.authenticate("a@b.co", "password123",
                             captcha_token="tok-4") == {"id": "u"}
    assert seen["auth"] == ("a@b.co", "password123", "tok-4")
    # And without a token the wrappers pass None (auth.py omits options).
    auth.create_user("a@b.co", "password123")
    assert seen["create"][2] is None


# ---------------------------------------------------------------------------
# turnstile_component.get_site_key(): config helper
# ---------------------------------------------------------------------------

def test_site_key_from_env_when_secrets_empty(monkeypatch):
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "0xENVKEY")
    monkeypatch.setattr("streamlit.secrets", {})
    assert turnstile_component.get_site_key() == "0xENVKEY"


def test_site_key_from_secrets_first(monkeypatch):
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "0xENVKEY")
    monkeypatch.setattr("streamlit.secrets",
                        {"TURNSTILE_SITE_KEY": "0xSECRETKEY"})
    assert turnstile_component.get_site_key() == "0xSECRETKEY"


def test_site_key_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("TURNSTILE_SITE_KEY", raising=False)
    monkeypatch.setattr("streamlit.secrets", {})
    assert turnstile_component.get_site_key() is None


def test_site_key_empty_string_is_none(monkeypatch):
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "   ")
    monkeypatch.setattr("streamlit.secrets", {})
    assert turnstile_component.get_site_key() is None


# ---------------------------------------------------------------------------
# turnstile_component.turnstile_token(): component wrapper
# ---------------------------------------------------------------------------

def _stub_component(monkeypatch, return_value):
    calls = []
    monkeypatch.setattr(turnstile_component, "_component", None)

    def _declare(name, path=None):
        calls.append((name, path))

        def _render(**kwargs):
            calls.append(kwargs)
            return return_value
        return _render

    monkeypatch.setattr(turnstile_component, "declare_component", _declare)
    return calls


def test_token_passes_args_and_return_through(monkeypatch):
    calls = _stub_component(monkeypatch, "tok-abc")
    assert turnstile_component.turnstile_token(
        "0xSITEKEY", key="turnstile-3", reset=3) == "tok-abc"
    assert calls[0][0] == "turnstile"
    assert Path(calls[0][1]).name == "frontend"
    assert calls[1] == {"site_key": "0xSITEKEY", "reset": 3,
                        "key": "turnstile-3", "default": None}


def test_token_none_without_key_never_touches_component(monkeypatch):
    calls = _stub_component(monkeypatch, "tok-abc")
    assert turnstile_component.turnstile_token(None) is None
    assert turnstile_component.turnstile_token("") is None
    assert calls == []


def test_token_none_or_junk_becomes_none(monkeypatch):
    calls = _stub_component(monkeypatch, None)
    assert turnstile_component.turnstile_token("0xSITEKEY") is None
    _stub_component(monkeypatch, "")
    assert turnstile_component.turnstile_token("0xSITEKEY") is None
    _stub_component(monkeypatch, 123)
    assert turnstile_component.turnstile_token("0xSITEKEY") is None


# ---------------------------------------------------------------------------
# Frontend files: the bundle the component serves
# ---------------------------------------------------------------------------

def test_frontend_files_carry_the_protocol():
    frontend = PROJECT_ROOT / "turnstile_component" / "frontend"
    html = (frontend / "index.html").read_text(encoding="utf-8")
    js = (frontend / "turnstile.js").read_text(encoding="utf-8")
    assert "challenges.cloudflare.com/turnstile/v0/api.js" in html
    assert "turnstile.js" in html
    for marker in ("streamlit:componentReady", "streamlit:setComponentValue",
                   "streamlit:setFrameHeight", "streamlit:render",
                   "turnstile.render", "expired-callback",
                   "theme: \"light\""):
        assert marker in js, f"missing frontend marker: {marker}"
    # Regression (2026-11-06, live app): the componentReady message
    # must carry apiVersion, or Streamlit rejects the handshake with
    # "Unrecognized component API version: 'undefined'" and the widget
    # shows a red error instead of the check.
    assert "apiVersion: 1" in js
    # No site key or secret may ever be baked into the frontend.
    assert "0x4AAAAA" not in html and "0x4AAAAA" not in js


# ---------------------------------------------------------------------------
# Turnstile width fix (2026-11-06, Supabase reskin): the widget must be
# fluid, not a fixed 300px box, or it overflows narrow layouts.
# ---------------------------------------------------------------------------

def test_turnstile_widget_size_is_flexible():
    js = (PROJECT_ROOT / "turnstile_component" / "frontend"
          / "turnstile.js").read_text(encoding="utf-8")
    assert 'size: "flexible"' in js
    assert 'size: "normal"' not in js


def test_turnstile_container_is_fluid_width():
    html = (PROJECT_ROOT / "turnstile_component" / "frontend"
            / "index.html").read_text(encoding="utf-8")
    assert "width: 100%" in html
    # The old fixed-width rule must be gone ("max-width: 300px" still
    # contains the substring "width: 300px", so match the full rule).
    assert "#turnstile-container { width: 300px" not in html


def test_turnstile_container_keeps_max_width_cap():
    html = (PROJECT_ROOT / "turnstile_component" / "frontend"
            / "index.html").read_text(encoding="utf-8")
    assert "max-width: 300px" in html
    assert "height: 65px" in html
