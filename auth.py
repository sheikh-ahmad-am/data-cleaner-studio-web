"""User accounts for the Data Cleaner Studio web version.

TWO BACKENDS, ONE API. The Streamlit app calls the same functions no
matter which backend is active; `get_auth_backend()` tells it which one.

* SUPABASE (primary) — Supabase Auth for signup/login (email/password)
  and Postgres tables for user records + sessions, via the supabase-py
  client. Active only when a valid config exists:
    - supabase_config.json in the project folder
      ({"url": ..., "anon_key": ...}), or
    - the SUPABASE_URL / SUPABASE_ANON_KEY environment variables.
  The config file is NEVER committed (see .gitignore). Only the anon
  key is used here — it is safe to expose to the client side by
  Supabase's design, and Row Level Security + SECURITY DEFINER
  functions (see supabase_setup.sql) do the authorisation. There is
  NO service-role key anywhere in this module: the server never needs
  one for auth. (Storage is different — see storage.py.)
  Google sign-in lives in google_auth.py (Supabase Auth OAuth redirect
  flow: authorization URL -> ?code=... -> exchange for a session).
  The entry points the app calls are re-exported here:
  `get_google_sign_in_url()` and `handle_oauth_code(code)`.

* LOCAL (fallback) — SQLite accounts (users + sessions tables) with
  PBKDF2-HMAC-SHA256 (200,000 iterations) password hashes and server-side
  opaque session tokens (7-day expiry), plus the per-user folders in
  storage.py. Active when no Supabase credentials are present, or the
  config is missing/malformed/unusable. Local mode shows the banner from
  `get_local_mode_banner()`.

FREE TIER ONLY. Everything here runs inside Supabase's free limits
(500 MB database, 50,000 monthly active users, 1 GB file storage,
5 GB egress/month, 2 projects). No paid feature is used or required.
A free project PAUSES after 1 week of inactivity: a paused project is
detected (failed client init or failed health query) and surfaced via
`get_backend_warning()` as the plain message
"Project paused — restore it in the Supabase dashboard" instead of
crashing. Restoring is one click in the dashboard and no data is lost
(see DEPLOY.md). The scheduler also runs a tiny keep-alive query at
least every 3 days so the project stays awake on its own.

IMPORTANT — no silent fallback for real Supabase users: once the backend
is 'supabase', every auth call goes to Supabase. If Supabase is then
unreachable or misconfigured, `authenticate()` raises AuthServiceError
(and `create_user()` returns a clear error string) instead of quietly
falling back to local accounts or reporting "wrong password". A local
account and a Supabase account with the same name are DIFFERENT users;
switching backends means re-registering.

Passwords are NEVER stored or logged in plain text, in either backend.

Public API (backend-agnostic; the app imports these):
    get_auth_backend() -> 'supabase' or 'local'
    get_backend_warning() -> str | None   (why local mode, or paused/setup)
    get_local_mode_banner() -> str | None (banner text, or None if supabase)
    create_user(username_or_email, password) -> (ok, error)
    authenticate(email_or_username, password) -> user dict or None
    create_session(user_id) -> token (str) or None
    validate_session(token) -> user dict or None
    delete_session(token) -> None
    get_user_by_id(user_id) -> user dict or None
    get_google_sign_in_url(redirect_to=None) -> str | None
    handle_oauth_code(code) -> (user, session_token, error)
    supabase_keepalive() -> bool  (tiny real query; scheduler keep-alive)

User dicts always have: {"id", "username", "email", "created_at"}.
Local mode: id is an int, email is None. Supabase mode: id is the
Supabase auth user id (uuid str), username == email.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent

# Repointable (tests point this at temp paths to force local mode).
SUPABASE_CONFIG_PATH = _PROJECT_ROOT / "supabase_config.json"

# Local-mode SQLite DB (unchanged from the original design).
DB_PATH = _PROJECT_ROOT / "data" / "users.db"

SESSION_TTL = timedelta(days=7)
_PBKDF2_ITERATIONS = 200_000
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^https?://[^/\s]+(?:/[^\\s]*)?$")

LOCAL_MODE_BANNER = (
    "Local mode \u2014 connect Supabase in Settings to enable cloud accounts"
)
PAUSED_MESSAGE = "Project paused \u2014 restore it in the Supabase dashboard"
SETUP_MESSAGE = (
    "Supabase tables are not set up yet \u2014 run supabase_setup.sql "
    "in the Supabase SQL editor."
)

# Cached backend decision for the process lifetime.
_BACKEND: str | None = None
_BACKEND_WARNING: str | None = None
_SUPABASE_CONFIG: dict | None = None
_SUPABASE_CLIENT = None  # supabase-py Client, once created
_HEALTH: str | None = None  # None=unchecked, "ok", "paused", "setup", or a message
_GOOGLE_URL: str | None = None  # cached OAuth URL (see google_auth.py)


class AuthServiceError(Exception):
    """Supabase is configured but unreachable/misconfigured.

    Raised (instead of a silent None / wrong-password) so the app can
    show a clear error instead of faking a failed login.
    """


class EmailNotConfirmedError(AuthServiceError):
    """The email address is registered but not confirmed yet.

    A subclass of AuthServiceError (so every existing
    ``except AuthServiceError`` still catches it), raised only when
    Supabase answers a sign-in with "Email not confirmed". The app
    catches this subclass FIRST and shows the inbox message instead
    of a wrong-password or service error — an unconfirmed email is
    neither.
    """


#: Plain-word message shown when Supabase rejects a login or sign-up
#: over the security check (Turnstile CAPTCHA). The raw Supabase error
#: ("captcha verification failed" and friends) must never reach the
#: user — see _classify_error and CaptchaFailedError below.
CAPTCHA_FAILED_MESSAGE = ("Security check failed — please complete the "
                          "check and try again.")


class CaptchaFailedError(AuthServiceError):
    """Supabase rejected the Turnstile security check.

    A subclass of AuthServiceError (so every existing
    ``except AuthServiceError`` still catches it), raised only when a
    sign-up or sign-in fails on captcha verification — a spent or
    missing token, or a failed check. The app catches this subclass
    FIRST and shows CAPTCHA_FAILED_MESSAGE instead of a raw error.
    """


#: create_user() return marker: the account WAS created, but the email
#: is not confirmed yet (Supabase "Confirm email" is on). The second
#: element of the (ok, error) tuple is this string instead of None.
#: The caller must NOT log the user in — tell them to check their
#: inbox and click the verification link first. Local mode never
#: returns this (local accounts have no confirmation step).
SIGNUP_NEEDS_CONFIRMATION = "needs_confirmation"


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(text: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

def _load_supabase_config() -> tuple[dict | None, str | None]:
    """Return (config, warning). config is None when Supabase is unusable.

    Missing config -> (None, None): plain local mode, no warning.
    Present-but-broken config -> (None, warning): local mode + warning.
    Config file wins; environment variables are the fallback (handy on
    a VPS / Streamlit Cloud secrets, where there is no project folder
    file to drop).
    """
    config = None
    source = ""
    if SUPABASE_CONFIG_PATH.is_file():
        source = "supabase_config.json"
        try:
            raw = json.loads(SUPABASE_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return None, f"supabase_config.json is unreadable: {exc}"
        if not isinstance(raw, dict):
            return None, "supabase_config.json must be a JSON object."
        config = raw
    else:
        url = os.environ.get("SUPABASE_URL", "").strip()
        anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
        if url or anon_key:
            source = "environment variables"
            config = {"url": url, "anon_key": anon_key}
    if config is None:
        return None, None
    url = config.get("url")
    anon_key = config.get("anon_key")
    if not isinstance(url, str) or not url.strip():
        return None, f"Supabase URL is missing ({source})."
    if not isinstance(anon_key, str) or not anon_key.strip():
        return None, f"Supabase anon key is missing ({source})."
    url = url.strip()
    anon_key = anon_key.strip()
    if "PASTE" in url or "PASTE" in anon_key or url == "..." or anon_key == "...":
        return None, (
            f"supabase_config.json still has placeholder values ({source}) "
            "— paste the real project URL and anon key."
        )
    if not _URL_RE.match(url):
        return None, f"Supabase URL does not look like a URL ({source})."
    return {"url": url, "anon_key": anon_key}, None


def _detect_backend() -> tuple[str, str | None]:
    config, warning = _load_supabase_config()
    if config is None:
        return "local", warning
    global _SUPABASE_CONFIG
    _SUPABASE_CONFIG = config
    # NOTE: no network call here — reachability is checked lazily by
    # _ensure_health(), so a paused project never slows down startup
    # and never flips the backend to local by surprise.
    return "supabase", None


def get_auth_backend() -> str:
    """Return 'supabase' or 'local'. Decision is cached per process."""
    global _BACKEND, _BACKEND_WARNING
    if _BACKEND is None:
        _BACKEND, _BACKEND_WARNING = _detect_backend()
    return _BACKEND


def get_backend_warning() -> str | None:
    """Why local mode is active, or why Supabase is degraded, if any.

    In Supabase mode this runs one cached health check (a tiny real
    query) and reports a paused project or missing tables in plain
    words instead of crashing.
    """
    get_auth_backend()
    if _BACKEND == "local":
        return _BACKEND_WARNING
    health = _ensure_health()
    if health == "ok":
        return None
    if health == "paused":
        return PAUSED_MESSAGE
    if health == "setup":
        return SETUP_MESSAGE
    return health  # a plain-word message from the health check


def get_local_mode_banner() -> str | None:
    """Banner text for local mode, or None when Supabase is active."""
    return LOCAL_MODE_BANNER if get_auth_backend() == "local" else None


def _reset_backend_cache() -> None:
    """Test helper: forget the cached backend decision (and client)."""
    global _BACKEND, _BACKEND_WARNING, _SUPABASE_CONFIG
    global _SUPABASE_CLIENT, _HEALTH, _GOOGLE_URL
    _BACKEND = None
    _BACKEND_WARNING = None
    _SUPABASE_CONFIG = None
    _SUPABASE_CLIENT = None
    _HEALTH = None
    _GOOGLE_URL = None


# ---------------------------------------------------------------------------
# LOCAL BACKEND — SQLite (original design, unchanged semantics)
# ---------------------------------------------------------------------------

def _local_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _local_init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        """
    )
    conn.commit()


