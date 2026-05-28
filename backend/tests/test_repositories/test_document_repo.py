"""
Tests for app.repositories.document.DocumentRepository

All operations run against the real test PostgreSQL database.
Each test is isolated by the per-test transaction rollback in conftest.db.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.document import Document
from app.repositories.document import DocumentRepository


@pytest.fixture
def repo(db) -> DocumentRepository:
    return DocumentRepository(db)


def _new_doc(user_id: uuid.UUID, title: str = "Test Doc") -> Document:
    return Document(
        id=uuid.uuid4(),
        user_id=user_id,
        file_name=title,
        title=title,
        file_type="pdf",
        file_size_bytes=512,
        blob_path=f"/tmp/{uuid.uuid4()}.pdf",
        processing_status="pending",
    )


class TestDocumentRepositoryCreate:
    def test_create_returns_persisted_document(self, repo, test_user):
        doc = repo.create(_new_doc(test_user.id, "My Paper"))
        assert doc.id is not None
        assert doc.title == "My Paper"
        assert doc.user_id == test_user.id

    def test_created_document_has_timestamps(self, repo, test_user):
        doc = repo.create(_new_doc(test_user.id))
        assert doc.created_at is not None


class TestDocumentRepositoryGetOwned:
    def test_returns_own_document(self, repo, test_user):
        doc = repo.create(_new_doc(test_user.id))
        fetched = repo.get_owned(doc.id, test_user.id)
        assert fetched is not None
        assert fetched.id == doc.id

    def test_returns_none_for_wrong_owner(self, repo, test_user, other_user):
        doc = repo.create(_new_doc(test_user.id))
        assert repo.get_owned(doc.id, other_user.id) is None

    def test_returns_none_for_nonexistent(self, repo, test_user):
        assert repo.get_owned(uuid.uuid4(), test_user.id) is None

    def test_returns_none_after_delete(self, repo, test_user):
        doc = repo.create(_new_doc(test_user.id))
        doc_id = doc.id
        repo.delete(doc)
        assert repo.get_owned(doc_id, test_user.id) is None


class TestDocumentRepositoryListForUser:
    def test_lists_only_own_documents(self, repo, test_user, other_user):
        repo.create(_new_doc(test_user.id, "Own Doc 1"))
        repo.create(_new_doc(test_user.id, "Own Doc 2"))
        repo.create(_new_doc(other_user.id, "Other's Doc"))

        docs = repo.list_for_user(test_user.id)
        titles = [d.title for d in docs]
        assert "Own Doc 1" in titles
        assert "Own Doc 2" in titles
        assert "Other's Doc" not in titles

    def test_excludes_deleted(self, repo, test_user):
        doc = repo.create(_new_doc(test_user.id, "Will Delete"))
        repo.delete(doc)
        titles = [d.title for d in repo.list_for_user(test_user.id)]
        assert "Will Delete" not in titles

    def test_returns_newest_first(self, repo, test_user):
        from datetime import datetime, timedelta, timezone
        # Give doc1 an older timestamp so the ordering is deterministic
        older_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        doc1 = _new_doc(test_user.id, "Alpha")
        doc1.created_at = older_time
        repo.create(doc1)
        doc2 = repo.create(_new_doc(test_user.id, "Beta"))
        docs = repo.list_for_user(test_user.id)
        # Most recently created should appear first
        ids = [d.id for d in docs]
        assert ids.index(doc2.id) < ids.index(doc1.id)

    def test_empty_for_user_with_no_docs(self, repo, other_user):
        assert repo.list_for_user(other_user.id) == []


class TestDocumentRepositoryDelete:
    def test_hard_delete_removes_row(self, repo, test_user):
        doc = repo.create(_new_doc(test_user.id))
        doc_id = doc.id
        repo.delete(doc)
        assert repo.get_owned(doc_id, test_user.id) is None
        assert repo.list_for_user(test_user.id) == []
