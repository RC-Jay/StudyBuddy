import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.collection import Collection, CollectionDocument
from app.models.document import Document
from app.models.user import User

router = APIRouter(prefix="/collections", tags=["collections"])


class CollectionIn(BaseModel):
    name: str


class CollectionOut(BaseModel):
    id: str
    name: str
    created_at: str
    document_count: int

    @classmethod
    def from_orm(cls, col: Collection) -> "CollectionOut":
        return cls(
            id=str(col.id),
            name=col.name,
            created_at=col.created_at.isoformat(),
            document_count=len([l for l in col.document_links]),
        )


@router.post("", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
def create_collection(body: CollectionIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    col = Collection(user_id=current_user.id, name=body.name)
    db.add(col)
    db.commit()
    db.refresh(col)
    return CollectionOut.from_orm(col)


@router.get("", response_model=list[CollectionOut])
def list_collections(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cols = db.query(Collection).filter_by(user_id=current_user.id).order_by(Collection.created_at.desc()).all()
    return [CollectionOut.from_orm(c) for c in cols]


@router.get("/{collection_id}", response_model=CollectionOut)
def get_collection(collection_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    col = _get_owned_col(db, collection_id, current_user.id)
    return CollectionOut.from_orm(col)


@router.put("/{collection_id}", response_model=CollectionOut)
def rename_collection(collection_id: uuid.UUID, body: CollectionIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    col = _get_owned_col(db, collection_id, current_user.id)
    col.name = body.name
    db.commit()
    db.refresh(col)
    return CollectionOut.from_orm(col)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    col = _get_owned_col(db, collection_id, current_user.id)
    db.delete(col)
    db.commit()


@router.post("/{collection_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_document(collection_id: uuid.UUID, document_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    col = _get_owned_col(db, collection_id, current_user.id)
    doc = db.query(Document).filter_by(id=document_id, user_id=current_user.id).filter(Document.deleted_at.is_(None)).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    existing = db.query(CollectionDocument).filter_by(collection_id=col.id, document_id=doc.id).first()
    if not existing:
        db.add(CollectionDocument(collection_id=col.id, document_id=doc.id))
        db.commit()


@router.delete("/{collection_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(collection_id: uuid.UUID, document_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    col = _get_owned_col(db, collection_id, current_user.id)
    link = db.query(CollectionDocument).filter_by(collection_id=col.id, document_id=document_id).first()
    if link:
        db.delete(link)
        db.commit()


def _get_owned_col(db: Session, col_id: uuid.UUID, user_id: uuid.UUID) -> Collection:
    col = db.query(Collection).filter_by(id=col_id, user_id=user_id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    return col
