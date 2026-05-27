"""
Document loading strategies using LangChain loaders.

Architecture — Strategy Pattern:
  BaseDocumentLoader   abstract strategy interface
  PDFLoader            concrete strategy for .pdf  (pymupdf4llm)
  DocxLoader           concrete strategy for .docx (langchain-community)

  _REGISTRY            maps file_type string → strategy instance
  get_loader()         looks up the right strategy by file type
  register_loader()    registers a new strategy — adding a new file type
                       is one subclass + one register_loader() call, nothing else changes

Adding a new file type (e.g. .txt, .html, .pptx):
  1. Create a subclass of BaseDocumentLoader
  2. Call register_loader("ext", MyLoader()) at module level
  That's it — document_processor.py requires zero changes.
"""
from abc import ABC, abstractmethod

from langchain_core.documents import Document as LCDocument


class BaseDocumentLoader(ABC):
    """Strategy interface. Each concrete loader wraps a LangChain document loader."""

    @abstractmethod
    def load(self, file_path: str) -> list[LCDocument]:
        """
        Load a file and return a list of LangChain Documents.
        Each Document should carry at minimum:
          - page_content : the extracted text
          - metadata["page"] : 1-indexed page / logical-page number
          - metadata["source"] : the file path
        """
        ...


class PDFLoader(BaseDocumentLoader):
    """
    PDF loader using LangChain's PyMuPDFLoader (pymupdf).
    Returns one Document per page with metadata["page"] as 0-indexed page number.
    Handles complex layouts (tables, columns, multi-column papers) well.
    """

    def load(self, file_path: str) -> list[LCDocument]:
        from langchain_community.document_loaders import PyMuPDFLoader
        return PyMuPDFLoader(file_path).load()


class DocxLoader(BaseDocumentLoader):
    """
    DOCX loader using LangChain's Docx2txtLoader (langchain-community).
    Returns the document as a single LangChain Document — the splitter
    downstream handles chunking.
    """

    def load(self, file_path: str) -> list[LCDocument]:
        from langchain_community.document_loaders import Docx2txtLoader
        return Docx2txtLoader(file_path).load()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, BaseDocumentLoader] = {
    "pdf":  PDFLoader(),
    "docx": DocxLoader(),
}


def get_loader(file_type: str) -> BaseDocumentLoader:
    """Return the loader strategy for the given file extension."""
    loader = _REGISTRY.get(file_type.lower())
    if not loader:
        supported = list(_REGISTRY.keys())
        raise ValueError(
            f"No loader registered for file type '{file_type}'. "
            f"Supported types: {supported}"
        )
    return loader


def register_loader(file_type: str, loader: BaseDocumentLoader) -> None:
    """
    Register a custom loader strategy for a new file type.
    Existing registrations can be overridden by passing the same file_type.
    """
    _REGISTRY[file_type.lower()] = loader
