"""
Tests for the /collections router.
"""
import uuid

import pytest


class TestCreateCollection:
    def test_create_returns_201(self, client):
        resp = client.post("/api/v1/collections", json={"name": "Physics"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Physics"
        assert "id" in data

    def test_create_missing_name_returns_422(self, client):
        resp = client.post("/api/v1/collections", json={})
        assert resp.status_code == 422


class TestListCollections:
    def test_empty(self, client):
        resp = client.get("/api/v1/collections")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_created_collection(self, client, test_collection):
        resp = client.get("/api/v1/collections")
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert str(test_collection.id) in ids


class TestGetCollection:
    def test_get_existing(self, client, test_collection):
        resp = client.get(f"/api/v1/collections/{test_collection.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_collection.id)

    def test_get_nonexistent_404(self, client):
        resp = client.get(f"/api/v1/collections/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestRenameCollection:
    def test_rename(self, client, test_collection):
        resp = client.put(f"/api/v1/collections/{test_collection.id}", json={"name": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    def test_rename_nonexistent_404(self, client):
        resp = client.put(f"/api/v1/collections/{uuid.uuid4()}", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteCollection:
    def test_delete_returns_204(self, client, test_collection):
        resp = client.delete(f"/api/v1/collections/{test_collection.id}")
        assert resp.status_code == 204

    def test_delete_nonexistent_404(self, client):
        resp = client.delete(f"/api/v1/collections/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_deleted_collection_no_longer_listed(self, client, test_collection):
        client.delete(f"/api/v1/collections/{test_collection.id}")
        resp = client.get("/api/v1/collections")
        ids = [c["id"] for c in resp.json()]
        assert str(test_collection.id) not in ids


class TestDocumentLinks:
    def test_add_document_to_collection(self, client, test_collection, test_document):
        resp = client.post(
            f"/api/v1/collections/{test_collection.id}/documents/{test_document.id}"
        )
        assert resp.status_code == 204

    def test_add_document_wrong_collection_404(self, client, test_document):
        resp = client.post(
            f"/api/v1/collections/{uuid.uuid4()}/documents/{test_document.id}"
        )
        assert resp.status_code == 404

    def test_add_nonexistent_document_404(self, client, test_collection):
        resp = client.post(
            f"/api/v1/collections/{test_collection.id}/documents/{uuid.uuid4()}"
        )
        assert resp.status_code == 404

    def test_remove_document_from_collection(self, client, test_collection, test_document):
        client.post(
            f"/api/v1/collections/{test_collection.id}/documents/{test_document.id}"
        )
        resp = client.delete(
            f"/api/v1/collections/{test_collection.id}/documents/{test_document.id}"
        )
        assert resp.status_code == 204

    def test_remove_document_wrong_collection_404(self, client, test_document):
        resp = client.delete(
            f"/api/v1/collections/{uuid.uuid4()}/documents/{test_document.id}"
        )
        assert resp.status_code == 404
