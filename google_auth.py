"""Google sign-in for the Data Cleaner Studio web version (Supabase mode).

How it works (Supabase Auth OAuth redirect flow — no JavaScript SDK,
no ID tokens in the URL):
  1. The Streamlit app calls `get_google_sign_in_url()` here (via the
     re-export on auth.py) and renders it as a plain link button
     ("Continue with Google"). The URL is Supabase's Google
     authorization URL for this project.
  2. The user signs in with Google, Supabase redirects the browser
     back to the app URL with `?code=<authorization code>`.
  3. The app reads `st.query_params["code"]`, calls
     `handle_oauth_code(code)` here (via auth.py), then IMMEDIATELY
     clears the query param (a code must never linger in the URL,
     history or logs). The code is exchanged server-side with
     supabase-py, the profiles row is created/updated, and a 7-day
     app session token is returned — the same session token shape as
     password login.

ENTRY POINTS (the app calls these on the auth module, which re-exports
them from here):
    get_google_sign_in_url(redirect_to=None) -> str | None
    handle_oauth_code(code) -> (user_dict, session_token, error)
    handle_google_callback(code) -> same as handle_oauth_code (alias)

PKCE note (read this before "fixing" it): supabase-py uses the PKCE
flow by default. The code verifier is kept in memory inside the
process-cached Supabase client (auth.py caches one client per
process), so the exchange in step 3 must run in the SAME server
process that built the URL in step 1 — true for a single Streamlit
server. Two consequences:
  * `get_google_sign_in_url()` caches the URL per process and returns
    the same URL on repeat calls. Regenerating it on every page render
    would overwrite the stored verifier and orphan the link the user
    is about to click. Pass force_refresh=True only to deliberately
    start a fresh sign-in.
  * If the Streamlit server restarts between the user clicking Google
    and the redirect landing, the verifier is gone and the exchange
    fails with "Google sign-in expired — please try again." The user
    just clicks the button again; nothing is lost.

STATUS: structural only — no Supabase project exists yet, so Google
sign-in has NOT been live-tested end-to-end. It needs
supabase_config.json AND Google enabled in the Supabase dashboard
(Authentication -> Providers -> Google), plus the app's URL in
Authentication -> URL Configuration -> Redirect URLs. Email/password
login does not need any of that.

Security notes for the app agent:
  * Never log or store the raw authorization code; exchange it, then
    discard it.
  * Clear `st.query_params["code"]` right after consuming it.
  * This module returns (None, None, error) or raises
    auth.AuthServiceError when Supabase is unreachable — show that as
    a service error, never as a login failure.
"""

from __future__ import annotations

import auth as _auth


def _client():
    """Return the cached Supabase client, or None in local mode."""
    if _auth.get_auth_backend() != "supabase":
        return None
    return _auth._get_client()


def get_google_sign_in_url(redirect_to=None, force_refresh=False) -> str | None:
    """Return the Supabase Google OAuth authorization URL, or None.

    None means Google sign-in is unavailable right now: local mode,
    no Supabase config, or Supabase unreachable. The app shows its
    "not set up yet" note in that case.

    The URL is cached per process (see the PKCE note in the module
    docstring): repeat calls return the same URL so the stored code
    verifier still matches the link the user clicks.
    """
    if _auth.get_auth_backend() != "supabase":
        return None
    if not force_refresh and _auth._GOOGLE_URL:
        return _auth._GOOGLE_URL
    try:
        client = _client()
        if client is None:
            return None
        credentials: dict = {"provider": "google"}
        if redirect_to:
            credentials["options"] = {"redirect_to": redirect_to}
        resp = client.auth.sign_in_with_oauth(credentials)
    except Exception:
        return None
    url = getattr(resp, "url", None)
    if not isinstance(url, str) or not url:
        return None
    _auth._GOOGLE_URL = url
    return url


def handle_oauth_code(code) -> tuple[dict | None, str | None, str | None]:
    """Full Google callback: exchange code -> user + app session token.

    Returns (user_dict, session_token, error). error is a human-readable
    string when the sign-in did not complete. The app should call this
    once per callback and then clear the query param.
    """
    if not isinstance(code, str) or not code:
        return None, None, "Google sign-in failed — please try again."
    if _auth.get_auth_backend() != "supabase":
        return None, None, "Google sign-in is not set up (local mode)."
    try:
        client = _client()
        resp = client.auth.exchange_code_for_session({"auth_code": code})
    except _auth.AuthServiceError as exc:
        return None, None, str(exc)
    except Exception as exc:  # noqa: BLE001 - surfaced as a plain error
        msg = str(exc).lower()
        if "verifier" in msg or "pkce" in msg or "expired" in msg:
            return None, None, (
                "Google sign-in expired — please click "
                "\"Continue with Google\" again."
            )
        return None, None, f"Google sign-in failed: {exc}"
    user = getattr(resp, "user", None)
    if user is None:
        return None, None, "Google sign-in failed — please try again."
    user_id = str(getattr(user, "id", "") or "")
    email = getattr(user, "email", None) or ""
    if not user_id:
        return None, None, "Google sign-in failed — please try again."
    try:
        user_dict = _auth._sb_upsert_profile(user_id, email)
    except _auth.AuthServiceError as exc:
        return None, None, str(exc)
    try:
        token = _auth.create_session(user_id)
    except _auth.AuthServiceError as exc:
        return None, None, str(exc)
    if not token:
        return None, None, (
            "Google sign-in verified but the session could not be created."
        )
    return user_dict, token, None


# Alias: the app also accepts this name for the same callback.
handle_google_callback = handle_oauth_code
