"""
Video ingestion pipeline.

Responsibilities:
  1. Load transcript + metadata via the registered video loader strategy
  2. Classify as academic/educational (reject entertainment, news, etc.)
  3. Convert transcript segments to LangChain Documents
  4. Split into overlapping chunks and embed into pgvector
  5. Auto-generate segment summaries + key concepts

Runs as a FastAPI BackgroundTask so the endpoint returns immediately.
The client polls GET /documents/{id}/status to track progress.

This module is intentionally video-source-agnostic — all source-specific
logic lives in app/services/video/. Adding support for a new video source
requires no changes here.
"""
import asyncio
import logging
import threading
import time
import uuid

import tiktoken
from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.database import SessionLocal
from app.enums import DocType, ProcessingStatus
from app.models.document import Document
from app.services.auto_summariser import summarise_video
from app.services.langchain_setup import get_vectorstore
from app.services.llm import get_chat_provider
from app.services.video import get_video_loader
from app.services.video.base import VideoContent
from app.services.video_classifier import classify_video

logger = logging.getLogger(__name__)

# Reuse the same embedding rate-limit guard as document_processor
# (imported lazily to avoid circular imports at module load time)
_embed_lock = threading.Semaphore(1)
_EMBED_TOKEN_BUDGET = 200_000
_CHUNK_TOKENS = 512


def _add_documents_batched(vectorstore, chunks, lock: threading.Semaphore) -> None:
    """Same rate-limit-aware batching as document_processor._add_documents_batched."""
    batch_size = max(1, _EMBED_TOKEN_BUDGET // _CHUNK_TOKENS)
    with lock:
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            vectorstore.add_documents(batch)
            if i + batch_size < len(chunks):
                time.sleep(65)


def _tiktoken_len(text: str) -> int:
    return len(tiktoken.get_encoding("cl100k_base").encode(text))


def _build_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=64,
        length_function=_tiktoken_len,
        separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
    )


def _content_to_documents(content: VideoContent, doc_id: uuid.UUID, doc_title: str) -> list[LCDocument]:
    """
    Convert VideoContent into LangChain Documents for embedding.

    Strategy:
      - If the video has chapters, create one Document per chapter so
        metadata["section"] enables chapter-scoped retrieval.
      - If no chapters, create a single Document from the full transcript.

    Each Document carries:
      - metadata["document_id"]   — for pgvector filtering
      - metadata["document_title"]
      - metadata["section"]       — chapter title (if available)
      - metadata["source"]        — canonical video URL
    """
    base_meta = {
        "document_id": str(doc_id),
        "document_title": doc_title,
        "source": content.url,
    }

    if content.chapters:
        return [
            LCDocument(
                page_content=ch.transcript,
                metadata={**base_meta, "section": ch.title, "page": None},
            )
            for ch in content.chapters
            if ch.transcript.strip()
        ]

    # Full transcript as a single document
    return [
        LCDocument(
            page_content=content.transcript,
            metadata={**base_meta, "section": None, "page": None},
        )
    ]


async def process_video(document_id: uuid.UUID) -> None:
    """
    Full video ingestion pipeline. Called as a FastAPI BackgroundTask.

    On failure the document is marked FAILED with a user-readable error message.
    """
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if not doc:
            return

        doc.processing_status = ProcessingStatus.PROCESSING
        db.commit()

        # 1. Load transcript + metadata
        loader = get_video_loader(doc.source_url)
        content: VideoContent = await loader.load(doc.source_url)

        # Update metadata fields discovered during loading
        doc.title = content.title
        doc.duration_seconds = content.duration_seconds
        doc.thumbnail_url = content.thumbnail_url
        # page_count = approximate "pages" (1 per 1000 chars, floored at 1)
        doc.page_count = max(1, len(content.transcript) // 1000)
        db.commit()

        # 2. Classify as academic
        provider = get_chat_provider()
        await classify_video(content.transcript, provider)

        doc.doc_type = DocType.VIDEO.value
        db.commit()

        # 3. Convert to LangChain Documents
        lc_docs = _content_to_documents(content, doc.id, doc.title)

        # 4. Split into overlapping chunks
        splitter = _build_splitter()
        chunks = splitter.split_documents(lc_docs)

        for i, chunk in enumerate(chunks):
            chunk.metadata.setdefault("page", None)
            chunk.metadata.update({
                "document_id": str(doc.id),
                "document_title": doc.title,
                "chunk_index": i,
            })

        # 5. Embed and store
        vectorstore = get_vectorstore()
        await asyncio.to_thread(_add_documents_batched, vectorstore, chunks, _embed_lock)

        # Embeddings done — Chat and Quiz are now usable
        doc.processing_status = ProcessingStatus.SUMMARISING
        db.commit()

        # 6. Generate summaries
        await summarise_video(doc, content, db, provider, vectorstore)

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


async def resume_video_summarisation(document_id: uuid.UUID) -> None:
    """
    Resume summary generation for a video stuck in SUMMARISING state.
    Re-loads the transcript and skips already-completed segments.
    """
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if not doc or doc.processing_status != ProcessingStatus.SUMMARISING:
            return

        logger.info("Resuming video summarisation for %s (%s)", doc.id, doc.title)

        from app.models.summary import Summary
        existing = db.query(Summary).filter_by(scope_id=doc.id).all()
        done_hints = {s.section_hint for s in existing if s.section_hint}
        done_granularities = {s.granularity for s in existing}

        loader = get_video_loader(doc.source_url)
        content: VideoContent = await loader.load(doc.source_url)

        provider = get_chat_provider()
        vectorstore = get_vectorstore()

        skip = done_hints | done_granularities
        await summarise_video(doc, content, db, provider, vectorstore, done_hints=skip)

        doc.processing_status = ProcessingStatus.READY
        db.commit()

    except Exception as exc:
        logger.error("Resume video summarisation failed for %s: %s", document_id, exc)
        db.rollback()
        doc = db.get(Document, document_id)
        if doc:
            doc.processing_status = ProcessingStatus.FAILED
            doc.processing_error = str(exc)
            db.commit()
    finally:
        db.close()
