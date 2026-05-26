"""
Tests for app.services.quiz_engine

Covers:
  - generate_questions() serves from bank when enough questions exist
  - generate_questions() calls LLM and adds to bank when not enough
  - generate_questions() handles malformed JSON gracefully
  - generate_questions() returns existing questions when no chunks found
  - evaluate_short_answer() parses LLM JSON response
  - evaluate_short_answer() handles malformed JSON gracefully

All LLM calls are replaced by MockChatProvider from conftest.
Vectorstore similarity_search is mocked via make_mock_vectorstore.
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.quiz import Question
from app.services.quiz_engine import evaluate_short_answer, generate_questions
from tests.conftest import MockChatProvider, make_mock_vectorstore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_question(scope_type="document", scope_id=None, fmt="mcq", difficulty="intermediate") -> Question:
    return Question(
        id=uuid.uuid4(),
        scope_type=scope_type,
        scope_id=scope_id or uuid.uuid4(),
        format=fmt,
        difficulty=difficulty,
        topic_tags=[],
        stem="What is the speed of light?",
        options=["3e8 m/s", "3e6 m/s", "3e10 m/s", "3e4 m/s"],
        correct_answer="3e8 m/s",
        explanation="Einstein, p.12",
        source_page_range="12",
    )


def _make_quiz_repo(existing: list[Question], db=None):
    repo = MagicMock()
    repo.get_bank_questions.return_value = existing
    repo.bulk_add_questions.return_value = None
    repo.db = db or MagicMock()
    return repo


def _llm_json_response(questions: list[dict]) -> str:
    return json.dumps(questions)


# ---------------------------------------------------------------------------
# generate_questions
# ---------------------------------------------------------------------------

class TestGenerateQuestionsFromBank:
    async def test_serves_from_bank_when_enough(self):
        """If the bank has >= count questions, LLM must not be called."""
        existing = [_make_question() for _ in range(5)]
        repo = _make_quiz_repo(existing)

        with patch("app.services.quiz_engine.get_chat_provider") as mock_provider_factory:
            result = await generate_questions(
                repo, uuid.uuid4(), "document", uuid.uuid4(),
                "mcq", "intermediate", 5, None,
            )

        mock_provider_factory.assert_not_called()
        assert result == existing


class TestGenerateQuestionsFromLLM:
    async def test_calls_llm_when_bank_insufficient(self):
        """When the bank has fewer questions than needed, LLM generates the rest."""
        existing = [_make_question()]
        repo = _make_quiz_repo(existing)

        generated_items = [
            {
                "format": "mcq",
                "stem": "What is gravity?",
                "options": ["9.8 m/s²", "9.0 m/s²", "10 m/s²", "8 m/s²"],
                "correct_answer": "9.8 m/s²",
                "explanation": "Newton, p.5",
                "topic_tags": ["gravity"],
                "source_page_range": "5",
            }
        ]
        mock_provider = MockChatProvider(response=_llm_json_response(generated_items))

        vs = make_mock_vectorstore([
            {"content": "Gravity is 9.8 m/s²", "metadata": {"document_title": "Newton", "page": 5}}
        ])

        with patch("app.services.quiz_engine.get_chat_provider", return_value=mock_provider):
            with patch("app.services.quiz_engine.retrieve", return_value=[
                MagicMock(document_title="Newton", page_number=5, content="Gravity is 9.8 m/s²", score=0.9)
            ]):
                result = await generate_questions(
                    repo, uuid.uuid4(), "document", uuid.uuid4(),
                    "mcq", "intermediate", 2, None,
                )

        assert len(result) == 2  # 1 from bank + 1 generated
        repo.bulk_add_questions.assert_called_once()

    async def test_returns_existing_when_no_chunks(self):
        """If no chunks are retrieved (no content), return only existing bank questions."""
        existing = [_make_question()]
        repo = _make_quiz_repo(existing)

        with patch("app.services.quiz_engine.retrieve", return_value=[]):
            with patch("app.services.quiz_engine.get_chat_provider") as mock_pf:
                result = await generate_questions(
                    repo, uuid.uuid4(), "document", uuid.uuid4(),
                    "mcq", "intermediate", 5, None,
                )

        mock_pf.assert_not_called()
        assert result == existing

    async def test_handles_malformed_json_gracefully(self):
        """LLM returning invalid JSON should not crash — return only existing questions."""
        existing = [_make_question()]
        repo = _make_quiz_repo(existing)
        mock_provider = MockChatProvider(response="not json at all {{")

        with patch("app.services.quiz_engine.get_chat_provider", return_value=mock_provider):
            with patch("app.services.quiz_engine.retrieve", return_value=[
                MagicMock(document_title="Doc", page_number=1, content="Some content", score=0.9)
            ]):
                result = await generate_questions(
                    repo, uuid.uuid4(), "document", uuid.uuid4(),
                    "mcq", "intermediate", 3, None,
                )

        assert result == existing
        repo.bulk_add_questions.assert_not_called()

    async def test_handles_code_fenced_json(self):
        """LLM sometimes wraps JSON in ```json ... ``` — should be stripped."""
        repo = _make_quiz_repo([])
        generated_item = {
            "format": "true_false",
            "stem": "The Earth is round.",
            "options": None,
            "correct_answer": "true",
            "explanation": "Geography, p.1",
            "topic_tags": [],
            "source_page_range": "1",
        }
        fenced = f"```json\n{json.dumps([generated_item])}\n```"
        mock_provider = MockChatProvider(response=fenced)

        with patch("app.services.quiz_engine.get_chat_provider", return_value=mock_provider):
            with patch("app.services.quiz_engine.retrieve", return_value=[
                MagicMock(document_title="Geo", page_number=1, content="Earth", score=0.9)
            ]):
                result = await generate_questions(
                    repo, uuid.uuid4(), "document", uuid.uuid4(),
                    "true_false", "introductory", 1, None,
                )

        assert len(result) == 1
        assert result[0].stem == "The Earth is round."


# ---------------------------------------------------------------------------
# evaluate_short_answer
# ---------------------------------------------------------------------------

class TestEvaluateShortAnswer:
    async def test_parses_valid_json_response(self):
        q = _make_question(fmt="short_answer")
        eval_json = {
            "is_correct": True,
            "score": 85,
            "feedback": "Good explanation citing page 3.",
            "correct_answer_summary": "Light travels at 3×10⁸ m/s.",
        }
        mock_provider = MockChatProvider(response=json.dumps(eval_json))

        with patch("app.services.quiz_engine.get_chat_provider", return_value=mock_provider):
            result = await evaluate_short_answer(q, "approx 3e8 m/s", "context text")

        assert result["is_correct"] is True
        assert result["score"] == 85
        assert "feedback" in result

    async def test_handles_malformed_json(self):
        """If LLM returns garbage, fall back to a safe default dict."""
        q = _make_question(fmt="short_answer")
        mock_provider = MockChatProvider(response="Sorry, I can't evaluate that.")

        with patch("app.services.quiz_engine.get_chat_provider", return_value=mock_provider):
            result = await evaluate_short_answer(q, "some answer", "context")

        assert result["is_correct"] is False
        assert result["score"] == 0
        assert result["correct_answer_summary"] == q.correct_answer

    async def test_handles_code_fenced_response(self):
        q = _make_question(fmt="short_answer")
        eval_json = {"is_correct": False, "score": 40, "feedback": "Partially correct.", "correct_answer_summary": "3e8"}
        fenced = f"```json\n{json.dumps(eval_json)}\n```"
        mock_provider = MockChatProvider(response=fenced)

        with patch("app.services.quiz_engine.get_chat_provider", return_value=mock_provider):
            result = await evaluate_short_answer(q, "wrong answer", "context")

        assert result["score"] == 40
