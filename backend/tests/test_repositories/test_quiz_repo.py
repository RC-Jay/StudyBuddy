"""
Tests for app.repositories.quiz.QuizRepository

Covers session lifecycle, question bank, and per-user flag filtering.
"""
import uuid

import pytest

from app.models.quiz import Question, QuestionFeedback, QuizSession
from app.repositories.quiz import QuizRepository


@pytest.fixture
def repo(db) -> QuizRepository:
    return QuizRepository(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_session(user_id: uuid.UUID, scope_id: uuid.UUID | None = None) -> QuizSession:
    return QuizSession(
        id=uuid.uuid4(),
        user_id=user_id,
        mode="exam",
        scope_type="document",
        scope_id=scope_id or uuid.uuid4(),
        config={"format": "mcq", "difficulty": "intermediate", "question_count": 5},
        question_ids=[],
    )


def _new_question(scope_id: uuid.UUID, fmt: str = "mcq", difficulty: str = "intermediate") -> Question:
    return Question(
        id=uuid.uuid4(),
        scope_type="document",
        scope_id=scope_id,
        format=fmt,
        difficulty=difficulty,
        topic_tags=[],
        stem="What is 1 + 1?",
        options=["1", "2", "3", "4"],
        correct_answer="2",
        explanation="Math, p.1",
        source_page_range="1",
    )


# ---------------------------------------------------------------------------
# QuizSession
# ---------------------------------------------------------------------------

class TestQuizSessionCRUD:
    def test_create_and_get_owned(self, repo, test_user):
        session = repo.create_session(_new_session(test_user.id))
        fetched = repo.get_owned_session(session.id, test_user.id)
        assert fetched is not None
        assert fetched.id == session.id

    def test_get_owned_wrong_user_returns_none(self, repo, test_user, other_user):
        session = repo.create_session(_new_session(test_user.id))
        assert repo.get_owned_session(session.id, other_user.id) is None

    def test_list_sessions_for_user(self, repo, test_user, other_user):
        s1 = repo.create_session(_new_session(test_user.id))
        s2 = repo.create_session(_new_session(test_user.id))
        repo.create_session(_new_session(other_user.id))

        sessions = repo.list_sessions_for_user(test_user.id)
        ids = [s.id for s in sessions]
        assert s1.id in ids and s2.id in ids
        assert len(ids) == 2

    def test_complete_session(self, repo, test_user):
        session = repo.create_session(_new_session(test_user.id))
        answers = [{"question_id": "q1", "user_answer": "A", "is_correct": True}]
        repo.complete_session(session, answers, 80)

        assert session.score == 80
        assert session.completed_at is not None
        assert session.answers == answers


# ---------------------------------------------------------------------------
# Question bank
# ---------------------------------------------------------------------------

class TestQuestionBank:
    def test_bulk_add_and_get_by_ids(self, repo, test_document):
        q1 = _new_question(test_document.id)
        q2 = _new_question(test_document.id)
        repo.bulk_add_questions([q1, q2])

        fetched = repo.get_questions_by_ids([q1.id, q2.id])
        ids = {q.id for q in fetched}
        assert q1.id in ids and q2.id in ids

    def test_get_bank_questions_filters_by_scope(self, repo, test_document, test_user):
        scope_id = test_document.id
        other_scope = uuid.uuid4()
        q_in_scope = _new_question(scope_id)
        q_other = _new_question(other_scope)
        repo.bulk_add_questions([q_in_scope, q_other])

        results = repo.get_bank_questions("document", scope_id, "mcq", "intermediate", test_user.id)
        ids = [q.id for q in results]
        assert q_in_scope.id in ids
        assert q_other.id not in ids

    def test_get_bank_questions_excludes_user_flagged(self, repo, test_document, test_user, other_user):
        """A question flagged by test_user must not appear in their bank query."""
        q = _new_question(test_document.id)
        repo.bulk_add_questions([q])
        repo.upsert_flag(q.id, test_user.id)

        # test_user should not see the flagged question
        for_test_user = repo.get_bank_questions(
            "document", test_document.id, "mcq", "intermediate", test_user.id
        )
        assert q.id not in [x.id for x in for_test_user]

        # other_user has NOT flagged the question — they should still see it
        for_other_user = repo.get_bank_questions(
            "document", test_document.id, "mcq", "intermediate", other_user.id
        )
        assert q.id in [x.id for x in for_other_user]

    def test_get_question_by_id(self, repo, test_document):
        q = _new_question(test_document.id)
        repo.bulk_add_questions([q])
        found = repo.get_question(q.id)
        assert found is not None
        assert found.id == q.id

    def test_get_question_nonexistent_returns_none(self, repo):
        assert repo.get_question(uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# Flagging
# ---------------------------------------------------------------------------

class TestFlagging:
    def test_upsert_flag_creates_feedback(self, repo, test_document, test_user):
        q = _new_question(test_document.id)
        repo.bulk_add_questions([q])
        repo.upsert_flag(q.id, test_user.id)

        feedback = repo.get_feedback(q.id, test_user.id)
        assert feedback is not None
        assert feedback.flagged_bad_quality is True

    def test_upsert_flag_idempotent(self, repo, test_document, test_user):
        """Flagging twice should not raise or create duplicate rows."""
        q = _new_question(test_document.id)
        repo.bulk_add_questions([q])
        repo.upsert_flag(q.id, test_user.id)
        repo.upsert_flag(q.id, test_user.id)  # second call

        feedback = repo.get_feedback(q.id, test_user.id)
        assert feedback.flagged_bad_quality is True

    def test_get_feedback_nonexistent_returns_none(self, repo, test_document, test_user):
        assert repo.get_feedback(uuid.uuid4(), test_user.id) is None
