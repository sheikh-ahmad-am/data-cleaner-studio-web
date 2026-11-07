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
    """The Profile section, in order: account info, change password,
    download my data, storage usage, log out, danger zone — one
    bordered settings card per section (the dashboard's settings-page
    shape: label + description left, controls right, Save at the
    card's bottom-right), with the title + caption fused into one
    heading element.

    Returns "deleted" when the account was deleted (the caller clears
    the session and reruns), "logout" when the Log out button was
    pressed and no on_logout callback was given (the caller logs the
    user out), and None otherwise. When on_logout is given it is
    called directly for the Log out button (the app passes its own
    logout helper, so the button behaves exactly like the sidebar
    one). On a failed delete the error is shown and the user stays
    logged in, so they can retry.
    """
    # One heading for the whole page — title + caption fused into a
    # single element, so the caption can never again be separated
    # from its title (the live check found the old st.caption missing
    # from the screen even though the code was there).
    ui_design.section_heading("Profile",
                              sub="Your account, sign-in and data.")

    # (1) Account info ------------------------------------------------------
    _acct_left, _acct_right, _acct_card = ui_design.settings_card(
        "Account info", "Your email, display name, and when you joined.")
    _email = user.get("email") or user.get("username") or "?"
    with _acct_right:
        st.write(f"Email: **{_email}**")
        st.write(f"Member since: **{_member_since_text(user.get('created_at'))}**")
        _has_display_name = isinstance(user, dict) and "display_name" in user
        _new_name = st.text_input(
            "Display name",
            value=str(user.get("display_name") or "") if _has_display_name else "",
            key="profile_display_name",
            disabled=not _has_display_name,
            help="The name shown on your avatar and on shared dashboards.")
        if not _has_display_name:
            st.caption("Display names need the updated database setup (run "
                       "supabase_setup.sql) — this field is disabled until "
                       "then.")
        if st.session_state.pop("profile_display_name_saved", False):
            st.success("Display name saved. It now shows as "
                       f"'{user.get('display_name')}' on your avatar.")
    with _acct_card:
        _sp, _save_col = st.columns([3, 1])
        with _save_col:
            if ui_design.icon_button(
                    "Save display name", "check", kind="primary",
                    key="profile_display_name_save",
                    disabled=not _has_display_name,
                    use_container_width=True,
                    help="Save the display name."):
                _ok, _err = auth.set_display_name(
                    user.get("id"), _new_name.strip())
                if _ok:
                    try:
                        st.session_state["current_user"]["display_name"] = (
                            _new_name.strip())
                    except Exception:  # noqa: BLE001 - session dict is best-effort
                        pass
                    st.session_state["profile_display_name_saved"] = True
                    st.success("Display name saved. It now shows as "
                               f"'{_new_name.strip()}' on your avatar.")
                else:
                    st.error(_err or "Could not save the display name.")

    # (2) Change password ---------------------------------------------------
    _pw_left, _pw_right, _pw_card = ui_design.settings_card(
        "Change password",
        "Reset your password by email (cloud accounts only).")
    with _pw_right:
        if auth.get_auth_backend() == "supabase":
            if st.session_state.pop("profile_reset_sent", False):
                st.success(f"Reset link sent to {user.get('email')} — check "
                           "your inbox (and spam).")
            if st.button("Send password-reset email",
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

    # (3) Download my data --------------------------------------------------
    _dl_left, _dl_right, _dl_card = ui_design.settings_card(
        "Download my data",
        "A copy of your account details, sessions, file list and storage "
        "usage — no passwords or keys in it.")
    with _dl_right:
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

    # (4) Storage usage -----------------------------------------------------
    # A proper card like the others, not a half-empty one: total + the
    # bar, then a per-folder breakdown (files and bytes each, so an
    # empty folder still reads as a line, not a blank), then the
    # free-tier limit. Every number comes from storage_usage /
    # list_all_files — nothing invented.
    _st_left, _st_right, _st_card = ui_design.settings_card(
        "Storage usage", "How much of your 1 GB free-tier storage is used.")
    with _st_right:
        try:
            _total_bytes, _per_folder = storage.storage_usage(storage_key)
            _files = storage.list_all_files(storage_key)
        except Exception as exc:  # noqa: BLE001 - show the error, don't crash
            st.error(f"Could not read your storage usage: {exc}")
            _total_bytes, _per_folder, _files = 0, {}, {}
        st.write(f"Total storage used: **{_total_bytes / (1024 * 1024):.1f} MB**")
        # Supabase profile pattern: storage as one thin hairline, green fill.
        _used_pct = _total_bytes / _FREE_TIER_BYTES * 100
        try:
            from ui_design import storage_bar as _storage_bar
        except Exception:  # noqa: BLE001 - fall back to the text lines below
            _storage_bar = None
        if _storage_bar is not None:
            _storage_bar(_used_pct,
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

    # (5) Log out -----------------------------------------------------------
    _lo_left, _lo_right, _lo_card = ui_design.settings_card(
        "Log out", "Sign out of this account on this device.")
    with _lo_right:
        if ui_design.icon_button(
                "Log out", "logout", key="profile_logout_btn",
                help="Log out of this account."):
            if on_logout is not None:
                on_logout()
            return "logout"

    # (6) Danger zone -------------------------------------------------------
    # The danger zone is its own card, separated from the ordinary
    # settings above it — it is the one section a visitor must not
    # read as ordinary settings.
    _dz_left, _dz_right, _dz_card = ui_design.settings_card(
        "Danger zone", "Permanent account deletion — this cannot be undone.")
    with _dz_right:
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
