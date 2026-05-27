"""
Shared test fixtures.

Test database
-------------
Tests run against a real PostgreSQL database named ``studybuddy_test``.
Create it once before running the suite:

    createdb studybuddy_test
    psql studybuddy_test -c "CREATE EXTENSION IF NOT EXISTS vector;"

Override the URL via the TEST_DATABASE_URL environment variable.

External services
-----------------
No live calls to Azure OpenAI, Google OAuth, or Azure Blob are made.
All external clients are replaced by lightweight doubles.
"""
import os
import uuid
from collections.abc import AsyncGenerator

# Set required env vars before any app imports so Pydantic Settings doesn't error
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/studybuddy_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-not-for-production")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id.apps.googleusercontent.com")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com/")

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document as LCDocument
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.middleware.auth import get_current_user
from app.models.collection import Collection
from app.models.document import Document
from app.models.user import User
from app.services.langchain_setup import get_vectorstore_dep
from app.services.llm import BaseChatProvider, get_provider_dep

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://localhost/studybuddy_test"
)


# ---------------------------------------------------------------------------
# Mock chat provider
# ---------------------------------------------------------------------------

class MockChatProvider(BaseChatProvider):
    """Deterministic chat provider for tests — no network calls."""

    def __init__(self, response: str = "Mock LLM response from tests"):
        self.response = response
        self.calls: list[list[dict]] = []

    async def complete(self, messages: list[dict], temperature: float = 0.3) -> str:
        self.calls.append(messages)
        return self.response

    async def stream(
        self, messages: list[dict], temperature: float = 0.3
    ) -> AsyncGenerator[str, None]:
        self.calls.append(messages)
        for word in self.response.split():
            yield word + " "


# ---------------------------------------------------------------------------
# Mock vector store
# ---------------------------------------------------------------------------

def make_mock_vectorstore(chunks: list[dict] | None = None):
    """
    Returns a MagicMock that satisfies the VectorStore interface.

    ``chunks`` is a list of dicts with keys:
        content   (str)
        metadata  (dict, should include document_id, document_title, page)
        score     (float, optional — default 0.9)
    """
    from unittest.mock import MagicMock
    vs = MagicMock()
    docs_and_scores = [
        (
            LCDocument(
                page_content=c["content"],
                metadata=c.get("metadata", {}),
            ),
            c.get("score", 0.9),
        )
        for c in (chunks or [])
    ]
    vs.similarity_search_with_score.return_value = docs_and_scores
    vs.add_documents.return_value = None
    return vs


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def db_engine():
    """Session-scoped engine; creates all tables once, drops them at the end."""
    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_engine):
    """
    Per-test database session.  All changes are wrapped in a transaction that
    is rolled back when the test finishes, so each test starts with a clean DB.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Domain object fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_user(db) -> User:
    user = User(
        oauth_provider="google",
        oauth_provider_id="google-test-user-id-001",
        email="testuser@example.com",
        display_name="Test User",
        picture_url="https://lh3.googleusercontent.com/test",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def other_user(db) -> User:
    """A second user — used to verify ownership checks."""
    user = User(
        oauth_provider="google",
        oauth_provider_id="google-other-user-id-002",
        email="other@example.com",
        display_name="Other User",
        picture_url=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_document(db, test_user) -> Document:
    doc = Document(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="Test Document",
        file_type="pdf",
        file_size_bytes=1024,
        blob_path="/tmp/test.pdf",
        processing_status="ready",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@pytest.fixture
def test_collection(db, test_user) -> Collection:
    col = Collection(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Test Collection",
    )
    db.add(col)
    db.commit()
    db.refresh(col)
    return col


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_token(test_user) -> str:
    """A valid JWT access token for test_user."""
    from app.services.auth import create_access_token
    return create_access_token(str(test_user.id))


@pytest.fixture
def auth_headers(auth_token) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_provider() -> MockChatProvider:
    return MockChatProvider()


@pytest.fixture
def mock_vectorstore():
    return make_mock_vectorstore()


@pytest.fixture
def client(db, test_user, mock_provider, mock_vectorstore):
    """
    TestClient with:
      - DB overridden to use the test session
      - current_user pinned to test_user (no JWT required in requests)
      - LLM provider replaced by MockChatProvider
      - Vector store replaced by mock (no PGVector connections)
    """
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_provider_dep] = lambda: mock_provider
    app.dependency_overrides[get_vectorstore_dep] = lambda: mock_vectorstore

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def client_with_auth(db, test_user, auth_headers, mock_provider, mock_vectorstore):
    """
    TestClient where auth is exercised via real JWT (does not override
    get_current_user).  Use when you want to test the auth middleware itself.
    """
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_provider_dep] = lambda: mock_provider
    app.dependency_overrides[get_vectorstore_dep] = lambda: mock_vectorstore

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, auth_headers

    app.dependency_overrides.clear()