def _local_ensure_db() -> sqlite3.Connection:
    conn = _local_connect()
    _local_init_db(conn)
    return conn


def _local_row_to_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": None,
        "created_at": row["created_at"],
    }


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    ).hex()


def _local_create_user(username, password) -> tuple[bool, str | None]:
    if not isinstance(username, str) or not _USERNAME_RE.match(username):
        return False, "Username must be 3-30 characters, letters, digits or underscore only."
    if not isinstance(password, str) or len(password) < 8:
        return False, "Password must be at least 8 characters."
    salt = secrets.token_bytes(16)
    password_hash = _hash_password(password, salt)
    try:
        conn = _local_ensure_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, created_at)"
                " VALUES (?, ?, ?, ?)",
                (username, password_hash, salt.hex(), _iso(_utcnow())),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.IntegrityError:
        return False, "Username already taken."
    except sqlite3.Error:
        return False, "Could not create user (database error)."
    return True, None


def _local_authenticate(username, password) -> dict | None:
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    try:
        conn = _local_ensure_db()
        try:
            row = conn.execute(
                "SELECT id, username, password_hash, salt, created_at"
                " FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    try:
        salt = bytes.fromhex(row["salt"])
    except (ValueError, TypeError):
        return None
    if not secrets.compare_digest(_hash_password(password, salt), row["password_hash"]):
        return None
    return _local_row_to_user(row)


def _local_create_session(user_id) -> str | None:
    if not isinstance(user_id, int):
        return None
    if _local_get_user_by_id(user_id) is None:
        return None
    token = secrets.token_urlsafe(32)
    now = _utcnow()
    try:
        conn = _local_ensure_db()
        try:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at)"
                " VALUES (?, ?, ?, ?)",
                (token, user_id, _iso(now), _iso(now + SESSION_TTL)),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return token


