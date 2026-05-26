"""
Tests for app.schemas.*

Validates that Pydantic schemas:
  - Accept valid input and produce the expected fields
  - Reject invalid enum values with a ValidationError
  - Enforce required-field rules
"""
import pytest
from pydantic import ValidationError

from app.schemas.chat import MessageIn, SessionCreate
from app.schemas.collection import CollectionIn
from app.schemas.quiz import AnswerSubmit, QuizCreate
from app.schemas.summary import SummaryRequest


# ---------------------------------------------------------------------------
# Chat schemas
# ---------------------------------------------------------------------------

class TestSessionCreate:
    def test_valid_document_scope(self):
        s = SessionCreate(scope_type="document", scope_id="abc-123")
        assert s.scope_type == "document"
        assert s.scope_id == "abc-123"
        assert s.title is None

    def test_valid_collection_scope_with_title(self):
        s = SessionCreate(scope_type="collection", scope_id="col-1", title="My Session")
        assert s.title == "My Session"

    def test_invalid_scope_type(self):
        with pytest.raises(ValidationError):
            SessionCreate(scope_type="invalid", scope_id="abc")


class TestMessageIn:
    def test_valid(self):
        m = MessageIn(content="Hello!")
        assert m.content == "Hello!"

    def test_missing_content(self):
        with pytest.raises(ValidationError):
            MessageIn()


# ---------------------------------------------------------------------------
# Collection schemas
# ---------------------------------------------------------------------------

class TestCollectionIn:
    def test_valid(self):
        c = CollectionIn(name="My Collection")
        assert c.name == "My Collection"

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            CollectionIn()


# ---------------------------------------------------------------------------
# Quiz schemas
# ---------------------------------------------------------------------------

class TestQuizCreate:
    def test_valid_defaults(self):
        q = QuizCreate(
            mode="exam",
            scope_type="document",
            scope_id="doc-1",
            format="mcq",
        )
        assert q.difficulty == "intermediate"
        assert q.question_count == 10
        assert q.topic_focus is None
        assert q.time_limit_seconds is None

    def test_valid_full(self):
        q = QuizCreate(
            mode="practice",
            scope_type="collection",
            scope_id="col-1",
            format="short_answer",
            difficulty="advanced",
            question_count=5,
            topic_focus="Newton's laws",
            time_limit_seconds=600,
        )
        assert q.format == "short_answer"
        assert q.difficulty == "advanced"
        assert q.question_count == 5

    def test_invalid_format(self):
        with pytest.raises(ValidationError):
            QuizCreate(
                mode="exam",
                scope_type="document",
                scope_id="x",
                format="essay",   # not in QuizFormat
            )

    def test_invalid_difficulty(self):
        with pytest.raises(ValidationError):
            QuizCreate(
                mode="exam",
                scope_type="document",
                scope_id="x",
                format="mcq",
                difficulty="expert",  # not in Difficulty
            )


class TestAnswerSubmit:
    def test_valid(self):
        a = AnswerSubmit(answers=[{"question_id": "q1", "answer": "A"}])
        assert len(a.answers) == 1

    def test_empty_answers(self):
        a = AnswerSubmit(answers=[])
        assert a.answers == []


# ---------------------------------------------------------------------------
# Summary schemas
# ---------------------------------------------------------------------------

class TestSummaryRequest:
    def test_valid_full_granularity(self):
        r = SummaryRequest(scope_type="document", scope_id="d1", granularity="full")
        assert r.granularity == "full"
        assert r.section_hint is None

    def test_valid_section_with_hint(self):
        r = SummaryRequest(
            scope_type="collection",
            scope_id="c1",
            granularity="section",
            section_hint="Chapter 3: Thermodynamics",
        )
        assert r.section_hint == "Chapter 3: Thermodynamics"

    def test_invalid_granularity(self):
        with pytest.raises(ValidationError):
            SummaryRequest(scope_type="document", scope_id="d1", granularity="bullet_points")
