import uuid
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.quiz import Question, QuestionFeedback, QuizSession


class QuizRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @property
    def db(self) -> Session:
        """Expose session for services that need it directly (e.g. rag.retrieve)."""
        return self._db

    # --- Sessions ---

    def get_owned_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> QuizSession | None:
        return self._db.query(QuizSession).filter_by(
            id=session_id, user_id=user_id
        ).first()

    def list_sessions_for_user(self, user_id: uuid.UUID) -> list[QuizSession]:
        return (
            self._db.query(QuizSession)
            .filter_by(user_id=user_id)
            .order_by(QuizSession.started_at.desc())
            .all()
        )

    def create_session(self, session: QuizSession) -> QuizSession:
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        return session

    def complete_session(
        self, session: QuizSession, answers: list[dict], score: int
    ) -> None:
        session.answers = answers
        session.score = score
        session.completed_at = datetime.now(timezone.utc)
        self._db.commit()

    # --- Questions ---

    def get_question(self, question_id: uuid.UUID) -> Question | None:
        return self._db.get(Question, question_id)

    def get_questions_by_ids(self, question_ids: list[uuid.UUID]) -> list[Question]:
        return self._db.query(Question).filter(Question.id.in_(question_ids)).all()

    def get_bank_questions(
        self,
        scope_type: str,
        scope_id: uuid.UUID,
        format: str,
        difficulty: str,
        user_id: uuid.UUID,
    ) -> list[Question]:
        """
        Return existing questions from the question bank for this scope/format/difficulty,
        excluding any flagged by this specific user.

        Note: filtering is per-user — one user flagging a question does NOT hide it
        from other users (consistent with the PRD spec).
        """
        user_flagged = (
            self._db.query(QuestionFeedback.question_id)
            .filter_by(user_id=user_id, flagged_bad_quality=True)
        )
        return (
            self._db.query(Question)
            .filter(
                Question.scope_type == scope_type,
                Question.scope_id == scope_id,
                Question.format == format,
                Question.difficulty == difficulty,
                Question.id.notin_(user_flagged),
            )
            .all()
        )

    def bulk_add_questions(self, questions: list[Question]) -> None:
        for q in questions:
            self._db.add(q)
        self._db.commit()
        for q in questions:
            self._db.refresh(q)

    # --- Feedback / flagging ---

    def get_feedback(
        self, question_id: uuid.UUID, user_id: uuid.UUID
    ) -> QuestionFeedback | None:
        return self._db.query(QuestionFeedback).filter_by(
            question_id=question_id, user_id=user_id
        ).first()

    def upsert_flag(self, question_id: uuid.UUID, user_id: uuid.UUID) -> None:
        existing = self.get_feedback(question_id, user_id)
        if existing:
            existing.flagged_bad_quality = True
        else:
            self._db.add(QuestionFeedback(
                question_id=question_id,
                user_id=user_id,
                flagged_bad_quality=True,
            ))
        self._db.commit()


# FastAPI dependency
def get_quiz_repo(db: Session = Depends(get_db)) -> QuizRepository:
    return QuizRepository(db)
