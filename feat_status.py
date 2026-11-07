"""Data Cleaner Studio — in-app status + changelog (Supabase pattern).

The research report's pattern 10 (``report.md`` §9, also §6
"Status / transparency"): a public status page leads with a
plain-language headline, then per-service health, and the changelog
is a dated list with Date / Milestone / User-action tables. This
module copies the format, not the scale — it reports the app's OWN
health and history, honestly:

  * Status: the mode (cloud / local) and, in cloud mode, the result
    of the existing health check in auth.py (one tiny real RPC,
    cached per process). "All systems operational" is shown ONLY
    when that check genuinely passed. No uptime numbers are shown
    anywhere — none are measured, so none are claimed. When the
    check cannot be run (local mode) the pill shows the mode only.
  * Changelog: dated entries read off the real git history (each
    entry carries its commit hash), newest first. The same entries
    live in CHANGELOG.md at the repo root, so the history is in the
    repo too.

Contract:
  - CHANGELOG_ENTRIES : list of {"date", "commit", "title",
    "user_action"} dicts, newest first
  - get_status() -> {"mode", "state", "detail"} — "mode" is
    "cloud" | "local"; "state" is "operational" | "unavailable" |
    "local"; "detail" is the plain-words backend warning, or None
  - render_status_pill(st) : one quiet pill in the sidebar
  - render_status_section(st) : the Status tab (headline, services,
    "What's new" table)

Widget keys: none — this section is read-only.
"""

from __future__ import annotations

import auth
import ui_design

__all__ = [
    "CHANGELOG_ENTRIES",
    "get_status",
    "render_status_pill",
    "render_status_section",
]

# ---------------------------------------------------------------------------
# Changelog — dated entries from the real git history, newest first.
# Each entry's "commit" is the full hash; verify with
# `git log --format='%H %ad %s' --date=short`. "user_action" is what
# changed for the person using the app (usually: nothing to do).
# ---------------------------------------------------------------------------
CHANGELOG_ENTRIES = [
    {
        "date": "2026-11-07",
        "commit": "c4c862ff487f60528d510e28ad21f816ba423637",
        "title": "Email login code replaces the security check",
        "user_action": ("Nothing — logging in and signing up now ask "
                        "for a 6-digit code sent to your email instead "
                        "of the old security check. The code expires "
                        "in 10 minutes; if it does not arrive, use "
                        "Resend."),
    },
    {
        "date": "2026-11-06",
        "commit": "6ce9c8acec24a78a31b6ae1d0d93a14933f2159f",
        "title": "Rebuilt on the Supabase design system",
        "user_action": ("Nothing — the whole app was restyled "
                        "(near-white, one green, hairline borders) "
                        "and works exactly as before."),
    },
    {
        "date": "2026-11-06",
        "commit": "fa9aa3fc546bb33f9d3db3f85e59e2001020272e",
        "title": "Profile section added",
        "user_action": ("Nothing — open Profile from the sidebar to "
                        "see your account, change your display name, "
                        "reset your password, download your data, or "
                        "delete your account."),
    },
    {
        "date": "2026-11-06",
        "commit": "845b1fdbb29b06b0b187ff47516dd3d1f4143921",
        "title": "Cleaner look: light theme, guided empty states",
        "user_action": ("Nothing — the app is lighter and the empty "
                        "screens now say what to do next instead of "
                        "leaving a blank page."),
    },
    {
        "date": "2026-11-06",
        "commit": "da01db8c8aaa8b94872ec7f8eedcdb0318b9dfc8",
        "title": "Security check on login and sign-up",
        "user_action": ("Nothing — a Cloudflare security check now "
                        "runs when you log in or sign up. If it ever "
                        "blocks you, reload and try again."),
    },
    {
        "date": "2026-11-06",
        "commit": "1d1311e9a53a48f16119e8873e4bee561d7d7a7d",
        "title": "Fix batch: login survives refresh, 26 fixes",
        "user_action": ("Nothing — logging in now survives a page "
                        "refresh, and 26 issues found by end-to-end "
                        "testing were fixed."),
    },
    {
        "date": "2026-11-06",
        "commit": "24b3b0a16dd53290897c751e1d5d31e0a6c00818",
        "title": "First version",
        "user_action": ("Nothing — the first working version: upload "
                        "a file, clean it, see KPIs and a report."),
    },
]


# ---------------------------------------------------------------------------
# get_status — the honest states
# ---------------------------------------------------------------------------

