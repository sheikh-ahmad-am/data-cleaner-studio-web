"""Per-user storage for the Data Cleaner Studio web version.

TWO BACKENDS, ONE API (mirrors auth.py):
  * LOCAL mode — every user gets an isolated tree under
    data/users/<username>/:
        uploads/  cleaned/  recipes/  views/  workspaces/
    All file operations below run against those folders.
  * SUPABASE mode — the same operations run against Supabase Storage,
    one private bucket (`user-files`), per-user paths
    `<storage-key>/<subfolder>/<filename>`. The storage key is what
    the app passes in (a local username, or the `u_<hash>` key the app
    derives from an email — never the raw email).

Every function takes the username (storage key) first and enforces
the boundary: in local mode the final resolved path must stay inside
that user's root; in Supabase mode the object path is built only from
validated parts, never from caller-supplied separators. Any escape
attempt raises ValueError.

Filenames are sanitized: any directory component in a filename is
rejected with ValueError, and only safe characters are kept, so a
hostile filename can never reach another user's tree.

SERVICE-ROLE KEY (read this before "simplifying" it): Storage access
goes through a SEPARATE client built with the SUPABASE_SERVICE_ROLE_KEY
environment variable (or a Streamlit Cloud secret of the same name) —
never from a file, never in the repo, never sent to the browser. The
reason is structural, not laziness: Supabase Storage RLS identifies
the user from the Supabase Auth JWT (auth.uid()), but this app's
sessions are custom server-side opaque tokens (see auth.py), so the
anon key carries no per-user identity and RLS cannot scope it.
The trusted server therefore uses the service-role key and enforces
per-user isolation in Python (the same validation as local mode),
after auth.validate_session() has already approved the caller.
The bucket stays private, and supabase_setup.sql ships the standard
auth.uid() bucket policies so any future direct client access is
per-user by construction. If the service-role key is not configured,
Supabase-mode storage raises a clear RuntimeError instead of silently
writing files locally — a Supabase user's files must never split
across two stores.

`user_root()` is the ONE function that stays local in both modes: it
returns the real local directory the feature modules need for their
direct Path I/O (settings.json, views.json, workspaces). In Supabase
mode it is the local working root; the canonical store for every
storage.py-mediated file is still the bucket. (The scheduler works
off local folders too — see DEPLOY.md for how scheduled refresh works
for Supabase-mode users: download -> refresh -> upload back.)

Public API (imported by the Streamlit app):
    user_root(username) -> Path
    save_upload(username, filename, data_bytes) -> Path
    save_file(username, subfolder, filename, data_bytes) -> Path
    list_files(username, subfolder) -> list[str]
    read_file(username, subfolder, filename) -> bytes
    delete_file(username, subfolder, filename) -> None
    save_json(username, subfolder, filename, obj) -> Path
    load_json(username, subfolder, filename) -> obj or None

In Supabase mode the Path returned by save_* is the object path
inside the bucket (e.g. Path("u_abc.../uploads/sales.csv")), NOT a
local file — do not read it off disk. The app ignores these return
values today.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import auth as _auth

BASE_DIR = Path(__file__).resolve().parent / "data" / "users"

SUBFOLDERS = ("uploads", "cleaned", "recipes", "views", "workspaces",
              "backups")

STORAGE_BUCKET = "user-files"

# A username that reaches the filesystem must be the same shape auth.py
# accepts; anything else is rejected rather than mapped to a directory.
# The app's Supabase-mode storage keys ("u_" + 20 hex chars) match it too.
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")

_SB_STORAGE_CLIENT = None  # supabase-py Client built with the service key


def _validate_username(username: str) -> None:
    if not isinstance(username, str) or not _USERNAME_RE.match(username):
        raise ValueError(f"Invalid username: {username!r}")


def _validate_subfolder(subfolder: str) -> str:
    if not isinstance(subfolder, str) or subfolder not in SUBFOLDERS:
        raise ValueError(f"Invalid subfolder: {subfolder!r}")
    return subfolder


def _sanitize_filename(filename: str) -> str:
    """Validate a filename. Directory separators are REJECTED (ValueError),
    never silently stripped — a caller passing 'a/b.csv' or '../x' is a
    bug or an attack, and hiding it would mask both. Only safe chars are
    kept; the result is never '' or '.'/'..'."""
    if not isinstance(filename, str) or not filename:
        raise ValueError("Filename must be a non-empty string.")
    if "/" in filename or "\\" in filename:
        raise ValueError(f"Filename must not contain directories: {filename!r}")
    name = _SAFE_CHARS_RE.sub("_", filename).strip("._")
    if not name or name in (".", ".."):
        raise ValueError(f"Invalid filename: {filename!r}")
    return name


def _resolve_within(root: Path, *parts: str) -> Path:
    """Resolve a path and enforce it stays inside root (symlink-safe)."""
    root_resolved = root.resolve()
    target = (root_resolved.joinpath(*parts)).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError(f"Path escapes user storage: {target}")
    return target


# ---------------------------------------------------------------------------
# LOCAL MODE — per-user server folders (original design, unchanged)
# ---------------------------------------------------------------------------

def user_root(username: str) -> Path:
    """Return (and create) the user's root directory with its subfolders.

    This stays a LOCAL path in both backends (see the module docstring):
    the feature modules need a real directory for their direct Path I/O.
    """
    _validate_username(username)
    root = _resolve_within(BASE_DIR, username)
    root.mkdir(parents=True, exist_ok=True)
    for sub in SUBFOLDERS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _subfolder_dir(username: str, subfolder: str) -> Path:
    root = user_root(username)
    subfolder = _validate_subfolder(subfolder)
    return _resolve_within(root, subfolder)


def _file_path(username: str, subfolder: str, filename: str) -> Path:
    folder = _subfolder_dir(username, subfolder)
    safe_name = _sanitize_filename(filename)
    return _resolve_within(folder, safe_name)


def _local_save(username: str, subfolder: str, filename: str,
                data_bytes: bytes) -> Path:
    path = _file_path(username, subfolder, filename)
    path.write_bytes(bytes(data_bytes))
    return path


def _local_list(username: str, subfolder: str) -> list[str]:
    folder = _subfolder_dir(username, subfolder)
    return sorted(p.name for p in folder.iterdir() if p.is_file())


def _local_read(username: str, subfolder: str, filename: str) -> bytes:
    return _file_path(username, subfolder, filename).read_bytes()


def _local_delete(username: str, subfolder: str, filename: str) -> None:
    _file_path(username, subfolder, filename).unlink()


# ---------------------------------------------------------------------------
# SUPABASE MODE — Supabase Storage (private bucket, per-user paths)
# ---------------------------------------------------------------------------

def _sb_service_key() -> str | None:
    """Service-role key from the environment (or a Streamlit secret).

    NEVER from a file, NEVER from the repo. Returns None when it is
    not configured at all.
    """
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if key:
        return key
    try:
        import streamlit as st  # only present inside the Streamlit app
        secrets = st.secrets
        value = secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception:  # noqa: BLE001 - no Streamlit / no secrets: not configured
        return None
    return None


def _sb_client():
    """Create (once) the Storage client (service-role key), or raise."""
    global _SB_STORAGE_CLIENT
    if _SB_STORAGE_CLIENT is not None:
        return _SB_STORAGE_CLIENT
    key = _sb_service_key()
    if not key:
        raise RuntimeError(
            "Supabase Storage is not configured: set the "
            "SUPABASE_SERVICE_ROLE_KEY environment variable (server-side "
            "only — never commit it, never put it in a file the app "
            "serves). Local folders are NOT used as a fallback, so a "
            "Supabase user's files never split across two stores."
        )
    config = _auth._load_supabase_config()[0]
    if config is None:
        raise RuntimeError("Supabase is not configured (no project URL).")
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(f"supabase package is not installed: {exc}")
    try:
        _SB_STORAGE_CLIENT = create_client(config["url"], key)
    except Exception as exc:
        raise RuntimeError(f"Could not start the Supabase client: {exc}")
    return _SB_STORAGE_CLIENT


def _sb_bucket():
    return _sb_client().storage.from_(STORAGE_BUCKET)


def _sb_object_path(username: str, subfolder: str, filename: str) -> str:
    """Validated bucket path: <storage-key>/<subfolder>/<safe filename>."""
    _validate_username(username)
    subfolder = _validate_subfolder(subfolder)
    safe_name = _sanitize_filename(filename)
    return f"{username}/{subfolder}/{safe_name}"


def _sb_is_not_found(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in (404, "404"):
        return True
    return "not found" in str(exc).lower()


def _sb_save(username: str, subfolder: str, filename: str,
             data_bytes: bytes) -> Path:
    object_path = _sb_object_path(username, subfolder, filename)
    try:
        _sb_bucket().upload(
            object_path, bytes(data_bytes), {"upsert": "true"}
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a plain error
        raise RuntimeError(f"Could not save to Supabase Storage: {exc}")
    return Path(object_path)


def _sb_list(username: str, subfolder: str) -> list[str]:
    _validate_username(username)
    subfolder = _validate_subfolder(subfolder)
    try:
        entries = _sb_bucket().list(f"{username}/{subfolder}")
    except Exception as exc:  # noqa: BLE001 - surfaced as a plain error
        if _sb_is_not_found(exc):
            return []
        raise RuntimeError(f"Could not list Supabase Storage: {exc}")
    names = []
    for entry in entries or []:
        name = entry.get("name") if isinstance(entry, dict) else None
        # list() returns only direct children; skip any nested prefix.
        if name and "/" not in name:
            names.append(name)
    return sorted(names)


def _sb_read(username: str, subfolder: str, filename: str) -> bytes:
    object_path = _sb_object_path(username, subfolder, filename)
    try:
        data = _sb_bucket().download(object_path)
    except Exception as exc:  # noqa: BLE001 - classified below
        if _sb_is_not_found(exc):
            raise FileNotFoundError(f"No such file: {object_path}")
        raise RuntimeError(f"Could not read from Supabase Storage: {exc}")
    return bytes(data)


def _sb_delete(username: str, subfolder: str, filename: str) -> None:
    object_path = _sb_object_path(username, subfolder, filename)
    if filename and _sanitize_filename(filename) not in _sb_list(username, subfolder):
        raise FileNotFoundError(f"No such file: {object_path}")
    try:
        _sb_bucket().remove([object_path])
    except Exception as exc:  # noqa: BLE001 - surfaced as a plain error
        raise RuntimeError(f"Could not delete from Supabase Storage: {exc}")


def _is_supabase_mode() -> bool:
    return _auth.get_auth_backend() == "supabase"


# ---------------------------------------------------------------------------
# BACKEND-AGNOSTIC PUBLIC API
# ---------------------------------------------------------------------------

def save_upload(username: str, filename: str, data_bytes: bytes) -> Path:
    """Store raw bytes under uploads/ and return the stored path."""
    if not isinstance(data_bytes, (bytes, bytearray)):
        raise ValueError("data_bytes must be bytes.")
    if _is_supabase_mode():
        return _sb_save(username, "uploads", filename, data_bytes)
    return _local_save(username, "uploads", filename, data_bytes)


def save_file(username: str, subfolder: str, filename: str,
              data_bytes: bytes) -> Path:
    """Store raw bytes under any allowed subfolder (uploads, cleaned,
    recipes, views, workspaces) and return the stored path. Same
    filename sanitisation and folder-boundary checks as save_upload."""
    if not isinstance(data_bytes, (bytes, bytearray)):
        raise ValueError("data_bytes must be bytes.")
    if _is_supabase_mode():
        return _sb_save(username, subfolder, filename, data_bytes)
    return _local_save(username, subfolder, filename, data_bytes)


def list_files(username: str, subfolder: str) -> list[str]:
    """Return sorted file names (not directories) in a subfolder."""
    if _is_supabase_mode():
        return _sb_list(username, subfolder)
    return _local_list(username, subfolder)


def read_file(username: str, subfolder: str, filename: str) -> bytes:
    """Return a file's bytes; raises FileNotFoundError if it does not exist."""
    if _is_supabase_mode():
        return _sb_read(username, subfolder, filename)
    return _local_read(username, subfolder, filename)


