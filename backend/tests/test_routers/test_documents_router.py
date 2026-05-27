"""
Tests for GET/DELETE document endpoints.
Upload is skipped here (requires file I/O + background tasks that need deeper mocking).
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest


class TestListDocuments:
    def test_empty_list(self, client):
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_user_documents(self, client, test_document):
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == str(test_document.id)
        assert data[0]["title"] == test_document.title


class TestGetDocument:
    def test_get_own_document(self, client, test_document):
        resp = client.get(f"/api/v1/documents/{test_document.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_document.id)

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get(f"/api/v1/documents/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_get_other_users_document_returns_404(self, client, db, other_user):
        from app.models.document import Document
        other_doc = Document(
            id=uuid.uuid4(),
            user_id=other_user.id,
            file_name="Other's Doc",
            title="Other's Doc",
            file_type="pdf",
            file_size_bytes=100,
            blob_path="/tmp/other.pdf",
            processing_status="ready",
        )
        db.add(other_doc)
        db.commit()

        resp = client.get(f"/api/v1/documents/{other_doc.id}")
        assert resp.status_code == 404


class TestGetDocumentStatus:
    def test_returns_processing_status(self, client, test_document):
        resp = client.get(f"/api/v1/documents/{test_document.id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ready"

    def test_nonexistent_returns_404(self, client):
        resp = client.get(f"/api/v1/documents/{uuid.uuid4()}/status")
        assert resp.status_code == 404


class TestDeleteDocument:
    def test_delete_own_document(self, client, test_document):
        with patch("app.routers.documents.delete_document_embeddings"), \
             patch("app.routers.documents.delete_file", new_callable=AsyncMock):
            resp = client.delete(f"/api/v1/documents/{test_document.id}")
        assert resp.status_code == 204

    def test_delete_nonexistent_returns_404(self, client):
        with patch("app.routers.documents.delete_document_embeddings"), \
             patch("app.routers.documents.delete_file", new_callable=AsyncMock):
            resp = client.delete(f"/api/v1/documents/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_removes_from_list(self, client, test_document):
        with patch("app.routers.documents.delete_document_embeddings"), \
             patch("app.routers.documents.delete_file", new_callable=AsyncMock):
            client.delete(f"/api/v1/documents/{test_document.id}")
        resp = client.get("/api/v1/documents")
        assert resp.json() == []