def get_status() -> dict:
    """The app's own health, in three honest states.

    * local mode — there is no cloud service to report on, so the
      state is "local" and detail is None: the pill shows the mode
      only, never a claim about a service that was not checked.
    * cloud mode, health check passed — state "operational": the
      check is a real RPC against the Supabase project (cached per
      process inside auth.py), so this is verified, not assumed.
    * cloud mode, health check failed — state "unavailable" and
      detail carries auth's plain-words warning verbatim (e.g. a
      paused project), so the section can say what is wrong and
      what to do about it.

    Never raises: a backend that cannot even be detected is
    reported as unavailable with the error as the detail.
    """
    try:
        backend = auth.get_auth_backend()
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        return {"mode": "cloud", "state": "unavailable",
                "detail": f"Could not check the backend: {exc}"}
    if backend == "local":
        return {"mode": "local", "state": "local", "detail": None}
    try:
        warning = auth.get_backend_warning()
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        return {"mode": "cloud", "state": "unavailable",
                "detail": f"Could not check the cloud backend: {exc}"}
    if warning:
        return {"mode": "cloud", "state": "unavailable",
                "detail": str(warning)}
    return {"mode": "cloud", "state": "operational", "detail": None}


# ---------------------------------------------------------------------------
# render functions — thin Streamlit wrappers (st passed in, never imported)
# ---------------------------------------------------------------------------

def render_status_pill(st) -> None:
    """One quiet pill for the sidebar, under the nav.

    * "All systems operational" (mint) — cloud mode and the health
      check genuinely passed.
    * "Cloud unavailable" (amber) — cloud mode and the health check
      failed; the Status tab says what is wrong.
    * "Local mode" (grey) — local mode: the mode only, no claim
      about a service that was not checked.
    """
    status = get_status()
    if status["state"] == "operational":
        label, kind, dot = ("All systems operational", "mint", "dcs-dot")
    elif status["state"] == "unavailable":
        label, kind, dot = ("Cloud unavailable", "amber",
                            "dcs-dot dcs-dot--warn")
    else:
        label, kind, dot = ("Local mode", "grey", "dcs-dot dcs-dot--muted")
    # The dot is the login screen's 8px status dot (.dcs-dot, same
    # size and green) — the pill alone reads as a label; dot + pill
    # reads as a status, the Supabase way.
    st.markdown(
        '<div class="dcs-micro-label">Status</div>'
        '<div style="display: flex; align-items: center; gap: 6px;">'
        f'<span class="{dot}"></span>'
        f"{ui_design.pill(label, kind=kind)}</div>",
        unsafe_allow_html=True)


def _changelog_table() -> str:
    """The changelog as a Markdown table, Date / Milestone /
    What changed for you — the report's changelog-table style.
    The short commit hash sits in the Milestone cell so every row
    traces back to the git history."""
    lines = ["| Date | Milestone | What changed for you |",
             "| --- | --- | --- |"]
    for entry in CHANGELOG_ENTRIES:
        short = entry["commit"][:7]
        lines.append(
            f"| {entry['date']} | {entry['title']} "
            f"(`{short}`) | {entry['user_action']} |")
    return "\n".join(lines)


def render_status_section(st) -> None:
    """The Status tab: a plain-language headline, per-service health,
    then the "What's new" changelog.

    No uptime percentages anywhere — none are measured, so none are
    claimed. What this page shows is what the app checked just now:
    the mode, and (in cloud mode) the result of the real health
    check. A failed check names the cause in plain words, the way
    the report's error pattern asks ("This page couldn't load —
    Reload to try again, or go back")."""
    status = get_status()
    ui_design.section_heading(
        "Status",
        sub="The app's own health, in plain words — and what changed, "
            "by date.")
    if status["state"] == "operational":
        st.write("**All systems operational.**")
        st.write("The cloud backend (Supabase) answered the health "
                 "check just now.")
    elif status["state"] == "unavailable":
        st.write("**The cloud backend is unavailable.**")
        if status["detail"]:
            st.warning(status["detail"])
        st.write("Reload to try again. If it stays down, the account "
                 "and file screens will say so in plain words too.")
    else:
        st.write("**Running in local mode.**")
        st.write("Accounts and files live on this server — there is "
                 "no cloud service to check, so there is no uptime to "
                 "report here.")
    st.subheader("Services")
    if status["mode"] == "local":
        _backend_row = "Local mode — on this server"
    elif status["state"] == "operational":
        _backend_row = "Cloud (Supabase) — connected ✓"
    else:
        _backend_row = "Cloud (Supabase) — unavailable"
    st.markdown(
        "| Service | Status |\n"
        "| --- | --- |\n"
        "| This app | Running |\n"
        f"| Accounts & files | {_backend_row} |\n",
        unsafe_allow_html=True)
    st.caption("No uptime percentages here — this page only reports "
               "what the app checked just now.")
    st.subheader("What's new")
    st.write("What changed, newest first. Every row links back to "
             "the change in the git history by its short commit hash.")
    st.markdown(_changelog_table(), unsafe_allow_html=True)
