"""Web smoke test for Data Cleaner Studio (AppTest — no browser needed).

Flow: fresh app -> login screen only (no data) -> sign up -> log in
-> upload the sample CSV (per-user storage) -> clean -> dashboard
renders with no exception (all chart types) -> share link renders the
dashboard without login -> revoke -> link shows "not found" ->
wrong-password login fails -> user A cannot see user B's files.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler jobs
file are pointed at a temp dir, so the real data/ folder is untouched.
Run:  .test-venv/bin/python tests/test_web_smoke.py   (from project root)
"""

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import auth  # noqa: E402
import storage  # noqa: E402
import scheduler  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


def find_button(at, label):
    for b in at.button:
        if b.label == label:
            return b
    raise AssertionError(f"button {label!r} missing")


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def find_text_input(at, label):
    for t in at.text_input:
        if t.label == label:
            return t
    raise AssertionError(f"text input {label!r} missing")


def goto_section(at, label):
    """Pick a section in the sticky section switcher (radio 'Section')."""
    radio = next(r for r in at.radio if r.label == "Section")
    radio.set_value(label).run()
    assert not at.exception, f"exception going to {label}: {at.exception}"


def main():
    tmp = tempfile.mkdtemp(prefix="dcs-web-test-")
    tmp_path = Path(tmp)
    # Point all server-side state at the temp dir (never the real data/).
    # The checkout's supabase_config.json holds real values, so local
    # mode also needs the config path pointed at a nonexistent file in
    # the temp dir — same redirection pattern test_profile.py uses.
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"

    # ---- 1. Fresh app: login screen only, no data screen. ----
    at = AppTest.from_file(APP)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    assert not any(b.label == "Try the messy sample" for b in at.button), \
        "data screen must not show before login"
    assert any(b.label == "Log in" for b in at.button), "login button missing"
    assert any("Local mode" in v for v in vals(at.info)), "local-mode banner missing"
    # My UI text only (markdown/caption/title) — NOT at.info: the banner
    # and warning there come verbatim from auth.py (Supabase rework).
    # The login screen must not mention the previous provider (name
    # built without the literal so this file stays grep-clean for it).
    _prev = "Fire" + "base"
    _login_text = (vals(at.markdown) + vals(at.caption)
                   + [t.value for t in at.title])
    assert not any(_prev in v for v in _login_text), \
        "login screen must not mention the previous provider"
    print("login gate works: no data before login, local-mode banner shown")

    # ---- 2. Wrong-password login fails (no account yet, so any login fails). ----
    find_text_input(at, "Username").set_value("alice1").run()
    find_text_input(at, "Password").set_value("wrongpassword").run()
    find_button(at, "Log in").click().run()
    assert not at.exception, f"exception on failed login: {at.exception}"
    assert any("Wrong email/username or password" in v for v in vals(at.error)), \
        "wrong-password login should show an error"
    assert not any(b.label == "Try the messy sample" for b in at.button), \
        "failed login must not open the app"
    print("wrong-password login fails as expected")

    # ---- 3. Sign up logs the user straight in (no manual login step). ----
    at.radio[0].set_value("Sign up").run()
    find_text_input(at, "Username").set_value("alice1").run()
    find_text_input(at, "Password").set_value("password123").run()
    find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    assert any("Account created" in v for v in vals(at.success)), \
        "signup should confirm the account was created"
    # The rail starts collapsed (the dashboard's default) — open it
    # so the full sidebar (sample button, uploader) is visible below.
    # (After the "Account created" check: that note is transient and
    # an extra rerun clears it.)
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert not at.exception, f"exception expanding rail: {at.exception}"
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "signup should log the user straight in"
    assert at.session_state.get("current_user", {}).get("username") == "alice1"
    print("signup -> logged in straight away (auto-login)")

    # ---- 4. Upload the sample CSV: stored per-user, data loads. ----
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([("messy_sales.csv", SAMPLE.read_bytes(), "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert at.session_state["raw"] is not None, "raw data not loaded"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    assert storage.list_files("alice1", "uploads") == ["messy_sales.csv"], \
        "upload must be saved in alice1's uploads/"
    print("upload works: 80 rows, saved to alice1/uploads/")

    # ---- 5. Clean -> 77 rows; dashboard renders; chart types switch. ----
    goto_section(at, "Clean")
    find_button(at, "Clean my data").click().run()
    assert not at.exception, f"exception after cleaning: {at.exception}"
    clean = at.session_state["clean"]
    assert clean is not None and len(clean) == 77, "cleaned data should have 77 rows"
    assert storage.list_files("alice1", "cleaned"), \
        "cleaned copy should be saved to alice1/cleaned/"
    goto_section(at, "Dashboard")
    assert any("Group by" in s.label for s in at.selectbox), "dashboard X picker missing"
    goto_section(at, "Report")
    assert any("Download cleaned Excel" in b.label for b in at.download_button), \
        "excel download missing"
    assert any("Download PDF report" in b.label for b in at.download_button), \
        "PDF download missing"
    print("clean works: 77 rows, cleaned copy saved, dashboard + report render")
    goto_section(at, "Dashboard")
    for kind in ("Histogram", "Scatter", "Box plot", "Heatmap", "Treemap",
                 "Funnel"):
        chart = next(s for s in at.selectbox if s.label == "Chart")
        chart.set_value(kind).run()
        assert not at.exception, f"exception on {kind} chart: {at.exception}"
    print("Histogram / Scatter / Box plot / Heatmap / Treemap / Funnel render")

    # v1.2 checkbox regression: unchecking "Drop duplicate rows" keeps 80.
    goto_section(at, "Clean")
    drop_box = next(c for c in at.checkbox if c.label == "Drop duplicate rows")
    drop_box.uncheck().run()
    find_button(at, "Clean my data").click().run()
    assert len(at.session_state["clean"]) == 80, \
        "unchecked drop_dupes should keep 80 rows"
    drop_box = next(c for c in at.checkbox if c.label == "Drop duplicate rows")
    drop_box.check().run()
    find_button(at, "Clean my data").click().run()
    assert len(at.session_state["clean"]) == 77, \
        "re-checked drop_dupes should give 77 rows"
    print("checkboxes really control cleaning (80 vs 77 rows)")

    # ---- 6. Share dashboard: renders without login; revoke -> not found. ----
    goto_section(at, "Dashboard")
    find_button(at, "Share dashboard").click().run()
    assert not at.exception, f"exception on share: {at.exception}"
    token = at.session_state.get("last_share_token")
    assert token, "share token was not created"
    registry = storage.load_json("alice1", "views", "shares.json")
    assert token in registry and not registry[token].get("revoked"), \
        "share registry must hold the token"
    assert registry[token]["kpis"], "snapshot must carry KPIs"
    assert registry[token]["rows"], "snapshot must carry chart rows"

    shared = AppTest.from_file(APP)
    shared.query_params["share"] = token
    shared.run()
    assert not shared.exception, f"exception on shared view: {shared.exception}"
    assert not any(b.label == "Log in" for b in shared.button), \
        "shared view must not ask for a login"
    assert any("shared dashboard" in t.value.lower() for t in shared.title), \
        f"shared title missing: {[t.value for t in shared.title]}"
    assert len(shared.metric) > 0, "shared dashboard should show KPI metrics"
    print("share link renders the dashboard without login")

    goto_section(at, "Settings")
    find_button(at, "Revoke").click().run()
    assert not at.exception, f"exception on revoke: {at.exception}"
    registry = storage.load_json("alice1", "views", "shares.json")
    assert registry[token].get("revoked") is True, "token must be revoked"

    gone = AppTest.from_file(APP)
    gone.query_params["share"] = token
    gone.run()
    assert not gone.exception, f"exception on revoked view: {gone.exception}"
    assert any("revoked or does not exist" in v for v in vals(gone.error)), \
        "revoked link must show 'revoked or does not exist'"
    print("revoked share link shows 'not found'")

    # ---- 7. User isolation: bob cannot see alice's files. ----
    ok, err = auth.create_user("bob1", "password123")
    assert ok, f"could not create bob: {err}"
    storage.save_upload("alice1", "alice_secret.csv", b"a,b\n1,2\n")
    assert "alice_secret.csv" in storage.list_files("alice1", "uploads")
    assert "alice_secret.csv" not in storage.list_files("bob1", "uploads"), \
        "bob must not list alice's files"
    assert storage.list_files("bob1", "uploads") == [], \
        "bob's uploads must start empty"
    try:
        storage.read_file("bob1", "uploads", "alice_secret.csv")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("bob must not read alice's file")

    bob = AppTest.from_file(APP)
    bob.run()
    find_text_input(bob, "Username").set_value("bob1").run()
    find_text_input(bob, "Password").set_value("password123").run()
    find_button(bob, "Log in").click().run()
    assert not bob.exception, f"exception on bob login: {bob.exception}"
    # The rail starts collapsed (the dashboard's default) — open it
    # so the full sidebar is visible below.
    bob.session_state["dcs_rail_collapsed"] = False
    bob.run()
    assert not bob.exception, f"exception expanding rail: {bob.exception}"
    assert any(b.label == "Try the messy sample" for b in bob.button), \
        "bob should reach the app"
    assert not any("alice_secret.csv" in str(o)
                   for s in bob.selectbox for o in s.options), \
        "bob's sidebar must not list alice's files"
    print("user isolation works: bob cannot list or read alice's files")

    # ---- 8. Log out returns to the login screen. ----
    # The "Log out" button lives on the Profile page (the avatar menu
    # says "Sign out" instead) — go there first.
    goto_section(at, "Profile")
    find_button(at, "Log out").click().run()
    assert not at.exception, f"exception on logout: {at.exception}"
    assert any(b.label == "Log in" for b in at.button), \
        "logout should return to the login screen"
    assert not any(b.label == "Try the messy sample" for b in at.button)
    print("logout works")

    print("WEB SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
