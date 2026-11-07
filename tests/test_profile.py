"""Profile section tests (AppTest — no browser needed).

Flow: sign up -> top bar shows the avatar (green circle, initial)
-> the avatar menu holds the email, Account, and Sign out -> clicking
Account opens the Profile view (account info, storage usage,
download button, danger zone) -> delete gating: the final delete
button without "DELETE" typed does nothing -> typing DELETE +
confirming deletes the account (user row gone, files gone) and
returns to the login screen -> the Profile view's own Log out button
logs out too.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler jobs
file are pointed at a temp dir, so the real data/ folder is untouched.
Run ONLY this file:  .test-venv-verify/bin/python -m pytest
tests/test_profile.py -q   (from project root)
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import auth  # noqa: E402
import feat_profile  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    The checkout's supabase_config.json holds real values, so local
    mode also needs the config path pointed at a nonexistent file in
    the temp dir — same redirection pattern as DB_PATH / BASE_DIR,
    and the real file is never touched.
    """
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    yield tmp_path


def find_button(at, label, key=None):
    for b in at.button:
        if b.label == label and (key is None or b.key == key):
            return b
    raise AssertionError(f"button {label!r} (key={key!r}) missing")


def find_text_input(at, label):
    for t in at.text_input:
        if t.label == label:
            return t
    raise AssertionError(f"text input {label!r} missing")


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def expand_rail(at):
    """Open the sidebar rail (it starts collapsed — the dashboard's
    own default, icon-only) so the full sidebar is visible: theme
    selectbox, labelled nav rows, uploader, sample button. The rail
    tests in test_supabase_rail.py cover the collapsed state itself;
    the older helpers below need the expanded sidebar to do their
    jobs."""
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert not at.exception, f"exception expanding rail: {at.exception}"


def signup(at, username, password="password123"):
    """Sign up (auto-login) and return the new user's id."""
    at.radio[0].set_value("Sign up").run()
    find_text_input(at, "Username").set_value(username).run()
    find_text_input(at, "Password").set_value(password).run()
    find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    expand_rail(at)
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "signup should log the user straight in"
    return at.session_state["current_user"]["id"]


def goto_profile(at):
    """Open the Profile section from the avatar menu's Account action."""
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert not at.exception, f"exception opening Profile: {at.exception}"
    radio = next(r for r in at.radio if r.label == "Section")
    assert radio.value == "Profile", \
        f"section switcher should read Profile, got {radio.value!r}"


def assert_profile_view(at):
    """The Profile view's sections are all on screen (one bordered
    settings card per section — the title is the card's heading,
    rendered as markdown, not a subheader)."""
    for section in ("Account info", "Change password", "Download my data",
                    "Storage usage", "Danger zone"):
        assert any(section in v for v in vals(at.markdown)), \
            f"Profile section {section!r} missing"
    assert any(b.label == "Download my data" for b in at.download_button), \
        "download-my-data button missing"
    assert any(b.label == "Delete my account" for b in at.button), \
        "danger-zone delete button missing"


