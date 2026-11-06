"""Tests for the Profile storage helpers in storage.py:
get_service_client, storage_usage, list_all_files, delete_user_files.

Run ONLY this file (other workers edit files concurrently):
    .test-venv-verify/bin/python -m pytest tests/test_profile_storage.py -q
(from the project root)

Local-mode tests point storage.BASE_DIR at a temp dir (pattern from
tests/test_web_smoke.py) and force local mode by monkeypatching
storage._is_supabase_mode. Supabase-mode tests monkeypatch
storage._sb_bucket with a fake bucket — no network, no credentials.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import storage  # noqa: E402


@pytest.fixture()
def tmp_base(tmp_path, monkeypatch):
    """Point storage at a temp dir and force local mode."""
    monkeypatch.setattr(storage, "BASE_DIR", tmp_path / "users")
    monkeypatch.setattr(storage, "_is_supabase_mode", lambda: False)
    return tmp_path / "users"


def _seed(tmp_base, username="alice1"):
    """Real files across several subfolders; returns {subfolder: size}."""
    sizes = {
        "uploads": [("a.csv", 10), ("b.csv", 25)],
        "cleaned": [("a_clean.csv", 100)],
        "recipes": [],
        "views": [("shares.json", 7)],
        "workspaces": [("ws.json", 3), ("ws2.json", 4)],
        "backups": [("bak.zip", 1000)],
    }
    for sub, files in sizes.items():
        folder = tmp_base / username / sub
        folder.mkdir(parents=True, exist_ok=True)
        for name, size in files:
            (folder / name).write_bytes(b"x" * size)
    return {sub: sum(size for _, size in files) for sub, files in sizes.items()}


# ---------------------------------------------------------------------------
# Local mode
# ---------------------------------------------------------------------------

def test_usage_sums_real_file_sizes(tmp_base):
    expected = _seed(tmp_base)
    total, per_sub = storage.storage_usage("alice1")
    assert per_sub == expected
    assert total == sum(expected.values())
    assert total == 10 + 25 + 100 + 7 + 3 + 4 + 1000


def test_usage_missing_user_is_zero(tmp_base):
    total, per_sub = storage.storage_usage("nobody1")
    assert total == 0
    assert per_sub == {sub: 0 for sub in storage.SUBFOLDERS}


def test_list_all_files_shape(tmp_base):
    _seed(tmp_base)
    result = storage.list_all_files("alice1")
    assert set(result) == set(storage.SUBFOLDERS)
    assert result["uploads"] == ["a.csv", "b.csv"]
    assert result["cleaned"] == ["a_clean.csv"]
    assert result["recipes"] == []
    assert result["views"] == ["shares.json"]
    assert result["workspaces"] == ["ws.json", "ws2.json"]
    assert result["backups"] == ["bak.zip"]


def test_list_all_files_missing_user_is_empty(tmp_base):
    result = storage.list_all_files("nobody1")
    assert result == {sub: [] for sub in storage.SUBFOLDERS}


def test_delete_user_files_removes_everything(tmp_base):
    _seed(tmp_base)
    count = storage.delete_user_files("alice1")
    assert count == 7
    assert storage.list_all_files("alice1") == {
        sub: [] for sub in storage.SUBFOLDERS}
    total, per_sub = storage.storage_usage("alice1")
    assert total == 0
    # Second call: nothing left to delete.
    assert storage.delete_user_files("alice1") == 0


def test_delete_missing_user_is_zero(tmp_base):
    assert storage.delete_user_files("nobody1") == 0


# ---------------------------------------------------------------------------
# Supabase mode (fake bucket)
# ---------------------------------------------------------------------------

class _FakeBucket:
    """Minimal stand-in for a Supabase Storage bucket handle."""

    def __init__(self, listing):
        # listing: {folder_path: [entry, ...]}; entry is a dict like the
        # real list() returns: {"name": ..., "metadata": {"size": ...}}.
        self.listing = listing
        self.removed = []  # one entry per remove() call (a list of paths)

    def list(self, folder):
        return list(self.listing.get(folder, []))

    def remove(self, paths):
        self.removed.append(list(paths))
        return paths


@pytest.fixture()
def sb_mode(monkeypatch):
    monkeypatch.setattr(storage, "_is_supabase_mode", lambda: True)
    return monkeypatch


def test_usage_supabase_sums_metadata_sizes(sb_mode):
    bucket = _FakeBucket({
        "alice1/uploads": [
            {"name": "a.csv", "metadata": {"size": 10}},
            {"name": "b.csv", "metadata": {"size": 25}},
            # Metadata may be missing/None: counts as 0, not an error.
            {"name": "c.csv", "metadata": None},
            {"name": "d.csv"},
        ],
        "alice1/cleaned": [
            {"name": "a_clean.csv", "metadata": {"size": 100}},
        ],
        # "alice1/recipes" absent: missing folder means 0 bytes.
    })
    sb_mode.setattr(storage, "_sb_bucket", lambda: bucket)
    total, per_sub = storage.storage_usage("alice1")
    assert per_sub["uploads"] == 35
    assert per_sub["cleaned"] == 100
    assert per_sub["recipes"] == 0
    assert per_sub["views"] == 0
    assert per_sub["workspaces"] == 0
    assert per_sub["backups"] == 0
    assert total == 135


def test_usage_supabase_missing_folder_404_is_zero(sb_mode):
    class _NotFoundBucket(_FakeBucket):
        def list(self, folder):
            if folder.endswith("/backups"):
                exc = RuntimeError("not found")
                exc.status_code = 404
                raise exc
            return super().list(folder)

    bucket = _NotFoundBucket({
        "alice1/uploads": [{"name": "a.csv", "metadata": {"size": 5}}],
    })
    sb_mode.setattr(storage, "_sb_bucket", lambda: bucket)
    total, per_sub = storage.storage_usage("alice1")
    assert per_sub["uploads"] == 5
    assert per_sub["backups"] == 0
    assert total == 5


def test_delete_supabase_one_remove_per_subfolder(sb_mode):
    bucket = _FakeBucket({
        "alice1/uploads": [
            {"name": "a.csv", "metadata": {"size": 10}},
            {"name": "b.csv", "metadata": {"size": 25}},
        ],
        "alice1/cleaned": [
            {"name": "a_clean.csv", "metadata": {"size": 100}},
        ],
        "alice1/views": [
            {"name": "shares.json", "metadata": {"size": 7}},
        ],
    })
    sb_mode.setattr(storage, "_sb_bucket", lambda: bucket)
    count = storage.delete_user_files("alice1")
    assert count == 4
    # One remove() call per non-empty subfolder, with the full paths.
    assert bucket.removed == [
        ["alice1/uploads/a.csv", "alice1/uploads/b.csv"],
        ["alice1/cleaned/a_clean.csv"],
        ["alice1/views/shares.json"],
    ]


def test_delete_supabase_missing_user_is_zero(sb_mode):
    bucket = _FakeBucket({})
    sb_mode.setattr(storage, "_sb_bucket", lambda: bucket)
    assert storage.delete_user_files("nobody1") == 0
    assert bucket.removed == []


def test_get_service_client_missing_key_raises(monkeypatch):
    monkeypatch.setattr(storage, "_sb_service_key", lambda: None)
    storage._reset_storage_cache()
    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_ROLE_KEY"):
        storage.get_service_client()
