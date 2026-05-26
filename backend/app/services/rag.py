"""
Retrieval-Augmented Generation helpers.
Retrieves relevant chunks from pgvector and builds context for the LLM.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.models.collection import CollectionDocument
from app.services.azure_openai import get_embedding

TOP_K = 6


@dataclass
class RetrievedChunk:
    document_title: str
    page_number: int | None
    content: str
    score: float


async def retrieve(
    db: Session,
    query: str,
    scope_type: str,
    scope_id: uuid.UUID,
    top_k: int = TOP_K,
) -> list[RetrievedChunk]:
    query_embedding = await get_embedding(query)
    vector_literal = f"[{','.join(str(v) for v in query_embedding)}]"

    if scope_type == "document":
        doc_ids = [scope_id]
    else:
        links = db.query(CollectionDocument).filter_by(collection_id=scope_id).all()
        doc_ids = [link.document_id for link in links]

    if not doc_ids:
        return []

    id_list = ", ".join(f"'{str(did)}'" for did in doc_ids)

    rows = db.execute(
        text(f"""
            SELECT
                dc.content,
                dc.page_number,
                dc.document_id,
                1 - (dc.embedding <=> '{vector_literal}'::vector) AS score
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE dc.document_id IN ({id_list})
              AND d.deleted_at IS NULL
              AND d.processing_status = 'ready'
            ORDER BY dc.embedding <=> '{vector_literal}'::vector
            LIMIT :top_k
        """),
        {"top_k": top_k},
    ).fetchall()

    doc_cache: dict[uuid.UUID, str] = {}
    results = []
    for row in rows:
        doc_id = row.document_id
        if doc_id not in doc_cache:
            doc = db.get(Document, doc_id)
            doc_cache[doc_id] = doc.title if doc else "Unknown"
        results.append(
            RetrievedChunk(
                document_title=doc_cache[doc_id],
                page_number=row.page_number,
                content=row.content,
                score=float(row.score),
            )
        )
    return results


def build_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for chunk in chunks:
        ref = f'["{chunk.document_title}", p.{chunk.page_number}]' if chunk.page_number else f'["{chunk.document_title}"]'
        parts.append(f"{ref}\n{chunk.content}")
    return "\n\n---\n\n".join(parts)


def build_citations(chunks: list[RetrievedChunk]) -> list[dict]:
    seen = set()
    citations = []
    for chunk in chunks:
        key = (chunk.document_title, chunk.page_number)
        if key not in seen:
            seen.add(key)
            citations.append({"document": chunk.document_title, "page": chunk.page_number})
    return citations
