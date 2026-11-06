"""Data Cleaner Studio — web version (Streamlit).

Port of the desktop .exe app (~/workspace/data-cleaner-studio/
simple_app.py, v1.4 feature set): load a messy file -> profile it ->
clean it -> KPIs -> dashboard -> report. Same engine, same cleaning
logic, same results as the .exe.

Web differences (all deliberate):
* PHASE 2 — SUPABASE WIRED IN. The cloud userbase is integrated:
  auth.py picks the Supabase backend whenever supabase_config.json
  (or SUPABASE_URL / SUPABASE_ANON_KEY) is present, and Settings
  shows the connection status. With no config the app still runs in
  LOCAL MODE (SQLite accounts) — local mode is the default, not a
  fallback error. No Supabase project exists yet, so the cloud path
  is structural only until the user creates the free project and
  adds the config (see README.md / DEPLOY.md section 0).
* AUTH GATE FIRST: nobody sees data without a valid session (auth.py —
  backend-agnostic API: create_user / authenticate / create_session /
  validate_session / delete_session). Sessions live in
  st.session_state and are validated with auth.validate_session on
  every run. The token is ALSO kept in a browser cookie (7 days, the
  same as auth.SESSION_TTL) so a page refresh does not log the user
  out — only the random token is stored, never a password. If the
  cookie library is missing, the app falls back to session-state-only
  behaviour. Passwords are never stored or logged. If the auth
  backend reports a problem, auth.get_backend_warning() says so
  plainly and the app shows that message instead of crashing.
* GOOGLE SIGN-IN: wired to auth.get_google_sign_in_url() /
  auth.handle_oauth_code() (Supabase Auth OAuth). In local mode
  those return None / a clean error, so the login screen shows a
  plain "needs Supabase" note instead of a button — never a crash.
  The button is ALSO gated on the GOOGLE_OAUTH_ENABLED flag
  (Streamlit secrets or environment, default OFF — only
  true/True/"true"/"1" switch it on), because the Google provider
  is not enabled in Supabase: with the flag off the button stays
  hidden even when Supabase is up. See _google_oauth_enabled().
  The OAuth callback (?code=...) is exchanged once and the code is
  cleared from the URL immediately (see _consume_oauth_callback).
  Google sign-in also needs Google enabled in the Supabase
  dashboard (Authentication -> Providers -> Google) — see DEPLOY.md.
* PER-USER STORAGE: every file operation goes through storage.py with
  the logged-in user's storage key (uploads/, cleaned/, recipes/,
  views/, workspaces/ under data/users/<key>/). Files persist across
  sessions. No file path is ever built from user input by hand.
* The .exe's app-folder files (settings.json, brand.json, views.json,
  recent.json, backups/, workspace/, versions.json) are repointed
  per user at login (see _apply_user_paths). NOTE: that repointing
  sets module-level paths, so it is per-process, not per-session —
  fine for one user at a time / low concurrency, but two users
  hitting the server in the same instant share those globals. The
  hard isolation (auth sessions, storage folders, share snapshots)
  does not depend on the globals.
* SHARING: a read-only dashboard link (?share=<token>) resolves to a
  stored snapshot only — never to a live file or another user's data.
* SETTINGS tab: backend status, API keys (your own Groq/Gemini keys,
  stored per user), white-label brand, scheduler jobs, share links.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

import ai_settings
import auth
import engine
import feat_analyse
import feat_automate
import feat_brand
import feat_combine
import feat_enrich
import feat_export
import feat_mobile
import feat_quality
import feat_schedule
import feat_share
import feat_tutorial
import scheduler
import storage
import turnstile_component

try:
    from auth import AuthServiceError
except ImportError:  # Cloud rework: fall back to a local stand-in
    class AuthServiceError(Exception):
        """Auth service error (fallback if auth.py does not define it)."""

st.set_page_config(page_title="Data Cleaner Studio", layout="wide")

_APP_DIR = Path(__file__).resolve().parent
_SHARES_FILENAME = "shares.json"
_STORAGE_KEY_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")

# The deployed app's public address, used for the full share link.
# Override it with the APP_PUBLIC_URL (or APP_URL) environment
# variable or Streamlit secret when the app moves to a new address.
# Default: the live Streamlit Community Cloud URL for this app.
_DEFAULT_APP_URL = "https://data-c-ak7dfcpvbzklkfn8gozels.streamlit.app"


def _app_base_url() -> str:
    """This app's public web address, for the full share link.

    APP_PUBLIC_URL / APP_URL (environment, then Streamlit secrets)
    wins when set; otherwise the known deployed URL above. Never a
    "<your-app>" placeholder — the example link must be openable."""
    raw = (os.environ.get("APP_PUBLIC_URL")
           or os.environ.get("APP_URL") or "").strip()
    if not raw:
        try:
            raw = str(st.secrets.get("APP_PUBLIC_URL", "")
                      or st.secrets.get("APP_URL", "") or "").strip()
        except Exception:  # noqa: BLE001 - no secrets file: use the default
            raw = ""
    return (raw or _DEFAULT_APP_URL).rstrip("/")


# ------------------------------------------------------------- sharing ----
def _find_share(token: str):
    """Resolve a share token to its stored snapshot dict, or None.

    Scans data/users/*/views/shares.json (read-only). The token maps
    to a stored snapshot — never to a live path or another user's
    files, so a shared link can only ever show what its owner saved
    into it at share time.
    """
    if not isinstance(token, str) or not token:
        return None
    base = storage.BASE_DIR
    if not base.is_dir():
        return None
    for user_dir in sorted(base.iterdir()):
        if not user_dir.is_dir():
            continue
        shares_file = user_dir / "views" / _SHARES_FILENAME
        if not shares_file.is_file():
            continue
        try:
            registry = json.loads(shares_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if isinstance(registry, dict) and token in registry:
            snap = registry.get(token)
            if isinstance(snap, dict):
                return snap
    return None


def _render_shared_dashboard(snapshot: dict) -> None:
    """Render ONLY a shared dashboard: no login, no sidebar, no data
    beyond the stored snapshot."""
    st.title(snapshot.get("title") or "Shared dashboard")
    st.caption(
        "Shared read-only view from Data Cleaner Studio. "
        f"Shared on {snapshot.get('created_at', 'an unknown date')}. "
        "This link shows a saved snapshot — it cannot open any other data.")
    kpis = snapshot.get("kpis") or []
    if kpis:
        cols = st.columns(3)
        for i, k in enumerate(kpis):
            if isinstance(k, dict):
                cols[i % 3].metric(str(k.get("label", "")),
                                   str(k.get("value", "")))
    rows = snapshot.get("rows") or []
    if rows:
        st.subheader("The numbers behind the chart")
        try:
            st.dataframe(pd.DataFrame(rows), width="stretch")
        except Exception:  # noqa: BLE001 - a bad snapshot must still render
            st.write(rows)
    else:
        st.info("This shared dashboard has no chart data saved in it.")


_share_token = None
try:
    _qp = st.query_params
    _share_token = _qp.get("share")
except Exception:  # noqa: BLE001 - no query params, no share link
    _share_token = None
if _share_token:
    _snap = _find_share(str(_share_token))
    if _snap is None or _snap.get("revoked"):
        st.error("This share link was revoked or does not exist.")
        st.write("Ask the person who shared it for a new link.")
        st.stop()
    _render_shared_dashboard(_snap)
    st.stop()


# ------------------------------------------------------- storage key ------
def _storage_key(user: dict) -> str:
    """The storage folder key for a user.

    Local mode: the username itself (already [a-zA-Z0-9_]{3,30}).
    Cloud mode: username == email, which storage.py rejects as a
    folder name — so use a stable hash-derived key instead
    ("u_" + first 20 hex chars of sha256(email)). Same user, same
    folder, every time; no two emails can collide in practice, and
    the key never contains the email itself.
    """
    name = str(user.get("username") or "")
    if _STORAGE_KEY_RE.match(name):
        return name
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:20]
    return f"u_{digest}"


def _apply_user_paths(user: dict, skey: str) -> dict:
    """Repoint every .exe-style app-folder file to this user's folder.

    Returns {"root", "ws_dir", "settings_path"} for the callers that
    need them. See the module docstring for the per-process caveat.
    """
    root = storage.user_root(skey)
    settings_path = root / "views" / "settings.json"
    ai_settings.SETTINGS_PATH = settings_path
    feat_analyse.VIEWS_FILE = root / "views" / "views.json"
    feat_analyse.SEEN_VERSION_FILE = root / "views" / "seen_version.json"

    def _versions_file(path=None):
        if path is not None:
            return Path(path)
        return root / "views" / "versions.json"

    feat_enrich._versions_file = _versions_file
    ws_dir = root / "workspaces"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return {"root": root, "ws_dir": ws_dir, "settings_path": settings_path}


# ------------------------------------------------------------- auth gate --
for key, default in [
    ("auth_token", None), ("current_user", None), ("storage_key", None),
    ("user_paths", None), ("auth_mode", "Log in"),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ------------------------------------------- login cookie (refresh-proof) --
# The session token ALSO lives in a browser cookie (7 days, the same
# as auth.SESSION_TTL) so refreshing the page does not log the user
# out. Only the random token is stored — never a password. If the
# cookie library is missing at runtime, the app falls back to the
# old session-state-only behaviour without crashing.
_AUTH_COOKIE = "dcs_auth_token"
_AUTH_COOKIE_MAX_AGE = 7 * 24 * 3600  # seconds; matches auth.SESSION_TTL

try:
    from streamlit_cookies_controller import CookieController
    _cookie_controller = CookieController()
except Exception:  # noqa: BLE001 - no cookie library: session-state only
    _cookie_controller = None


def _cookie_get(name):
    """Cookie value, or None when cookies are unavailable/empty."""
    if _cookie_controller is None:
        return None
    try:
        value = _cookie_controller.get(name)
    except Exception:  # noqa: BLE001 - a cookie read never crashes login
        return None
    return value if isinstance(value, str) and value else None


def _cookie_set(name, value):
    """Store a cookie: 7-day expiry, Secure, SameSite=Lax."""
    if _cookie_controller is None:
        return
    try:
        _cookie_controller.set(name, value, max_age=_AUTH_COOKIE_MAX_AGE,
                               secure=True, same_site="lax")
    except Exception:  # noqa: BLE001 - a cookie write never crashes login
        pass


def _cookie_clear(name):
    """Remove a cookie (same attributes it was set with)."""
    if _cookie_controller is None:
        return
    try:
        _cookie_controller.remove(name, secure=True, same_site="lax")
    except Exception:  # noqa: BLE001 - a cookie clear never crashes logout
        pass


def _remember_session(token):
    """Persist a login: session state AND the login cookie."""
    st.session_state["auth_token"] = token
    _cookie_set(_AUTH_COOKIE, token)


def _log_user_in(user):
    """Start a session for an authenticated user dict and persist it
    (session state + login cookie) — the one path the Log in button
    and the auto-login after sign-up both use. Returns True when the
    session is live, False when no session could be started (the
    caller shows the error)."""
    try:
        token = auth.create_session(user["id"])
    except AuthServiceError as exc:
        st.error(f"Account service error: {exc}")
        return False
    if not token:
        st.error("Could not start a session. Try again.")
        return False
    _remember_session(token)
    st.session_state["current_user"] = user
    st.session_state["storage_key"] = _storage_key(user)
    return True


def _restore_session_from_cookie():
    """On startup, when session state has no token: read the token
    from the login cookie and validate it with auth.validate_session.

    Returns the user dict when the cookie holds a live session (and
    restores session state), else None — and clears a dead/expired
    cookie so a stale token never lingers. Never raises."""
    if st.session_state.get("auth_token"):
        return None
    token = _cookie_get(_AUTH_COOKIE)
    if not token:
        return None
    try:
        user = auth.validate_session(token)
    except AuthServiceError:
        user = None
    except Exception:  # noqa: BLE001 - a broken backend never crashes login
        return None
    if user is None:
        _cookie_clear(_AUTH_COOKIE)
        return None
    st.session_state["auth_token"] = token
    st.session_state["current_user"] = user
    st.session_state["storage_key"] = _storage_key(user)
    return user


def _google_oauth_enabled() -> bool:
    """True only when Google OAuth is explicitly switched on.

    Flag: GOOGLE_OAUTH_ENABLED in Streamlit secrets or the
    environment. Only true/True/"true"/"1" count as on; anything
    else — including a missing flag — is OFF. Default OFF, because
    the Google provider is not enabled in the Supabase dashboard:
    with the flag off the "Continue with Google" button stays
    hidden instead of leading to a dead end.
    """
    raw = (os.environ.get("GOOGLE_OAUTH_ENABLED") or "").strip()
    if not raw:
        try:
            raw = str(st.secrets.get("GOOGLE_OAUTH_ENABLED", "") or "").strip()
        except Exception:  # noqa: BLE001 - no secrets file: not configured
            raw = ""
    return raw in ("true", "True", "1")


def _turnstile_site_key() -> str | None:
    """The Cloudflare Turnstile site key, or None when the check is off.

    Delegates to turnstile_component.get_site_key(): Streamlit secret
    TURNSTILE_SITE_KEY first, then the environment — the same shape
    as _google_oauth_enabled above. The key is public by design (it
    ships in the page); the secret key never lives here — it belongs
    in the Supabase dashboard (Authentication -> Attack Protection)
    and only matters once CAPTCHA is switched on there. Until a key
    is configured the login screen behaves exactly as before, with
    no widget and no token sent.
    """
    try:
        return turnstile_component.get_site_key()
    except Exception:  # noqa: BLE001 - no key, no widget
        return None


def _consume_oauth_callback() -> None:
    """Consume an OAuth redirect (?code=...) once, if one ever arrives.

    The auth module exposes handle_oauth_code (via auth.py, backed by
    google_auth.py): exchange the code for a user + session token and
    clear the code from the URL immediately, so it never lingers in
    the address bar, history or logs. In local mode the handler
    returns a clean error ("Google sign-in is not set up (local
    mode)") and no button exists to start the flow, so a stray ?code=
    is answered with a plain note. Never crashes on a bad callback.
    """
    try:
        _params = st.query_params
    except Exception:  # noqa: BLE001
        return
    _oauth_error = None
    try:
        _oauth_error = _params.get("error_description") or _params.get("error")
    except Exception:  # noqa: BLE001
        _oauth_error = None
    if _oauth_error:
        st.session_state["google_error"] = f"Google sign-in failed: {_oauth_error}"
        return
    try:
        code = _params.get("code")
    except Exception:  # noqa: BLE001
        return
    if not code:
        return
    try:
        del st.query_params["code"]
    except Exception:  # noqa: BLE001 - clearing is best-effort
        pass
    handler = (getattr(auth, "handle_oauth_code", None)
               or getattr(auth, "exchange_oauth_code", None)
               or getattr(auth, "handle_google_callback", None))
    if handler is None or not callable(handler):
        st.session_state["google_error"] = (
            "Google sign-in needs Supabase configured — add the "
            "Supabase details to the app's secrets (see README.md) "
            "and enable Google in the Supabase dashboard. "
            "Use email and password for now.")
        return
    try:
        user, session_token, error = handler(str(code))
    except AuthServiceError as exc:
        st.session_state["google_error"] = str(exc)
        return
    except Exception as exc:  # noqa: BLE001 - a bad callback never crashes
        st.session_state["google_error"] = f"Google sign-in failed: {exc}"
        return
    if error:
        st.session_state["google_error"] = error
        return
    if user is not None and session_token:
        _remember_session(session_token)
        st.session_state["current_user"] = user
        st.session_state["storage_key"] = _storage_key(user)


_consume_oauth_callback()

# A refresh wipes session state but not the login cookie: when there
# is no token in state, try to restore the session from the cookie
# before deciding the user is logged out.
_restore_session_from_cookie()

_current_user = None
if st.session_state.get("auth_token"):
    try:
        _current_user = auth.validate_session(st.session_state["auth_token"])
    except AuthServiceError as exc:
        st.error(f"Account service error: {exc}")
        _current_user = None
    if _current_user is None:
        st.session_state["auth_token"] = None
        st.session_state["current_user"] = None
        st.session_state["storage_key"] = None
        st.session_state["user_paths"] = None
    else:
        st.session_state["current_user"] = _current_user
        st.session_state["storage_key"] = _storage_key(_current_user)

if _current_user is None:
    # ---- login / signup screen ONLY. No data, no sidebar, no tabs. ----
    st.title("Data Cleaner Studio")
    st.write("Put in messy data. Get clean data, KPIs, charts and a report.")
    banner = auth.get_local_mode_banner()
    if banner:
        st.info(banner)
    warning = auth.get_backend_warning()
    if warning:
        st.warning(warning)
    backend = auth.get_auth_backend()
    if backend == "local":
        st.caption("Local mode — accounts live on this server only. "
                   "Cloud accounts need Supabase configured "
                   "(see Settings).")
    else:
        st.caption("Cloud accounts are active.")
    if st.session_state.get("google_error"):
        st.error(st.session_state.pop("google_error"))
    mode = st.radio("Account", ["Log in", "Sign up"], key="auth_mode",
                    horizontal=True)
    id_label = "Email" if backend != "local" else "Username"
    id_help = ("Your email address." if backend != "local"
               else "3–30 characters, letters, digits or underscore only.")
    ident = st.text_input(id_label, key="auth_id_input", help=id_help)
    password = st.text_input("Password", type="password",
                             key="auth_pw_input",
                             help="At least 8 characters.")
    # Turnstile security check (cloud mode + key configured only; local
    # mode has no check). One widget serves both Log in and Sign up:
    # it sits above the buttons, and its token rides to Supabase with
    # the submit. Tokens are single-use, so after every attempt the
    # counter below remounts the widget for a fresh token.
    _turnstile_key = _turnstile_site_key() if backend != "local" else None
    _turnstile_token = None
    if _turnstile_key:
        if "turnstile_counter" not in st.session_state:
            st.session_state["turnstile_counter"] = 0
        _turnstile_token = turnstile_component.turnstile_token(
            _turnstile_key,
            key=f"turnstile-{st.session_state['turnstile_counter']}",
            reset=st.session_state["turnstile_counter"],
        )
    if mode == "Log in":
        if st.button("Log in", key="auth_login_btn", type="primary"):
            if not ident.strip() or not password:
                st.error("Enter your email/username and password.")
            elif _turnstile_key and not _turnstile_token:
                st.error("Complete the security check above first.")
            else:
                _unconfirmed = False
                _captcha_failed = False
                with st.spinner("Logging you in…"):
                    try:
                        user = auth.authenticate(
                            ident.strip(), password,
                            captcha_token=_turnstile_token)
                    except auth.EmailNotConfirmedError:
                        # Registered but the email is not confirmed yet:
                        # neither a wrong password nor a service error.
                        st.error("Check your inbox — click the verification "
                                 "link first, then log in.")
                        user = None
                        _unconfirmed = True
                    except auth.CaptchaFailedError:
                        st.error(auth.CAPTCHA_FAILED_MESSAGE)
                        user = None
                        _captcha_failed = True
                    except AuthServiceError as exc:
                        st.error(f"Account service error: {exc}")
                        user = None
                # The token is spent now (single-use): the next
                # attempt gets a fresh widget.
                if _turnstile_key:
                    st.session_state["turnstile_counter"] = (
                        st.session_state.get("turnstile_counter", 0) + 1)
                if user is None:
                    if not _unconfirmed and not _captcha_failed:
                        st.error("Wrong email/username or password. Try again.")
                elif _log_user_in(user):
                    st.rerun()
    else:
        if st.button("Create account", key="auth_signup_btn", type="primary"):
            if not ident.strip() or not password:
                st.error("Enter an email/username and a password "
                         "(at least 8 characters).")
            elif _turnstile_key and not _turnstile_token:
                st.error("Complete the security check above first.")
            else:
                _captcha_failed = False
                with st.spinner("Creating your account…"):
                    try:
                        ok, error = auth.create_user(
                            ident.strip(), password,
                            captcha_token=_turnstile_token)
                    except auth.CaptchaFailedError:
                        st.error(auth.CAPTCHA_FAILED_MESSAGE)
                        ok, error = False, None
                        _captcha_failed = True
                    except AuthServiceError as exc:
                        st.error(f"Account service error: {exc}")
                        ok, error = False, None
                # The token is spent now (single-use): the next
                # attempt gets a fresh widget.
                if _turnstile_key:
                    st.session_state["turnstile_counter"] = (
                        st.session_state.get("turnstile_counter", 0) + 1)
                if not ok:
                    if not _captcha_failed:
                        st.error(error or "Could not create the account.")
                elif error == auth.SIGNUP_NEEDS_CONFIRMATION:
                    # The account exists but the email is not confirmed
                    # yet ("Confirm email" is on): no auto-login and no
                    # session cookie — the user must click the link in
                    # their inbox first.
                    st.success("Account created — check your inbox and click "
                               "the verification link first, then log in here.")
                else:
                    # Confirmed account (or local mode, which has no
                    # confirmation step): log the new user straight in,
                    # on the same session path the Log in button uses.
                    # If that ever fails, fall back to the old
                    # "switch to Log in" message.
                    _unconfirmed = False
                    _captcha_spent = False
                    with st.spinner("Logging you in…"):
                        try:
                            # Same token as the sign-up call: with
                            # CAPTCHA still off in Supabase it is
                            # ignored and the login succeeds; with
                            # CAPTCHA on it is spent (single-use) and
                            # the login asks for a fresh check instead
                            # — the account already exists, so the
                            # user just logs in with a new check.
                            user = auth.authenticate(
                                ident.strip(), password,
                                captcha_token=_turnstile_token)
                        except auth.EmailNotConfirmedError:
                            user = None
                            _unconfirmed = True
                        except auth.CaptchaFailedError:
                            user = None
                            _captcha_spent = True
                        except AuthServiceError:
                            user = None
                    if user is not None and _log_user_in(user):
                        st.session_state["just_signed_up"] = True
                        st.rerun()
                    elif _unconfirmed:
                        st.success("Account created — check your inbox and click "
                                   "the verification link first, then log in here.")
                    elif _captcha_spent:
                        st.success("Account created — log in with your new "
                                   "account.")
                    else:
                        st.success("Account created — switch to 'Log in' "
                                   "above and log in with it.")
    google_url = None
    _google_entry = (getattr(auth, "get_google_sign_in_url", None)
                     or getattr(auth, "google_sign_in_url", None))
    if callable(_google_entry):
        try:
            google_url = _google_entry()
        except Exception:  # noqa: BLE001 - no Google URL, show the note
            google_url = None
    if google_url and _google_oauth_enabled():
        st.write("— or —")
        st.link_button("Continue with Google", google_url)
    elif not google_url:
        # Local mode: get_google_sign_in_url() returns None, so there
        # is no button — show the plain-words reason instead.
        st.caption("Google sign-in needs Supabase configured first: "
                   "add the Supabase details to the app's secrets "
                   "(see README.md) and enable Google in the Supabase "
                   "dashboard. "
                   "For now, use email and password above.")
    # else: Supabase is up but GOOGLE_OAUTH_ENABLED is off (the
    # default) — the button stays hidden, no dead end, no note.
    st.stop()

# ---- logged in from here on. ----
_user = st.session_state["current_user"]
_skey = st.session_state["storage_key"]
_paths = _apply_user_paths(_user, _skey)
st.session_state["user_paths"] = _paths
_user_root = _paths["root"]
_ws_dir = _paths["ws_dir"]
_settings_path = _paths["settings_path"]

# ------------------------------------------------------- brand + mobile ---
# Theme first, brand second: with the default accent both agree, and
# a user-picked accent wins the tie on buttons and links.
try:
    _brand = feat_brand.load_brand(base_dir=_user_root)
except Exception:  # noqa: BLE001 - a broken brand file must not stop the app
    _brand = {"name": "Data Cleaner Studio",
              "accent": feat_brand.DEFAULT_ACCENT, "logo": None}
try:
    st.markdown(feat_mobile.mobile_css(), unsafe_allow_html=True)
except Exception:  # noqa: BLE001 - theme CSS must never stop the app
    pass
try:
    st.markdown(feat_brand.brand_css(
        _brand.get("accent", feat_brand.DEFAULT_ACCENT)),
        unsafe_allow_html=True)
except Exception:  # noqa: BLE001 - brand CSS must never stop the app
    pass

for key, default in [
    ("raw", None), ("clean", None), ("actions", None), ("kpis", None),
    ("source_name", ""), ("source_kind", "upload"), ("source_url", None),
    ("clean_opts", None), ("fuzzy_groups", None), ("fuzzy_col_used", None),
    ("join_result", None), ("auto_refresh", False), ("refresh_seconds", 900),
    ("q_audit", []), ("a_snaps", []), ("a_recipes", []),
    ("a_bulk_results", None), ("pending_excel", None),
    ("client_mode", False), ("an_pending_view", None),
    ("n_ws_fingerprint", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# Recipes persist per user (recipes/); restore them into the session.
# A storage failure here (e.g. Supabase Storage not configured yet)
# must never stop the app: a first-time user has no recipes anyway.
if not st.session_state.get("a_recipes"):
    try:
        _saved_recipes = storage.load_json(_skey, "recipes", "recipes.json")
    except Exception:  # noqa: BLE001 - missing recipes are not fatal
        _saved_recipes = None
    if isinstance(_saved_recipes, list):
        st.session_state["a_recipes"] = _saved_recipes

# ------------------------------------------------------- language + title ---
try:
    _lang = (st.session_state.get("n_lang_data")
             or ai_settings.load_settings().get("language", "en"))
except Exception:  # noqa: BLE001 - a broken settings file must not stop the app
    _lang = "en"
if _lang not in ("en", "hi", "ur"):
    _lang = "en"


def _t(key):
    return feat_enrich.get_text(key, _lang)


_title = (_brand.get("name") if _brand.get("name")
          and _brand["name"] != "Data Cleaner Studio" else _t("app_title"))
st.title(_title)
st.write("Put in messy data. Get clean data, KPIs, charts and a report.")
# The main flow, at a glance: upload -> clean -> KPIs -> export.
# One step is "you are here"; finished steps get a tick.
_flow_current = 2 if st.session_state.clean is None else 3
_flow_parts = []
for _i, _label in enumerate(["Upload", "Clean", "KPIs", "Export"], start=1):
    if _i < _flow_current:
        _flow_parts.append(f"{_label} ✓")
    elif _i == _flow_current:
        _flow_parts.append(f"**{_label}** — you are here")
    else:
        _flow_parts.append(_label)
st.caption("Your flow: " + " → ".join(_flow_parts))
if st.session_state.pop("just_signed_up", False):
    st.success("Account created — you're logged in. Welcome!")
feat_tutorial.render_first_run_banner(st, settings_path=_settings_path)
feat_analyse.render_whats_new(st, user_key=_skey)

# ------------------------------------------- workspace restore (startup) ---
_ws_marker = _ws_dir / "autosave.txt"
if "n_workspace_toggle" not in st.session_state:
    st.session_state["n_workspace_toggle"] = _ws_marker.exists()
if st.session_state.raw is None and _ws_marker.exists():
    try:
        _ws_restored = feat_enrich.load_workspace(base_dir=_ws_dir)
    except Exception:  # noqa: BLE001 - a broken workspace must not stop the app
        _ws_restored = None
    if _ws_restored is not None:
        st.session_state.raw = _ws_restored["raw"]
        st.session_state.clean = _ws_restored["clean"]
        st.session_state.actions = _ws_restored["actions"] or None
        st.session_state.kpis = _ws_restored["kpis"] or None
        st.session_state.source_name = _ws_restored["source_name"]
        st.session_state.source_kind = "workspace"


def _set_raw(df, name, kind="upload", url=None):
    st.session_state.raw = df
    st.session_state.clean = None
    st.session_state.actions = None
    st.session_state.kpis = None
    st.session_state.source_name = name
    st.session_state.source_kind = kind
    st.session_state.source_url = url
    st.session_state.clean_opts = None
    st.session_state.fuzzy_groups = None
    st.session_state.join_result = None
    st.session_state.q_audit = []
    st.session_state.a_snaps = []


def _audit(step, detail):
    feat_quality.record_audit(st.session_state, step, detail)


def _apply_new_clean(new_df, new_actions, audit_step=None, replace_actions=False):
    """Apply a cleaned frame returned by a render function: snapshot the
    old state first (so Undo works), then update clean/actions/KPIs.
    Recipes/templates clean from raw, so they replace the log; the other
    fix-ups build on the current clean data, so they append to it."""
    feat_automate.push_snapshot(st.session_state, audit_step or "Before change")
    st.session_state.clean = new_df
    if replace_actions:
        st.session_state.actions = new_actions
    else:
        st.session_state.actions = st.session_state.actions + new_actions
    st.session_state.kpis = engine.auto_kpis(new_df)
    if audit_step:
        _audit(audit_step, f"{len(new_df):,} rows")
    return new_df


def _apply_pending_view(view):
    """Apply a saved view (from render_saved_views) before its widgets
    are created this run: chart choice, group-by/number columns and
    slicer values. Invalid values are skipped, never forced."""
    if not isinstance(view, dict) or st.session_state.clean is None:
        return
    clean_now = st.session_state.clean
    cols = list(clean_now.columns)
    ct = view.get("chart_type")
    if ct in ("Bar", "Line", "Donut", "Histogram", "Scatter", "Box plot",
              "Heatmap", "Treemap", "Funnel"):
        st.session_state["chart_type"] = ct
    _key_map = {"Bar": ("dash_x", "dash_y"), "Line": ("dash_x", "dash_y"),
                "Donut": ("dash_x", "dash_y"), "Histogram": (None, "hist_col"),
                "Scatter": ("sc_x", "sc_y"), "Box plot": ("box_x", "box_y"),
                "Treemap": ("tm_x", "tm_y"), "Funnel": ("fn_x", "fn_y")}
    if ct in _key_map:
        gx, ny = _key_map[ct]
        gb, nc = view.get("group_by"), view.get("num_col")
        if gx and gb in cols:
            st.session_state[gx] = gb
        if ny and nc in cols:
            st.session_state[ny] = nc
    slicers = view.get("slicers") or {}
    if isinstance(slicers, dict):
        for col, vals in slicers.items():
            if col in cols and isinstance(vals, list):
                allowed = set(clean_now[col].dropna().unique())
                valid = [v for v in vals if v in allowed]
                if valid:
                    st.session_state[f"slice_{col}"] = valid


def _save_cleaned_copy(df, source_name):
    """Best-effort: persist the cleaned frame to cleaned/ so it
    survives the session, plus a small state file (actions, KPIs,
    clean options) so reopening the file restores the cleaned data
    too instead of only the raw file. Never stops the app when it
    fails."""
    try:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(source_name or "data"))
        storage.save_file(_skey, "cleaned", f"cleaned_{safe}.csv",
                          df.to_csv(index=False).encode("utf-8"))
        storage.save_json(_skey, "cleaned", f"cleaned_{safe}.state", {
            "source_name": str(source_name or ""),
            "actions": [[str(a), str(b)] for a, b in
                        (st.session_state.get("actions") or [])],
            "kpis": st.session_state.get("kpis") or [],
            "clean_opts": st.session_state.get("clean_opts"),
        })
    except Exception:  # noqa: BLE001 - saving a copy must never stop the app
        pass


def _restore_cleaned_state(source_name):
    """Best-effort: restore the cleaned frame + KPIs saved by
    _save_cleaned_copy for this source file. Returns True when the
    cleaned state was restored, False otherwise (the caller then
    says plainly that only the raw file came back). Never raises."""
    try:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(source_name or "data"))
        state = storage.load_json(_skey, "cleaned", f"cleaned_{safe}.state")
        if not isinstance(state, dict):
            return False
        raw_bytes = storage.read_file(_skey, "cleaned", f"cleaned_{safe}.csv")
        cleaned = engine.load_file(f"cleaned_{safe}.csv", raw_bytes)
        st.session_state.clean = cleaned
        st.session_state.actions = (
            [(str(a), str(b)) for a, b in (state.get("actions") or [])]
            or None)
        st.session_state.kpis = state.get("kpis") or engine.auto_kpis(cleaned)
        st.session_state.clean_opts = state.get("clean_opts")
        return True
    except Exception:  # noqa: BLE001 - a missing/broken copy is not fatal
        return False


# ------------------------------------------------------------------ load ---
_logo = feat_brand.brand_for_exports(base_dir=_user_root).get("logo")
if _logo:
    try:
        st.sidebar.image(_logo, width=140)
    except Exception:  # noqa: BLE001 - a bad logo must not stop the app
        pass
st.sidebar.write(f"Signed in as **{_user.get('username') or _user.get('email') or '?'}**")
if st.sidebar.button("Log out", key="logout_btn"):
    try:
        auth.delete_session(st.session_state.get("auth_token"))
    except AuthServiceError:
        pass
    _cookie_clear(_AUTH_COOKIE)
    for _k in ("auth_token", "current_user", "storage_key", "user_paths",
               "raw", "clean", "actions", "kpis", "active_tab"):
        st.session_state[_k] = None
    st.rerun()
_banner = auth.get_local_mode_banner()
if _banner:
    st.sidebar.info(_banner)

st.sidebar.header(_t("load") + " your data")

uploaded = st.sidebar.file_uploader(
    "Upload a file", type=["csv", "xlsx", "xls", "json", "parquet"],
    help="CSV, Excel, JSON or Parquet. Up to 1000MB.")
if uploaded is not None and st.session_state.get("last_upload") != uploaded.name:
    try:
        storage.save_upload(_skey, uploaded.name, uploaded.getvalue())
    except Exception as e:  # noqa: BLE001 - show the error, don't crash
        st.sidebar.error(f"Could not save that upload: {e}")
    if uploaded.name.lower().endswith((".xlsx", ".xls")):
        # Excel: hold the bytes and let the user pick a sheet below.
        st.session_state["pending_excel"] = (uploaded.name, uploaded.getvalue())
        st.session_state["last_upload"] = uploaded.name
    elif uploaded.name.lower().endswith(".parquet"):
        try:
            _set_raw(engine.load_parquet(uploaded.getvalue()),
                     uploaded.name)
            st.session_state["last_upload"] = uploaded.name
        except Exception as e:  # noqa: BLE001 - show the error, don't crash
            st.sidebar.error(f"Could not read that file: {e}")
    else:
        try:
            _set_raw(engine.load_file(uploaded.name, uploaded.getvalue()),
                     uploaded.name)
            st.session_state["last_upload"] = uploaded.name
        except Exception as e:  # noqa: BLE001 - show the error, don't crash
            st.sidebar.error(f"Could not read that file: {e}")

if st.session_state.get("pending_excel"):
    ex_name, ex_bytes = st.session_state["pending_excel"]
    try:
        ex_sheets = feat_combine.list_excel_sheets(ex_bytes)
    except Exception as e:  # noqa: BLE001
        st.sidebar.error(f"Could not read that workbook: {e}")
        ex_sheets = []
    if ex_sheets:
        ex_choice = st.sidebar.selectbox(
            "Sheet", ex_sheets + ["All sheets combined"], key="excel_sheet_pick")
        if st.sidebar.button("Load sheet", key="excel_sheet_load"):
            try:
                if ex_choice == "All sheets combined":
                    ex_df, _ = feat_combine.load_excel_all(ex_bytes)
                    _set_raw(ex_df, f"{ex_name} (all sheets)")
                else:
                    _set_raw(feat_combine.load_excel_sheet(ex_bytes, ex_choice),
                             f"{ex_name} : {ex_choice}")
                st.session_state["pending_excel"] = None
            except Exception as e:  # noqa: BLE001
                st.sidebar.error(f"Could not load that sheet: {e}")

if st.sidebar.button(_t("try_sample"), key="sample_btn"):
    _sample_path = _APP_DIR / "sample_data" / "messy_sales.csv"
    with st.spinner("Loading the sample file…"):
        _set_raw(engine.load_file("messy_sales.csv",
                                  _sample_path.read_bytes()),
                 "messy_sales.csv (sample)", kind="sample")
    st.session_state["last_upload"] = None

# Your saved uploads (per-user storage): re-open without uploading again.
try:
    _saved_uploads = storage.list_files(_skey, "uploads")
except Exception:  # noqa: BLE001
    _saved_uploads = []
if _saved_uploads:
    with st.sidebar.expander("Your saved files"):
        _saved_pick = st.sidebar.selectbox(
            "Open a saved upload", [""] + _saved_uploads,
            key="saved_upload_pick")
        _c1, _c2 = st.sidebar.columns(2)
        if _c1.button("Open", key="saved_upload_open",
                      disabled=not _saved_pick) and _saved_pick:
            try:
                _saved_bytes = storage.read_file(_skey, "uploads", _saved_pick)
                _set_raw(engine.load_file(_saved_pick, _saved_bytes),
                         _saved_pick, kind="upload")
                st.session_state["last_upload"] = None
                if _restore_cleaned_state(_saved_pick):
                    st.sidebar.success(
                        f"Opened {_saved_pick} — cleaned data restored too.")
                else:
                    st.sidebar.success(
                        f"Opened {_saved_pick}. Clean it in the Clean tab "
                        "to rebuild the KPIs and the report.")
            except Exception as e:  # noqa: BLE001
                st.sidebar.error(f"Could not open that file: {e}")
        if _c2.button("Delete", key="saved_upload_delete",
                      disabled=not _saved_pick) and _saved_pick:
            try:
                storage.delete_file(_skey, "uploads", _saved_pick)
                st.sidebar.success(f"Deleted {_saved_pick}.")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.sidebar.error(f"Could not delete that file: {e}")

with st.sidebar.expander("More ways to load"):
    sheet_url = st.text_input(
        "Google Sheets link (public sheet)",
        help="File -> Share -> Anyone with the link. Paste the link here.")
    if st.button("Load sheet", key="sheet_btn"):
        if not sheet_url.strip():
            st.error("Paste a Google Sheets link first — "
                     "File -> Share -> Anyone with the link, then "
                     "paste the link here.")
        else:
            try:
                _set_raw(engine.load_sheets_url(sheet_url.strip()), "Google Sheet",
                         kind="sheets", url=sheet_url.strip())
                st.session_state["last_upload"] = None
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not load that sheet: {e}")

    st.write("... or a database file")
    db_file = st.file_uploader(
        "SQLite database (.db)", type=["db", "sqlite", "sqlite3"],
        help="A SQLite database file — pick one of its tables to load.")
    if db_file is not None:
        try:
            tables = engine.list_sqlite_tables(db_file.getvalue())
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read that database: {e}")
            tables = []
        if tables:
            table = st.selectbox("Table", tables, key="db_table")
            if st.button("Load table", key="db_load"):
                try:
                    _set_raw(engine.load_sqlite(db_file.getvalue(), table),
                             f"{db_file.name} : {table}")
                    st.session_state["last_upload"] = None
                except Exception as e:  # noqa: BLE001
                    st.error(f"Could not load that table: {e}")

_last_raw_bytes = uploaded.getvalue() if uploaded is not None else None
_reopened = feat_share.render_recent(
    st, df=st.session_state.raw,
    source_name=st.session_state.source_name, raw_bytes=_last_raw_bytes,
    base_dir=_user_root, storage_key=_skey)
if _reopened is not None:
    _reopened_name = st.session_state.pop("s_recent_opened", None)
    _set_raw(_reopened, "Recent file (reopened)", kind="recent")
    if _reopened_name and _restore_cleaned_state(_reopened_name):
        st.sidebar.success(f"Opened {_reopened_name} — cleaned data "
                           "restored too.")
    elif _reopened_name:
        st.sidebar.info(f"Opened {_reopened_name}. Clean it in the Clean "
                        "tab to rebuild the KPIs and the report.")

feat_analyse.render_client_mode_toggle(st)

with st.sidebar.expander("Settings (API key)"):
    ai_settings.render_settings(st)

feat_enrich.render_theme_picker(st)
# Extra readable-contrast rules: the theme stylesheet already covers
# secondary buttons, but KPI metric values, file-uploader chips and
# info boxes still relied on Streamlit's faint defaults. Ink #23272E
# on warm neutrals; accent teal #2F5D5A for primary actions only.
# Injected AFTER the theme picker (which injects its own CSS), so
# these rules win. The section-switcher rules style the radio below
# as a tab bar; if Streamlit ever changes those selectors it
# degrades to a plain option row, still fully working.
st.markdown("""<style>
/* KPI metric values + labels: ink, never faint grey. */
div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] * {
  color: #23272E !important;
}
div[data-testid="stMetricLabel"], div[data-testid="stMetricLabel"] * {
  color: #6E6A61 !important;
}
/* File-uploader dropzone + uploaded-file chips: ink text on white. */
div[data-testid="stFileUploader"], div[data-testid="stFileUploader"] * {
  color: #23272E !important;
}
/* Info / success / warning / error boxes: every nested element ink. */
div[data-testid="stAlert"], div[data-testid="stAlert"] * {
  color: #23272E !important;
}
div[data-testid="stAlert"] a {
  color: #2F5D5A !important;
}
/* Section switcher (radio styled as a tab bar). */
div[data-testid="stRadio"] div[role="radiogroup"] {
  gap: 0.35rem !important;
}
div[data-testid="stRadio"] div[role="radiogroup"] label {
  background-color: #EFEDE8 !important;
  border: 1px solid #D9D4C9 !important;
  border-radius: 8px !important;
  padding: 0.35rem 0.9rem !important;
  color: #23272E !important;
}
div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
  background-color: #2F5D5A !important;
  border-color: #2F5D5A !important;
  color: #FFFFFF !important;
}
</style>""", unsafe_allow_html=True)
feat_enrich.render_language_picker(st)
_ws_on = feat_enrich.render_workspace_toggle(st)

# ---------------------------------------------------------- auto-refresh ---
raw = st.session_state.raw
if raw is not None and st.session_state.source_kind == "sheets":
    with st.sidebar.expander("Auto-refresh"):
        st.checkbox("Auto-refresh this sheet", value=False,
                    key="auto_refresh",
                    help="While the app is open, it re-checks the sheet "
                         "and updates the data and KPIs by itself.")
        if st.session_state.get("auto_refresh"):
            mins = st.selectbox(
                "Every", [5, 15, 30, 60], index=1, key="refresh_mins",
                format_func=lambda m: f"{m} minutes")
            st.session_state["refresh_seconds"] = mins * 60
        if st.button("Refresh now", key="refresh_now_btn"):
            try:
                opts = st.session_state.get("clean_opts")
                fresh = engine.load_sheets_url(st.session_state["source_url"])
                _set_raw(fresh, st.session_state["source_name"],
                         kind="sheets", url=st.session_state["source_url"])
                if opts:
                    cleaned, actions = engine.clean(
                        fresh, feat_automate.to_engine_opts(opts))
                    st.session_state["clean"] = cleaned
                    st.session_state["actions"] = actions
                    st.session_state["kpis"] = engine.auto_kpis(cleaned)
                    st.session_state["clean_opts"] = opts
                st.success("Refreshed.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Refresh failed: {e}")

if raw is None:
    st.info("Upload a file, load a Google Sheet, open a database table, "
            "or try the messy sample to begin.")
    st.stop()

if (st.session_state.get("auto_refresh")
        and st.session_state.source_kind == "sheets"
        and st.session_state.get("source_url")):
    @st.fragment(run_every=st.session_state.get("refresh_seconds", 900))
    def _auto_refresh():
        changed = False
        try:
            fresh = engine.load_sheets_url(st.session_state["source_url"])
            if not fresh.equals(st.session_state["raw"]):
                opts = st.session_state.get("clean_opts")
                st.session_state["raw"] = fresh
                if opts:
                    cleaned, actions = engine.clean(
                        fresh, feat_automate.to_engine_opts(opts))
                    st.session_state["clean"] = cleaned
                    st.session_state["actions"] = actions
                    st.session_state["kpis"] = engine.auto_kpis(cleaned)
                else:
                    st.session_state["clean"] = None
                    st.session_state["actions"] = None
                    st.session_state["kpis"] = None
                changed = True
        except Exception:  # noqa: BLE001 - a failed refresh just waits
            changed = False
        if changed:
            st.rerun()

    _auto_refresh()

clean = st.session_state.clean

# ---------------------------------------------- workspace auto-save check ---
if _ws_on:
    _fp = (st.session_state.source_name, len(raw),
           len(clean) if clean is not None else None,
           len(st.session_state.actions) if st.session_state.actions else None)
    if st.session_state.get("n_ws_fingerprint") != _fp:
        try:
            _ws_folder = feat_enrich.save_workspace(
                raw, clean, st.session_state.source_name,
                st.session_state.actions, st.session_state.kpis,
                base_dir=_ws_dir)
            (_ws_folder / "autosave.txt").write_text("on", encoding="utf-8")
            st.session_state["n_ws_fingerprint"] = _fp
        except Exception:  # noqa: BLE001 - auto-save must never stop the app
            pass
elif _ws_marker.exists():
    try:
        _ws_marker.unlink()
    except OSError:
        pass

# -------------------------------------------- apply a pending saved view ---
_pending_view = st.session_state.pop("an_pending_view", None)
if _pending_view:
    _apply_pending_view(_pending_view)

# --------------------------------------------------------------- slicers ---
st.sidebar.header("Filters (slicers)")
filtered = clean
if clean is not None:
    num_cols = engine.numeric_cols(clean)
    cat_cols = [c for c in clean.columns
                if str(clean[c].dtype) in ("object", "str")
                and clean[c].nunique() <= 50]
    date_cols = engine.date_cols(clean)
    for c in cat_cols:
        picked = st.sidebar.multiselect(
            f"{engine._pretty(c)}", sorted(clean[c].dropna().unique()),
            default=sorted(clean[c].dropna().unique()), key=f"slice_{c}")
        filtered = filtered[filtered[c].isin(picked)]
    if date_cols:
        dcol = date_cols[0]
        dmin, dmax = clean[dcol].min(), clean[dcol].max()
        start, end = st.sidebar.date_input(
            f"{engine._pretty(dcol)} range",
            value=(dmin.date(), dmax.date()), key=f"slice_{dcol}")
        if start and end:
            mask = (clean[dcol] >= pd.Timestamp(start)) & (
                clean[dcol] <= pd.Timestamp(end) + pd.Timedelta(days=1)
                - pd.Timedelta(seconds=1))
            filtered = filtered[mask]
    st.sidebar.caption(f"Showing {len(filtered):,} of {len(clean):,} rows")

_client = bool(st.session_state.get("client_mode", False))
# Main flow first (upload -> clean -> KPIs -> export), then the
# secondary views. Nothing removed — just ordered by how often it
# is used.
_tab_keys = ["preview", "clean", "kpis", "dashboard", "report",
             "join", "compare", "tools", "tutorial", "settings"]
if _client:
    _tab_keys = ["preview", "clean", "kpis", "dashboard", "report", "tutorial"]
_tab_labels = {"preview": _t("preview"), "join": _t("join"),
               "clean": _t("clean"), "kpis": _t("kpis"),
               "dashboard": _t("dashboard"), "compare": _t("compare"),
               "report": _t("report"), "tools": _t("tools"),
               "tutorial": _t("tutorial"), "settings": "Settings"}
# Section switcher: a horizontal radio, NOT st.tabs.
# Streamlit's tab selection is not sticky — it resets to the first
# tab after some actions (downloads, saves), yanking the user away
# from where they were. A radio IS sticky: its value lives in
# session state under "active_tab", survives every rerun, and can
# be set programmatically (e.g. back to the first section on
# logout). The CSS below (injected after the theme picker) styles
# the options as a tab bar; if those selectors ever stop matching
# a new Streamlit version it degrades to a plain option row, still
# fully working. `tab` stays a set of the available keys so the
# `if "join" in tab:` guards below keep working.
_tab_options = [_tab_labels[k] for k in _tab_keys]
if st.session_state.get("active_tab") not in _tab_options:
    st.session_state["active_tab"] = _tab_options[0]
_active_label = st.radio("Section", _tab_options, key="active_tab",
                         horizontal=True, label_visibility="collapsed")
_active_tab = next(k for k, v in _tab_labels.items()
                   if v == _active_label)
tab = set(_tab_keys)

# --------------------------------------------------------------- preview ---
if _active_tab == "preview":
    if _client and clean is not None:
        st.info(feat_analyse.client_summary(clean, st.session_state.kpis))
    if st.session_state.source_kind == "workspace":
        st.caption("Restored from your last auto-saved workspace.")
    st.subheader(f"Loaded: {st.session_state.source_name}")
    st.write(f"{len(raw):,} rows, {len(raw.columns)} columns")
    pasted = feat_enrich.render_paste(st)
    if pasted is not None:
        _set_raw(pasted, "Pasted table", kind="paste")
        raw = pasted
        clean = None
        filtered = None
    shown = feat_share.render_sort(st, raw)
    st.dataframe(shown.head(100), width="stretch")
    feat_share.render_search(st, raw)
    with st.expander("Search, filter & suggested fixes"):
        feat_enrich.render_filter_builder(st, raw)
        sugg_df, sugg_actions = feat_share.render_suggestions(st, raw)
        if sugg_df is not None:
            _set_raw(sugg_df, st.session_state.source_name)
            _audit("Suggestion applied",
                   sugg_actions[0][1] if sugg_actions else "Fix applied")
            raw = sugg_df
            clean = None
            filtered = None
    with st.expander("Health check & data dictionary"):
        profile = engine.profile(raw)
        st.subheader("Health check")
        st.write(f"Missing cells: {int(raw.isna().sum().sum()):,}  |  "
                 f"Duplicate rows: {int(raw.duplicated().sum())}")
        st.table(pd.DataFrame(profile))
        feat_quality.render_quality_panel(st, raw)
        feat_analyse.render_trust(st, raw)
        # One data dictionary, shown once: heading + table + download.
        # (render_dictionary would show the same table twice — once as
        # markdown, once as a dataframe — so the pieces are rendered
        # here directly from data_dictionary().)
        _dict_md, _dict_table = feat_quality.data_dictionary(raw)
        st.subheader("Data dictionary")
        st.dataframe(_dict_table, width="stretch")
        st.download_button("Download data dictionary (.md)",
                           _dict_md.encode("utf-8"),
                           file_name="data_dictionary.md",
                           key="q_dict_download")
        feat_export.render_column_charts(st, clean)

# ------------------------------------------------------------------ join ---
if "join" in tab:
    if _active_tab == "join":
        st.subheader("Join two files")
        st.write("Combine this file with a second one on a shared column — "
                 "like a customer ID or order ID. Nothing changes until you "
                 "press 'Use joined data'.")
        joined_file = st.file_uploader(
            "Second file (CSV, Excel or JSON)", type=["csv", "xlsx", "xls", "json"],
            key="join_upload")
        if joined_file is not None:
            try:
                right = engine.load_file(joined_file.name, joined_file.getvalue())
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not read that file: {e}")
                right = None
            if right is not None:
                c1, c2, c3 = st.columns(3)
                left_key = c1.selectbox("Key in this file", list(raw.columns),
                                        key="join_left_key")
                right_key = c2.selectbox("Key in second file", list(right.columns),
                                         key="join_right_key")
                how_label = c3.selectbox(
                    "How to join",
                    ["Left (keep all rows from this file)",
                     "Inner (only matching rows)",
                     "Outer (keep everything)"],
                    key="join_how")
                how = {"Left (keep all rows from this file)": "left",
                       "Inner (only matching rows)": "inner",
                       "Outer (keep everything)": "outer"}[how_label]
                if st.button("Preview join", key="join_preview_btn"):
                    try:
                        st.session_state["join_result"] = engine.join_frames(
                            raw, right, left_key, right_key, how)
                    except Exception as e:  # noqa: BLE001
                        st.error(str(e))
                preview = st.session_state.get("join_result")
                if preview:
                    joined, info = preview
                    st.write(f"Left: {info['left_rows']:,} rows  ·  "
                             f"Right: {info['right_rows']:,} rows  →  "
                             f"Joined: {info['joined_rows']:,} rows")
                    st.write(f"Matched keys: {info['matched_keys']:,}  ·  "
                             f"Only in this file: {info['left_only']:,}  ·  "
                             f"Only in second file: {info['right_only']:,}")
                    st.dataframe(joined.head(100), width="stretch")
                    if st.button("Use joined data", type="primary", key="join_use"):
                        _set_raw(joined,
                                 f"{st.session_state['source_name']} + {joined_file.name}")
                        st.session_state["join_result"] = None
                        _audit("Join", f"{info['joined_rows']:,} rows")
                        st.success("Joined — now clean it in the Clean tab.")

# ----------------------------------------------------------------- clean ---
if _active_tab == "clean":
    feat_automate.render_undo(st)
    restored = feat_share.render_backups(
        st, df=raw, source_name=st.session_state.source_name,
        base_dir=_user_root, storage_key=_skey,
        key_prefix="s_backup_clean")
    if restored is not None:
        _set_raw(restored,
                 st.session_state.source_name + " (restored from backup)")
        raw = restored
        clean = None
        filtered = None
    st.subheader("Clean my data")
    st.write("Tick what to fix, then press the button. Every fix is listed "
             "in the log below, so you can check the work.")
    opts = {
        "tidy_names": st.checkbox("Tidy column names", value=True),
        "strip": st.checkbox("Strip extra spaces from text", value=True),
        "drop_empty": st.checkbox("Drop empty columns and rows", value=True),
        "fix_numbers": st.checkbox("Fix numbers stored as text (₹, $, %, commas)",
                                   value=True),
        "parse_dates": st.checkbox("Parse dates", value=True),
        "fix_categories": st.checkbox("Set categories to one case", value=True),
        "drop_dupes": st.checkbox("Drop duplicate rows", value=True),
        "fill_missing": st.checkbox("Fill missing values", value=True),
    }
    if st.button(_t("clean_my_data"), type="primary", key="clean_btn"):
        feat_automate.push_snapshot(st.session_state, "Before cleaning")
        _opts = feat_automate.to_engine_opts(opts)
        with st.spinner("Cleaning your data…"):
            if (len(raw) > 100_000 and uploaded is not None
                    and uploaded.name.lower().endswith(".csv")):
                # Big file: clean in chunks (same result, less memory).
                cleaned, actions = engine.clean_csv_chunked(
                    uploaded.getvalue(), _opts)
            else:
                cleaned, actions = engine.clean(raw, _opts)
        st.session_state.clean = cleaned
        st.session_state.actions = actions
        st.session_state.kpis = engine.auto_kpis(cleaned)
        st.session_state.clean_opts = opts
        _audit("Clean", f"{len(raw):,} -> {len(cleaned):,} rows")
        _save_cleaned_copy(cleaned, st.session_state.source_name)
        clean = cleaned
        filtered = cleaned
    _samp = feat_enrich.render_sampling(
        st, raw,
        clean_opts=feat_automate.to_engine_opts(opts))
    if _samp is not None:
        _full_clean, _full_actions = engine.clean(raw, _samp["clean_opts"])
        feat_automate.push_snapshot(st.session_state, "Before sampling apply")
        st.session_state.clean = _full_clean
        st.session_state.actions = _full_actions
        st.session_state.kpis = engine.auto_kpis(_full_clean)
        _audit("Sampling applied to full file", f"{len(raw):,} rows")
        _save_cleaned_copy(_full_clean, st.session_state.source_name)
        clean = _full_clean
        filtered = _full_clean
    if clean is not None:
        st.success(f"Done: {len(raw):,} rows -> {len(clean):,} rows, "
                   f"{len(raw.columns)} -> {len(clean.columns)} columns.")
        st.subheader("What was fixed")
        for step, detail in st.session_state.actions:
            st.write(f"- **{step}:** {detail}")
        st.dataframe(clean.head(100), width="stretch")

        st.subheader("Fix similar names (fuzzy matching)")
        st.write("Finds misspellings like Aarav / Arav and Delhi / Dehli "
                 "and merges them into one spelling. You review the groups "
                 "first — nothing merges without your word.")
        text_cols = [c for c in clean.columns
                     if str(clean[c].dtype) in ("object", "str")
                     and 1 < clean[c].nunique() <= 500]
        if text_cols:
            fcol = st.selectbox("Column", text_cols, key="fuzzy_col")
            fthr = st.slider("How similar must names be? (higher = stricter)",
                             0.70, 0.95, 0.85, 0.01, key="fuzzy_thr")
            if st.button("Find similar names", key="fuzzy_find"):
                st.session_state["fuzzy_groups"] = engine.fuzzy_groups(
                    clean[fcol], fthr)
                st.session_state["fuzzy_col_used"] = fcol
            groups = st.session_state.get("fuzzy_groups")
            if groups is not None:
                if len(groups) == 0:
                    st.info("No similar names found in that column.")
                else:
                    for g in groups:
                        members = ", ".join(f"{v} ({n:,})"
                                            for v, n in g["members"])
                        st.write(f"→ **{g['canonical']}**: {members}")
                    if st.button("Merge these names",
                                 key="fuzzy_apply"):
                        mapping = {}
                        for g in groups:
                            for v, _ in g["members"][1:]:
                                mapping[v] = g["canonical"]
                        feat_automate.push_snapshot(
                            st.session_state, "Before fuzzy merge")
                        new_clean = engine.apply_fuzzy(
                            clean, st.session_state["fuzzy_col_used"], mapping)
                        st.session_state["clean"] = new_clean
                        st.session_state["actions"] = (
                            st.session_state["actions"]
                            + [(f"Fuzzy merge: {st.session_state['fuzzy_col_used']}",
                              f"{len(mapping)} spelling(s) merged")])
                        st.session_state["kpis"] = engine.auto_kpis(new_clean)
                        st.session_state["fuzzy_groups"] = None
                        _audit("Fuzzy merge",
                               f"{len(mapping)} spelling(s) merged")
                        clean = new_clean
                        filtered = new_clean
                        st.success(f"Merged {len(mapping)} spelling(s) into "
                                   "their main form.")
        else:
            st.info("No text column with a manageable number of values "
                    "in this file.")

        with st.expander("More fixes (column type, phones, special characters)"):
            _ov = feat_share.render_type_override(st, clean)
            if _ov is not None:
                _ov_col = st.session_state.get("s_type_col", "?")
                _ov_kind = st.session_state.get("s_type_kind", "?")
                clean = _apply_new_clean(
                    _ov, [("Column type override",
                           f"{_ov_col} forced to {_ov_kind}")],
                    "Column type override")
                filtered = clean
            _nd, _na = feat_share.render_standardize_phones(st, clean)
            if _nd is not None:
                clean = _apply_new_clean(_nd, _na, "Standardize phones")
                filtered = clean
            _nd, _na = feat_share.render_strip_specials(st, clean)
            if _nd is not None:
                clean = _apply_new_clean(_nd, _na, "Strip special characters")
                filtered = clean

        with st.expander("Recipes & templates"):
            new_df, new_actions = feat_automate.render_recipes(st, raw)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Recipe applied",
                                         replace_actions=True)
                filtered = clean
            new_df, new_actions = feat_automate.render_templates(st)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Template applied",
                                         replace_actions=True)
                filtered = clean
            _recipes = st.session_state.get("a_recipes") or []
            _picked_name = st.session_state.get("a_recipe_select")
            _recipe = (next((r for r in _recipes if r["name"] == _picked_name),
                            None) if _picked_name else None)
            _imported = feat_analyse.render_share_recipe(st, _recipe)
            if _imported is not None:
                _recipes[:] = [r for r in _recipes
                               if r["name"] != _imported["name"]]
                _recipes.append(_imported)
            # Persist recipes per user (recipes/recipes.json).
            try:
                storage.save_json(_skey, "recipes", "recipes.json",
                                  list(st.session_state.get("a_recipes") or []))
            except Exception:  # noqa: BLE001 - recipe save must never stop the app
                pass

        with st.expander("Fix values"):
            new_df, new_actions = feat_automate.render_find_replace(st, clean)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Find and replace")
                filtered = clean
            new_df, new_actions = feat_combine.render_calculated(st, clean)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Calculated column")
                filtered = clean
            new_df, new_actions = feat_quality.render_outliers(st, clean)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Outliers")
                filtered = clean
            new_df, new_actions = feat_quality.render_near_dupes(st, clean)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Near-duplicates merged")
                filtered = clean
            feat_quality.render_validation(st, clean)
            _nd, _na = feat_enrich.render_split_merge(st, clean)
            if _nd is not None:
                clean = _apply_new_clean(_nd, _na, "Split / merge columns")
                filtered = clean
            _nd, _na = feat_enrich.render_date_intelligence(st, clean)
            if _nd is not None:
                clean = _apply_new_clean(_nd, _na, "Date intelligence")
                filtered = clean
            _nd, _na = feat_enrich.render_currency(st, clean)
            if _nd is not None:
                clean = _apply_new_clean(_nd, _na, "Currency conversion")
                filtered = clean
            feat_enrich.render_masking(st, clean)

        with st.expander("Clean many files at once"):
            feat_automate.render_bulk(st)

# ------------------------------------------------------------------ KPIs ---
if _active_tab == "kpis":
    if clean is None:
        st.info("Clean the data first — the KPIs will appear here.")
    else:
        st.subheader("KPIs")
        kpis = engine.auto_kpis(filtered)
        cols = st.columns(3)
        for i, k in enumerate(kpis):
            cols[i % 3].metric(k["label"], k["value"])
        st.subheader("Build your own KPI")
        num_cols = engine.numeric_cols(clean)
        if num_cols:
            c1, c2, c3 = st.columns(3)
            kcol = c1.selectbox("Column", num_cols, key="kpi_col")
            kfn = c2.selectbox("Function",
                               ["Sum", "Average", "Count", "Min",
                                "Max", "Median"], key="kpi_fn")
            if c3.button("Add KPI", key="kpi_add"):
                value = engine.custom_kpi(filtered, kcol, kfn)
                st.session_state.kpis = st.session_state.kpis + [
                    {"label": f"{kfn} of {engine._pretty(kcol)}",
                     "value": f"{value:,.2f}"}]
            for k in st.session_state.kpis:
                if k["label"].startswith(("Sum of", "Average of", "Count of",
                                          "Min of", "Max of",
                                          "Median of")):
                    st.write(f"- **{k['label']}:** {k['value']}")
        feat_share.render_goal(st, filtered)
        feat_analyse.render_what_if(st, filtered)
        feat_enrich.render_ai_insights(st, filtered, st.session_state.kpis)

# -------------------------------------------------------------- dashboard ---
if _active_tab == "dashboard":
    if clean is None:
        st.info("Clean the data first — the charts will appear here.")
    else:
        import altair as alt

        st.subheader("Dashboard")
        st.write("The slicers on the left filter every chart and KPI here.")
        df = filtered
        num_cols = engine.numeric_cols(clean)
        cat_cols = [c for c in clean.columns
                    if str(clean[c].dtype) in ("object", "str")
                    and clean[c].nunique() <= 50]
        date_cols = engine.date_cols(clean)
        _ct_now = st.session_state.get("chart_type", "Bar")
        _gb_now = _nc_now = None
        if _ct_now in ("Bar", "Line", "Donut"):
            _gb_now = st.session_state.get("dash_x")
            _nc_now = st.session_state.get("dash_y")
        elif _ct_now == "Histogram":
            _nc_now = st.session_state.get("hist_col")
        elif _ct_now == "Scatter":
            _gb_now = st.session_state.get("sc_x")
            _nc_now = st.session_state.get("sc_y")
        elif _ct_now == "Box plot":
            _gb_now = st.session_state.get("box_x")
            _nc_now = st.session_state.get("box_y")
        elif _ct_now == "Treemap":
            _gb_now = st.session_state.get("tm_x")
            _nc_now = st.session_state.get("tm_y")
        elif _ct_now == "Funnel":
            _gb_now = st.session_state.get("fn_x")
            _nc_now = st.session_state.get("fn_y")
        _slicers_now = {}
        for _c in cat_cols:
            _k = f"slice_{_c}"
            if _k in st.session_state:
                _slicers_now[_c] = list(st.session_state[_k])
        _view_now = (None if (_gb_now is None and _nc_now is None) else
                     {"chart_type": _ct_now, "group_by": _gb_now,
                      "num_col": _nc_now, "slicers": _slicers_now})
        _applied_view = feat_analyse.render_saved_views(st, _view_now)
        if _applied_view is not None:
            st.session_state["an_pending_view"] = _applied_view
            st.rerun()
        chart_type = st.selectbox(
            "Chart", ["Bar", "Line", "Donut", "Histogram", "Scatter",
                      "Box plot", "Heatmap", "Treemap", "Funnel"],
            key="chart_type")
        grouped = None
        gx = gy = None
        if chart_type == "Histogram":
            hcol = st.selectbox("Number column", num_cols, key="hist_col")
            chart = alt.Chart(df).mark_bar().encode(
                x=alt.X(hcol, bin=True), y="count()",
                tooltip=["count()"]).properties(height=380)
            st.altair_chart(chart, width="stretch")
            st.write(df[hcol].describe().to_frame().T)
        elif chart_type == "Scatter":
            c1, c2, c3 = st.columns(3)
            sx = c1.selectbox("X (number)", num_cols, key="sc_x")
            sy = c2.selectbox("Y (number)", num_cols, key="sc_y")
            color = c3.selectbox("Colour by (optional)",
                                 ["(none)"] + cat_cols, key="sc_c")
            enc = {"x": sx, "y": sy, "tooltip": [sx, sy]}
            if color != "(none)":
                enc["color"] = color
            chart = alt.Chart(df).mark_circle(size=60).encode(
                **enc).properties(height=380)
            st.altair_chart(chart, width="stretch")
        elif chart_type == "Box plot":
            c1, c2 = st.columns(2)
            bx = c1.selectbox("Group by", cat_cols, key="box_x")
            by = c2.selectbox("Number", num_cols, key="box_y")
            chart = alt.Chart(df).mark_boxplot().encode(
                x=bx, y=by).properties(height=380)
            st.altair_chart(chart, width="stretch")
        elif chart_type == "Heatmap":
            if len(num_cols) < 2:
                st.info("Need at least two number columns for a heatmap.")
            else:
                st.altair_chart(feat_export.heatmap_corr(df), width="stretch")
        elif chart_type == "Treemap":
            c1, c2 = st.columns(2)
            tx = c1.selectbox("Group by", cat_cols, key="tm_x")
            ty = c2.selectbox("Size by", num_cols, key="tm_y")
            st.altair_chart(feat_export.treemap_chart(df, tx, ty),
                            width="stretch")
        elif chart_type == "Funnel":
            c1, c2 = st.columns(2)
            fx = c1.selectbox("Step", cat_cols, key="fn_x")
            fy = c2.selectbox("Value", num_cols, key="fn_y")
            st.altair_chart(feat_export.funnel_chart(df, fx, fy),
                            width="stretch")
        else:
            c1, c2, c3 = st.columns(3)
            x_col = c1.selectbox(
                "Group by", cat_cols + date_cols, key="dash_x")
            y_col = c2.selectbox("Number", num_cols, key="dash_y")
            grouped = df.groupby(x_col, dropna=False)[y_col].sum().reset_index()
            grouped = grouped.sort_values(y_col, ascending=False)
            gx, gy = x_col, y_col
            if chart_type == "Bar":
                chart = alt.Chart(grouped).mark_bar().encode(
                    x=alt.X(x_col, sort=None),
                    y=y_col, tooltip=[x_col, y_col]).properties(height=380)
            elif chart_type == "Line":
                chart = alt.Chart(grouped).mark_line(point=True).encode(
                    x=x_col, y=y_col,
                    tooltip=[x_col, y_col]).properties(height=380)
            else:
                chart = alt.Chart(grouped).mark_arc().encode(
                    theta=y_col, color=x_col,
                    tooltip=[x_col, y_col]).properties(height=380)
            st.altair_chart(chart, width="stretch")
            st.subheader("The numbers behind the chart")
            _grouped_display = grouped.copy()
            _grouped_display[y_col] = _grouped_display[y_col].map(
                lambda v: (f"{v:,.2f}" if float(v) % 1 else f"{v:,.0f}")
                if pd.notna(v) else v)
            st.dataframe(_grouped_display, width="stretch")
            feat_share.render_chart_png(
                st, grouped, x_col, y_col, title=f"{x_col} vs {y_col}",
                kind="line" if chart_type == "Line" else "bar",
                key_suffix="_dash")

        # ---- shareable read-only dashboard link (snapshot, not live data) ----
        with st.expander("Share this dashboard"):
            st.write("Creates a read-only link anyone can open without logging "
                     "in. It shows a saved snapshot of the KPIs and the chart "
                     "numbers — not your files, and not live data. You can "
                     "revoke it any time in Settings.")
            if st.button("Share dashboard", key="share_create_btn"):
                try:
                    _snap_grouped = grouped
                    _snap_gx, _snap_gy = gx, gy
                    if _snap_grouped is None and cat_cols and num_cols:
                        _snap_gx = cat_cols[0]
                        _snap_gy = num_cols[0]
                        _snap_grouped = df.groupby(
                            _snap_gx, dropna=False)[_snap_gy].sum().reset_index()
                        _snap_grouped = _snap_grouped.sort_values(
                            _snap_gy, ascending=False)
                    _rows = []
                    if _snap_grouped is not None:
                        _rows = [{str(k): (None if pd.isna(v) else v)
                                  for k, v in row.items()}
                                 for row in
                                 _snap_grouped.head(50).to_dict("records")]
                    _token = secrets.token_urlsafe(24)
                    with st.spinner("Creating your share link…"):
                        _registry = storage.load_json(_skey, "views", _SHARES_FILENAME)
                        if not isinstance(_registry, dict):
                            _registry = {}
                        _registry[_token] = {
                            "title": f"{_brand.get('name', 'Data Cleaner Studio')} — shared dashboard",
                            "kpis": [{"label": str(k.get("label", "")),
                                      "value": str(k.get("value", ""))}
                                     for k in (st.session_state.kpis or [])],
                            "rows": _rows,
                            "x_col": str(_snap_gx) if _snap_gx else None,
                            "y_col": str(_snap_gy) if _snap_gy else None,
                            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "revoked": False,
                        }
                        storage.save_json(_skey, "views", _SHARES_FILENAME, _registry)
                    st.session_state["last_share_token"] = _token
                    st.success("Share link created — it stays valid until you "
                               "revoke it in Settings.")
                except Exception as e:  # noqa: BLE001 - show the error, don't crash
                    st.error(f"Could not create the share link: {e}")
            _last_token = st.session_state.get("last_share_token")
            if _last_token:
                st.code(f"{_app_base_url()}?share={_last_token}",
                        language="text")
                st.caption("Anyone with this link can open the read-only dashboard — no login needed.")

        # One pivot table only: render_pivot() prints its own heading.
        feat_combine.render_pivot(st, df)
        with st.expander("More analysis"):
            feat_analyse.render_correlations(st, df)
            feat_analyse.render_forecast(st, df)
            feat_analyse.render_ask(st, df)

# --------------------------------------------------------------- compare ---
if "compare" in tab:
    if _active_tab == "compare":
        st.subheader("Compare & combine")
        st.write("See what changed between two files, stack files together, "
                 "or check whether this month's numbers jumped.")
        feat_combine.render_compare(st)
        with st.expander("Combine & check (stack files, anomalies, multi-KPI)"):
            feat_combine.render_append(st)
            if clean is not None:
                feat_combine.render_anomaly(st, clean)
            feat_analyse.render_multi_kpi(st)

# ---------------------------------------------------------------- report ---
if _active_tab == "report":
    if clean is None:
        st.info("Clean the data first — the report will appear here.")
    else:
        st.subheader("Report")
        report = engine.build_report(raw, clean, st.session_state.actions,
                                     st.session_state.kpis)
        st.markdown(report)
        _formulas = st.checkbox("Excel KPIs as live formulas",
                                value=True, key="rep_formulas",
                                help="The Excel workbook gets a 'KPIs (live)' "
                                     "sheet where totals are real Excel "
                                     "formulas, not just numbers.")
        _brand_x = feat_brand.brand_for_exports(base_dir=_user_root)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.download_button(_t("download_report") + " (.md)", report,
                           file_name="report.md", key="dl_report")
        c2.download_button("Download cleaned CSV",
                           clean.to_csv(index=False).encode("utf-8"),
                           file_name="cleaned_data.csv", key="dl_csv")
        c3.download_button("Download cleaned Excel",
                           engine.to_excel_bytes(clean, st.session_state.kpis,
                                                 st.session_state.actions,
                                                 formulas=_formulas),
                           file_name="cleaned_data.xlsx", key="dl_xlsx")
        pdf_bytes = engine.to_pdf_bytes(
            "Data Cleaner Studio — Report", st.session_state.kpis,
            st.session_state.actions,
            f"Rows: {len(raw):,} loaded -> {len(clean):,} after cleaning. "
            f"Columns: {len(raw.columns)} -> {len(clean.columns)}.",
            brand=_brand_x)
        c4.download_button("Download PDF report", pdf_bytes,
                           file_name="report.pdf", mime="application/pdf",
                           key="dl_pdf")
        c5.download_button("Download cleaned Parquet",
                           engine.to_parquet_bytes(clean),
                           file_name="cleaned_data.parquet",
                           key="dl_parquet")
        _oc_opts = (st.session_state.get("clean_opts")
                    or dict(feat_automate.DEFAULT_CLEAN_OPTS))
        _oc = feat_share.render_one_click(st, raw, _oc_opts,
                                          base_dir=_user_root,
                                          storage_key=_skey)
        _oc_ran = isinstance(_oc, dict) and _oc.get("status") == "done"
        if _oc_ran:
            st.session_state.clean = _oc["cleaned"]
            st.session_state.actions = _oc["actions"]
            st.session_state.kpis = _oc["kpis"]
            st.session_state.clean_opts = _oc_opts
            _audit("One-click flow",
                   f"{len(raw):,} -> {len(_oc['cleaned']):,} rows")
            _save_cleaned_copy(_oc["cleaned"], st.session_state.source_name)
            clean = _oc["cleaned"]
            filtered = clean
        feat_enrich.render_versioned_download(st, clean)
        with st.expander("More export formats & sharing"):
            _num = engine.numeric_cols(clean)
            _cat = [c for c in clean.columns
                    if str(clean[c].dtype) in ("object", "str")
                    and clean[c].nunique() <= 50]
            if _cat and _num:
                _gx, _gy = _cat[0], _num[0]
                _grouped = clean.groupby(_gx, dropna=False)[_gy].sum().reset_index()
                _grouped = _grouped.sort_values(_gy, ascending=False)
                feat_share.render_html_download(
                    st, st.session_state.kpis, st.session_state.actions,
                    _grouped, _gx, _gy, brand=_brand_x)
                feat_share.render_chart_png(
                    st, _grouped, _gx, _gy, title=f"{_gx} vs {_gy}",
                    key_suffix="_report")
            feat_share.render_portfolio_download(
                st, clean, st.session_state.kpis, st.session_state.actions)
            feat_share.render_styled_excel_download(
                st, clean, st.session_state.kpis, st.session_state.actions)
            feat_export.render_pptx_download(
                st, st.session_state.kpis, st.session_state.actions, raw, clean,
                brand=_brand_x)
            feat_export.render_sheets_export(st, clean)
            if not _oc_ran:
                feat_export.render_email_schedule(
                    st, st.session_state.kpis, st.session_state.actions, raw, clean)
            feat_quality.render_audit(st)

# ----------------------------------------------------------------- tools ---
if "tools" in tab:
    if _active_tab == "tools":
        st.subheader("Watch folder (automatic cleaning)")
        st.write("The app cleans files while it is open. For hands-free "
                 "cleaning, run this small script: drop a messy file into a "
                 "folder and the cleaned version appears in the output folder "
                 "by itself.")
        watch_path = _APP_DIR / "watch_folder.py"
        if watch_path.exists():
            st.download_button("Download watch_folder.py",
                               watch_path.read_bytes(),
                               file_name="watch_folder.py", key="tools_watch_dl")
        st.code("python watch_folder.py --watch incoming --out cleaned "
                "--recipe my_recipe.json", language="bash")
        st.write("Save a recipe from the Clean tab first, then point the "
                 "script at it. It also works with `--once` to clean the files "
                 "already waiting in the folder and stop.")
        feat_schedule.render_schedule_section(st)
        with st.expander("Shortcuts & morning run"):
            feat_analyse.render_morning_run(st)
            feat_analyse.render_shortcuts_panel(st)
        with st.expander("Backups & live databases"):
            _restored_tools = feat_share.render_backups(
                st, base_dir=_user_root, storage_key=_skey,
                key_prefix="s_backup_tools")
            if _restored_tools is not None:
                _set_raw(_restored_tools,
                         st.session_state.source_name + " (restored from backup)")
            st.subheader("Live database connections")
            _db_df, _db_name = feat_export.render_db_connect(st)
            if _db_df is not None:
                _set_raw(_db_df, _db_name, kind="database")
                _audit("Database load", f"{len(_db_df):,} rows from {_db_name}")
                st.success(f"Loaded {_db_name} — clean it in the Clean tab.")

# ------------------------------------------------------------- tutorial ---
if "tutorial" in tab:
    if _active_tab == "tutorial":
        feat_tutorial.render_tutorial_page(st, settings_path=_settings_path)

# -------------------------------------------------------------- settings ---
if "settings" in tab:
    if _active_tab == "settings":
        st.subheader("Settings")

        st.subheader("Account")
        # Supabase connection status (Phase 2, wired in): backend from
        # auth.get_auth_backend(), problem text from
        # auth.get_backend_warning() — shown verbatim, so a paused
        # free project reads exactly "Project paused — restore it in
        # the Supabase dashboard".
        _backend = auth.get_auth_backend()
        _backend_label = ("Local (this server)" if _backend == "local"
                          else "Cloud (Supabase)")
        st.write(f"Signed in as **{_user.get('username') or _user.get('email') or '?'}** "
                 f"(account backend: **{_backend_label}**).")
        _config_exists = auth.SUPABASE_CONFIG_PATH.is_file()
        _env_configured = bool((os.environ.get("SUPABASE_URL") or "").strip()
                               and (os.environ.get("SUPABASE_ANON_KEY") or "").strip())
        _cloud_ready = _config_exists or _env_configured
        st.write("Cloud setup: "
                 f"{'connected ✓' if _cloud_ready else 'not set up yet'}")
        _warn = auth.get_backend_warning()
        if _warn:
            st.warning(_warn)
        if _backend == "local":
            st.info("Local mode — accounts live in a file on this "
                    "server, and your files live in your folder on this "
                    "server. That means: your data leaves your computer — "
                    "it lives on the server. Cloud accounts (including "
                    "Google sign-in) need a Supabase project: create the "
                    "free project, add its URL and anon key to the app's "
                    "secrets, and run the setup SQL in the Supabase SQL "
                    "editor. Full steps: "
                    "[README.md — Auth: Supabase](README.md) and "
                    "[DEPLOY.md — section 0](DEPLOY.md). "
                    "Local accounts and Supabase accounts are different "
                    "users — switching backends means re-registering.")
        else:
            st.success("Cloud accounts are active (Supabase). Sign in "
                       "with your email and password, or with Google if "
                       "it is enabled in the Supabase dashboard. Your "
                       "local-mode account (if you had one) is a "
                       "different user — it does not carry over.")

        st.subheader("AI keys (yours, stored per user)")
        st.write("AI insights and natural-language questions use your own "
                 "key. It is saved in your folder only, and is never baked "
                 "into the code or the repo. Leave a field empty to turn "
                 "that provider off.")
        _cur_settings = ai_settings.load_settings()
        _groq_set = bool((_cur_settings.get("groq_api_key") or "").strip())
        _gemini_saved = ""
        try:
            _stored_settings = storage.load_json(_skey, "views", "settings.json")
            if isinstance(_stored_settings, dict):
                _gemini_saved = str(_stored_settings.get("gemini_api_key") or "")
        except Exception:  # noqa: BLE001
            _stored_settings = None
        st.write(f"Groq key: {'set ✓' if _groq_set else 'not set'}  ·  "
                 f"Gemini key: {'set ✓' if _gemini_saved.strip() else 'not set'}")
        _new_groq = st.text_input("Groq API key", type="password",
                                  key="settings_groq_key",
                                  help="Starts with gsk_ — get one free at console.groq.com. "
                                       "Leave empty to keep the saved key.")
        _new_gemini = st.text_input("Gemini API key", type="password",
                                    key="settings_gemini_key",
                                    help="Google AI Studio key. The app stores it; "
                                         "the Groq endpoint is used first when both are set. "
                                         "Leave empty to keep the saved key.")
        if st.button("Save API keys", key="settings_keys_save"):
            _merged = dict(ai_settings.load_settings())
            if isinstance(_stored_settings, dict):
                for _k, _v in _stored_settings.items():
                    if _k not in _merged:
                        _merged[_k] = _v
            if _new_groq.strip():
                _merged["groq_api_key"] = _new_groq.strip()
            if _new_gemini.strip():
                _merged["gemini_api_key"] = _new_gemini.strip()
            try:
                storage.save_json(_skey, "views", "settings.json", _merged)
                st.success("API keys saved in your folder.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not save the keys: {e}")

        # One "Your brand" heading only: render_brand_section prints its own.
        feat_brand.render_brand_section(st, base_dir=_user_root)

        with st.expander("Scheduled refresh jobs"):
            st.write("Jobs refresh a Google Sheet or a database table into "
                     "your folder on a schedule. The app only manages the "
                     "list below — the refresh itself is done by the separate "
                     "scheduler process (`python scheduler.py --daemon`), "
                     "which is not running inside this app. On Streamlit "
                     "Community Cloud the daemon cannot run at all.")
            st.write("The default interval below is 3 days — a regular job "
                     "keeps your data fresh without refreshing every hour.")
            _jobs_file = scheduler.DEFAULT_JOBS_FILE
            _payload, _jobs_err = scheduler.load_registry(_jobs_file)
            if _jobs_err:
                st.error(f"Could not read the job registry: {_jobs_err}")
                _payload = {"version": 1, "jobs": []}
            _all_jobs = _payload.get("jobs", []) if isinstance(_payload, dict) else []
            _my_idx = [i for i, j in enumerate(_all_jobs)
                       if isinstance(j, dict) and j.get("user") == _skey]
            if not _my_idx:
                st.info("No scheduled jobs yet.")
            for _pos, _ji in enumerate(_my_idx):
                _job = _all_jobs[_ji]
                _c1, _c2, _c3 = st.columns([3, 1, 1])
                _c1.write(f"**{_job.get('source_type', '?')}** — "
                          f"{_job.get('source', '')} → {_job.get('target', '')} "
                          f"· every {_job.get('interval_minutes', 60)} min · "
                          f"{'enabled' if _job.get('enabled', True) else 'disabled'}"
                          f"{' · last: ' + str(_job.get('last_status')) if _job.get('last_status') else ''}"
                          f"{' · ' + str(_job.get('last_error')) if _job.get('last_error') else ''}")
                if _c2.button("Enable" if not _job.get("enabled", True) else "Disable",
                              key=f"sched_toggle_{_pos}"):
                    _all_jobs[_ji]["enabled"] = not _job.get("enabled", True)
                    try:
                        scheduler.save_registry(_jobs_file, _payload)
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not save the job list: {e}")
                if _c3.button("Delete", key=f"sched_delete_{_pos}"):
                    del _all_jobs[_ji]
                    try:
                        scheduler.save_registry(_jobs_file, _payload)
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not save the job list: {e}")
            st.write("Add a job:")
            _nj_type = st.selectbox("Source type", ["sheets", "db"],
                                    key="sched_new_type",
                                    help="'sheets' = a public Google Sheet link. "
                                         "'db' = a saved connection name (create it "
                                         "in the Tools tab first).")
            _nj_source = st.text_input("Source (sheet link, or saved connection name)",
                                       key="sched_new_source")
            _nj_target = st.text_input("Save refreshed data to (inside your folder)",
                                       value="uploads/refreshed.csv",
                                       key="sched_new_target")
            _nj_interval = st.number_input("Every (minutes)", min_value=5,
                                           max_value=10080, value=4320,
                                           key="sched_new_interval",
                                           help="Defaults to 3 days (4320 minutes). "
                                                "Set it shorter if you want fresher data.")
            if st.button("Add scheduled job", key="sched_new_add"):
                if not _nj_source.strip() or not _nj_target.strip():
                    st.error("Fill in the source and the target file first.")
                else:
                    _all_jobs.append({
                        "user": _skey, "source_type": _nj_type,
                        "source": _nj_source.strip(),
                        "target": _nj_target.strip(),
                        "interval_minutes": int(_nj_interval),
                        "last_run": None, "next_run": None, "enabled": True,
                    })
                    try:
                        scheduler.save_registry(_jobs_file, _payload)
                        st.success("Job added.")
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not save the job list: {e}")

        with st.expander("Shared dashboard links"):
            try:
                _shares = storage.load_json(_skey, "views", _SHARES_FILENAME)
            except Exception:  # noqa: BLE001 - no share links without storage
                _shares = None
            if not isinstance(_shares, dict) or not _shares:
                st.info("No share links yet — create one from the Dashboard tab.")
            else:
                for _pos, (_tok, _snap) in enumerate(sorted(_shares.items())):
                    _c1, _c2 = st.columns([3, 1])
                    _c1.write(f"`?share={_tok[:12]}…` — "
                              f"created {_snap.get('created_at', '?')} — "
                              f"{'REVOKED' if _snap.get('revoked') else 'active'}")
                    if not _snap.get("revoked"):
                        if _c2.button("Revoke", key=f"share_revoke_{_pos}"):
                            _shares[_tok]["revoked"] = True
                            try:
                                storage.save_json(_skey, "views", _SHARES_FILENAME,
                                                  _shares)
                                st.success("Link revoked — it now shows "
                                           "'revoked or does not exist'.")
                                st.rerun()
                            except Exception as e:  # noqa: BLE001
                                st.error(f"Could not revoke the link: {e}")
                    else:
                        _c2.write("—")

        with st.expander("Still needs your details"):
            st.write("- **Email reports (SMTP):** the Report tab asks for your "
                     "SMTP server, port, username, app password and recipient. "
                     "Nothing is sent until you fill those in and press send.")
            st.write("- **Export to Google Sheets:** needs your Google "
                     "credentials and the Sheets API — not connected yet.")
            st.write("- **Live databases:** need your server details and the "
                     "right driver installed on the server (see the Tools tab).")
            st.write("- **Hosting:** "
                     + ("cloud (Streamlit Cloud)" if _backend != "local"
                        else "this computer")
                     + ". The app is deployed and running here — see DEPLOY.md "
                       "for the hosting notes.")
