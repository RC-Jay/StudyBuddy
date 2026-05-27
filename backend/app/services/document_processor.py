"""
Document ingestion pipeline.

Responsibilities:
  1. Load raw bytes from storage
  2. Delegate text extraction to the appropriate loader strategy (document_loader.py)
  3. Classify as book or research paper (reject anything else)
  4. Split into overlapping chunks (RecursiveCharacterTextSplitter, token-accurate)
  5. Embed and persist to pgvector via LangChain PGVector
  6. Auto-generate summaries (chapter-wise for books; full + concepts for papers)

This module is intentionally file-type-agnostic — all format-specific logic
lives in document_loader.py. Adding support for a new file type requires
no changes here.

Runs as a FastAPI BackgroundTask so the upload endpoint returns immediately.
The client polls GET /documents/{id}/status to track progress.
"""
import asyncio
import os
import tempfile
import threading
import time
import uuid

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.database import SessionLocal
from app.enums import DocType, ProcessingStatus
from app.models.document import Document
from app.services.auto_summariser import summarise_book, summarise_paper
from app.services.document_classifier import classify_document
from app.services.document_loader import get_loader
from app.services.langchain_setup import get_vectorstore
from app.services.llm import get_chat_provider
from app.services.storage import load_file


# Only one document's embedding job runs at a time across all background tasks.
# This prevents concurrent uploads from combining token usage and hitting the
# Azure rate limit (250K tokens/min).
_embed_lock = threading.Semaphore(1)

# Stay comfortably under the 250K tokens/minute Azure rate limit.
# At 512 tokens per chunk this allows ~390 chunks per batch.
_EMBED_TOKEN_BUDGET = 200_000
_CHUNK_TOKENS = 512  # matches chunk_size below


def _add_documents_batched(vectorstore, chunks, lock: threading.Semaphore) -> None:
    """Embed and store chunks in rate-limit-aware batches.

    Holds the process-level lock for the entire duration so concurrent uploads
    queue up rather than combining their token usage and hitting the Azure
    per-minute cap. Chunks are split into batches of ~200K tokens; batches
    for the same document are separated by a 65-second pause.
    """
    batch_size = max(1, _EMBED_TOKEN_BUDGET // _CHUNK_TOKENS)
    with lock:
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            vectorstore.add_documents(batch)
            if i + batch_size < len(chunks):
                time.sleep(65)


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

        doc.processing_status = ProcessingStatus.PROCESSING
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

        # 4. Classify document — reject anything that isn't a book or research paper
        provider = get_chat_provider()
        doc_type = await classify_document(pages, provider)
        doc.doc_type = doc_type.value
        db.commit()

        # 5. Split into overlapping chunks
        chunks = _build_splitter().split_documents(pages)

        # 6. Enrich chunk metadata for filtering at query time
        for i, chunk in enumerate(chunks):
            # pymupdf4llm sets metadata["page"] as 1-indexed already;
            # ensure it is always present for all loaders
            chunk.metadata.setdefault("page", None)
            chunk.metadata.update({
                "document_id": str(doc.id),
                "document_title": doc.title,
                "chunk_index": i,
            })

        # 7. Embed and store — serialised across concurrent uploads via _embed_lock
        vectorstore = get_vectorstore()
        await asyncio.to_thread(_add_documents_batched, vectorstore, chunks, _embed_lock)

        # Embeddings are done — Chat and Quiz are now usable.
        # Switch to SUMMARISING so the frontend can unlock those tabs
        # while summaries continue to generate in the background.
        doc.processing_status = ProcessingStatus.SUMMARISING
        db.commit()

        # 8. Auto-generate summaries based on document type
        if doc_type == DocType.BOOK:
            await summarise_book(doc, pages, db, provider, vectorstore)
        elif doc_type == DocType.RESEARCH_PAPER:
            await summarise_paper(doc, pages, db, provider, vectorstore)

        doc.processing_status = ProcessingStatus.READY
        db.commit()

    except Exception as exc:
        db.rollback()
        doc = db.get(Document, document_id)
        if doc:
            doc.processing_status = ProcessingStatus.FAILED
            doc.processing_error = str(exc)
            db.commit()
    finally:
        db.close()
