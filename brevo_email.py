"""Send the 6-digit login code by email via Brevo (transactional API).

Why Brevo: the app's free tier is $0 — Brevo's free plan allows 300
transactional emails a day, which covers every login for this app
many times over. One API key, one call: POST /v3/smtp/email with the
key in the `api-key` header (Brevo's own convention — not a Bearer
token). The sender address must be verified in the Brevo dashboard
first, or Brevo rejects the send.

Configuration (Streamlit secrets first, then the environment):
  BREVO_API_KEY       — the v3 API key (starts with `xkeysib-`)
  BREVO_SENDER_EMAIL  — the verified sender address

The key is never logged and never returned to the UI — callers only
learn whether it exists. Tests pass an httpx.Client with a
MockTransport, so no test ever sends a real email.
"""

from __future__ import annotations

import os

import httpx

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoNotConfiguredError(Exception):
    """BREVO_API_KEY or BREVO_SENDER_EMAIL is missing."""


class BrevoSendError(Exception):
    """Brevo rejected the send, or the request failed."""


def get_brevo_config() -> tuple[str, str] | None:
    """(api_key, sender_email), or None when either is missing.

    Streamlit secrets first, then the environment. A missing secrets
    file (local runs, tests) is not an error — it just falls back to
    the environment.
    """
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    sender = os.environ.get("BREVO_SENDER_EMAIL", "").strip()
    try:
        import streamlit as st  # noqa: PLC0415 - lazy: auth.py stays importable without it
        secrets = st.secrets
        api_key = str(secrets.get("BREVO_API_KEY", "") or "").strip() or api_key
        sender = str(secrets.get("BREVO_SENDER_EMAIL", "") or "").strip() or sender
    except Exception:  # noqa: BLE001 - no secrets file: environment only
        pass
    if not api_key or not sender:
        return None
    return api_key, sender


def build_login_code_email(sender: str, recipient: str, code: str) -> dict:
    """The Brevo API payload for one login-code email."""
    subject = "Your Data Cleaner Studio login code"
    text = (
        f"Your Data Cleaner Studio login code is: {code}\n\n"
        "It expires in 10 minutes. Enter it on the login screen to "
        "finish signing in.\n\n"
        "If you didn't request this code, ignore this email — no one "
        "can sign in without it.\n"
    )
    html = (
        "<p>Your Data Cleaner Studio login code is:</p>"
        f"<p style=\"font-size: 28px; font-weight: bold; "
        f"letter-spacing: 4px;\">{code}</p>"
        "<p>It expires in 10 minutes. Enter it on the login screen to "
        "finish signing in.</p>"
        "<p>If you didn't request this code, ignore this email — no one "
        "can sign in without it.</p>"
    )
    return {
        "sender": {"name": "Data Cleaner Studio", "email": sender},
        "to": [{"email": recipient}],
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
    }


def send_login_code(email: str, code: str, client=None) -> bool:
    """Send the 6-digit code to `email` via Brevo. Returns True.

    Raises BrevoNotConfiguredError when the key or sender is missing
    and BrevoSendError when Brevo rejects the send or the request
    fails. `client` is an httpx.Client (tests pass one with a
    MockTransport); without it a short-lived client is created. The
    plain code is never logged.
    """
    config = get_brevo_config()
    if config is None:
        raise BrevoNotConfiguredError(
            "Email verification isn't set up yet — add your Brevo API key "
            "in Streamlit secrets."
        )
    api_key, sender = config
    payload = build_login_code_email(sender, email, code)
    headers = {
        "api-key": api_key,
        "accept": "application/json",
        "content-type": "application/json",
    }
    try:
        if client is not None:
            resp = client.post(BREVO_API_URL, json=payload, headers=headers)
        else:
            with httpx.Client(timeout=15) as http:
                resp = http.post(BREVO_API_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise BrevoSendError(
            f"Could not reach Brevo to send the code: {exc}"
        ) from exc
    if resp.status_code not in (200, 201):
        raise BrevoSendError(
            f"Brevo rejected the email (status {resp.status_code})."
        )
    return True
