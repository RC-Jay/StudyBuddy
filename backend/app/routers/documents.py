import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status

from app.config import settings
from app.enums import ProcessingStatus
from app.middleware.auth import get_current_user
from app.models.chat import ChatSession
from app.models.collection import CollectionDocument
from app.models.document import Document
from app.models.quiz import Question, QuizSession
from app.models.summary import Summary
from app.models.user import User
from app.repositories.document import DocumentRepository, get_document_repo
from app.schemas.document import DocumentOut, DocumentRenameIn, DocumentStatusOut
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
    original_name = file.filename or "Untitled"
    doc = repo.create(Document(
        user_id=current_user.id,
        file_name=original_name,
        title=original_name,
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


@router.patch("/{document_id}", response_model=DocumentOut)
def rename_document(
    document_id: uuid.UUID,
    body: DocumentRenameIn,
    repo: DocumentRepository = Depends(get_document_repo),
    current_user: User = Depends(get_current_user),
):
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    doc = _require_owned(repo, document_id, current_user.id)
    return DocumentOut.from_orm(repo.rename(doc, body.title.strip()))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    repo: DocumentRepository = Depends(get_document_repo),
    current_user: User = Depends(get_current_user),
):
    doc = _require_owned(repo, document_id, current_user.id)
    db = repo.db

    # 1. Remove embeddings from the vector store (best-effort — non-fatal)
    try:
        await asyncio.to_thread(delete_document_embeddings, doc.id)
    except Exception:
        pass

    # 2. Delete all related rows that have no FK to documents (orphan-safe cleanup).
    #    Order matters: collection_links must go before the document row itself (FK).

    # Summaries (scope_id is a plain UUID — no FK, so this is just a cleanup query)
    db.query(Summary).filter_by(scope_type="document", scope_id=doc.id).delete(
        synchronize_session=False
    )

    # Chat sessions + their messages (cascade="all, delete-orphan" on ChatSession.messages)
    chat_sessions = (
        db.query(ChatSession).filter_by(scope_type="document", scope_id=doc.id).all()
    )
    for session in chat_sessions:
        db.delete(session)

    # Quiz sessions
    db.query(QuizSession).filter_by(scope_type="document", scope_id=doc.id).delete(
        synchronize_session=False
    )

    # Questions generated from this document (cascade deletes QuestionFeedback)
    questions = db.query(Question).filter_by(source_document_id=doc.id).all()
    for question in questions:
        db.delete(question)

    # Collection memberships (FK → documents.id, must be deleted before the document)
    db.query(CollectionDocument).filter_by(document_id=doc.id).delete(
        synchronize_session=False
    )

    # 3. Hard-delete the document row
    repo.delete(doc)

    # 4. Remove the blob file (best-effort — no blob for videos, silently skipped)
    if doc.blob_path:
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
