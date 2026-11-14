"""Data Cleaner Studio — Profile section (Supabase Preferences page).

The account page as Supabase's Preferences (``/dashboard/account/me``,
~740px centred, left sub-nav + bordered cards): "Profile
information" (First/Last name, Primary email, Username, green Save —
wired to the real profile store), "Sign-in methods" (Email +
Change password, the real email+code login; ChatGPT and GitHub
shown as Not connected — this app signs in with email only),
"Connections" (GitHub Connect — no GitHub OAuth exists in this
app, shown as Not connected), "Appearance" (Theme mode preview
cards System/Dark/Light wired to the REAL theme preference through
``ui_design.set_theme_pref``; Theme colors sliders shown for
reference only — this app has no theme-color settings; Sidebar
behavior wired to the REAL 3-way rail mode; Timezone "Auto detect
(Asia/Calcutta)" as an honest display — the app has one timezone),
"Keyboard shortcuts" (this app has none; Quick Jump is the honest
equivalent — no fake switches), "Dashboard" (Edit entities in SQL /
Queue table operations — no counterparts here, both stay off),
"Analytics and Marketing" (no telemetry exists in this app, the
switch stays off), then the app's own "Storage usage", "Download
my data", "Log out", and "Danger zone".

HONESTY CONTRACT (load-bearing, every round): a control that cannot
save is DISABLED, never clickable-then-silent; a section with no
counterpart is rendered as an honest note, never faked. The theme
preview thumbnails are inline-style depictions (a dark-theme picture
cannot live in the light stylesheet — the token test forbids dark
hexes there — so the depiction carries its own colours); picking a
card restyles the whole app at once, which is the live preview.

DANGER ZONE — CORRECTION: the account-deletion flow is REAL, not
absent. ``delete_account`` below deletes the user's files
(``storage.delete_user_files``), database rows
(``auth.delete_account_rows``) and, in Supabase mode, the auth user
itself (service-role admin delete) — gated on typing DELETE, and
covered end to end by tests/test_profile.py. An earlier brief
claimed no deletion flow exists; that was wrong, and disabling a
working, tested flow to render a dead card would be the fake, not
the fix. The card is kept as the real flow.

Contract (functions provided by the auth / storage workers — called
exactly as specified, never reimplemented here):
  - auth.set_display_name(user_id, display_name) -> (ok, error)
  - auth.request_password_reset(email) -> (ok, error)
  - auth.list_user_sessions(user_id) -> [{"created_at", "expires_at"}]
  - auth.delete_account_rows(user_id) -> None
  - storage.get_service_client() -> service-role client
  - storage.storage_usage(username) -> (total_bytes, {subfolder: bytes})
  - storage.list_all_files(username) -> {subfolder: [names]}
  - storage.delete_user_files(username) -> int (count deleted)

Widget keys all start with "profile_".
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

import auth
import storage
import ui_design

__all__ = [
    "delete_account",
    "build_data_export",
    "render_profile_view",
]

_DELETE_CONFIRMATION = "DELETE"
_FREE_TIER_BYTES = 1024 * 1024 * 1024  # 1 GB free-tier bucket


# ---------------------------------------------------------------------------
# delete_account / build_data_export (pure logic — no Streamlit widgets)
# ---------------------------------------------------------------------------

def delete_account(user, storage_key, confirmation):
    """Delete an account permanently.

    Returns (True, None) only when every step succeeded, else
    (False, plain message) — never reports success part-way through.

    Order (each step idempotent, so a retry resumes cleanly):
      (a) PRE-CHECK, Supabase mode only: get the service client
          FIRST — without it nothing is deleted at all.
      (b) delete the user's files.
      (c) delete the user's database rows.
      (d) Supabase mode only: delete the auth user itself — only
          after the files and rows are gone.
    Local mode runs (b) + (c) only.
    """
    if confirmation != _DELETE_CONFIRMATION:
        return False, "Type DELETE to confirm."
    user_id = user.get("id") if isinstance(user, dict) else None
    if user_id is None:
        return False, "Could not delete your account: missing user id."
    backend = auth.get_auth_backend()
    service_client = None
    if backend == "supabase":
        try:
            service_client = storage.get_service_client()
        except Exception as exc:  # noqa: BLE001 - pre-check failure
            return False, (
                "Could not delete your account: the service connection "
                f"is not available ({exc}). Nothing was deleted — "
                "please try again later.")
    try:
        storage.delete_user_files(storage_key)
    except Exception as exc:  # noqa: BLE001 - surfaced as a plain error
        return False, f"Could not delete your files: {exc}"
    try:
        auth.delete_account_rows(user_id)
    except Exception as exc:  # noqa: BLE001 - surfaced as a plain error
        return False, f"Could not delete your account data: {exc}"
    if backend == "supabase":
        try:
            service_client.auth.admin.delete_user(user_id)
        except Exception as exc:  # noqa: BLE001 - surfaced as plain error
            return False, (
                "Could not delete your login: "
                f"{exc}. Your files and data are already gone — "
                "please try again to finish removing the login.")
    return True, None


def build_data_export(user, storage_key):
    """Build the download-my-data payload. No tokens, no passwords,
    no keys anywhere in it — just the profile, the sessions, the
    file list and the storage total."""
    try:
        total_bytes, _per_folder = storage.storage_usage(storage_key)
    except Exception:  # noqa: BLE001 - an export never fails on usage
        total_bytes = 0
    try:
        sessions = auth.list_user_sessions(user.get("id"))
        if not isinstance(sessions, list):
            sessions = []
    except Exception:  # noqa: BLE001 - an export never fails on sessions
        sessions = []
    try:
        files = storage.list_all_files(storage_key)
        if not isinstance(files, dict):
            files = {}
    except Exception:  # noqa: BLE001 - an export never fails on files
        files = {}
    return {
        "profile": {
            "email": user.get("email"),
            "display_name": user.get("display_name"),
            "member_since": user.get("created_at"),
            "backend": auth.get_auth_backend(),
        },
        "sessions": sessions,
        "files": files,
        "storage_usage_bytes": int(total_bytes or 0),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# render_profile_view — the Profile section (st passed in, never imported)
# ---------------------------------------------------------------------------

def _profile_section(st, anchor, title, sub=None):
    """A section heading above a bordered card (Supabase's settings
    pages): the title carries an ``id`` so the sub-nav's anchor
    links can scroll to it. The page is one stacked page, not
    separate pages — Supabase's sub-nav lists separate pages; this
    app has one Preferences page, so the rows scroll to the card."""
    sub_html = (f'<div class="dcs-profile-section-sub">'
                f"{html.escape(sub)}</div>" if sub else "")
    st.markdown(
        f'<h3 id="{anchor}" class="dcs-profile-section">'
        f"{html.escape(title)}</h3>{sub_html}",
        unsafe_allow_html=True)


def _profile_row(st, label, sub=None):
    """One Supabase settings row inside a bordered card: the label +
    muted sub-line at the left, an empty controls column at the
    right for the caller to fill. Returns the right column. The
    label classes are the settings card's own
    (``.dcs-settings-title`` / ``.dcs-settings-desc``)."""
    _left, _right = st.columns([1.1, 1])
    with _left:
        st.markdown(
            f'<div class="dcs-settings-title">{html.escape(label)}</div>',
            unsafe_allow_html=True)
        if sub:
            st.markdown(
                f'<div class="dcs-settings-desc">{html.escape(sub)}</div>',
                unsafe_allow_html=True)
    return _right


def _profile_subnav_link(st, anchor, label):
    """One sub-nav row: an anchor link to the section heading."""
    st.markdown(
        f'<a class="dcs-profile-subnav-link" href="#{anchor}">'
        f"{html.escape(label)}</a>",
        unsafe_allow_html=True)

# The theme-mode preview thumbnails: a mini mock of the app shell
# (header bar + two text lines) in the mode's own colours. The
# colours are INLINE, not stylesheet classes — the token test
# forbids dark hexes in the light stylesheet, so a dark-theme
# picture cannot live in CSS at all; the depiction carries its own
# colours, using only existing token hexes. Picking a card restyles
# the whole app at once, which is the live preview — the thumbnail
# is the label, the restyle is the proof. "System" is a split
# thumbnail: the left half light, the right half dark.
_THEME_PREVIEW = {
    # (shell background, header bar, text line)
    "light": ("#fdfdfd", "#f3f3f3", "#d0d0d0"),
    "dark": ("#1b1d1c", "#232625", "#4a4d4c"),
    # "system" has no single triple: its halves are built inline
    # in _theme_preview_html below.
}
_THEME_PREVIEW_LABELS = {
    "system": "System",
    "dark": "Dark",
    "light": "Light",
}
_THEME_PREVIEW_DESCS = {
    "system": "Follows your device setting",
    "dark": "Dark pages, light text",
    "light": "Light pages, dark text",
}


def _theme_preview_html(mode, selected, accent):
    """One theme-mode preview thumbnail as HTML: a bordered mini
    mock of the app shell. ``selected`` draws the green outline
    (the accent of the theme in effect). Returns the HTML string —
    the caller renders it with st.markdown(..., unsafe_allow_html)."""
    _outline = (f"outline: 2px solid {accent}; outline-offset: 2px; "
                if selected else "")
    if mode == "system":
        # Two half-mocks side by side: light on the left, dark on
        # the right, each with its own bar + lines.
        def _half(bg, bar, line):
            return (
                f'<div style="flex:1;background:{bg};padding:6px;">'
                f'<div style="height:10px;background:{bar};'
                f'border-radius:2px;margin-bottom:5px"></div>'
                f'<div style="height:5px;background:{line};'
                f'border-radius:2px;margin-bottom:3px;width:85%"></div>'
                f'<div style="height:5px;background:{line};'
                f'border-radius:2px;width:60%"></div></div>')
        _left = _half("#fdfdfd", "#f3f3f3", "#d0d0d0")
        _right = _half("#1b1d1c", "#232625", "#4a4d4c")
        return (
            f'<div style="display:flex;border:1px solid #e8e8e8;'
            f'border-radius:8px;overflow:hidden;{_outline}">'
            f"{_left}{_right}</div>")
    _bg, _bar, _line = _THEME_PREVIEW[mode]
    return (
        f'<div style="background:{_bg};border:1px solid #e8e8e8;'
        f'border-radius:8px;padding:8px;{_outline}">'
        f'<div style="height:14px;background:{_bar};border-radius:3px;'
        f'margin-bottom:6px"></div>'
        f'<div style="height:6px;background:{_line};border-radius:3px;'
        f'margin-bottom:4px;width:80%"></div>'
        f'<div style="height:6px;background:{_line};border-radius:3px;'
        f'width:60%"></div></div>')


def _member_since_text(created_at):
    """created_at (ISO string) -> a plain date, or the raw value."""
    if not created_at:
        return "?"
    try:
        return datetime.fromisoformat(str(created_at)).date().isoformat()
    except (ValueError, TypeError):
        return str(created_at)[:10] or "?"


def _format_bytes(n) -> str:
    """A byte count as a short human size (0 B, 1.2 KB, 3.4 MB, 1.0 GB)."""
    try:
        _n = float(n or 0)
    except (TypeError, ValueError):
        return "0 B"
    for _unit in ("B", "KB", "MB", "GB"):
        if _n < 1024 or _unit == "GB":
            return f"{_n:.1f} {_unit}" if _unit != "B" else f"{int(_n)} B"
        _n /= 1024
    return f"{_n:.1f} GB"


def render_profile_view(st, user, storage_key, on_logout=None):
    """The Profile section, Supabase's Preferences page in layout:
    a narrow left sub-nav ("← Back to dashboard", the sections this
    app genuinely has) and the main content as bordered cards in
    Supabase's row format — "Profile information" (First name /
    Last name / Primary email / Username + Save, wired to the real
    profile data), "Sign-in methods" (Email + Change password, the
    app's real email+code login; ChatGPT and GitHub honestly Not
    connected), "Connections" (GitHub, honestly Not connected),
    "Appearance" (Theme mode preview cards System/Dark/Light wired
    to the real theme preference, Theme colors sliders shown for
    reference only, Sidebar behavior wired to the real 3-way rail
    mode, Timezone as an honest display), "Keyboard shortcuts"
    (honest note — the app has none, Quick Jump is the equivalent),
    "Dashboard" (two switches, both off, no counterparts),
    "Analytics and Marketing" (telemetry switch off — the app
    collects no usage data), "Storage usage", "Download my data",
    "Log out", "Danger zone" (the real delete flow — see the module
    docstring). No Access Tokens, no Audit Logs, no Upgrade to Pro:
    the app has none of those, and a button to nowhere would be
    fake.

    The sub-nav rows are anchor links to the section headings (one
    stacked page, not separate pages). "Preferences" itself is the
    current page, highlighted, not a link. First / Last name are the
    display name split on the first whitespace (there are no
    first/last-name columns); Save recombines them through the
    existing ``auth.set_display_name``. The username is the sign-in
    name (the email in Supabase mode, the login name in local mode)
    — it is not the display name, so its sub-line says so.

    Returns "deleted" when the account was deleted (the caller clears
    the session and reruns), "logout" when the Log out button was
    pressed and no on_logout callback was given (the caller logs the
    user out), "back" when "← Back to dashboard" was pressed (the
    caller opens the Dashboard tab), and None otherwise. When on_logout is
    given it is called directly for the Log out button (the app
    passes its own logout helper, so the button behaves exactly
    like the sidebar one). On a failed delete the error is shown
    and the user stays logged in, so they can retry.
    """
    _email = user.get("email") or user.get("username") or "?"
    _display = str(user.get("display_name") or "")
    _parts = _display.split(None, 1)
    _first = _parts[0] if _parts else ""
    _last = _parts[1] if len(_parts) > 1 else ""
    _has_display_name = isinstance(user, dict) and "display_name" in user

    # Marker for the sub-nav divider rule (the stylesheet scopes it
    # to this page only) — it must sit directly before the columns.
    st.markdown('<div class="dcs-profile-page"></div>',
                unsafe_allow_html=True)
    _nav_col, _main_col = st.columns([1, 4])
    with _nav_col:
        if st.button("← Back to dashboard",
                     key="profile_back_dashboard",
                     use_container_width=True):
            return "back"
        st.markdown('<div class="dcs-micro-label">Account settings</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<span class="dcs-profile-subnav-link '
            'dcs-profile-subnav-active">Preferences</span>',
            unsafe_allow_html=True)
        _profile_subnav_link(st, "profile-signin", "Sign-in methods")
        _profile_subnav_link(st, "profile-connections", "Connections")
        _profile_subnav_link(st, "profile-appearance", "Appearance")
        _profile_subnav_link(st, "profile-shortcuts",
                             "Keyboard shortcuts")
        _profile_subnav_link(st, "profile-dashboard", "Dashboard")
        _profile_subnav_link(st, "profile-analytics",
                             "Analytics and Marketing")
        st.markdown('<div class="dcs-micro-label">Data</div>',
                    unsafe_allow_html=True)
        _profile_subnav_link(st, "profile-storage", "Storage usage")
        _profile_subnav_link(st, "profile-download", "Download my data")
        _profile_subnav_link(st, "profile-logout", "Log out")
        _profile_subnav_link(st, "profile-danger", "Danger zone")
    with _main_col:
        # One heading for the whole page — title + caption fused
        # into a single element, so the caption can never again be
        # separated from its title (the live check found the old
        # st.caption missing from the screen even though the code
        # was there).
        ui_design.section_heading(
            "Preferences", sub="Manage your account, sign-in and data.")

        # (1) Profile information --------------------------------------
        _profile_section(st, "profile-information", "Profile information")
        with st.container(border=True):
            _r = _profile_row(st, "First name")
            with _r:
                _first_name = st.text_input(
                    "First name", value=_first,
                    key="profile_first_name",
                    label_visibility="collapsed",
                    disabled=not _has_display_name,
                    help="The first part of the name shown on your "
                         "avatar.")
            _r = _profile_row(st, "Last name")
            with _r:
                _last_name = st.text_input(
                    "Last name", value=_last,
                    key="profile_last_name",
                    label_visibility="collapsed",
                    disabled=not _has_display_name,
                    help="The rest of the name shown on your avatar.")
            _r = _profile_row(st, "Primary email",
                              "Used for account notifications")
            with _r:
                st.text_input("Primary email", value=_email,
                              key="profile_primary_email", disabled=True,
                              label_visibility="collapsed")
            _r = _profile_row(st, "Username", "Your sign-in name.")
            with _r:
                st.text_input(
                    "Username",
                    value=str(user.get("username") or _email),
                    key="profile_username", disabled=True,
                    label_visibility="collapsed")
            _r = _profile_row(st, "Member since")
            with _r:
                st.write(
                    f"**{_member_since_text(user.get('created_at'))}**")
            if not _has_display_name:
                st.caption("Display names need the updated database setup "
                           "(run supabase_setup.sql) — this field is "
                           "disabled until then.")
            if st.session_state.pop("profile_display_name_saved", False):
                st.success("Display name saved. It now shows as "
                           f"'{user.get('display_name')}' on your avatar.")
            _sp, _save_col = st.columns([3, 1])
            with _save_col:
                if ui_design.icon_button(
                        "Save", "check", kind="primary",
                        key="profile_display_name_save",
                        disabled=not _has_display_name,
                        use_container_width=True,
                        help="Save the display name."):
                    _combined = (f"{_first_name.strip()} "
                                 f"{_last_name.strip()}").strip()
                    _ok, _err = auth.set_display_name(
                        user.get("id"), _combined)
                    if _ok:
                        try:
                            st.session_state["current_user"]["display_name"] = (
                                _combined)
                        except Exception:  # noqa: BLE001 - session dict is best-effort
                            pass
                        st.session_state["profile_display_name_saved"] = True
                        st.success("Display name saved. It now shows as "
                                   f"'{_combined}' on your avatar.")
                    else:
                        st.error(_err or "Could not save the display name.")

        # (2) Sign-in methods -------------------------------------------
        _profile_section(st, "profile-signin", "Sign-in methods",
                         "Manage the providers linked to your account and "
                         "update their details.")
        with st.container(border=True):
            _r = _profile_row(st, "Email", _email)
            with _r:
                if auth.get_auth_backend() == "supabase":
                    if st.session_state.pop("profile_reset_sent", False):
                        st.success(f"Reset link sent to {user.get('email')} — check "
                                   "your inbox (and spam).")
                    if st.button("Change password",
                                 key="profile_reset_password"):
                        _ok, _err = auth.request_password_reset(user.get("email"))
                        if _ok:
                            st.session_state["profile_reset_sent"] = True
                            st.success(f"Reset link sent to {user.get('email')} — "
                                       "check your inbox (and spam).")
                        else:
                            st.error(_err or "Could not send the reset email.")
                else:
                    st.write("Password reset by email is only available for cloud "
                             "accounts — local accounts have no email address on file.")
            # ChatGPT / GitHub sign-in do not exist in this app (no
            # OAuth providers are enabled — only the email + code
            # flow above). Rendered as Not connected with a disabled
            # Connect button: the shape of Supabase's rows, with
            # nothing that pretends to link an account.
            _r = _profile_row(
                st, "ChatGPT",
                "Not connected — this app signs in with email only.")
            with _r:
                ui_design.icon_button(
                    "Connect", "connect",
                    key="profile_signin_chatgpt_connect",
                    disabled=True,
                    help="ChatGPT sign-in does not exist in this app.")
            _r = _profile_row(
                st, "GitHub",
                "Not connected — this app signs in with email only.")
            with _r:
                ui_design.icon_button(
                    "Connect", "connect",
                    key="profile_signin_github_connect",
                    disabled=True,
                    help="GitHub sign-in does not exist in this app.")

        # (2b) Connections ---------------------------------------------
        # Supabase's Connections card: GitHub Connect. Same honesty
        # rule as the sign-in rows above — there is no GitHub OAuth
        # in this app, so the row says so and the button is disabled.
        _profile_section(st, "profile-connections", "Connections",
                         "External accounts linked to this app.")
        with st.container(border=True):
            _r = _profile_row(
                st, "GitHub",
                "Not connected — there is no GitHub connection in "
                "this app.")
            with _r:
                ui_design.icon_button(
                    "Connect", "connect",
                    key="profile_connections_github_connect",
                    disabled=True,
                    help="GitHub Connect does not exist in this app.")

        # (3) Appearance --------------------------------------------------
        # Theme mode preview cards own the PREFERENCE (System / Dark /
        # Light) — the avatar menu's radio does the same; the Light /
        # Dark radio below still owns only the RESOLVED theme (it is
        # pinned by the Round 5/10 regression tests, so it stays).
        # Both write through the theme machinery, so all four
        # controls agree on the next run.
        _profile_section(st, "profile-appearance", "Appearance",
                         "Choose how the app looks.")
        with st.container(border=True):
            # Theme mode — Supabase's preview cards, wired to the
            # REAL theme preference through ui_design.set_theme_pref
            # (the same write the avatar menu's radio performs).
            # Picking a card restyles the whole app at once — that
            # is the live preview. Buttons are stateless, so no
            # stale-frontend value can survive (the key-bump lesson
            # does not apply to buttons).
            _pref = ui_design.normalize_theme_pref(
                st.session_state.get(ui_design.THEME_PREF_KEY))
            _resolved = ui_design.normalize_theme(
                st.session_state.get("dcs_theme", ui_design.THEME_DEFAULT))
            _accent = ("#4acd8b" if _resolved == "dark" else "#117f50")
            _r = _profile_row(st, "Theme mode",
                              "System follows your device; Dark and Light "
                              "are fixed — the choice applies across the "
                              "app at once.")
            with _r:
                _mode_cols = st.columns(3)
                for _i, _mode in enumerate(("system", "dark", "light")):
                    with _mode_cols[_i]:
                        st.markdown(
                            _theme_preview_html(
                                _mode, _mode == _pref, _accent),
                            unsafe_allow_html=True)
                        st.caption(_THEME_PREVIEW_DESCS[_mode])
                        if st.button(
                                _THEME_PREVIEW_LABELS[_mode],
                                key=f"profile_theme_mode_{_mode}",
                                use_container_width=True,
                                help="Use the "
                                f"{_THEME_PREVIEW_LABELS[_mode]} "
                                "theme mode."):
                            ui_design.set_theme_pref(st, _mode)
                            st.rerun()
                        if _mode == _pref:
                            st.markdown("**✓ Current**")
            _r = _profile_row(st, "Theme",
                              "Light or dark — the choice applies across "
                              "the app.")
            with _r:
                _current_theme = ui_design.normalize_theme(
                    st.session_state.get("dcs_theme", ui_design.THEME_DEFAULT))
                # Re-sync immediately before creating the radio, for
                # the same reason as the avatar menu's radio: the
                # theme may have flipped earlier in this run, and
                # the top-of-run sync predates that flip.
                st.session_state[ui_design.PROFILE_THEME_RADIO_KEY] = (
                    _current_theme)
                st.session_state[ui_design.THEME_SYNCED_KEY] = (
                    _current_theme)

                def _on_profile_theme():
                    _new = ui_design.normalize_theme(
                        st.session_state.get(
                            ui_design.PROFILE_THEME_RADIO_KEY,
                            _current_theme))
                    if _new == st.session_state.get(
                            ui_design.THEME_SYNCED_KEY):
                        # The value changed because the sync wrote
                        # the resolved theme into the key (a late
                        # restore seeding, or a flip from another
                        # control) — not because the user picked it.
                        # Applying it would overwrite the
                        # preference with the resolved theme
                        # ("System" -> "Dark").
                        return
                    # set_theme also writes the preference, so the
                    # account menu's System/Dark/Light radio agrees
                    # with the resolved theme on the next run.
                    ui_design.set_theme(st, _new)
                    # Round 10: rerun at once, like the login
                    # toggle. Without it the new theme only
                    # applies on the NEXT run (the stylesheet is
                    # injected at the top of the run, before this
                    # callback fires), so the Profile page sat
                    # light for a full run after picking Dark —
                    # the window the live check read as "reverts
                    # to Light". The sibling keys cannot be
                    # written here (the avatar radio + sidebar
                    # selectbox were already created this run),
                    # but the rerun re-syncs them from dcs_theme
                    # at the top of the next run, so all three
                    # controls agree. The probes could not
                    # reproduce a real revert (dark persisted on
                    # both the empty-state and data-loaded paths);
                    # this removes the lag window itself.
                    st.rerun()

                st.radio("Theme", options=list(ui_design.THEMES),
                         format_func=lambda t: ("Dark" if t == "dark"
                                                else "Light"),
                         key=ui_design.PROFILE_THEME_RADIO_KEY,
                         on_change=_on_profile_theme,
                         label_visibility="collapsed")

            # Sidebar behavior — the same 3-way setting as the
            # rail's bottom control (clone Round 1): Expanded /
            # Collapsed / Expand on hover. One setting, two
            # controls, so a pick here and a pick in the rail menu
            # are the same action.
            _r = _profile_row(st, "Sidebar behavior",
                              "How the sidebar opens — expanded, "
                              "collapsed, or expanding on hover.")
            with _r:
                _current_mode = ui_design.rail_mode(st)
                # Re-sync immediately before creating the radio,
                # for the same reason as the theme radio above:
                # the mode may have flipped earlier in this run
                # (rail menu), and the top-of-run state predates
                # that flip.
                st.session_state[ui_design.RAIL_MODE_PROFILE_RADIO_KEY] = (
                    _current_mode)

                def _on_profile_sidebar_behavior():
                    _new = ui_design.normalize_rail_mode(
                        st.session_state.get(
                            ui_design.RAIL_MODE_PROFILE_RADIO_KEY,
                            _current_mode))
                    ui_design.set_rail_mode(st, _new)
                    # The rail menu's radio is created earlier in
                    # the run, so its key cannot be written here —
                    # the rerun re-syncs it from the mode at the
                    # top of the next run, like the theme radio
                    # above. The stylesheet is injected at the top
                    # of the run, so rerun at once for the new
                    # width to apply on this very run.
                    st.rerun()

                st.radio("Sidebar behavior",
                         options=list(ui_design.RAIL_MODES),
                         format_func=lambda m: (
                             ui_design.RAIL_MODE_LABELS.get(m, m)),
                         key=ui_design.RAIL_MODE_PROFILE_RADIO_KEY,
                         on_change=_on_profile_sidebar_behavior,
                         label_visibility="collapsed")

            # Theme colors — Supabase's four sliders (Surface tint 0 /
            # Contrast 23 / Surface brightness 100 / Layer contrast
            # 100). This app has NO theme-color settings: the sliders
            # are DISABLED and show Supabase's defaults for reference
            # only. There is no save path — nothing writes a
            # theme-color key anywhere.
            _r = _profile_row(
                st, "Theme colors",
                "Supabase theme colors, shown for reference — this app "
                "has no theme-color settings, so these cannot be "
                "changed.")
            with _r:
                st.slider("Surface tint", 0, 100, 0, disabled=True,
                          key="profile_theme_surface_tint",
                          help="Reference only — this app has no "
                               "theme-color settings.")
                st.slider("Contrast", 0, 100, 23, disabled=True,
                          key="profile_theme_contrast",
                          help="Reference only — this app has no "
                               "theme-color settings.")
                st.slider("Surface brightness", 0, 100, 100, disabled=True,
                          key="profile_theme_surface_brightness",
                          help="Reference only — this app has no "
                               "theme-color settings.")
                st.slider("Layer contrast", 0, 100, 100, disabled=True,
                          key="profile_theme_layer_contrast",
                          help="Reference only — this app has no "
                               "theme-color settings.")

            # Timezone — the avatar menu shows the same value ("Auto
            # (Asia/Calcutta)"). The app has no per-user timezone
            # setting: every time in the app is India time (IST).
            _r = _profile_row(
                st, "Timezone",
                "Times in this app are shown in India time (IST).")
            with _r:
                st.write("**Auto detect (Asia/Calcutta)**")
                st.caption("No per-user timezone setting — the app has "
                           "one timezone.")

        # (3b) Keyboard shortcuts ---------------------------------------
        # Supabase's switches (all checked) have no counterpart here:
        # this app has NO keyboard shortcuts at all. No switches are
        # rendered — a switch that did nothing would be the fake.
        # The honest equivalent is Quick Jump (Search in the top bar).
        _profile_section(st, "profile-shortcuts", "Keyboard shortcuts",
                         "Shortcuts for moving around the app.")
        with st.container(border=True):
            st.write("This app has no keyboard shortcuts. The equivalent "
                     "here is Quick Jump — press Search in the top bar "
                     "and type to jump to any tab.")

        # (3c) Dashboard -------------------------------------------------
        # Supabase's Dashboard switches (Edit entities in SQL off,
        # Queue table operations off). No counterparts in this app:
        # there is no SQL entity editor and no operation queue, so
        # both stay off and disabled.
        _profile_section(st, "profile-dashboard", "Dashboard",
                         "Supabase dashboard options.")
        with st.container(border=True):
            st.caption("These Supabase dashboard options have no "
                       "counterpart in this app — this app has no SQL "
                       "entity editor and no operation queue, so both "
                       "stay off.")
            _r = _profile_row(st, "Edit entities in SQL",
                              "Edit database entities directly in SQL.")
            with _r:
                st.toggle("Edit entities in SQL", value=False,
                          disabled=True,
                          key="profile_dashboard_edit_entities_sql",
                          label_visibility="collapsed",
                          help="No counterpart in this app — stays off.")
            _r = _profile_row(st, "Queue table operations",
                              "Queue table operations instead of running "
                              "them at once.")
            with _r:
                st.toggle("Queue table operations", value=False,
                          disabled=True,
                          key="profile_dashboard_queue_table_ops",
                          label_visibility="collapsed",
                          help="No counterpart in this app — stays off.")

        # (3d) Analytics and Marketing -----------------------------------
        # Supabase's telemetry switch (on there). This app collects NO
        # usage data and sends nothing anywhere — there is nothing to
        # opt out of, so the switch stays off and disabled.
        _profile_section(st, "profile-analytics",
                         "Analytics and Marketing",
                         "Usage data this app collects.")
        with st.container(border=True):
            st.caption("This app collects no usage data and sends nothing "
                       "anywhere — there is nothing to opt out of, so "
                       "this switch stays off.")
            _r = _profile_row(st, "Telemetry",
                              "Send anonymous usage data to help improve "
                              "the app.")
            with _r:
                st.toggle("Telemetry", value=False, disabled=True,
                          key="profile_analytics_telemetry",
                          label_visibility="collapsed",
                          help="This app sends no usage data — stays off.")

        # (4) Storage usage ----------------------------------------------
        # A proper card like the others, not a half-empty one: total +
        # the bar, then a per-folder breakdown (files and bytes each,
        # so an empty folder still reads as a line, not a blank),
        # then the free-tier limit. Every number comes from
        # storage_usage / list_all_files — nothing invented.
        _profile_section(st, "profile-storage", "Storage usage",
                         "How much of your 1 GB free-tier storage is used.")
        with st.container(border=True):
            try:
                _total_bytes, _per_folder = storage.storage_usage(storage_key)
                _files = storage.list_all_files(storage_key)
            except Exception as exc:  # noqa: BLE001 - show the error, don't crash
                st.error(f"Could not read your storage usage: {exc}")
                _total_bytes, _per_folder, _files = 0, {}, {}
            st.write(f"Total storage used: **{_total_bytes / (1024 * 1024):.1f} MB**")
            # Supabase profile pattern: storage as one thin hairline, green fill.
            _used_pct = _total_bytes / _FREE_TIER_BYTES * 100
            ui_design.storage_bar(
                _used_pct,
                f"{_total_bytes / (1024 * 1024):.1f} MB of 1 GB used")
            _folder_notes = {
                "uploads": "files you uploaded",
                "cleaned": "cleaned copies saved after each clean",
                "recipes": "saved cleaning recipes",
                "views": "saved views",
                "workspaces": "auto-saved workspaces",
                "backups": "backups",
            }
            for _sub in storage.SUBFOLDERS:
                _names = _files.get(_sub, []) if isinstance(_files, dict) else []
                _bytes = (_per_folder.get(_sub, 0)
                          if isinstance(_per_folder, dict) else 0)
                _note = _folder_notes.get(_sub, "")
                st.write(f"**{_sub}** — {len(_names)} file(s), "
                         f"{_format_bytes(_bytes)}"
                         + (f" ({_note})" if _note else ""))
            st.caption(
                "Free-tier storage limit: 1 GB "
                f"({_used_pct:.1f}% used). Only your own files count — "
                "nothing is shared.")

        # (5) Download my data -------------------------------------------
        _profile_section(st, "profile-download", "Download my data",
                         "A copy of your account details, sessions, file "
                         "list and storage usage — no passwords or keys "
                         "in it.")
        with st.container(border=True):
            _r = _profile_row(st, "Download a copy of your account data")
            with _r:
                try:
                    _export = build_data_export(user, storage_key)
                    st.download_button(
                        "Download my data",
                        data=json.dumps(_export, indent=2).encode("utf-8"),
                        file_name="my-data-export.json",
                        mime="application/json",
                        icon=ui_design.icon_for("download"),
                        key="profile_export_download")
                except Exception as exc:  # noqa: BLE001 - show the error, don't crash
                    st.error(f"Could not build your data export: {exc}")

        # (6) Log out -----------------------------------------------------
        _profile_section(st, "profile-logout", "Log out",
                         "Sign out of this account on this device.")
        with st.container(border=True):
            _r = _profile_row(st, "Sign out of this account")
            with _r:
                if ui_design.icon_button(
                        "Log out", "logout", key="profile_logout_btn",
                        help="Log out of this account."):
                    if on_logout is not None:
                        on_logout()
                    return "logout"

        # (7) Danger zone -------------------------------------------------
        # The danger zone is its own card, separated from the ordinary
        # settings above it — it is the one section a visitor must not
        # read as ordinary settings.
        _profile_section(st, "profile-danger", "Danger zone",
                         "Permanent account deletion — this cannot be undone.")
        with st.container(border=True):
            st.warning("Deleting your account is permanent. It removes your "
                       "files, your data and the login itself. "
                       "This cannot be undone.")
            _armed = bool(st.session_state.get("profile_delete_armed", False))
            if ui_design.icon_button(
                    "Delete my account", "delete", kind="danger",
                    key="profile_delete_reveal",
                    help="Reveal the delete confirmation."):
                st.session_state["profile_delete_armed"] = True
                _armed = True
            if _armed:
                _confirm = st.text_input("Type DELETE to confirm",
                                         key="profile_delete_confirm_input")
                if ui_design.icon_button(
                        "Yes, delete my account forever", "warning",
                        kind="danger", key="profile_delete_confirm",
                        help="Permanently delete the account."):
                    _ok, _err = delete_account(user, storage_key, _confirm)
                    if _ok:
                        try:
                            st.session_state.pop("profile_delete_armed", None)
                        except Exception:  # noqa: BLE001 - a lost flag is fine
                            pass
                        return "deleted"
                    st.error(_err or "Could not delete your account.")
    return None