def delete_file(username: str, subfolder: str, filename: str) -> None:
    """Delete a file; raises FileNotFoundError if it does not exist."""
    if _is_supabase_mode():
        _sb_delete(username, subfolder, filename)
    else:
        _local_delete(username, subfolder, filename)


def save_json(username: str, subfolder: str, filename: str, obj) -> Path:
    """Write obj as JSON (UTF-8) and return the stored path."""
    if not filename.endswith(".json"):
        filename = filename + ".json"
    payload = json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")
    if _is_supabase_mode():
        return _sb_save(username, subfolder, filename, payload)
    return _local_save(username, subfolder, filename, payload)


def load_json(username: str, subfolder: str, filename: str):
    """Load a JSON file; returns None if it does not exist or is invalid."""
    if not filename.endswith(".json"):
        filename = filename + ".json"
    try:
        raw = read_file(username, subfolder, filename)
    except FileNotFoundError:
        return None
    except RuntimeError:
        raise
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _reset_storage_cache() -> None:
    """Test helper: forget the cached Supabase Storage client."""
    global _SB_STORAGE_CLIENT
    _SB_STORAGE_CLIENT = None


# ---------------------------------------------------------------------------
# PROFILE HELPERS — storage usage, full file listing, account wipe
# (used by the Profile section; another worker depends on these names)
# ---------------------------------------------------------------------------

