"""
Shared LangChain configuration — embeddings provider and vector store.

Design:
  get_embeddings()  → langchain_core.embeddings.Embeddings   (interface)
  get_vectorstore() → langchain_core.vectorstores.VectorStore (interface)

Both are process-level singletons (lru_cache). Callers receive the
LangChain base type, not the concrete Azure/PGVector types, so swapping
providers (e.g. Cohere embeddings, Pinecone vector store) only requires
changing the factory functions here — zero changes to rag.py,
document_processor.py, or anywhere else that calls them.

Adding a new embeddings provider:
  1. Pick a LangChain embeddings class (OpenAIEmbeddings, CohereEmbeddings…)
  2. Replace the return value in get_embeddings()
  3. Invalidate the cache if hot-swapping at runtime: get_embeddings.cache_clear()

Adding a new vector store:
  Same pattern — replace get_vectorstore().
"""
import uuid
from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from langchain_openai import AzureOpenAIEmbeddings
from langchain_postgres import PGVector
from sqlalchemy import text

from app.config import settings
from app.database import engine

COLLECTION_NAME = "studybuddy"


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    """
    Return the embeddings provider singleton.
    Currently: Azure OpenAI text-embedding-3-large (3072 dimensions).
    Returns the LangChain Embeddings interface — swap the implementation
    here without touching any caller.
    """
    return AzureOpenAIEmbeddings(
        azure_deployment=settings.azure_openai_embedding_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_embedding_api_version,
    )


@lru_cache(maxsize=1)
def get_vectorstore() -> VectorStore:
    """
    Return the vector store singleton.
    Currently: LangChain PGVector (PostgreSQL + pgvector extension).
    Returns the LangChain VectorStore interface — swap to Pinecone, Chroma,
    Weaviate, etc. by changing this function without touching any caller.

    Singleton rationale: PGVector opens a connection pool on construction.
    Without caching, every retrieve() / add_documents() call would open a
    fresh pool — one per request.
    """
    # langchain-postgres requires psycopg v3 — swap the driver in the URL
    connection = settings.database_url.replace(
        "postgresql://", "postgresql+psycopg://"
    ).replace(
        "postgresql+psycopg2://", "postgresql+psycopg://"
    )
    return PGVector(
        embeddings=get_embeddings(),
        collection_name=COLLECTION_NAME,
        connection=connection,
        use_jsonb=True,
    )


def get_vectorstore_dep() -> VectorStore:
    """
    FastAPI dependency — thin wrapper around get_vectorstore() so routers can
    declare ``Depends(get_vectorstore_dep)`` and tests can override it via
    ``app.dependency_overrides[get_vectorstore_dep]``.
    """
    return get_vectorstore()


def delete_document_embeddings(document_id: uuid.UUID) -> None:
    """
    Remove all embeddings for a document from the LangChain vector store.
    LangChain does not expose a delete-by-metadata API, so we go directly
    to the underlying tables.
    """
    with engine.connect() as conn:
        conn.execute(
            text("""
                DELETE FROM langchain_pg_embedding
                WHERE collection_id = (
                    SELECT uuid FROM langchain_pg_collection WHERE name = :name
                )
                AND cmetadata->>'document_id' = :doc_id
            """),
            {"name": COLLECTION_NAME, "doc_id": str(document_id)},
        )
        conn.commit()
