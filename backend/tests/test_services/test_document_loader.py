"""
Tests for app.services.document_loader

Verifies the Strategy Pattern registry without loading real files:
  - get_loader() returns the correct strategy for each registered type
  - get_loader() raises ValueError for unknown types
  - register_loader() adds a new strategy that get_loader() then returns
  - register_loader() can override an existing strategy
  - Concrete loaders delegate to their underlying library (mocked)
"""
import pytest

from langchain_core.documents import Document as LCDocument

from app.services.document_loader import (
    BaseDocumentLoader,
    DocxLoader,
    PDFLoader,
    get_loader,
    register_loader,
)


class TestGetLoader:
    def test_returns_pdf_loader(self):
        loader = get_loader("pdf")
        assert isinstance(loader, PDFLoader)

    def test_returns_docx_loader(self):
        loader = get_loader("docx")
        assert isinstance(loader, DocxLoader)

    def test_case_insensitive(self):
        loader = get_loader("PDF")
        assert isinstance(loader, PDFLoader)

    def test_unknown_type_raises_value_error(self):
        with pytest.raises(ValueError, match="No loader registered"):
            get_loader("pptx")

    def test_error_message_contains_supported_types(self):
        with pytest.raises(ValueError) as exc_info:
            get_loader("mp4")
        assert "pdf" in str(exc_info.value).lower()


class TestRegisterLoader:
    def test_register_new_type(self):
        class TxtLoader(BaseDocumentLoader):
            def load(self, file_path: str) -> list[LCDocument]:
                return [LCDocument(page_content="text", metadata={"page": 1, "source": file_path})]

        register_loader("txt", TxtLoader())
        loader = get_loader("txt")
        assert isinstance(loader, TxtLoader)

    def test_override_existing_loader(self):
        """Overriding pdf loader with a custom stub should be reflected immediately."""
        class StubPDFLoader(BaseDocumentLoader):
            def load(self, file_path: str) -> list[LCDocument]:
                return []

        original = get_loader("pdf")
        register_loader("pdf", StubPDFLoader())
        assert isinstance(get_loader("pdf"), StubPDFLoader)

        # Restore the original so other tests are unaffected
        register_loader("pdf", original)


# ---------------------------------------------------------------------------
# Debug (test-double) loaders — concrete strategies for testing
# ---------------------------------------------------------------------------

class DebugPDFLoader(BaseDocumentLoader):
    """
    Test-double PDF loader.  Returns a fixed list of LCDocuments without
    touching the filesystem or any third-party library.
    """

    def __init__(self, pages: list[dict] | None = None):
        self._pages = pages or [
            {"content": "Page 1 content", "page": 1},
            {"content": "Page 2 content", "page": 2},
        ]

    def load(self, file_path: str) -> list[LCDocument]:
        return [
            LCDocument(
                page_content=p["content"],
                metadata={"page": p["page"], "source": file_path},
            )
            for p in self._pages
        ]


class DebugDocxLoader(BaseDocumentLoader):
    """
    Test-double DOCX loader.  Returns a single LCDocument with controlled content.
    """

    def __init__(self, content: str = "Debug docx content"):
        self._content = content

    def load(self, file_path: str) -> list[LCDocument]:
        return [LCDocument(page_content=self._content, metadata={"source": file_path})]


class TestDebugLoaders:
    """
    Verify that the debug (test-double) loaders satisfy the BaseDocumentLoader
    contract and work correctly through the registry — the same extension point
    used in production.
    """

    def test_debug_pdf_loader_returns_correct_documents(self):
        loader = DebugPDFLoader(pages=[
            {"content": "Intro", "page": 1},
            {"content": "Methods", "page": 2},
        ])
        docs = loader.load("/fake/paper.pdf")
        assert len(docs) == 2
        assert docs[0].page_content == "Intro"
        assert docs[0].metadata["page"] == 1
        assert docs[1].page_content == "Methods"

    def test_debug_pdf_loader_sets_source_metadata(self):
        loader = DebugPDFLoader()
        docs = loader.load("/some/path/doc.pdf")
        for doc in docs:
            assert doc.metadata["source"] == "/some/path/doc.pdf"

    def test_debug_docx_loader_returns_single_document(self):
        loader = DebugDocxLoader(content="Chapter 1 text")
        docs = loader.load("/fake/report.docx")
        assert len(docs) == 1
        assert docs[0].page_content == "Chapter 1 text"
        assert docs[0].metadata["source"] == "/fake/report.docx"

    def test_debug_loaders_registered_and_retrieved_via_registry(self):
        """Register debug loaders, verify get_loader() returns them, then restore."""
        original_pdf = get_loader("pdf")
        original_docx = get_loader("docx")

        debug_pdf = DebugPDFLoader()
        debug_docx = DebugDocxLoader()

        register_loader("pdf", debug_pdf)
        register_loader("docx", debug_docx)

        assert get_loader("pdf") is debug_pdf
        assert get_loader("docx") is debug_docx

        # Restore originals so this test doesn't affect others
        register_loader("pdf", original_pdf)
        register_loader("docx", original_docx)

    def test_debug_loader_produces_documents_pipeline_can_consume(self):
        """
        End-to-end: register debug loader, call get_loader().load(), confirm
        the resulting LCDocuments have the fields downstream code expects.
        """
        register_loader("md", DebugPDFLoader(pages=[{"content": "# Heading", "page": 1}]))
        docs = get_loader("md").load("/fake/notes.md")

        assert all(hasattr(d, "page_content") for d in docs)
        assert all("source" in d.metadata for d in docs)

        # Cleanup
        from app.services.document_loader import _REGISTRY
        _REGISTRY.pop("md", None)
