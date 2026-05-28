"""
Application-wide enumerations.

All discriminated string fields use str-enums so they:
  - Serialize to plain strings in JSON (no wrapping)
  - Compare equal to their string values  (e.g. status == "ready")
  - Are validated by Pydantic automatically in request bodies
  - Can be stored as strings in existing VARCHAR columns — no migration needed
"""
from enum import Enum


class ScopeType(str, Enum):
    DOCUMENT = "document"
    COLLECTION = "collection"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUMMARISING = "summarising"  # embeddings done, summaries being auto-generated
    READY = "ready"
    FAILED = "failed"


class QuizFormat(str, Enum):
    MCQ = "mcq"
    SHORT_ANSWER = "short_answer"
    TRUE_FALSE = "true_false"


class QuizMode(str, Enum):
    PRACTICE = "practice"
    EXAM = "exam"


class Difficulty(str, Enum):
    INTRODUCTORY = "introductory"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class DocType(str, Enum):
    BOOK = "book"
    RESEARCH_PAPER = "research_paper"
    VIDEO = "video"


class SummaryGranularity(str, Enum):
    FULL = "full"
    TLDR = "tldr"
    CONCEPTS = "concepts"
    SECTION = "section"
    CHAPTER = "chapter"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class StorageBackend(str, Enum):
    LOCAL = "local"
    AZURE = "azure"
