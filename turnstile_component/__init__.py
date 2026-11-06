"""Cloudflare Turnstile widget for the login / signup screens.

Minimal custom Streamlit component: the frontend is hand-rolled
vanilla JS (frontend/index.html + frontend/turnstile.js) speaking
the Streamlit component protocol over postMessage — no framework,
no npm build, no node_modules. The built files ARE the bundle:
declare_component serves the frontend/ directory as-is, so
Streamlit Cloud needs no build step at deploy time.

Only the SITE key lives here. It is public by design (it ships in
the page). The SECRET key never belongs in this repo — it goes in
the Supabase dashboard (Authentication -> Attack Protection) and
is only needed when CAPTCHA is switched on there.
"""

import os
from pathlib import Path

import streamlit as st
from streamlit.components.v1 import declare_component

_FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

_component = None


def get_site_key() -> str | None:
    """The Turnstile site key (public), or None when not configured.

    Streamlit secrets first, then the TURNSTILE_SITE_KEY environment
    variable — the same shape as app.py's _google_oauth_enabled flag.
    A missing key means the check is off and the app must not render
    the widget at all.
    """
    raw = ""
    try:
        raw = str(st.secrets.get("TURNSTILE_SITE_KEY", "") or "").strip()
    except Exception:  # noqa: BLE001 - no secrets file: not configured
        raw = ""
    if not raw:
        raw = (os.environ.get("TURNSTILE_SITE_KEY") or "").strip()
    return raw or None


def _get_component():
    """The declared component, built once per process (patchable in tests)."""
    global _component
    if _component is None:
        _component = declare_component("turnstile", path=str(_FRONTEND_DIR))
    return _component


def _normalize_theme(theme) -> str:
    """Return ``"dark"`` only for the dark theme; anything else
    (None, unknown, legacy names) falls back to ``"light"``, so a
    stale value can never strand the widget in an unknown style.
    Cloudflare Turnstile only accepts "light" / "dark" / "auto" —
    the app passes its own theme explicitly, never "auto"."""
    return "dark" if theme == "dark" else "light"


def turnstile_token(site_key, key="turnstile", reset=0,
                    theme="light") -> str | None:
    """Render the Turnstile widget and return its token, or None.

    Returns None when there is no site key (the caller must not
    render the widget then), when the check has not completed yet,
    or when the token expired. Tokens are single-use: after an
    attempt, call again with a new `key` (and a bumped `reset`) for
    a fresh widget.

    `theme` follows the app's theme ("light" / "dark"); the widget
    renders in that style, so it never shows as a white box on the
    dark page. A theme flip remounts the widget (the frontend keys
    its render on sitekey + reset + theme), which discards any
    in-flight token — the check is simply done again.
    """
    if not site_key:
        return None
    component = _get_component()
    value = component(site_key=site_key, reset=int(reset),
                      theme=_normalize_theme(theme), key=key,
                      default=None)
    return value if isinstance(value, str) and value else None
