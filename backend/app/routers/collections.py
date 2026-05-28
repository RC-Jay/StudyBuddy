import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.middleware.auth import get_current_user
from app.models.chat import ChatSession
from app.models.collection import Collection
from app.models.quiz import Question, QuizSession
from app.models.user import User
from app.repositories.collection import CollectionRepository, get_collection_repo
from app.repositories.document import DocumentRepository, get_document_repo
from app.schemas.collection import CollectionIn, CollectionOut

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
def create_collection(
    body: CollectionIn,
    repo: CollectionRepository = Depends(get_collection_repo),
    current_user: User = Depends(get_current_user),
):
    col = repo.create(Collection(user_id=current_user.id, name=body.name))
    return CollectionOut.from_orm(col)


@router.get("", response_model=list[CollectionOut])
def list_collections(
    repo: CollectionRepository = Depends(get_collection_repo),
    current_user: User = Depends(get_current_user),
):
    return [CollectionOut.from_orm(c) for c in repo.list_for_user(current_user.id)]


@router.get("/{collection_id}", response_model=CollectionOut)
def get_collection(
    collection_id: uuid.UUID,
    repo: CollectionRepository = Depends(get_collection_repo),
    current_user: User = Depends(get_current_user),
):
    return CollectionOut.from_orm(_require_owned(repo, collection_id, current_user.id))


@router.put("/{collection_id}", response_model=CollectionOut)
def rename_collection(
    collection_id: uuid.UUID,
    body: CollectionIn,
    repo: CollectionRepository = Depends(get_collection_repo),
    current_user: User = Depends(get_current_user),
):
    col = _require_owned(repo, collection_id, current_user.id)
    col.name = body.name
    return CollectionOut.from_orm(repo.update(col))


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: uuid.UUID,
    repo: CollectionRepository = Depends(get_collection_repo),
    current_user: User = Depends(get_current_user),
):
    col = _require_owned(repo, collection_id, current_user.id)
    db = repo.db

    # Clean up collection-scoped chat sessions (ORM cascade removes their messages)
    for session in db.query(ChatSession).filter_by(scope_type="collection", scope_id=col.id).all():
        db.delete(session)

    # Clean up collection-scoped quiz sessions
    db.query(QuizSession).filter_by(scope_type="collection", scope_id=col.id).delete(
        synchronize_session=False
    )

    # Clean up collection-scoped questions (ORM cascade removes QuestionFeedback)
    for question in db.query(Question).filter_by(scope_type="collection", scope_id=col.id).all():
        db.delete(question)

    # Delete the collection — ORM cascade removes CollectionDocument memberships.
    # Documents themselves and their own summaries/chats/quizzes are NOT touched.
    repo.delete(col)


@router.post(
    "/{collection_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def add_document(
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    col_repo: CollectionRepository = Depends(get_collection_repo),
    doc_repo: DocumentRepository = Depends(get_document_repo),
    current_user: User = Depends(get_current_user),
):
    col = _require_owned(col_repo, collection_id, current_user.id)
    doc = doc_repo.get_owned(document_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    col_repo.add_document_link(col.id, doc.id)


@router.delete(
    "/{collection_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_document(
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    col_repo: CollectionRepository = Depends(get_collection_repo),
    current_user: User = Depends(get_current_user),
):
    col = _require_owned(col_repo, collection_id, current_user.id)
    col_repo.remove_document_link(col.id, document_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_owned(
    repo: CollectionRepository, col_id: uuid.UUID, user_id: uuid.UUID
) -> Collection:
    col = repo.get_owned(col_id, user_id)
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    return col
