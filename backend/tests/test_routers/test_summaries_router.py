"""
Tests for the /summaries router.

MockChatProvider is injected to avoid real LLM calls.
Vectorstore is mocked to return content so the "no content" 422 branch
is exercised when needed.
"""
import uuid

import pytest

from tests.conftest import make_mock_vectorstore


def _summary_body(scope_id: str, granularity: str = "full", section_hint: str | None = None):
    body = {"scope_type": "document", "scope_id": scope_id, "granularity": granularity}
    if section_hint:
        body["section_hint"] = section_hint
    return body


class TestGenerateSummary:
    def test_full_summary_returns_201(self, client, test_document, mock_provider):
        """With chunks returned by the mock vectorstore, summary generation should succeed."""
        from app.main import app
        from app.database import get_db
        from app.middleware.auth import get_current_user
        from app.services.llm import get_provider_dep
        from app.services.langchain_setup import get_vectorstore_dep
        from fastapi.testclient import TestClient
        from tests.conftest import MockChatProvider

        vs = make_mock_vectorstore([
            {"content": "Some study content", "metadata": {"document_title": "Test Doc", "page": 1}}
        ])
        mock_provider = MockChatProvider(response="A comprehensive summary.")

        db_fixture = client.app.dependency_overrides[get_db]()

        # Re-wire with custom vs that has content
        app.dependency_overrides[get_vectorstore_dep] = lambda: vs
        app.dependency_overrides[get_provider_dep] = lambda: mock_provider

        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.post("/api/v1/summaries", json=_summary_body(str(test_document.id)))

        app.dependency_overrides.pop(get_vectorstore_dep, None)
        app.dependency_overrides.pop(get_provider_dep, None)

        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "A comprehensive summary."
        assert data["granularity"] == "full"

    def test_no_content_returns_422(self, client, test_document):
        """When vectorstore returns nothing, the endpoint should return 422."""
        # The default mock_vectorstore fixture returns empty chunks
        resp = client.post("/api/v1/summaries", json=_summary_body(str(test_document.id)))
        assert resp.status_code == 422

    def test_section_granularity_requires_hint(self, client, test_document):
        resp = client.post(
            "/api/v1/summaries",
            json=_summary_body(str(test_document.id), granularity="section"),
        )
        assert resp.status_code == 422

    def test_section_with_hint_accepted(self, client, test_document, db, test_user):
        """section granularity + hint with content should succeed."""
        from app.main import app
        from app.database import get_db
        from app.middleware.auth import get_current_user
        from app.services.llm import get_provider_dep
        from app.services.langchain_setup import get_vectorstore_dep
        from fastapi.testclient import TestClient
        from tests.conftest import MockChatProvider

        vs = make_mock_vectorstore([
            {"content": "Chapter 3 text", "metadata": {"document_title": "Test Doc", "page": 3}}
        ])
        mock_provider = MockChatProvider(response="Section summary content.")

        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_vectorstore_dep] = lambda: vs
        app.dependency_overrides[get_provider_dep] = lambda: mock_provider

        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.post("/api/v1/summaries", json={
                "scope_type": "document",
                "scope_id": str(test_document.id),
                "granularity": "section",
                "section_hint": "Chapter 3: Thermodynamics",
            })

        app.dependency_overrides.clear()

        assert resp.status_code == 201
        assert resp.json()["granularity"] == "section"

    def test_invalid_granularity_422(self, client, test_document):
        resp = client.post(
            "/api/v1/summaries",
            json={
                "scope_type": "document",
                "scope_id": str(test_document.id),
                "granularity": "bullet_points",  # not a valid enum
            },
        )
        assert resp.status_code == 422


class TestListSummaries:
    def test_empty_list(self, client):
        resp = client.get("/api/v1/summaries")
        assert resp.status_code == 200
        assert resp.json() == []
