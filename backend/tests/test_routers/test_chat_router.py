"""
Tests for the /chat router.

MockChatProvider and mock_vectorstore are injected via the `client` fixture.
The vector store mock returns no chunks by default (empty context),
which is fine — chat still streams a response.
"""
import uuid

import pytest

from tests.conftest import make_mock_vectorstore


class TestCreateSession:
    def test_create_document_session(self, client, test_document):
        resp = client.post("/api/v1/chat/sessions", json={
            "scope_type": "document",
            "scope_id": str(test_document.id),
            "title": "My Study Session",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["scope_type"] == "document"
        assert data["scope_id"] == str(test_document.id)
        assert data["title"] == "My Study Session"
        assert data["message_count"] == 0

    def test_create_session_invalid_scope_type_422(self, client):
        resp = client.post("/api/v1/chat/sessions", json={
            "scope_type": "invalid",
            "scope_id": str(uuid.uuid4()),
        })
        assert resp.status_code == 422


class TestListSessions:
    def test_empty(self, client):
        resp = client.get("/api/v1/chat/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_created_sessions(self, client, test_document):
        client.post("/api/v1/chat/sessions", json={
            "scope_type": "document",
            "scope_id": str(test_document.id),
        })
        resp = client.get("/api/v1/chat/sessions")
        assert len(resp.json()) == 1


class TestGetSession:
    def test_get_existing_session(self, client, test_document):
        created = client.post("/api/v1/chat/sessions", json={
            "scope_type": "document",
            "scope_id": str(test_document.id),
        }).json()

        resp = client.get(f"/api/v1/chat/sessions/{created['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == created["id"]
        assert "messages" in data
        assert data["messages"] == []

    def test_get_nonexistent_404(self, client):
        resp = client.get(f"/api/v1/chat/sessions/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestSendMessage:
    def test_send_message_streams_response(self, client, test_document, mock_provider):
        session = client.post("/api/v1/chat/sessions", json={
            "scope_type": "document",
            "scope_id": str(test_document.id),
        }).json()

        mock_provider.response = "Hello from the mock LLM."

        resp = client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "What is this document about?"},
        )
        assert resp.status_code == 200
        # Response is SSE — should contain the 'done' event
        assert b"done" in resp.content

    def test_send_message_to_nonexistent_session_404(self, client):
        resp = client.post(
            f"/api/v1/chat/sessions/{uuid.uuid4()}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 404

    def test_send_message_persists_in_session(self, client, test_document, mock_provider):
        """After sending a message the session should show message_count > 0."""
        session = client.post("/api/v1/chat/sessions", json={
            "scope_type": "document",
            "scope_id": str(test_document.id),
        }).json()

        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "Test question"},
        )

        resp = client.get(f"/api/v1/chat/sessions/{session['id']}")
        data = resp.json()
        # user message + assistant response = 2
        assert data["message_count"] >= 1

    def test_mock_provider_records_call(self, client, test_document, mock_provider):
        """Verify the mock provider's calls list is populated."""
        session = client.post("/api/v1/chat/sessions", json={
            "scope_type": "document",
            "scope_id": str(test_document.id),
        }).json()

        prev_call_count = len(mock_provider.calls)
        client.post(
            f"/api/v1/chat/sessions/{session['id']}/messages",
            json={"content": "A question"},
        )
        assert len(mock_provider.calls) == prev_call_count + 1

    def test_vectorstore_called_with_right_filter(self, db, test_user, test_document, mock_provider):
        """Vectorstore should be called during message send with the document filter."""
        from app.main import app
        from app.database import get_db
        from app.middleware.auth import get_current_user
        from app.services.llm import get_provider_dep
        from app.services.langchain_setup import get_vectorstore_dep
        from fastapi.testclient import TestClient

        vs = make_mock_vectorstore([])

        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_provider_dep] = lambda: mock_provider
        app.dependency_overrides[get_vectorstore_dep] = lambda: vs

        with TestClient(app, raise_server_exceptions=True) as c:
            session = c.post("/api/v1/chat/sessions", json={
                "scope_type": "document",
                "scope_id": str(test_document.id),
            }).json()
            c.post(
                f"/api/v1/chat/sessions/{session['id']}/messages",
                json={"content": "Tell me about Newton"},
            )

        app.dependency_overrides.clear()

        vs.similarity_search_with_score.assert_called_once()
        call_kwargs = vs.similarity_search_with_score.call_args
        filter_arg = call_kwargs.kwargs.get("filter") or (call_kwargs.args[2] if len(call_kwargs.args) > 2 else None)
        assert filter_arg == {"document_id": str(test_document.id)}
