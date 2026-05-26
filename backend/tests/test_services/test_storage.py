"""
Tests for app.services.storage

Strategy Pattern tests:
  - LocalStorageBackend: save / load / delete against a real temp directory
  - get_storage_backend() factory returns the correct type based on config
  - get_storage_backend() raises on unknown backend

AzureBlobStorageBackend is not tested here (requires live credentials).
"""
import os
import pytest
from unittest.mock import patch

from app.services.storage import (
    LocalStorageBackend,
    get_storage_backend,
)


# ---------------------------------------------------------------------------
# LocalStorageBackend
# ---------------------------------------------------------------------------

class TestLocalStorageBackend:
    @pytest.fixture
    def backend(self, tmp_path):
        """Return a LocalStorageBackend that writes to tmp_path."""
        with patch("app.services.storage.settings") as mock_settings:
            mock_settings.local_storage_path = str(tmp_path)
            yield LocalStorageBackend()

    async def test_save_returns_a_path(self, backend):
        key = await backend.save(b"hello", "test.txt")
        assert "test.txt" in key
        assert os.path.exists(key)

    async def test_load_returns_saved_bytes(self, backend):
        content = b"StudyBuddy test content"
        key = await backend.save(content, "data.bin")
        loaded = await backend.load(key)
        assert loaded == content

    async def test_delete_removes_file(self, backend):
        key = await backend.save(b"to be deleted", "delete_me.txt")
        assert os.path.exists(key)
        await backend.delete(key)
        assert not os.path.exists(key)

    async def test_delete_missing_file_is_silent(self, backend):
        """Deleting a non-existent file should not raise."""
        await backend.delete("/tmp/definitely_does_not_exist_xyz.txt")

    async def test_save_creates_directory_if_missing(self, tmp_path):
        nested = tmp_path / "nested" / "dir"
        with patch("app.services.storage.settings") as mock_settings:
            mock_settings.local_storage_path = str(nested)
            b = LocalStorageBackend()
            key = await b.save(b"data", "file.txt")
        assert os.path.exists(key)

    async def test_saved_keys_are_unique(self, backend):
        key1 = await backend.save(b"a", "same_name.txt")
        key2 = await backend.save(b"b", "same_name.txt")
        assert key1 != key2


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestGetStorageBackend:
    def test_local_backend(self):
        with patch("app.services.storage.settings") as mock_settings:
            mock_settings.storage_backend = "local"
            # Clear the lru_cache so fresh call goes through factory logic
            get_storage_backend.cache_clear()
            backend = get_storage_backend()
            assert isinstance(backend, LocalStorageBackend)
        get_storage_backend.cache_clear()

    def test_unknown_backend_raises(self):
        with patch("app.services.storage.settings") as mock_settings:
            mock_settings.storage_backend = "gcs"
            get_storage_backend.cache_clear()
            with pytest.raises(ValueError, match="Unknown storage backend"):
                get_storage_backend()
        get_storage_backend.cache_clear()
