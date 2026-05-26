"""
File storage abstraction — Strategy Pattern.

Architecture:
  BaseStorageBackend   abstract interface (save / load / delete)
  LocalStorageBackend  local filesystem (development)
  AzureBlobStorageBackend  Azure Blob Storage (production)

  get_storage_backend()  factory — reads STORAGE_BACKEND from config,
                         returns a process-level singleton backend.

Adding a new backend (e.g. S3, GCS):
  1. Subclass BaseStorageBackend
  2. Add an elif branch in get_storage_backend()
  3. Set STORAGE_BACKEND=<key> in .env
  No other files change — callers use save_file / load_file / delete_file.
"""
import os
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

import aiofiles

from app.config import settings
from app.enums import StorageBackend


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class BaseStorageBackend(ABC):
    """
    Strategy interface for file storage backends.
    All methods are async. save() returns an opaque key/path that can be
    passed back to load() and delete() verbatim.
    """

    @abstractmethod
    async def save(self, content: bytes, filename: str) -> str:
        """Persist bytes and return an opaque storage key."""
        ...

    @abstractmethod
    async def load(self, key: str) -> bytes:
        """Retrieve bytes by the key returned from save()."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the stored object. Silently ignores missing keys."""
        ...


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------

class LocalStorageBackend(BaseStorageBackend):
    """Stores files on the local filesystem. Suitable for development."""

    async def save(self, content: bytes, filename: str) -> str:
        storage_dir = Path(settings.local_storage_path)
        storage_dir.mkdir(parents=True, exist_ok=True)
        key = f"{uuid.uuid4()}_{filename}"
        dest = storage_dir / key
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)
        return str(dest)

    async def load(self, key: str) -> bytes:
        async with aiofiles.open(key, "rb") as f:
            return await f.read()

    async def delete(self, key: str) -> None:
        try:
            os.remove(key)
        except FileNotFoundError:
            pass


class AzureBlobStorageBackend(BaseStorageBackend):
    """Stores files in Azure Blob Storage. Suitable for production."""

    async def save(self, content: bytes, filename: str) -> str:
        from azure.storage.blob.aio import BlobServiceClient
        key = f"{uuid.uuid4()}_{filename}"
        client = BlobServiceClient.from_connection_string(settings.azure_blob_connection_string)
        async with client:
            blob = client.get_blob_client(container=settings.azure_blob_container, blob=key)
            await blob.upload_blob(content, overwrite=True)
        return key

    async def load(self, key: str) -> bytes:
        from azure.storage.blob.aio import BlobServiceClient
        client = BlobServiceClient.from_connection_string(settings.azure_blob_connection_string)
        async with client:
            blob = client.get_blob_client(container=settings.azure_blob_container, blob=key)
            stream = await blob.download_blob()
            return await stream.readall()

    async def delete(self, key: str) -> None:
        from azure.storage.blob.aio import BlobServiceClient
        client = BlobServiceClient.from_connection_string(settings.azure_blob_connection_string)
        async with client:
            blob = client.get_blob_client(container=settings.azure_blob_container, blob=key)
            await blob.delete_blob(delete_snapshots="include")


# ---------------------------------------------------------------------------
# Factory + singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_storage_backend() -> BaseStorageBackend:
    """
    Return the configured storage backend singleton.
    Reads STORAGE_BACKEND from settings (default: local).
    """
    backend = settings.storage_backend.lower()

    if backend == StorageBackend.LOCAL:
        return LocalStorageBackend()
    if backend == StorageBackend.AZURE:
        return AzureBlobStorageBackend()

    raise ValueError(
        f"Unknown storage backend: '{backend}'. "
        f"Supported: {[e.value for e in StorageBackend]}"
    )


# ---------------------------------------------------------------------------
# Public convenience functions (stable API for callers)
# ---------------------------------------------------------------------------

async def save_file(content: bytes, filename: str) -> str:
    return await get_storage_backend().save(content, filename)


async def load_file(key: str) -> bytes:
    return await get_storage_backend().load(key)


async def delete_file(key: str) -> None:
    await get_storage_backend().delete(key)
