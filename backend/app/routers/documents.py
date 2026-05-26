import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.document import Document
from app.models.user import User
from app.services.document_processor import process_document
from app.services.langchain_setup import delete_document_embeddings
from app.services.storage import delete_file, save_file

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_TYPES = {"application/pdf": "pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}


class DocumentOut(BaseModel):
    id: str
    title: str
    file_type: str
    page_count: int | None
    file_size_bytes: int
    processing_status: str
    created_at: str

    @classmethod
    def from_orm(cls, doc: Document) -> "DocumentOut":
        return cls(
            id=str(doc.id),
            title=doc.title,
            file_type=doc.file_type,
            page_count=doc.page_count,
            file_size_bytes=doc.file_size_bytes,
            processing_status=doc.processing_status,
            created_at=doc.created_at.isoformat(),
        )


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        raise HTTPException(status_code=400, detail=f"File exceeds the {settings.max_file_size_mb}MB limit.")

    blob_path = await save_file(content, file.filename or "upload")
    doc = Document(
        user_id=current_user.id,
        title=file.filename or "Untitled",
        file_type=ALLOWED_TYPES[file.content_type],
        file_size_bytes=len(content),
        blob_path=blob_path,
        processing_status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(process_document, doc.id)
    return DocumentOut.from_orm(doc)


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    docs = (
        db.query(Document)
        .filter_by(user_id=current_user.id)
        .filter(Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
        .all()
    )
    return [DocumentOut.from_orm(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = _get_owned_doc(db, document_id, current_user.id)
    return DocumentOut.from_orm(doc)


@router.get("/{document_id}/status")
def get_processing_status(document_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = _get_owned_doc(db, document_id, current_user.id)
    return {"status": doc.processing_status, "error": doc.processing_error}


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = _get_owned_doc(db, document_id, current_user.id)
    # Remove embeddings from LangChain vector store
    try:
        await asyncio.to_thread(delete_document_embeddings, doc.id)
    except Exception:
        pass
    # Soft-delete the document record
    doc.deleted_at = datetime.now(timezone.utc)
    db.commit()
    # Best-effort file removal
    try:
        await delete_file(doc.blob_path)
    except Exception:
        pass


def _get_owned_doc(db: Session, doc_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    doc = db.query(Document).filter_by(id=doc_id, user_id=user_id).filter(Document.deleted_at.is_(None)).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
