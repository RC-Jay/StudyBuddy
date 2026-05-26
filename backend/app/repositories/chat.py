import uuid

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.chat import ChatMessage, ChatSession


class ChatRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @property
    def db(self) -> Session:
        """Expose session for services that need it directly (e.g. rag.retrieve)."""
        return self._db

    def get_owned_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ChatSession | None:
        return self._db.query(ChatSession).filter_by(
            id=session_id, user_id=user_id
        ).first()

    def list_sessions_for_user(self, user_id: uuid.UUID) -> list[ChatSession]:
        return (
            self._db.query(ChatSession)
            .filter_by(user_id=user_id)
            .order_by(ChatSession.created_at.desc())
            .all()
        )

    def create_session(self, session: ChatSession) -> ChatSession:
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        return session

    def add_message(self, message: ChatMessage) -> ChatMessage:
        self._db.add(message)
        self._db.commit()
        self._db.refresh(message)
        return message

    def add_message_no_flush(self, message: ChatMessage) -> None:
        """Add a message without committing — used mid-stream to get the id after stream ends."""
        self._db.add(message)

    def commit(self) -> None:
        self._db.commit()


# FastAPI dependency
def get_chat_repo(db: Session = Depends(get_db)) -> ChatRepository:
    return ChatRepository(db)
