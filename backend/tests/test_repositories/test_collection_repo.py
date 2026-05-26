"""
Tests for app.repositories.collection.CollectionRepository

Covers CRUD operations plus document-link management.
"""
import uuid

import pytest

from app.models.collection import Collection
from app.repositories.collection import CollectionRepository


@pytest.fixture
def repo(db) -> CollectionRepository:
    return CollectionRepository(db)


def _new_col(user_id: uuid.UUID, name: str = "My Collection") -> Collection:
    return Collection(id=uuid.uuid4(), user_id=user_id, name=name)


class TestCollectionCreate:
    def test_create_and_retrieve(self, repo, test_user):
        col = repo.create(_new_col(test_user.id, "Physics Notes"))
        assert col.id is not None
        assert col.name == "Physics Notes"
        assert col.user_id == test_user.id


class TestCollectionGetOwned:
    def test_returns_own_collection(self, repo, test_user):
        col = repo.create(_new_col(test_user.id))
        found = repo.get_owned(col.id, test_user.id)
        assert found is not None
        assert found.id == col.id

    def test_returns_none_for_wrong_owner(self, repo, test_user, other_user):
        col = repo.create(_new_col(test_user.id))
        assert repo.get_owned(col.id, other_user.id) is None

    def test_returns_none_for_nonexistent(self, repo, test_user):
        assert repo.get_owned(uuid.uuid4(), test_user.id) is None


class TestCollectionListForUser:
    def test_lists_only_own_collections(self, repo, test_user, other_user):
        repo.create(_new_col(test_user.id, "Mine A"))
        repo.create(_new_col(test_user.id, "Mine B"))
        repo.create(_new_col(other_user.id, "Theirs"))

        cols = repo.list_for_user(test_user.id)
        names = [c.name for c in cols]
        assert "Mine A" in names
        assert "Mine B" in names
        assert "Theirs" not in names

    def test_empty_for_new_user(self, repo, other_user):
        assert repo.list_for_user(other_user.id) == []


class TestCollectionUpdate:
    def test_rename(self, repo, test_user):
        col = repo.create(_new_col(test_user.id, "Old Name"))
        col.name = "New Name"
        updated = repo.update(col)
        assert updated.name == "New Name"


class TestCollectionDelete:
    def test_delete_removes_collection(self, repo, test_user):
        col = repo.create(_new_col(test_user.id))
        repo.delete(col)
        assert repo.get_owned(col.id, test_user.id) is None


class TestDocumentLinks:
    def test_add_and_get_link(self, repo, test_collection, test_document):
        repo.add_document_link(test_collection.id, test_document.id)
        link = repo.get_document_link(test_collection.id, test_document.id)
        assert link is not None

    def test_add_duplicate_link_is_idempotent(self, repo, test_collection, test_document):
        """Adding the same document twice should not raise or duplicate."""
        repo.add_document_link(test_collection.id, test_document.id)
        repo.add_document_link(test_collection.id, test_document.id)  # second call
        link = repo.get_document_link(test_collection.id, test_document.id)
        assert link is not None

    def test_remove_link(self, repo, test_collection, test_document):
        repo.add_document_link(test_collection.id, test_document.id)
        repo.remove_document_link(test_collection.id, test_document.id)
        assert repo.get_document_link(test_collection.id, test_document.id) is None

    def test_remove_nonexistent_link_is_silent(self, repo, test_collection):
        """Removing a link that doesn't exist should not raise."""
        repo.remove_document_link(test_collection.id, uuid.uuid4())

    def test_get_nonexistent_link_returns_none(self, repo, test_collection):
        assert repo.get_document_link(test_collection.id, uuid.uuid4()) is None
