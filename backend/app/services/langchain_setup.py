"""
Shared LangChain configuration — embeddings model and vector store.
Import from here rather than constructing these in individual services.
"""
import uuid

from langchain_openai import AzureOpenAIEmbeddings
from langchain_postgres import PGVector
from sqlalchemy import text

from app.config import settings
from app.database import engine

COLLECTION_NAME = "studybuddy"


def get_embeddings() -> AzureOpenAIEmbeddings:
    return AzureOpenAIEmbeddings(
        azure_deployment=settings.azure_openai_embedding_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_embedding_api_version,
    )


def get_vectorstore() -> PGVector:
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
