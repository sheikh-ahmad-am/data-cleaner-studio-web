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

# The email logo: a PNG rendered from assets/logo.svg (email clients
# do not reliably render SVG). The file is committed in the public
# repo, so the email links to it by its raw URL; alt text keeps the
# email readable when images are blocked. Rendered at 240px and
# displayed at 120px for retina sharpness.
LOGO_EMAIL_URL = (
    "https://raw.githubusercontent.com/sheikh-ahmad-am/"
    "data-cleaner-studio-web/main/assets/logo-email.png"
)

# Welcome line (neutral on purpose: the same email goes out on every
# password login, first or returning).
WELCOME_LINE = (
    "Welcome to Data Cleaner Studio — here's your code to finish "
    "signing in."
)

TAGLINE = (
    "Put in a messy file. Get the cleaned file back, with its KPIs, "
    "charts and a one-page report."
)


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
    """The Brevo API payload for one login-code email.

    The email carries the website's look: near-white background,
    white card, one green accent (#117f50), hairline borders
    (#e8e8e8), Inter with a system-sans fallback — the same tokens
    as ui_design.py's light theme. Table layout + inline styles
    only, so it renders in plain email clients too (no dark theme
    in email — light and clean). The plain-text version says the
    same things, so nothing is lost when HTML is off.
    """
    subject = "Your Data Cleaner Studio login code"
    text = (
        f"{WELCOME_LINE}\n\n"
        f"Your login code is: {code}\n\n"
        "It expires in 10 minutes. Enter it on the login screen to "
        "finish signing in.\n\n"
        "If you didn't request this code, ignore this email — no one "
        "can sign in without it.\n\n"
        "—\n"
        f"Data Cleaner Studio\n{TAGLINE}\n"
    )
    font = (
        "Inter, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, "
        "sans-serif"
    )
    html = (
        "<!DOCTYPE html>"
        "<html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,"
        " initial-scale=1\"></head>"
        f"<body style=\"margin: 0; padding: 0; background-color: #fdfdfd; "
        f"font-family: {font};\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" "
        "cellpadding=\"0\" style=\"background-color: #fdfdfd;\">"
        "<tr><td align=\"center\" style=\"padding: 32px 16px;\">"
        "<table role=\"presentation\" width=\"480\" cellspacing=\"0\" "
        "cellpadding=\"0\" style=\"background-color: #ffffff; "
        "border: 1px solid #e8e8e8; border-radius: 12px;\">"
        "<tr><td align=\"center\" "
        "style=\"padding: 32px 32px 8px 32px;\">"
        f"<img src=\"{LOGO_EMAIL_URL}\" width=\"120\" height=\"120\" "
        "alt=\"Data Cleaner Studio\" "
        "style=\"display: block; border: 0;\">"
        "</td></tr>"
        "<tr><td align=\"center\" "
        "style=\"padding: 16px 32px 0 32px; font-size: 22px; "
        "font-weight: 600; color: #030303;\">"
        "Data Cleaner Studio"
        "</td></tr>"
        "<tr><td align=\"center\" "
        "style=\"padding: 12px 32px 0 32px; font-size: 15px; "
        "line-height: 1.6; color: #4d4d4d;\">"
        f"{WELCOME_LINE}"
        "</td></tr>"
        "<tr><td align=\"center\" style=\"padding: 24px 32px 0 32px;\">"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\">"
        "<tr><td align=\"center\" "
        "style=\"padding: 16px 28px; font-family: ui-monospace, "
        "'SF Mono', Menlo, Consolas, monospace; font-size: 32px; "
        "font-weight: 700; letter-spacing: 8px; color: #030303; "
        "background-color: #ffffff; border: 1px solid #117f50; "
        "border-radius: 6px;\">"
        f"{code}"
        "</td></tr></table>"
        "</td></tr>"
        "<tr><td align=\"center\" "
        "style=\"padding: 20px 32px 0 32px; font-size: 14px; "
        "line-height: 1.6; color: #4d4d4d;\">"
        "It expires in 10 minutes. Enter it on the login screen to "
        "finish signing in."
        "</td></tr>"
        "<tr><td align=\"center\" "
        "style=\"padding: 12px 32px 32px 32px; font-size: 13px; "
        "line-height: 1.6; color: #696969;\">"
        "If you didn't request this code, ignore this email — no one "
        "can sign in without it."
        "</td></tr>"
        "<tr><td style=\"padding: 0 32px 24px 32px;\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" "
        "cellpadding=\"0\"><tr><td "
        "style=\"border-top: 1px solid #e8e8e8; padding-top: 16px; "
        "font-size: 12px; line-height: 1.6; color: #696969; "
        "text-align: center;\">"
        "Data Cleaner Studio<br>"
        f"{TAGLINE}"
        "</td></tr></table>"
        "</td></tr>"
        "</table>"
        "</td></tr></table>"
        "</body></html>"
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
