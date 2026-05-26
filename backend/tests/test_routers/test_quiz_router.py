"""
Tests for the /quiz router.

generate_questions() is patched at the router boundary to return controlled
Question objects — no LLM calls happen.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.quiz import Question


def _make_question(scope_id: uuid.UUID) -> Question:
    return Question(
        id=uuid.uuid4(),
        scope_type="document",
        scope_id=scope_id,
        format="mcq",
        difficulty="intermediate",
        topic_tags=["test"],
        stem="What is gravity?",
        options=["9.8", "10.0", "9.0", "8.0"],
        correct_answer="9.8",
        explanation="Physics, p.5",
        source_page_range="5",
    )


def _quiz_body(doc_id: str) -> dict:
    return {
        "mode": "exam",
        "scope_type": "document",
        "scope_id": doc_id,
        "format": "mcq",
        "difficulty": "intermediate",
        "question_count": 1,
    }


class TestCreateQuizSession:
    def test_create_returns_201(self, client, test_document):
        q = _make_question(test_document.id)
        with patch("app.routers.quiz.generate_questions", new=AsyncMock(return_value=[q])):
            resp = client.post("/api/v1/quiz/sessions", json=_quiz_body(str(test_document.id)))

        assert resp.status_code == 201
        data = resp.json()
        assert "session" in data
        assert "questions" in data
        assert len(data["questions"]) == 1
        assert data["questions"][0]["stem"] == "What is gravity?"

    def test_create_questions_hidden_in_exam_mode(self, client, test_document):
        """In exam mode, correct_answer should not be in the question list response."""
        q = _make_question(test_document.id)
        with patch("app.routers.quiz.generate_questions", new=AsyncMock(return_value=[q])):
            resp = client.post("/api/v1/quiz/sessions", json=_quiz_body(str(test_document.id)))

        questions = resp.json()["questions"]
        assert "correct_answer" not in questions[0]

    def test_invalid_format_422(self, client, test_document):
        body = _quiz_body(str(test_document.id))
        body["format"] = "essay"
        resp = client.post("/api/v1/quiz/sessions", json=body)
        assert resp.status_code == 422


class TestListQuizSessions:
    def test_empty(self, client):
        resp = client.get("/api/v1/quiz/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_created_sessions(self, client, test_document):
        q = _make_question(test_document.id)
        with patch("app.routers.quiz.generate_questions", new=AsyncMock(return_value=[q])):
            client.post("/api/v1/quiz/sessions", json=_quiz_body(str(test_document.id)))

        resp = client.get("/api/v1/quiz/sessions")
        assert len(resp.json()) == 1


class TestGetQuizSession:
    def test_get_existing_session(self, client, test_document):
        q = _make_question(test_document.id)
        with patch("app.routers.quiz.generate_questions", new=AsyncMock(return_value=[q])):
            created = client.post(
                "/api/v1/quiz/sessions", json=_quiz_body(str(test_document.id))
            ).json()

        session_id = created["session"]["id"]
        resp = client.get(f"/api/v1/quiz/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session"]["id"] == session_id
        assert "questions" in data
        assert "answers" in data

    def test_completed_session_shows_correct_answers(self, client, db, test_document):
        """After submitting, GET should include correct_answer in questions."""
        q = _make_question(test_document.id)
        db.add(q)
        db.commit()

        with patch("app.routers.quiz.generate_questions", new=AsyncMock(return_value=[q])):
            created = client.post("/api/v1/quiz/sessions", json=_quiz_body(str(test_document.id))).json()

        session_id = created["session"]["id"]
        question_id = created["questions"][0]["id"]

        client.post(f"/api/v1/quiz/sessions/{session_id}/submit", json={
            "answers": [{"question_id": question_id, "answer": "9.8"}]
        })

        resp = client.get(f"/api/v1/quiz/sessions/{session_id}")
        questions = resp.json()["questions"]
        assert len(questions) == 1
        assert "correct_answer" in questions[0]

    def test_get_nonexistent_session_404(self, client):
        resp = client.get(f"/api/v1/quiz/sessions/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestSubmitQuiz:
    def test_submit_scores_correctly(self, client, db, test_document, mock_vectorstore):
        q = _make_question(test_document.id)
        db.add(q)
        db.commit()

        with patch("app.routers.quiz.generate_questions", new=AsyncMock(return_value=[q])):
            created = client.post(
                "/api/v1/quiz/sessions", json=_quiz_body(str(test_document.id))
            ).json()

        session_id = created["session"]["id"]
        question_id = created["questions"][0]["id"]

        resp = client.post(f"/api/v1/quiz/sessions/{session_id}/submit", json={
            "answers": [{"question_id": question_id, "answer": "9.8"}]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_score"] == 100
        assert data["results"][0]["is_correct"] is True

    def test_submit_incorrect_answer(self, client, db, test_document):
        q = _make_question(test_document.id)
        db.add(q)
        db.commit()

        with patch("app.routers.quiz.generate_questions", new=AsyncMock(return_value=[q])):
            created = client.post(
                "/api/v1/quiz/sessions", json=_quiz_body(str(test_document.id))
            ).json()

        session_id = created["session"]["id"]
        question_id = created["questions"][0]["id"]

        resp = client.post(f"/api/v1/quiz/sessions/{session_id}/submit", json={
            "answers": [{"question_id": question_id, "answer": "10.0"}]  # wrong
        })
        assert resp.status_code == 200
        assert resp.json()["results"][0]["is_correct"] is False

    def test_double_submit_returns_400(self, client, db, test_document):
        q = _make_question(test_document.id)
        db.add(q)
        db.commit()

        with patch("app.routers.quiz.generate_questions", new=AsyncMock(return_value=[q])):
            created = client.post(
                "/api/v1/quiz/sessions", json=_quiz_body(str(test_document.id))
            ).json()

        session_id = created["session"]["id"]
        question_id = created["questions"][0]["id"]
        answers = {"answers": [{"question_id": question_id, "answer": "9.8"}]}

        client.post(f"/api/v1/quiz/sessions/{session_id}/submit", json=answers)
        resp = client.post(f"/api/v1/quiz/sessions/{session_id}/submit", json=answers)
        assert resp.status_code == 400


class TestFlagQuestion:
    def test_flag_returns_204(self, client, test_document, db):
        q = _make_question(test_document.id)
        db.add(q)
        db.commit()

        resp = client.post(f"/api/v1/quiz/questions/{q.id}/flag")
        assert resp.status_code == 204

    def test_flag_nonexistent_question_404(self, client):
        resp = client.post(f"/api/v1/quiz/questions/{uuid.uuid4()}/flag")
        assert resp.status_code == 404
