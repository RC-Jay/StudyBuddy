import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status

from app.config import settings
from app.enums import ProcessingStatus
from app.middleware.auth import get_current_user
from app.models.document import Document
from app.models.user import User
from app.repositories.document import DocumentRepository, get_document_repo
from app.schemas.document import DocumentOut, DocumentStatusOut
from app.services.document_processor import process_document
from app.services.langchain_setup import delete_document_embeddings
from app.services.storage import delete_file, save_file

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    repo: DocumentRepository = Depends(get_document_repo),
    current_user: User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")

    content = await file.read()
    if len(content) / (1024 * 1024) > settings.max_file_size_mb:
        raise HTTPException(status_code=400, detail=f"File exceeds the {settings.max_file_size_mb}MB limit.")

    blob_path = await save_file(content, file.filename or "upload")
    doc = repo.create(Document(
        user_id=current_user.id,
        title=file.filename or "Untitled",
        file_type=ALLOWED_TYPES[file.content_type],
        file_size_bytes=len(content),
        blob_path=blob_path,
        processing_status=ProcessingStatus.PENDING,
    ))

    background_tasks.add_task(process_document, doc.id)
    return DocumentOut.from_orm(doc)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    repo: DocumentRepository = Depends(get_document_repo),
    current_user: User = Depends(get_current_user),
):
    return [DocumentOut.from_orm(d) for d in repo.list_for_user(current_user.id)]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: uuid.UUID,
    repo: DocumentRepository = Depends(get_document_repo),
    current_user: User = Depends(get_current_user),
):
    return DocumentOut.from_orm(_require_owned(repo, document_id, current_user.id))


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
def get_processing_status(
    document_id: uuid.UUID,
    repo: DocumentRepository = Depends(get_document_repo),
    current_user: User = Depends(get_current_user),
):
    doc = _require_owned(repo, document_id, current_user.id)
    return DocumentStatusOut(status=doc.processing_status, error=doc.processing_error)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    repo: DocumentRepository = Depends(get_document_repo),
    current_user: User = Depends(get_current_user),
):
    doc = _require_owned(repo, document_id, current_user.id)

    # Best-effort: remove embeddings then file (neither blocks the soft-delete)
    try:
        await asyncio.to_thread(delete_document_embeddings, doc.id)
    except Exception:
        pass

    repo.soft_delete(doc)

    try:
        await delete_file(doc.blob_path)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_owned(repo: DocumentRepository, doc_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    doc = repo.get_owned(doc_id, user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