def get_service_client():
    """Return the cached service-role Supabase client.

    Same client _sb_client() builds (and the same RuntimeError when the
    service key is not configured) — no duplicated key lookup here.
    """
    return _sb_client()


def storage_usage(username: str) -> tuple[int, dict[str, int]]:
    """Return (total_bytes, {subfolder: bytes}) across ALL subfolders.

    Never raises for a missing/empty user: a missing folder (or a
    404 in Supabase mode) counts 0 bytes for that subfolder.
    """
    per_sub = {sub: 0 for sub in SUBFOLDERS}
    if _is_supabase_mode():
        _validate_username(username)
        bucket = _sb_bucket()
        for sub in SUBFOLDERS:
            try:
                entries = bucket.list(f"{username}/{sub}")
            except Exception as exc:  # noqa: BLE001 - classified below
                if _sb_is_not_found(exc):
                    continue
                raise RuntimeError(
                    f"Could not list Supabase Storage: {exc}")
            for entry in entries or []:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                # list() returns only direct children; skip nested prefixes.
                if not name or "/" in name:
                    continue
                metadata = entry.get("metadata") or {}
                size = metadata.get("size") if isinstance(metadata, dict) else 0
                if isinstance(size, (int, float)):
                    per_sub[sub] += int(size)
    else:
        _validate_username(username)
        root = _resolve_within(BASE_DIR, username)
        for sub in SUBFOLDERS:
            folder = _resolve_within(root, sub)
            if not folder.is_dir():
                continue
            for path in folder.iterdir():
                if path.is_file():
                    per_sub[sub] += os.path.getsize(path)
    return sum(per_sub.values()), per_sub


