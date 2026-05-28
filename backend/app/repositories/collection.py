import uuid

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.collection import Collection, CollectionDocument


class CollectionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_owned(self, col_id: uuid.UUID, user_id: uuid.UUID) -> Collection | None:
        """Return a collection owned by user_id, or None."""
        return self._db.query(Collection).filter_by(id=col_id, user_id=user_id).first()

    def list_for_user(self, user_id: uuid.UUID) -> list[Collection]:
        return (
            self._db.query(Collection)
            .filter_by(user_id=user_id)
            .order_by(Collection.created_at.desc())
            .all()
        )

    def create(self, col: Collection) -> Collection:
        self._db.add(col)
        self._db.commit()
        self._db.refresh(col)
        return col

    def update(self, col: Collection) -> Collection:
        self._db.commit()
        self._db.refresh(col)
        return col

    @property
    def db(self) -> Session:
        return self._db

    def delete(self, col: Collection) -> None:
        self._db.delete(col)
        self._db.commit()

    def get_document_link(
        self, col_id: uuid.UUID, doc_id: uuid.UUID
    ) -> CollectionDocument | None:
        return self._db.query(CollectionDocument).filter_by(
            collection_id=col_id, document_id=doc_id
        ).first()

    def add_document_link(self, col_id: uuid.UUID, doc_id: uuid.UUID) -> None:
        if not self.get_document_link(col_id, doc_id):
            self._db.add(CollectionDocument(collection_id=col_id, document_id=doc_id))
            self._db.commit()

    def remove_document_link(self, col_id: uuid.UUID, doc_id: uuid.UUID) -> None:
        link = self.get_document_link(col_id, doc_id)
        if link:
            self._db.delete(link)
            self._db.commit()


# FastAPI dependency
def get_collection_repo(db: Session = Depends(get_db)) -> CollectionRepository:
    return CollectionRepository(db)
