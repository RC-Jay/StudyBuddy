"""
Tests for app.enums

Verifies that every enum:
  - Has the expected string values
  - Compares equal to its plain string value (str-enum contract)
  - Serialises to a plain string (not wrapped in an enum container)
"""
import json

import pytest

from app.enums import (
    Difficulty,
    MessageRole,
    ProcessingStatus,
    QuizFormat,
    QuizMode,
    ScopeType,
    StorageBackend,
    SummaryGranularity,
)


# ---------------------------------------------------------------------------
# ScopeType
# ---------------------------------------------------------------------------

class TestScopeType:
    def test_values(self):
        assert ScopeType.DOCUMENT == "document"
        assert ScopeType.COLLECTION == "collection"

    def test_str_equality(self):
        assert ScopeType.DOCUMENT == "document"

    def test_serialises_as_string(self):
        data = json.dumps({"scope": ScopeType.DOCUMENT})
        assert json.loads(data)["scope"] == "document"


# ---------------------------------------------------------------------------
# ProcessingStatus
# ---------------------------------------------------------------------------

class TestProcessingStatus:
    def test_values(self):
        assert ProcessingStatus.PENDING == "pending"
        assert ProcessingStatus.PROCESSING == "processing"
        assert ProcessingStatus.READY == "ready"
        assert ProcessingStatus.FAILED == "failed"

    def test_all_members(self):
        assert len(ProcessingStatus) == 4


# ---------------------------------------------------------------------------
# QuizFormat
# ---------------------------------------------------------------------------

class TestQuizFormat:
    def test_values(self):
        assert QuizFormat.MCQ == "mcq"
        assert QuizFormat.SHORT_ANSWER == "short_answer"
        assert QuizFormat.TRUE_FALSE == "true_false"


# ---------------------------------------------------------------------------
# QuizMode
# ---------------------------------------------------------------------------

class TestQuizMode:
    def test_values(self):
        assert QuizMode.PRACTICE == "practice"
        assert QuizMode.EXAM == "exam"


# ---------------------------------------------------------------------------
# Difficulty
# ---------------------------------------------------------------------------

class TestDifficulty:
    def test_values(self):
        assert Difficulty.INTRODUCTORY == "introductory"
        assert Difficulty.INTERMEDIATE == "intermediate"
        assert Difficulty.ADVANCED == "advanced"


# ---------------------------------------------------------------------------
# SummaryGranularity
# ---------------------------------------------------------------------------

class TestSummaryGranularity:
    def test_values(self):
        assert SummaryGranularity.FULL == "full"
        assert SummaryGranularity.TLDR == "tldr"
        assert SummaryGranularity.CONCEPTS == "concepts"
        assert SummaryGranularity.SECTION == "section"


# ---------------------------------------------------------------------------
# MessageRole
# ---------------------------------------------------------------------------

class TestMessageRole:
    def test_values(self):
        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"


# ---------------------------------------------------------------------------
# StorageBackend
# ---------------------------------------------------------------------------

class TestStorageBackend:
    def test_values(self):
        assert StorageBackend.LOCAL == "local"
        assert StorageBackend.AZURE == "azure"

    def test_str_enum_lookup(self):
        assert StorageBackend("local") is StorageBackend.LOCAL
        assert StorageBackend("azure") is StorageBackend.AZURE

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            StorageBackend("s3")