def list_all_files(username: str) -> dict[str, list[str]]:
    """Return {subfolder: sorted names} for every subfolder.

    A missing folder lists as [].
    """
    return {sub: list_files(username, sub) for sub in SUBFOLDERS}


def delete_user_files(username: str) -> int:
    """Delete EVERY file of the user in every subfolder; return the count.

    Missing folders/files are not errors. Nothing outside the user's
    own tree is touched.
    """
    deleted = 0
    if _is_supabase_mode():
        _validate_username(username)
        bucket = _sb_bucket()
        for sub in SUBFOLDERS:
            names = _sb_list(username, sub)
            if not names:
                continue
            paths = [f"{username}/{sub}/{name}" for name in names]
            try:
                bucket.remove(paths)
            except Exception as exc:  # noqa: BLE001 - surfaced as a plain error
                raise RuntimeError(
                    f"Could not delete from Supabase Storage: {exc}")
            deleted += len(names)
    else:
        _validate_username(username)
        root = _resolve_within(BASE_DIR, username)
        for sub in SUBFOLDERS:
            folder = _resolve_within(root, sub)
            if not folder.is_dir():
                continue
            for path in folder.iterdir():
                if path.is_file():
                    # Resolve each file inside its folder first, so a
                    # symlink inside the tree can never delete elsewhere.
                    _resolve_within(folder, path.name).unlink()
                    deleted += 1
    return deleted
