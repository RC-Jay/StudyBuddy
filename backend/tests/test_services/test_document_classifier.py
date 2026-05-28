"""
Tests for document_classifier.classify_document.

All LLM calls are mocked — no live API calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.documents import Document as LCDocument

from app.enums import DocType
from app.services.document_classifier import classify_document


def _pages(text: str = "sample text") -> list[LCDocument]:
    return [LCDocument(page_content=text)]


def _provider(response: str) -> MagicMock:
    p = MagicMock()
    p.complete = AsyncMock(return_value=response)
    return p


# ─── Accepted documents ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_academic_book_accepted():
    result = await classify_document(_pages(), _provider('{"type": "book", "academic": true}'))
    assert result == DocType.BOOK


@pytest.mark.asyncio
async def test_research_paper_accepted():
    result = await classify_document(_pages(), _provider('{"type": "research_paper"}'))
    assert result == DocType.RESEARCH_PAPER


@pytest.mark.asyncio
async def test_research_paper_no_academic_flag():
    """research_paper responses have no 'academic' key — should still be accepted."""
    result = await classify_document(_pages(), _provider('{"type": "research_paper"}'))
    assert result == DocType.RESEARCH_PAPER


# ─── Rejected documents ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_academic_book_rejected():
    with pytest.raises(ValueError, match="does not appear to be academic"):
        await classify_document(_pages(), _provider('{"type": "book", "academic": false}'))


@pytest.mark.asyncio
async def test_other_document_rejected():
    with pytest.raises(ValueError, match="does not appear to be a book or research paper"):
        await classify_document(_pages(), _provider('{"type": "other"}'))


@pytest.mark.asyncio
async def test_fiction_novel_rejected():
    """Explicit fiction label should be rejected."""
    with pytest.raises(ValueError, match="does not appear to be academic"):
        await classify_document(_pages(), _provider('{"type": "book", "academic": false}'))


# ─── Error handling ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_json_falls_back_to_other():
    """Unparseable response should fall back gracefully and reject."""
    with pytest.raises(ValueError):
        await classify_document(_pages(), _provider("I don't know what this is"))


@pytest.mark.asyncio
async def test_malformed_json_with_research_paper_hint():
    """Raw text mentioning research paper should be accepted as fallback."""
    result = await classify_document(_pages(), _provider("this looks like a research_paper to me"))
    assert result == DocType.RESEARCH_PAPER


@pytest.mark.asyncio
async def test_malformed_json_with_book_hint():
    """Raw text mentioning book (without 'false') should accept as BOOK."""
    result = await classify_document(_pages(), _provider("this is a book"))
    assert result == DocType.BOOK


@pytest.mark.asyncio
async def test_malformed_json_book_with_false_hint():
    """Raw text mentioning book with 'false' should reject."""
    with pytest.raises(ValueError):
        await classify_document(_pages(), _provider('this is a book but academic is false'))


@pytest.mark.asyncio
async def test_empty_response_rejected():
    with pytest.raises(ValueError):
        await classify_document(_pages(), _provider(""))


@pytest.mark.asyncio
async def test_truncates_long_input():
    """Long documents should not crash — the 8000-char truncation is exercised."""
    long_text = "word " * 5000  # ~25 000 chars
    result = await classify_document(_pages(long_text), _provider('{"type": "research_paper"}'))
    assert result == DocType.RESEARCH_PAPER
