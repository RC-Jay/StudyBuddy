"""
Storage abstraction — local filesystem for dev, Azure Blob for prod.
Set STORAGE_BACKEND=azure and AZURE_BLOB_CONNECTION_STRING to switch.
"""
import os
import uuid
from pathlib import Path

import aiofiles

from app.config import settings


async def save_file(content: bytes, filename: str) -> str:
    """Saves file and returns a path/key that can be passed to load_file / delete_file."""
    if settings.storage_backend == "azure":
        return await _azure_save(content, filename)
    return await _local_save(content, filename)


async def load_file(path: str) -> bytes:
    if settings.storage_backend == "azure":
        return await _azure_load(path)
    return await _local_load(path)


async def delete_file(path: str) -> None:
    if settings.storage_backend == "azure":
        await _azure_delete(path)
    else:
        await _local_delete(path)


# --- local ---

async def _local_save(content: bytes, filename: str) -> str:
    storage_dir = Path(settings.local_storage_path)
    storage_dir.mkdir(parents=True, exist_ok=True)
    key = f"{uuid.uuid4()}_{filename}"
    dest = storage_dir / key
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)
    return str(dest)


async def _local_load(path: str) -> bytes:
    async with aiofiles.open(path, "rb") as f:
        return await f.read()


async def _local_delete(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# --- azure blob ---

async def _azure_save(content: bytes, filename: str) -> str:
    from azure.storage.blob.aio import BlobServiceClient
    key = f"{uuid.uuid4()}_{filename}"
    client = BlobServiceClient.from_connection_string(settings.azure_blob_connection_string)
    async with client:
        blob = client.get_blob_client(container=settings.azure_blob_container, blob=key)
        await blob.upload_blob(content, overwrite=True)
    return key


async def _azure_load(key: str) -> bytes:
    from azure.storage.blob.aio import BlobServiceClient
    client = BlobServiceClient.from_connection_string(settings.azure_blob_connection_string)
    async with client:
        blob = client.get_blob_client(container=settings.azure_blob_container, blob=key)
        stream = await blob.download_blob()
        return await stream.readall()


async def _azure_delete(key: str) -> None:
    from azure.storage.blob.aio import BlobServiceClient
    client = BlobServiceClient.from_connection_string(settings.azure_blob_connection_string)
    async with client:
        blob = client.get_blob_client(container=settings.azure_blob_container, blob=key)
        await blob.delete_blob(delete_snapshots="include")
