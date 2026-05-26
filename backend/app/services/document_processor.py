"""
Document ingestion pipeline.

Responsibilities:
  1. Load raw bytes from storage
  2. Delegate text extraction to the appropriate loader strategy (document_loader.py)
  3. Split into overlapping chunks (RecursiveCharacterTextSplitter, token-accurate)
  4. Embed and persist to pgvector via LangChain PGVector

This module is intentionally file-type-agnostic — all format-specific logic
lives in document_loader.py. Adding support for a new file type requires
no changes here.

Runs as a FastAPI BackgroundTask so the upload endpoint returns immediately.
The client polls GET /documents/{id}/status to track progress.
"""
import asyncio
import os
import tempfile
import uuid

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.database import SessionLocal
from app.models.document import Document
from app.services.document_loader import get_loader
from app.services.langchain_setup import get_vectorstore
from app.services.storage import load_file


def _tiktoken_len(text: str) -> int:
    """Token-accurate length function — cl100k_base is the encoding used by GPT-4o and text-embedding-3-large."""
    return len(tiktoken.get_encoding("cl100k_base").encode(text))


def _build_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=64,
        length_function=_tiktoken_len,
        # Tries each separator in order, only going smaller if the chunk is still too large
        separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
    )


async def process_document(document_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if not doc:
            return

        doc.processing_status = "processing"
        db.commit()

        # 1. Load raw bytes from storage
        content = await load_file(doc.blob_path)

        # 2. Write to a temp file — LangChain loaders work with file paths
        with tempfile.NamedTemporaryFile(suffix=f".{doc.file_type}", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # 3. Delegate to the registered loader strategy for this file type
            loader = get_loader(doc.file_type)
            pages = loader.load(tmp_path)
        finally:
            os.unlink(tmp_path)

        doc.page_count = len(pages)
        db.commit()

        # 4. Split into overlapping chunks
        chunks = _build_splitter().split_documents(pages)

        # 5. Enrich chunk metadata for filtering at query time
        for i, chunk in enumerate(chunks):
            # pymupdf4llm sets metadata["page"] as 1-indexed already;
            # ensure it is always present for all loaders
            chunk.metadata.setdefault("page", None)
            chunk.metadata.update({
                "document_id": str(doc.id),
                "document_title": doc.title,
                "chunk_index": i,
            })

        # 6. Embed and store — PGVector.add_documents is sync, run in a thread
        vectorstore = get_vectorstore()
        await asyncio.to_thread(vectorstore.add_documents, chunks)

        doc.processing_status = "ready"
        db.commit()

    except Exception as exc:
        db.rollback()
        doc = db.get(Document, document_id)
        if doc:
            doc.processing_status = "failed"
            doc.processing_error = str(exc)
            db.commit()
    finally:
        db.close()
