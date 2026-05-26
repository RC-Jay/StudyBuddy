"""
Tests for app.services.rag

Covers:
  - retrieve() with document scope — passes correct filter to vectorstore
  - retrieve() with collection scope — builds doc-id list from DB
  - retrieve() with empty collection returns []
  - retrieve() uses injected vectorstore (no singleton call)
  - build_context() formats chunks correctly
  - build_citations() deduplicates correctly
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document as LCDocument

from app.services.rag import RetrievedChunk, build_citations, build_context, retrieve


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(title: str, page: int | None, content: str, score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(document_title=title, page_number=page, content=content, score=score)


def _make_vs(docs_and_scores: list) -> MagicMock:
    vs = MagicMock()
    vs.similarity_search_with_score.return_value = docs_and_scores
    return vs


def _make_lc_doc(content: str, title: str = "Doc", page: int | None = 1) -> LCDocument:
    return LCDocument(
        page_content=content,
        metadata={"document_title": title, "page": page},
    )


# ---------------------------------------------------------------------------
# retrieve()
# ---------------------------------------------------------------------------

class TestRetrieve:
    async def test_document_scope_passes_correct_filter(self, db):
        doc_id = uuid.uuid4()
        lc_doc = _make_lc_doc("content", "My Doc", 3)
        vs = _make_vs([(lc_doc, 0.85)])

        chunks = await retrieve(db, "query", "document", doc_id, top_k=5, vectorstore=vs)

        vs.similarity_search_with_score.assert_called_once_with(
            "query", k=5, filter={"document_id": str(doc_id)}
        )
        assert len(chunks) == 1
        assert chunks[0].document_title == "My Doc"
        assert chunks[0].page_number == 3
        assert chunks[0].content == "content"
        assert abs(chunks[0].score - 0.85) < 1e-9

    async def test_collection_scope_builds_doc_id_filter(self, db, test_collection, test_document):
        """Collection scope should join CollectionDocument to build filter."""
        from app.models.collection import CollectionDocument
        link = CollectionDocument(
            collection_id=test_collection.id, document_id=test_document.id
        )
        db.add(link)
        db.flush()

        lc_doc = _make_lc_doc("chunk text", "Test Document", 2)
        vs = _make_vs([(lc_doc, 0.9)])

        chunks = await retrieve(
            db, "query", "collection", test_collection.id, top_k=3, vectorstore=vs
        )

        call_kwargs = vs.similarity_search_with_score.call_args
        filter_arg = call_kwargs.kwargs.get("filter") or call_kwargs.args[2]
        assert str(test_document.id) in filter_arg["document_id"]["$in"]
        assert len(chunks) == 1

    async def test_empty_collection_returns_empty_list(self, db, test_collection):
        """Collection with no documents should return [] without calling vectorstore."""
        vs = _make_vs([])
        chunks = await retrieve(
            db, "query", "collection", test_collection.id, vectorstore=vs
        )
        assert chunks == []
        vs.similarity_search_with_score.assert_not_called()

    async def test_no_results_returns_empty_list(self, db):
        vs = _make_vs([])
        doc_id = uuid.uuid4()
        chunks = await retrieve(db, "query", "document", doc_id, vectorstore=vs)
        assert chunks == []

    async def test_uses_injected_vectorstore_not_singleton(self, db):
        """retrieve() must NOT call get_vectorstore() when a vectorstore is injected."""
        doc_id = uuid.uuid4()
        vs = _make_vs([])

        with patch("app.services.rag.get_vectorstore") as mock_singleton:
            await retrieve(db, "query", "document", doc_id, vectorstore=vs)
            mock_singleton.assert_not_called()

    async def test_falls_back_to_singleton_when_no_vectorstore(self, db):
        doc_id = uuid.uuid4()
        vs = _make_vs([])
        with patch("app.services.rag.get_vectorstore", return_value=vs):
            await retrieve(db, "query", "document", doc_id)  # no vectorstore kwarg
            vs.similarity_search_with_score.assert_called_once()


# ---------------------------------------------------------------------------
# build_context()
# ---------------------------------------------------------------------------

class TestBuildContext:
    def test_single_chunk_with_page(self):
        chunks = [_make_chunk("Physics Notes", 5, "F = ma")]
        ctx = build_context(chunks)
        assert '"Physics Notes", p.5' in ctx
        assert "F = ma" in ctx

    def test_single_chunk_without_page(self):
        chunks = [_make_chunk("Lecture Slides", None, "Newton's first law")]
        ctx = build_context(chunks)
        assert '"Lecture Slides"' in ctx
        assert "p." not in ctx

    def test_multiple_chunks_separated_by_divider(self):
        chunks = [
            _make_chunk("Doc A", 1, "Chunk one"),
            _make_chunk("Doc B", 2, "Chunk two"),
        ]
        ctx = build_context(chunks)
        assert "---" in ctx
        assert "Chunk one" in ctx
        assert "Chunk two" in ctx

    def test_empty_chunks_returns_empty_string(self):
        assert build_context([]) == ""


# ---------------------------------------------------------------------------
# build_citations()
# ---------------------------------------------------------------------------

class TestBuildCitations:
    def test_deduplicates_same_doc_and_page(self):
        chunks = [
            _make_chunk("Doc A", 3, "alpha"),
            _make_chunk("Doc A", 3, "beta"),   # duplicate
            _make_chunk("Doc A", 4, "gamma"),
        ]
        citations = build_citations(chunks)
        assert len(citations) == 2
        pages = [c["page"] for c in citations]
        assert 3 in pages and 4 in pages

    def test_empty_chunks_returns_empty_list(self):
        assert build_citations([]) == []

    def test_citation_structure(self):
        chunks = [_make_chunk("My Paper", 7, "content")]
        citations = build_citations(chunks)
        assert citations == [{"document": "My Paper", "page": 7}]
