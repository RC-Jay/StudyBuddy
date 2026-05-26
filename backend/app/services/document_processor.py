"""
Extracts text from PDF/DOCX, splits into chunks, generates embeddings, persists to DB.
Designed to run in a FastAPI BackgroundTask — updates document.processing_status throughout.
"""
import io
import re
import uuid
from datetime import datetime, timezone

import pdfplumber
import pymupdf
from docx import Document as DocxDocument
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.document import Document, DocumentChunk
from app.services.azure_openai import get_embedding
from app.services.storage import load_file

CHUNK_SIZE = 512      # tokens (approximated as words * 1.3)
CHUNK_OVERLAP = 64


def _word_count(text: str) -> int:
    return len(text.split())


def _chunk_text(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """
    Takes a list of (page_number, page_text) pairs and returns
    (page_number, chunk_text) pairs with overlap between consecutive chunks.
    """
    chunks: list[tuple[int, str]] = []
    buffer_words: list[str] = []
    buffer_page = 1
    target_words = int(CHUNK_SIZE / 1.3)
    overlap_words = int(CHUNK_OVERLAP / 1.3)

    for page_num, text in pages:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        for sentence in sentences:
            words = sentence.split()
            if _word_count(" ".join(buffer_words)) + len(words) > target_words:
                if buffer_words:
                    chunks.append((buffer_page, " ".join(buffer_words)))
                buffer_words = buffer_words[-overlap_words:] + words
                buffer_page = page_num
            else:
                if not buffer_words:
                    buffer_page = page_num
                buffer_words.extend(words)

    if buffer_words:
        chunks.append((buffer_page, " ".join(buffer_words)))

    return chunks


def _extract_pdf(content: bytes) -> tuple[int, list[tuple[int, str]]]:
    pages: list[tuple[int, str]] = []
    doc = pymupdf.open(stream=content, filetype="pdf")
    page_count = doc.page_count
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if text.strip():
            pages.append((i, text))
    doc.close()
    return page_count, pages


def _extract_docx(content: bytes) -> tuple[int, list[tuple[int, str]]]:
    doc = DocxDocument(io.BytesIO(content))
    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    # DOCX has no native pages — treat every ~500 words as a logical page
    words = full_text.split()
    page_size = 500
    pages = []
    for i in range(0, len(words), page_size):
        page_num = i // page_size + 1
        pages.append((page_num, " ".join(words[i : i + page_size])))
    return len(pages), pages


async def process_document(document_id: uuid.UUID) -> None:
    db: Session = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if not doc:
            return

        doc.processing_status = "processing"
        db.commit()

        content = await load_file(doc.blob_path)

        if doc.file_type == "pdf":
            page_count, pages = _extract_pdf(content)
        else:
            page_count, pages = _extract_docx(content)

        doc.page_count = page_count
        db.commit()

        chunks = _chunk_text(pages)

        for idx, (page_num, chunk_text) in enumerate(chunks):
            embedding = await get_embedding(chunk_text)
            db.add(
                DocumentChunk(
                    document_id=doc.id,
                    content=chunk_text,
                    page_number=page_num,
                    chunk_index=idx,
                    embedding=embedding,
                )
            )
            if idx % 50 == 0:
                db.commit()

        db.commit()
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