def _local_validate_session(token) -> dict | None:
    if not isinstance(token, str) or not token:
        return None
    try:
        conn = _local_ensure_db()
        try:
            row = conn.execute(
                "SELECT s.user_id, s.expires_at, u.id, u.username, u.created_at"
                " FROM sessions s JOIN users u ON u.id = s.user_id"
                " WHERE s.token = ?",
                (token,),
            ).fetchone()
            if row is None:
                return None
            expires = _parse_iso(row["expires_at"])
            if expires is None or expires <= _utcnow():
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                return None
            return {
                "id": row["id"],
                "username": row["username"],
                "email": None,
                "created_at": row["created_at"],
            }
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def _local_delete_session(token) -> None:
    if not isinstance(token, str) or not token:
        return
    try:
        conn = _local_ensure_db()
        try:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        return


def _local_get_user_by_id(user_id) -> dict | None:
    if not isinstance(user_id, int):
        return None
    try:
        conn = _local_ensure_db()
        try:
            row = conn.execute(
                "SELECT id, username, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return _local_row_to_user(row)


# ---------------------------------------------------------------------------
# SUPABASE BACKEND — Supabase Auth + Postgres (profiles/sessions tables)
#
# How the pieces fit (all free-tier):
#   * Passwords live ONLY in Supabase Auth (auth.users) — this module
#     never sees or stores a password hash.
#   * The app-facing user record lives in public.profiles
#     (id uuid = auth user id, email, created_at).
#   * App sessions are server-side opaque tokens (7-day expiry) in
#     public.sessions (token, user_id, created_at, expires_at).
#   * The anon key CANNOT read or write profiles/sessions directly:
#     RLS is enabled with no permissive policies, so direct table
#     access is denied. All reads/writes go through SECURITY DEFINER
#     Postgres functions (supabase_setup.sql) called via client.rpc():
#     app_upsert_profile, app_get_profile, app_create_session,
#     app_validate_session, app_delete_session, app_ping. The functions
#     run with the database owner's rights and only do the one narrow
#     job each — the anon key plus RLS does the authorisation, and no
#     service-role key is needed anywhere in auth.
# ---------------------------------------------------------------------------

def _get_client():
    """Create (once) and return the supabase-py client, or raise.

    Raises AuthServiceError when the package is missing or the client
    cannot be built — that is a service error, never a login failure.
    """
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT
    get_auth_backend()
    if _SUPABASE_CONFIG is None:
        raise AuthServiceError("Supabase is not configured.")
    try:
        from supabase import create_client
    except ImportError as exc:
        raise AuthServiceError(f"supabase package is not installed: {exc}")
    try:
        _SUPABASE_CLIENT = create_client(
            _SUPABASE_CONFIG["url"], _SUPABASE_CONFIG["anon_key"]
        )
    except Exception as exc:
        raise AuthServiceError(f"Could not start the Supabase client: {exc}")
    return _SUPABASE_CLIENT


def _is_network_error(exc: Exception) -> bool:
    """True when the failure looks like an unreachable/paused project
    (transport failure, DNS, timeout, or a 502/503/504 from the host)
    rather than a bad request or a missing table."""
    try:
        import httpx
    except ImportError:
        httpx = None  # type: ignore[assignment]
    if httpx is not None and isinstance(
        exc, (httpx.TransportError, httpx.TimeoutException)
    ):
        return True
    if isinstance(exc, (ConnectionError, OSError, TimeoutError)):
        return True
    text = str(exc)
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in (502, 503, 504, "502", "503", "504"):
        return True
    lowered = text.lower()
    for marker in ("connection refused", "name or service not known",
                   "temporary failure in name resolution", "timed out",
                   "network is unreachable", "connection reset",
                   "failed to establish a new connection", "503", "502"):
        if marker in lowered:
            return True
    return False


def _is_missing_table_error(exc: Exception) -> bool:
    """True when PostgREST says the table/function is not there yet —
    i.e. supabase_setup.sql has not been run in the SQL editor."""
    text = str(exc)
    return (
        "PGRST205" in text  # could not find the table
        or "PGRST202" in text  # could not find the function
        or "relation" in text and "does not exist" in text
        or "function" in text and "does not exist" in text
        or "Could not find the table" in text
        or "Could not find the function" in text
    )


def _classify_error(exc: Exception, action: str) -> AuthServiceError:
    """Turn a supabase-py failure into a plain-word AuthServiceError."""
    if _is_network_error(exc):
        return AuthServiceError(
            f"{PAUSED_MESSAGE} (could not reach Supabase while {action})."
        )
    if _is_missing_table_error(exc):
        return AuthServiceError(
            f"{SETUP_MESSAGE} (failed while {action})."
        )
    msg = str(exc) or type(exc).__name__
    if "captcha" in msg.lower():
        # Supabase rejected the Turnstile check (spent/missing token
        # or a failed verification). Never expose the raw error.
        return CaptchaFailedError(CAPTCHA_FAILED_MESSAGE)
    if "invalid api key" in msg.lower() or "jwt" in msg.lower():
        return AuthServiceError(
            "Supabase rejected the anon key — check supabase_config.json "
            f"(failed while {action})."
        )
    return AuthServiceError(f"Supabase error while {action}: {msg}")


def _ensure_health() -> str:
    """One cached health check: a tiny real RPC call (app_get_profile).

    The check goes through the SECURITY DEFINER function on purpose:
    the profiles/sessions tables deliberately grant nothing to the
    anon role (direct SELECTs fail with 42501 by design), so a direct
    table SELECT here would report a healthy project as broken.

    Returns "ok", "paused", "setup", or a plain-word message. A paused
    free project fails here (connection refused / 5xx); a project
    whose tables were never created fails with the setup message.
    """
    global _HEALTH
    if _HEALTH is not None:
        return _HEALTH
    try:
        client = _get_client()
    except AuthServiceError as exc:
        _HEALTH = str(exc)
        return _HEALTH
    try:
        # Nil UUID: never matches a real user, so a healthy project
        # answers None; a missing setup fails (PGRST202 / 42P01).
        client.rpc(
            "app_get_profile",
            {"p_id": "00000000-0000-0000-0000-000000000000"},
        ).execute()
    except Exception as exc:  # noqa: BLE001 - classified below
        if _is_network_error(exc):
            _HEALTH = "paused"
        elif _is_missing_table_error(exc):
            _HEALTH = "setup"
        else:
            _HEALTH = str(_classify_error(exc, "checking the project"))
        return _HEALTH
    _HEALTH = "ok"
    return _HEALTH


def supabase_keepalive() -> bool:
    """Run one tiny real query via the app_get_profile RPC function.

    Used by the scheduler (scheduler.py) as the keep-alive: a free
    Supabase project pauses after 1 week of inactivity, and the pause
    clock is reset by REAL database activity, not by opening the app.
    The RPC is used on purpose — the profiles table deliberately
    grants nothing to the anon role, so a direct SELECT would fail
    with 42501 on a healthy project. Returns True when the query ran,
    False on any failure. Never raises — the scheduler logs the result
    and carries on.
    """
    try:
        if get_auth_backend() != "supabase":
            return False
        client = _get_client()
        client.rpc(
            "app_get_profile",
            {"p_id": "00000000-0000-0000-0000-000000000000"},
        ).execute()
    except Exception:  # noqa: BLE001 - keep-alive must never crash the caller
        return False
    return True


def _sb_user_dict(user_id: str, email: str, created_at: str | None) -> dict:
    return {
        "id": user_id,
        "username": email,
        "email": email,
        "created_at": created_at or _iso(_utcnow()),
    }


def _sb_rpc(function: str, params: dict, action: str):
    """Call a SECURITY DEFINER function; return its .data.

    Raises AuthServiceError (classified) on any failure.
    """
    client = _get_client()
    try:
        resp = client.rpc(function, params).execute()
    except Exception as exc:  # noqa: BLE001 - classified below
        raise _classify_error(exc, action)
    return resp.data


def _sb_upsert_profile(user_id: str, email: str) -> dict:
    """Create/update the profiles row; return the user dict."""
    data = _sb_rpc(
        "app_upsert_profile",
        {"p_id": user_id, "p_email": email},
        "saving the user record",
    )
    if isinstance(data, dict) and data.get("id"):
        return _sb_user_dict(str(data["id"]), data.get("email") or email,
                             data.get("created_at"))
    if isinstance(data, list) and data and isinstance(data[0], dict):
        row = data[0]
        return _sb_user_dict(str(row["id"]), row.get("email") or email,
                             row.get("created_at"))
    # The function ran but returned nothing usable — fall back to the
    # values we already know rather than failing the login.
    return _sb_user_dict(user_id, email, None)


def _sb_create_user(email, password, captcha_token=None) -> tuple[bool, str | None]:
    if not isinstance(email, str) or not _EMAIL_RE.match(email):
        return False, "Enter a valid email address."
    if not isinstance(password, str) or len(password) < 8:
        return False, "Password must be at least 8 characters."
    client = _get_client()
    # The token rides INSIDE the credentials dict, under options.
    # captcha_token is NotRequired in supabase-py's types: omit
    # `options` entirely when there is no token (local runs and
    # deploys without Turnstile configured must send exactly what
    # they sent before).
    credentials = {"email": email, "password": password}
    if captcha_token:
        credentials["options"] = {"captcha_token": captcha_token}
    try:
        resp = client.auth.sign_up(credentials)
    except Exception as exc:  # noqa: BLE001 - classified below
        err = _classify_error(exc, "signing up")
        raise err
    user = getattr(resp, "user", None)
    if user is None:
        return False, "Could not create the account — please try again."
    # Supabase answers a duplicate email with a user that has no
    # identities (it must not confirm whether an email is registered).
    identities = getattr(user, "identities", None)
    if isinstance(identities, list) and not identities:
        return False, "Email already registered."
    user_id = str(getattr(user, "id", "") or "")
    if not user_id:
        return False, "Could not create the account — please try again."
    # Whether the new account still needs its email confirmed:
    # with "Confirm email" ON, Supabase answers the sign-up with no
    # session and email_confirmed_at unset, and sign-in stays blocked
    # until the user clicks the link in their inbox. With confirmation
    # OFF the sign-up comes back with a session and a confirmed email.
    # Either positive sign counts as confirmed; anything else means
    # the account needs the inbox step first.
    _confirmed = (getattr(resp, "session", None) is not None
                  or bool(getattr(user, "email_confirmed_at", None)))
    try:
        _sb_upsert_profile(user_id, email)
    except AuthServiceError:
        raise
    if not _confirmed:
        return True, SIGNUP_NEEDS_CONFIRMATION
    return True, None


def _sb_authenticate(email, password, captcha_token=None) -> dict | None:
    """Sign in via Supabase Auth.

    Returns the user dict on success, None on wrong email/password.
    Raises EmailNotConfirmedError (an AuthServiceError subclass) when
    the email is not confirmed yet, CaptchaFailedError when the
    Turnstile check fails, and AuthServiceError if Supabase is
    unreachable/misconfigured — neither is a wrong password and
    each must be shown as its own message.
    """
    if not isinstance(email, str) or not isinstance(password, str):
        return None
    client = _get_client()
    # Same shape as sign-up: the token rides in options, omitted
    # entirely when there is none.
    credentials = {"email": email, "password": password}
    if captcha_token:
        credentials["options"] = {"captcha_token": captcha_token}
    try:
        resp = client.auth.sign_in_with_password(credentials)
    except Exception as exc:  # noqa: BLE001 - classified below
        msg = str(exc)
        lowered = msg.lower()
        if "invalid login credentials" in lowered:
            return None
        if "email not confirmed" in lowered:
            raise EmailNotConfirmedError(
                "Email not confirmed — check your inbox for the "
                "confirmation link, then try again."
            )
        raise _classify_error(exc, "signing in")
    user = getattr(resp, "user", None)
    if user is None:
        return None
    user_id = str(getattr(user, "id", "") or "")
    if not user_id:
        return None
    return _sb_upsert_profile(user_id, getattr(user, "email", None) or email)


def _sb_create_session(user_id) -> str | None:
    if not isinstance(user_id, str) or not user_id:
        return None
    if _sb_get_user_by_id(user_id) is None:
        return None
    token = secrets.token_urlsafe(32)
    now = _utcnow()
    _sb_rpc(
        "app_create_session",
        {
            "p_token": token,
            "p_user_id": user_id,
            "p_created_at": _iso(now),
            "p_expires_at": _iso(now + SESSION_TTL),
        },
        "creating the session",
    )
    return token


def _sb_validate_session(token) -> dict | None:
    if not isinstance(token, str) or not token:
        return None
    data = _sb_rpc(
        "app_validate_session", {"p_token": token}, "checking the session"
    )
    user_id = None
    if isinstance(data, str) and data:
        user_id = data
    elif isinstance(data, list) and data:
        user_id = data[0]
    if not user_id:
        return None
    return _sb_get_user_by_id(str(user_id))


def _sb_delete_session(token) -> None:
    if not isinstance(token, str) or not token:
        return
    try:
        _sb_rpc("app_delete_session", {"p_token": token}, "ending the session")
    except AuthServiceError:
        return  # logout is best-effort; a dead backend must not block it


def _sb_get_user_by_id(user_id) -> dict | None:
    if not isinstance(user_id, str) or not user_id:
        return None
    data = _sb_rpc("app_get_profile", {"p_id": user_id}, "reading the user")
    row = None
    if isinstance(data, dict) and data.get("id"):
        row = data
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        row = data[0]
    if row is None:
        return None
    return _sb_user_dict(str(row["id"]), row.get("email") or "",
                         row.get("created_at"))


# ---------------------------------------------------------------------------
# BACKEND-AGNOSTIC PUBLIC API
# ---------------------------------------------------------------------------

def create_user(username_or_email, password, captcha_token=None) -> tuple[bool, str | None]:
    """Sign up. Local mode: identifier is a username (3-30 [a-zA-Z0-9_]).
    Supabase mode: identifier is an email address. Returns (ok, error).

    When ok is True and error is SIGNUP_NEEDS_CONFIRMATION, the
    account was created but the email is not confirmed yet — do NOT
    log the user in; tell them to check their inbox first. Local mode
    never returns that marker.

    Raises AuthServiceError in Supabase mode when the service is
    unreachable or the tables are not set up yet. Raises
    CaptchaFailedError when the Turnstile check fails (Supabase mode
    with CAPTCHA on). `captcha_token` is ignored in local mode, which
    has no security check.
    """
    if get_auth_backend() == "supabase":
        return _sb_create_user(username_or_email, password,
                               captcha_token=captcha_token)
    return _local_create_user(username_or_email, password)


def authenticate(email_or_username, password, captcha_token=None) -> dict | None:
    """Log in. Returns the user dict, or None for wrong credentials.

    Raises EmailNotConfirmedError (an AuthServiceError subclass) when
    the email is registered but not confirmed yet, CaptchaFailedError
    when the Turnstile check fails, and AuthServiceError when the
    Supabase backend is configured but unreachable — the app must
    show each as its own message, not as a wrong-password message.
    `captcha_token` is ignored in local mode.
    """
    if get_auth_backend() == "supabase":
        return _sb_authenticate(email_or_username, password,
                                captcha_token=captcha_token)
    return _local_authenticate(email_or_username, password)


def create_session(user_id) -> str | None:
    """Create a 7-day server-side session token. Returns the token or None.

    Raises AuthServiceError in Supabase mode if the sessions table is
    unreachable.
    """
    if get_auth_backend() == "supabase":
        return _sb_create_session(user_id)
    return _local_create_session(user_id)


def validate_session(token) -> dict | None:
    """Return the user dict for a live session token, else None.

    Raises AuthServiceError in Supabase mode if the service is
    unreachable.
    """
    if get_auth_backend() == "supabase":
        return _sb_validate_session(token)
    return _local_validate_session(token)


def delete_session(token) -> None:
    """Invalidate a session token. No-op for unknown/invalid tokens."""
    if get_auth_backend() == "supabase":
        _sb_delete_session(token)
    else:
        _local_delete_session(token)


def get_user_by_id(user_id) -> dict | None:
    """Return the user dict for an id (int in local mode, uuid str in
    Supabase mode), or None."""
    if get_auth_backend() == "supabase":
        return _sb_get_user_by_id(user_id)
    return _local_get_user_by_id(user_id)


# ---------------------------------------------------------------------------
# Google sign-in entry points (implemented in google_auth.py; the app
# looks for these names on THIS module — see app.py _consume_oauth_callback
# and the Google button block). Lazy imports avoid a circular import:
# google_auth.py imports this module.
# ---------------------------------------------------------------------------

def get_google_sign_in_url(redirect_to=None) -> str | None:
    """Return the Supabase Google OAuth authorization URL, or None when
    Google sign-in is unavailable (local mode, or Supabase unreachable).
    See google_auth.get_google_sign_in_url for the full story."""
    import google_auth

    return google_auth.get_google_sign_in_url(redirect_to=redirect_to)


# Backwards-tolerant alias (app.py also accepts this name).
google_sign_in_url = get_google_sign_in_url


def handle_oauth_code(code) -> tuple[dict | None, str | None, str | None]:
    """Exchange a ?code=... OAuth callback for (user, session_token, error).
    See google_auth.handle_oauth_code for the full story."""
    import google_auth

    return google_auth.handle_oauth_code(code)


# Alias the app also accepts.
handle_google_callback = handle_oauth_code
exchange_oauth_code = handle_oauth_code
