"""Unit tests for the Profile backend (auth.py + supabase_setup.sql).

Covers, with everything mocked (no live Supabase, no browser):
  * display name: set/get round-trip through the fake RPC, invalid
    names rejected without touching the RPC, surrounding whitespace
    stripped, and a missing-function error becomes the plain setup
    message instead of a crash.
  * password reset: reset_password_email is called with the email;
    a failure becomes a plain classified error.
  * sessions: list returns metadata only — no token values anywhere.
  * account deletion: the delete RPC is called with the right user
    id, and a failure raises AuthServiceError.
  * local mode (temp DB): set display name, list sessions, delete
    rows removes the user and their sessions; password reset by
    email is unavailable there.
  * supabase_setup.sql carries the three new functions + grants.

Run:  .test-venv-verify/bin/python -m pytest tests/test_profile_backend.py -q
       (from project root)
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import auth  # noqa: E402

UID = "11111111-1111-1111-1111-111111111111"
EMAIL = "alice@example.com"
SETUP_MESSAGE = (
    "Display name saving needs the updated database setup \u2014 run "
    "supabase_setup.sql in the Supabase SQL editor."
)


# ---------------------------------------------------------------------------
# Fake Supabase client (records the exact RPC / auth calls it receives)
# ---------------------------------------------------------------------------

class _FakeRPC:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeAuth:
    def __init__(self, client):
        self._client = client

    def reset_password_email(self, email):
        self._client.auth_calls.append(("reset_password_email", email))
        if self._client.auth_exc is not None:
            raise self._client.auth_exc


class _FakeClient:
    """rpc() answers come from `handler`; auth failures from `auth_exc`."""

    def __init__(self, handler=None, auth_exc=None):
        self.rpc_calls = []
        self.auth_calls = []
        self.handler = handler
        self.auth_exc = auth_exc
        self.auth = _FakeAuth(self)

    def rpc(self, function, params):
        self.rpc_calls.append((function, params))
        if self.handler is None:
            return _FakeRPC(None)
        return _FakeRPC(self.handler(function, params))


def _patch_supabase(monkeypatch, client):
    monkeypatch.setattr(auth, "_get_client", lambda: client)
    monkeypatch.setattr(auth, "get_auth_backend", lambda: "supabase")


class _FakeProfileStore:
    """A tiny in-memory profiles table behind the fake RPCs."""

    def __init__(self):
        self.profiles = {
            UID: {"id": UID, "email": EMAIL,
                  "created_at": "2026-11-06T00:00:00+00:00",
                  "display_name": None},
        }
        self.sessions = [
            {"token": "tok-secret-1",
             "created_at": "2026-11-06T10:00:00+00:00",
             "expires_at": "2026-11-13T10:00:00+00:00"},
            {"token": "tok-secret-2",
             "created_at": "2026-11-05T10:00:00+00:00",
             "expires_at": "2026-11-12T10:00:00+00:00"},
        ]

    def handler(self, function, params):
        if function == "app_set_display_name":
            row = self.profiles.setdefault(
                params["p_id"],
                {"id": params["p_id"], "email": EMAIL,
                 "created_at": "2026-11-06T00:00:00+00:00",
                 "display_name": None})
            row["display_name"] = params["p_display_name"]
            return dict(row)
        if function == "app_get_profile":
            row = self.profiles.get(params["p_id"])
            return dict(row) if row else None
        if function == "app_list_sessions":
            return [dict(s) for s in self.sessions]
        if function == "app_delete_account_data":
            self.profiles.pop(params["p_user_id"], None)
            self.sessions = []
            return None
        raise AssertionError(f"unexpected RPC: {function}")


# ---------------------------------------------------------------------------
# Supabase mode: display name
# ---------------------------------------------------------------------------

def test_set_display_name_round_trip_through_rpc(monkeypatch):
    store = _FakeProfileStore()
    client = _FakeClient(handler=store.handler)
    _patch_supabase(monkeypatch, client)

    user = auth.get_user_by_id(UID)
    assert user is not None and user["display_name"] is None

    # Surrounding whitespace is stripped before the RPC call.
    assert auth.set_display_name(UID, "  Ahm  ") == (True, None)
    assert client.rpc_calls[-1] == (
        "app_set_display_name",
        {"p_id": UID, "p_display_name": "Ahm"},
    )

    user = auth.get_user_by_id(UID)
    assert user["display_name"] == "Ahm"
    assert user["email"] == EMAIL and user["username"] == EMAIL


@pytest.mark.parametrize("bad_name", [
    "", "   ", "x" * 61, None, 123, ["Ahm"],
])
def test_set_display_name_rejects_invalid_names(monkeypatch, bad_name):
    client = _FakeClient(handler=_FakeProfileStore().handler)
    _patch_supabase(monkeypatch, client)
    ok, error = auth.set_display_name(UID, bad_name)
    assert not ok and error, f"{bad_name!r} must be rejected"
    assert client.rpc_calls == [], "invalid names must never reach the RPC"


def test_set_display_name_accepts_60_chars(monkeypatch):
    store = _FakeProfileStore()
    client = _FakeClient(handler=store.handler)
    _patch_supabase(monkeypatch, client)
    assert auth.set_display_name(UID, "x" * 60) == (True, None)


def test_set_display_name_missing_function_returns_setup_message(monkeypatch):
    def _missing(function, params):
        raise Exception(
            "PGRST202: Could not find the function "
            "public.app_set_display_name(uuid, text) in the schema cache")

    client = _FakeClient(handler=_missing)
    _patch_supabase(monkeypatch, client)
    ok, error = auth.set_display_name(UID, "Ahm")
    assert ok is False
    assert error == SETUP_MESSAGE
    assert "supabase_setup.sql" in error


# ---------------------------------------------------------------------------
# Supabase mode: password reset
# ---------------------------------------------------------------------------

def test_request_password_reset_calls_supabase(monkeypatch):
    client = _FakeClient()
    _patch_supabase(monkeypatch, client)
    assert auth.request_password_reset(EMAIL) == (True, None)
    assert client.auth_calls == [("reset_password_email", EMAIL)]


def test_request_password_reset_failure_is_classified(monkeypatch):
    client = _FakeClient(auth_exc=Exception("SMTP gateway down"))
    _patch_supabase(monkeypatch, client)
    ok, error = auth.request_password_reset(EMAIL)
    assert not ok and error
    assert "requesting a password reset" in error


def test_request_password_reset_rejects_bad_email(monkeypatch):
    client = _FakeClient()
    _patch_supabase(monkeypatch, client)
    ok, error = auth.request_password_reset("not-an-email")
    assert not ok and error
    assert client.auth_calls == []


# ---------------------------------------------------------------------------
# Supabase mode: sessions + account deletion
# ---------------------------------------------------------------------------

def test_list_user_sessions_returns_metadata_only(monkeypatch):
    store = _FakeProfileStore()
    client = _FakeClient(handler=store.handler)
    _patch_supabase(monkeypatch, client)
    sessions = auth.list_user_sessions(UID)
    assert sessions == [
        {"created_at": "2026-11-06T10:00:00+00:00",
         "expires_at": "2026-11-13T10:00:00+00:00"},
        {"created_at": "2026-11-05T10:00:00+00:00",
         "expires_at": "2026-11-12T10:00:00+00:00"},
    ]
    # No token value anywhere in the returned data.
    assert "token" not in json.dumps(sessions)
    for session in sessions:
        assert set(session) == {"created_at", "expires_at"}
    assert client.rpc_calls == [
        ("app_list_sessions", {"p_user_id": UID}),
    ]


def test_list_user_sessions_failure_returns_empty(monkeypatch):
    def _boom(function, params):
        raise Exception("boom")

    client = _FakeClient(handler=_boom)
    _patch_supabase(monkeypatch, client)
    assert auth.list_user_sessions(UID) == []


def test_delete_account_rows_calls_delete_rpc(monkeypatch):
    store = _FakeProfileStore()
    client = _FakeClient(handler=store.handler)
    _patch_supabase(monkeypatch, client)
    assert auth.delete_account_rows(UID) is None
    assert ("app_delete_account_data", {"p_user_id": UID}) in client.rpc_calls
    assert auth.get_user_by_id(UID) is None


def test_delete_account_rows_failure_raises(monkeypatch):
    def _boom(function, params):
        raise Exception("boom")

    client = _FakeClient(handler=_boom)
    _patch_supabase(monkeypatch, client)
    with pytest.raises(auth.AuthServiceError):
        auth.delete_account_rows(UID)


# ---------------------------------------------------------------------------
# Local mode (temp DB): display name, sessions, deletion, reset
# ---------------------------------------------------------------------------

@pytest.fixture
def _local(monkeypatch, tmp_path):
    """Point auth at a temp DB with no Supabase config (local mode)."""
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(auth, "SUPABASE_CONFIG_PATH",
                        tmp_path / "no-supabase_config.json")
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
        monkeypatch.delenv(key, raising=False)
    auth._reset_backend_cache()
    assert auth.get_auth_backend() == "local"
    yield
    auth._reset_backend_cache()


def _make_local_user():
    ok, err = auth.create_user("alice", "supersecret1")
    assert ok and err is None, f"signup failed: {err}"
    user = auth.authenticate("alice", "supersecret1")
    assert user is not None
    return user


def test_local_display_name_round_trip(_local):
    user = _make_local_user()
    assert user["display_name"] is None

    assert auth.set_display_name(user["id"], "  Ahm  ") == (True, None)
    fetched = auth.get_user_by_id(user["id"])
    assert fetched["display_name"] == "Ahm"

    # The name also rides along on login and on session validation.
    assert auth.authenticate("alice", "supersecret1")["display_name"] == "Ahm"
    token = auth.create_session(user["id"])
    assert auth.validate_session(token)["display_name"] == "Ahm"


def test_local_display_name_invalid_and_unknown_user(_local):
    user = _make_local_user()
    for bad_name in ("", "   ", "x" * 61, None, 123):
        ok, error = auth.set_display_name(user["id"], bad_name)
        assert not ok and error, f"{bad_name!r} must be rejected"
    ok, error = auth.set_display_name(999999, "Ahm")
    assert not ok and error
    assert auth.get_user_by_id(user["id"])["display_name"] is None


def test_local_display_name_column_survives_reinit(_local):
    """The ALTER TABLE ... IF NOT EXISTS runs on every open: a DB
    created before the column existed still gains it."""
    user = _make_local_user()
    auth.set_display_name(user["id"], "Ahm")
    conn = sqlite3.connect(str(auth.DB_PATH))
    conn.execute("ALTER TABLE users DROP COLUMN display_name")
    conn.commit()
    conn.close()
    assert auth.get_user_by_id(user["id"])["display_name"] is None
    assert auth.set_display_name(user["id"], "Ahm") == (True, None)


def test_local_list_sessions(_local):
    user = _make_local_user()
    assert auth.list_user_sessions(user["id"]) == []
    token1 = auth.create_session(user["id"])
    token2 = auth.create_session(user["id"])
    assert token1 and token2 and token1 != token2
    sessions = auth.list_user_sessions(user["id"])
    assert len(sessions) == 2
    for session in sessions:
        assert set(session) == {"created_at", "expires_at"}
    # Newest first.
    assert sessions == sorted(sessions, key=lambda s: s["created_at"],
                              reverse=True)
    assert "token" not in json.dumps(sessions)


def test_local_delete_rows_removes_user_and_sessions(_local):
    user = _make_local_user()
    token = auth.create_session(user["id"])
    assert auth.validate_session(token) is not None
    assert auth.list_user_sessions(user["id"]) != []

    assert auth.delete_account_rows(user["id"]) is None
    assert auth.get_user_by_id(user["id"]) is None
    assert auth.list_user_sessions(user["id"]) == []
    assert auth.validate_session(token) is None
    assert auth.authenticate("alice", "supersecret1") is None


def test_local_delete_rows_unknown_user_is_noop(_local):
    _make_local_user()
    assert auth.delete_account_rows(999999) is None
    assert auth.get_user_by_id(1) is not None


def test_local_request_password_reset_unavailable(_local):
    ok, error = auth.request_password_reset(EMAIL)
    assert ok is False
    assert error == ("Password reset by email is only available "
                     "for cloud accounts.")


# ---------------------------------------------------------------------------
# supabase_setup.sql carries the new profile pieces
# ---------------------------------------------------------------------------

def test_sql_setup_has_new_profile_functions():
    sql = (PROJECT_ROOT / "supabase_setup.sql").read_text(encoding="utf-8")
    lowered = sql.lower()
    for needle in (
        "alter table public.profiles",
        "display_name text",
        "app_set_display_name",
        "app_list_sessions",
        "app_delete_account_data",
        "returns table(created_at timestamptz, expires_at timestamptz)",
        "delete from public.sessions where user_id = p_user_id",
        "delete from public.profiles where id = p_user_id",
    ):
        assert needle in lowered, f"supabase_setup.sql missing: {needle}"
    for fn in ("app_set_display_name(uuid, text)",
               "app_list_sessions(uuid)",
               "app_delete_account_data(uuid)"):
        assert f"grant execute on function public.{fn} to anon, authenticated" in lowered
        assert f"revoke execute on function public.{fn} from public" in lowered
    assert "8 security definer functions" in lowered
    assert "service_role" not in lowered, "SQL must not mention service_role"
