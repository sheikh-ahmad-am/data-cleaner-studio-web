"""Data Cleaner Studio — Profile section.

The account page: account info + display name, password reset,
download-my-data export, storage usage, log out, and the danger
zone (permanent account deletion).

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
    app's real email+code login), "Appearance" (Light/Dark theme),
    "Storage usage", "Download my data", "Log out", "Danger zone".
    No Access Tokens, no Audit Logs, no Upgrade to Pro: the app has
    none of those, and a button to nowhere would be fake.

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
        _profile_subnav_link(st, "profile-appearance", "Appearance")
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

        # (3) Appearance --------------------------------------------------
        # Light/Dark only — there is no System row here: System lives
        # in the account menu's Theme section (it follows the OS
        # through the Round 3 cookie bridge). Picking Light or Dark
        # here sets the preference too (set_theme), so the account
        # menu's radio agrees on the next run.
        _profile_section(st, "profile-appearance", "Appearance",
                         "Choose how the app looks.")
        with st.container(border=True):
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
