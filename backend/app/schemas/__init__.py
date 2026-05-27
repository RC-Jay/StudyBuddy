# Re-export all schemas for convenient importing
from app.schemas.auth import OAuthLoginBody, TokenResponse
from app.schemas.chat import MessageIn, MessageOut, SessionCreate, SessionOut
from app.schemas.collection import CollectionIn, CollectionOut
from app.schemas.document import DocumentOut, DocumentStatusOut
from app.schemas.quiz import AnswerSubmit, QuestionOut, QuizCreate, QuizOut
from app.schemas.summary import SummaryOut, SummaryRequest

__all__ = [
    "OAuthLoginBody", "TokenResponse",
    "MessageIn", "MessageOut", "SessionCreate", "SessionOut",
    "CollectionIn", "CollectionOut",
    "DocumentOut", "DocumentStatusOut",
    "AnswerSubmit", "QuestionOut", "QuizCreate", "QuizOut",
    "SummaryOut", "SummaryRequest",
]
