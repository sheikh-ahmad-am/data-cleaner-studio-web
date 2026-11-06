"""Tests for auth.py and storage.py (web version).

Run:  python3 tests/test_auth_storage.py   (from the project root)
Uses a temp dir for the users DB and per-user storage so real data is
never touched. No Streamlit needed.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth
import storage


def _isolate(tmp: Path):
    """Point auth DB + storage at a temp dir; return a restore function.

    Also repoints the Supabase config path at a nonexistent temp file
    and clears Supabase env vars, so the backend is deterministically
    'local' no matter what credential files exist in the project folder.
    """
    auth_db = tmp / "users.db"
    store_base = tmp / "users"
    old_db, old_base = auth.DB_PATH, storage.BASE_DIR
    old_cfg = auth.SUPABASE_CONFIG_PATH
    old_env = {k: os.environ.pop(k, None)
               for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY")}
    auth.DB_PATH = auth_db
    storage.BASE_DIR = store_base
    auth.SUPABASE_CONFIG_PATH = tmp / "no-supabase_config.json"
    auth._reset_backend_cache()
    assert auth.get_auth_backend() == "local"
    assert auth.get_local_mode_banner() is not None
    return old_db, old_base, old_cfg, old_env


def test_signup_login_success():
    ok, err = auth.create_user("alice", "supersecret1")
    assert ok and err is None, f"signup failed: {err}"
    user = auth.authenticate("alice", "supersecret1")
    assert user is not None and user["username"] == "alice"
    assert "password_hash" not in user and "salt" not in user
    fetched = auth.get_user_by_id(user["id"])
    assert fetched is not None and fetched["username"] == "alice"
    print("signup + login OK")


def test_wrong_password_fails():
    assert auth.authenticate("alice", "wrongpassword") is None
    assert auth.authenticate("nosuchuser", "supersecret1") is None
    assert auth.authenticate("alice", "") is None
    print("wrong password fails OK")


def test_duplicate_username_rejected():
    ok, err = auth.create_user("alice", "anotherpass1")
    assert not ok and err, "duplicate username must be rejected"
    print("duplicate rejected OK:", err)


def test_bad_signup_inputs():
    for bad_user in ("ab", "a" * 31, "bad name", "bad-name", "", None, 123):
        ok, err = auth.create_user(bad_user, "supersecret1")
        assert not ok and err, f"bad username {bad_user!r} must be rejected"
    for bad_pw in ("short", "", None, 123):
        ok, err = auth.create_user("carol", bad_pw)
        assert not ok and err, f"bad password {bad_pw!r} must be rejected"
    print("bad signup inputs OK")


def test_session_validates_and_expires():
    user = auth.authenticate("alice", "supersecret1")
    token = auth.create_session(user["id"])
    assert isinstance(token, str) and len(token) >= 32
    assert auth.validate_session(token)["username"] == "alice"
    assert auth.validate_session("bogus-token") is None
    assert auth.validate_session("") is None
    assert auth.create_session(999999) is None  # unknown user
    # Force expiry by backdating the stored expiry, then validate.
    import sqlite3
    from datetime import datetime, timedelta, timezone

    conn = sqlite3.connect(str(auth.DB_PATH))
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    conn.execute("UPDATE sessions SET expires_at = ? WHERE token = ?", (past, token))
    conn.commit()
    conn.close()
    assert auth.validate_session(token) is None, "expired token must not validate"
    print("session validates + expires OK")


def test_logout_invalidates():
    user = auth.authenticate("alice", "supersecret1")
    token = auth.create_session(user["id"])
    assert auth.validate_session(token) is not None
    auth.delete_session(token)
    assert auth.validate_session(token) is None
    auth.delete_session(token)  # deleting twice is a harmless no-op
    auth.delete_session("nonexistent")
    print("logout invalidates OK")


def test_storage_isolation():
    auth.create_user("bob", "bobspassword1")
    # Alice writes her own files.
    p = storage.save_upload("alice", "sales.csv", b"a,b\n1,2\n")
    assert p.read_bytes() == b"a,b\n1,2\n"
    storage.save_json("alice", "recipes", "clean1", {"steps": ["trim"]})
    assert storage.load_json("alice", "recipes", "clean1") == {"steps": ["trim"]}
    assert storage.load_json("alice", "recipes", "clean1.json") == {"steps": ["trim"]}
    assert storage.load_json("alice", "recipes", "missing") is None
    assert storage.list_files("alice", "uploads") == ["sales.csv"]
    assert storage.read_file("alice", "uploads", "sales.csv") == b"a,b\n1,2\n"
    # Bob's tree starts empty and stays separate.
    for sub in storage.SUBFOLDERS:
        assert storage.list_files("bob", sub) == [], f"bob/{sub} must start empty"
    # Bob cannot read/list/delete Alice's files, even by name.
    for fn in (storage.read_file, storage.delete_file):
        try:
            fn("bob", "uploads", "sales.csv")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError(f"{fn.__name__} must not reach alice's file")
    assert storage.load_json("bob", "recipes", "clean1") is None
    print("storage isolation OK")


def test_traversal_blocked():
    # '..' traversal attempts must raise ValueError, never escape the root.
    for fn, args in (
        (storage.read_file, ("alice", "uploads", "../bob/secret.txt")),
        (storage.read_file, ("alice", "uploads", "../../etc/passwd")),
        (storage.delete_file, ("alice", "uploads", "../bob/x.csv")),
        (storage.list_files, ("alice", "../bob")),
        (storage.save_upload, ("alice", "../bob/evil.csv", b"x")),
        (storage.save_json, ("alice", "recipes", "../../bob/evil", {})),
        (storage.user_root, ("../bob",)),
        (storage.user_root, ("alice/../../bob",)),
    ):
        try:
            fn(*args)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{fn.__name__}{args} must raise ValueError")
    # A filename with any directory component is rejected outright —
    # never silently rewritten to a different name.
    try:
        storage.save_upload("alice", "subdir/../../weird.csv", b"z")
    except ValueError:
        pass
    else:
        raise AssertionError("directory in filename must raise ValueError")
    print("traversal blocked OK")


def test_storage_delete_and_tree():
    root = storage.user_root("alice")
    assert root.name == "alice"
    assert sorted(d.name for d in root.iterdir() if d.is_dir()) == sorted(
        storage.SUBFOLDERS
    )
    storage.save_upload("alice", "todelete.csv", b"x")
    assert "todelete.csv" in storage.list_files("alice", "uploads")
    storage.delete_file("alice", "uploads", "todelete.csv")
    assert "todelete.csv" not in storage.list_files("alice", "uploads")
    try:
        storage.delete_file("alice", "uploads", "todelete.csv")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("deleting a missing file must raise FileNotFoundError")
    print("delete + folder tree OK")


def test_full_flow_signup_login_upload_clean_isolation():
    """End to end in local mode: signup -> login -> session -> upload a
    messy CSV -> clean it with the engine -> save the cleaned file ->
    user B cannot see any of it."""
    import engine

    ok, err = auth.create_user("dave", "davespassword1")
    assert ok and err is None, f"signup failed: {err}"
    user = auth.authenticate("dave", "davespassword1")
    assert user is not None
    token = auth.create_session(user["id"])
    assert auth.validate_session(token)["username"] == "dave"

    messy = b"Name, Age, City\n Alice , 30 , Delhi\nBOB,30,delhi\nAlice,30,Delhi\n"
    storage.save_upload("dave", "messy.csv", messy)
    raw = storage.read_file("dave", "uploads", "messy.csv")
    df = engine.load_file("messy.csv", raw)
    assert len(df) == 3
    clean, actions = engine.clean(df)
    assert len(clean) < 3 or actions, "clean must change something"
    cleaned_csv = clean.to_csv(index=False).encode("utf-8")
    storage.save_file("dave", "cleaned", "cleaned_messy.csv", cleaned_csv)
    assert storage.read_file("dave", "cleaned", "cleaned_messy.csv") == cleaned_csv
    assert "cleaned_messy.csv" in storage.list_files("dave", "cleaned")

    # Bob (created earlier) sees none of Dave's files, in any subfolder.
    for sub in ("uploads", "cleaned"):
        assert storage.list_files("bob", sub) == []
        try:
            storage.read_file("bob", sub, "messy.csv")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError(f"bob must not read dave's {sub}/messy.csv")
    print("full flow signup->login->upload->clean->isolation OK")


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        old_db, old_base, old_cfg, old_env = _isolate(tmp)
        try:
            test_signup_login_success()
            test_wrong_password_fails()
            test_duplicate_username_rejected()
            test_bad_signup_inputs()
            test_session_validates_and_expires()
            test_logout_invalidates()
            test_storage_isolation()
            test_traversal_blocked()
            test_storage_delete_and_tree()
            test_full_flow_signup_login_upload_clean_isolation()
        finally:
            auth.DB_PATH, storage.BASE_DIR = old_db, old_base
            auth.SUPABASE_CONFIG_PATH = old_cfg
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            auth._reset_backend_cache()
    print("\nALL AUTH/STORAGE TESTS PASSED")


if __name__ == "__main__":
    main()
