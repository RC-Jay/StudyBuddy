"""
Retrieval-Augmented Generation helpers using LangChain PGVector.
"""
import asyncio
import uuid
from dataclasses import dataclass

from langchain_core.vectorstores import VectorStore
from sqlalchemy.orm import Session

from app.models.collection import CollectionDocument
from app.services.langchain_setup import get_vectorstore

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
    *,
    vectorstore: VectorStore | None = None,
) -> list[RetrievedChunk]:
    """
    Retrieve the top-k most relevant chunks for *query* from the vector store.

    ``vectorstore`` is an optional keyword-only argument that allows callers
    (routers, tests) to inject a specific VectorStore instance.  When omitted
    the process-level singleton from ``get_vectorstore()`` is used.
    """
    if scope_type == "document":
        filter_dict = {"document_id": str(scope_id)}
    else:
        links = db.query(CollectionDocument).filter_by(collection_id=scope_id).all()
        doc_ids = [str(link.document_id) for link in links]
        if not doc_ids:
            return []
        filter_dict = {"document_id": {"$in": doc_ids}}

    vs = vectorstore if vectorstore is not None else get_vectorstore()

    # similarity_search_with_score is synchronous — run in a thread
    results = await asyncio.to_thread(
        vs.similarity_search_with_score,
        query,
        k=top_k,
        filter=filter_dict,
    )

    return [
        RetrievedChunk(
            document_title=doc.metadata.get("document_title", "Unknown"),
            page_number=doc.metadata.get("page"),
            content=doc.page_content,
            score=float(score),
        )
        for doc, score in results
    ]



def build_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for chunk in chunks:
        ref = (
            f'["{chunk.document_title}", p.{chunk.page_number}]'
            if chunk.page_number
            else f'["{chunk.document_title}"]'
        )
        parts.append(f"{ref}\n{chunk.content}")
    return "\n\n---\n\n".join(parts)


def build_citations(chunks: list[RetrievedChunk]) -> list[dict]:
    seen: set[tuple] = set()
    citations = []
    for chunk in chunks:
        key = (chunk.document_title, chunk.page_number)
        if key not in seen:
            seen.add(key)
            citations.append({"document": chunk.document_title, "page": chunk.page_number})
    return citations
