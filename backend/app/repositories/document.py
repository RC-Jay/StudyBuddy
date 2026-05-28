import uuid

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.document import Document


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @property
    def db(self) -> Session:
        return self._db

    def get_owned(self, doc_id: uuid.UUID, user_id: uuid.UUID) -> Document | None:
        """Return a document owned by user_id, or None."""
        return (
            self._db.query(Document)
            .filter_by(id=doc_id, user_id=user_id)
            .first()
        )

    def list_for_user(self, user_id: uuid.UUID) -> list[Document]:
        """Return all documents for a user, newest first."""
        return (
            self._db.query(Document)
            .filter_by(user_id=user_id)
            .order_by(Document.created_at.desc())
            .all()
        )

    def create(self, doc: Document) -> Document:
        self._db.add(doc)
        self._db.commit()
        self._db.refresh(doc)
        return doc

    def rename(self, doc: Document, title: str) -> Document:
        doc.title = title
        self._db.commit()
        self._db.refresh(doc)
        return doc

    def delete(self, doc: Document) -> None:
        """Hard-delete the document row. Caller must clean up related data first."""
        self._db.delete(doc)
        self._db.commit()


# FastAPI dependency
def get_document_repo(db: Session = Depends(get_db)) -> DocumentRepository:
    return DocumentRepository(db)