def upload_sample(at, username):
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([("messy_sales.csv", SAMPLE.read_bytes(), "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert storage.list_files(username, "uploads") == ["messy_sales.csv"], \
        "upload must be saved in the user's uploads/"


# ---------------------------------------------------------------------------
# 1. Sidebar avatar + opening the Profile view
# ---------------------------------------------------------------------------

def test_sidebar_avatar_and_open_profile(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    signup(at, "alice1")

    # Top-bar avatar: no card, no standalone buttons — the username
    # and email must not appear as sidebar markdown, and the old
    # Profile / Log out buttons are gone. The avatar menu (popover)
    # holds the Account + Sign out actions instead (local users have
    # no email, so no email caption shows here — the email case is
    # covered in test_sidebar_avatar.py).
    assert not any("alice1" in v for v in vals(at.sidebar.markdown)), \
        "sidebar must not show the username as markdown (card gone)"
    assert not any("@" in v for v in vals(at.sidebar.markdown)), \
        "sidebar must not show the email as markdown (card gone)"
    assert not any("Signed in as" in v for v in vals(at.markdown)), \
        "old 'Signed in as' sidebar line should be gone"
    assert not any(b.key == "profile_btn" for b in at.sidebar.button), \
        "old standalone sidebar Profile button should be gone"
    assert not any(b.key == "logout_btn" for b in at.sidebar.button), \
        "old standalone sidebar Log out button should be gone"
    find_button(at, "Account", key="avatar_account_btn")
    find_button(at, "Sign out", key="avatar_logout_btn")

    # The section switcher only renders once data is loaded (the app
    # stops at "Nothing loaded yet" before that), so load the sample
    # first — same as the smoke test's upload-then-navigate flow.
    upload_sample(at, "alice1")
    goto_profile(at)
    assert_profile_view(at)

    # Local mode: the user dict now carries a display_name key (None
    # until set), so the editor is enabled — saving a name works
    # end to end and the avatar picks the new initial up.
    name_input = find_text_input(at, "Display name")
    assert not name_input.disabled, \
        "display-name editor should be enabled once the DB setup exists"
    assert not any("updated database setup" in v for v in vals(at.caption)), \
        "no DB-setup note should show once the setup exists"
    name_input.set_value("Alice A").run()
    find_button(at, "Save display name").click().run()
    assert not at.exception, f"exception saving display name: {at.exception}"
    assert any("Display name saved." in v for v in vals(at.success)), \
        "saving the display name should confirm"
    assert at.session_state["current_user"].get("display_name") == "Alice A", \
        "saved display name should land in the session user"
    assert auth.get_user_by_id(
        at.session_state["current_user"]["id"])["display_name"] == "Alice A"
    # Local mode: password reset is cloud-only.
    assert any("only available for cloud accounts" in v
               for v in vals(at.markdown)), \
        "local mode should note password reset is cloud-only"
    # Storage usage line: total in MB, one decimal.
    assert any("Total storage used:" in v and "MB" in v
               for v in vals(at.markdown)), "storage usage line missing"
    assert any("Free-tier storage limit: 1 GB" in v
               for v in vals(at.caption)), "1 GB free-tier note missing"


# ---------------------------------------------------------------------------
# 2. Delete gating: confirming without DELETE does nothing
# ---------------------------------------------------------------------------

def test_delete_gating_without_confirmation(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    user_id = signup(at, "alice1")
    upload_sample(at, "alice1")
    goto_profile(at)

    find_button(at, "Delete my account").click().run()
    assert not at.exception, f"exception revealing delete: {at.exception}"
    find_text_input(at, "Type DELETE to confirm")
    find_button(at, "Yes, delete my account forever").click().run()
    assert not at.exception, f"exception on ungated delete: {at.exception}"
    assert any("Type DELETE to confirm." in v for v in vals(at.error)), \
        "confirming without DELETE should show the gate message"
    # Still logged in, user row and files untouched.
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "ungated delete must keep the user logged in"
    assert auth.get_user_by_id(user_id) is not None, \
        "ungated delete must not remove the user row"
    assert storage.list_files("alice1", "uploads") == ["messy_sales.csv"], \
        "ungated delete must not remove files"


# ---------------------------------------------------------------------------
# 3. Typing DELETE + confirming deletes the account and logs out
# ---------------------------------------------------------------------------

def test_delete_with_confirmation_removes_account(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    user_id = signup(at, "alice1")
    upload_sample(at, "alice1")
    goto_profile(at)

    find_button(at, "Delete my account").click().run()
    find_text_input(at, "Type DELETE to confirm").set_value("DELETE").run()
    find_button(at, "Yes, delete my account forever").click().run()
    assert not at.exception, f"exception on confirmed delete: {at.exception}"
    assert any(b.label == "Log in" for b in at.button), \
        "confirmed delete should return to the login screen"
    assert not any(b.label == "Try the messy sample" for b in at.button), \
        "confirmed delete must log the user out"
    assert auth.get_user_by_id(user_id) is None, \
        "confirmed delete must remove the local user row"
    for sub in storage.SUBFOLDERS:
        assert storage.list_files("alice1", sub) == [], \
            f"confirmed delete must empty {sub}/"


# ---------------------------------------------------------------------------
# 4. The Profile view's own Log out button logs out
# ---------------------------------------------------------------------------

def test_profile_logout_button(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    upload_sample(at, "alice1")
    goto_profile(at)
    find_button(at, "Log out", key="profile_logout_btn").click().run()
    assert not at.exception, f"exception on profile logout: {at.exception}"
    assert any(b.label == "Log in" for b in at.button), \
        "profile Log out should return to the login screen"
    assert not any(b.label == "Try the messy sample" for b in at.button)


# ---------------------------------------------------------------------------
# 5. Unit level: delete_account gating + export shape
# ---------------------------------------------------------------------------

def test_delete_account_and_export_units(_tmp_env):
    ok, err = auth.create_user("carol1", "password123")
    assert ok, f"could not create carol: {err}"
    user = auth.get_user_by_id(
        auth.authenticate("carol1", "password123")["id"])
    assert user is not None
    storage.save_upload("carol1", "notes.csv", b"a,b\n1,2\n")

    # Wrong confirmation: nothing happens, exact message.
    done, err = feat_profile.delete_account(user, "carol1", "delete")
    assert done is False and err == "Type DELETE to confirm."
    assert auth.get_user_by_id(user["id"]) is not None
    assert storage.list_files("carol1", "uploads") == ["notes.csv"]

    # Export: profile + sessions + files + usage, no secrets in it.
    export = feat_profile.build_data_export(user, "carol1")
    assert export["profile"]["email"] is None  # local users have no email
    assert export["profile"]["backend"] == "local"
    assert export["profile"]["member_since"] == user["created_at"]
    assert isinstance(export["sessions"], list)
    assert export["files"]["uploads"] == ["notes.csv"]
    assert export["storage_usage_bytes"] == len(b"a,b\n1,2\n")
    assert "exported_at" in export
    blob = json.dumps(export).lower()
    assert "password" not in blob and "token" not in blob, \
        "export must not contain passwords or tokens"

    # Exact confirmation: files + row gone.
    done, err = feat_profile.delete_account(user, "carol1", "DELETE")
    assert (done, err) == (True, None), f"delete failed: {err}"
    assert auth.get_user_by_id(user["id"]) is None
    assert storage.list_files("carol1", "uploads") == []
    # Idempotent retry: deleting again reports success, not a crash.
    done, err = feat_profile.delete_account(user, "carol1", "DELETE")
    assert done is True, f"retry delete should succeed: {err}"


# ---------------------------------------------------------------------------
# 6. Profile is reachable with NO data loaded (empty-state branch)
# ---------------------------------------------------------------------------

def test_profile_reachable_without_data(_tmp_env):
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "alice1")
    # No file loaded: the app shows the empty state and stops before
    # the section switcher — the avatar menu's Account action must
    # still open the Profile view (no data needed for an account page).
    # The empty state is rendered by ui_design.empty_state as
    # markdown (<h3>), not st.subheader, since the Supabase rebuild.
    assert any("Nothing loaded yet" in m.value for m in at.markdown), \
        "fresh login with no data should show the empty state"
    find_button(at, "Account", key="avatar_account_btn").click().run()
    assert not at.exception, f"exception opening Profile empty: {at.exception}"
    assert_profile_view(at)
    # Back returns to the empty state.
    find_button(at, "← Back to data").click().run()
    assert not at.exception, f"exception going back: {at.exception}"
    assert any("Nothing loaded yet" in m.value for m in at.markdown), \
        "Back should return to the empty state"
    assert not any("Account info" in v for v in vals(at.markdown)), \
        "profile view should be gone after Back"
