"""
LLM-based document type classifier.

Classifies documents as BOOK or RESEARCH_PAPER using the first 10 pages of
extracted text. Raises ValueError for anything else so the processor can mark
the document as FAILED with a user-readable message.

Only two document types are accepted:
  - book          → a full-length book (monograph, textbook, etc.)
  - research_paper → a journal article, conference paper, thesis, technical report

Anything else (invoices, presentations, manuals, etc.) is rejected.
"""
import json
import logging

from langchain_core.documents import Document as LCDocument

from app.enums import DocType
from app.services.llm.base import BaseChatProvider

logger = logging.getLogger(__name__)

_PAGES_FOR_CLASSIFICATION = 10

_SYSTEM_PROMPT = """\
You are a document type classifier. Your task is to determine whether a document \
is a book or a research paper based on the provided text.

A BOOK is a full-length work intended for extended reading — monographs, textbooks, \
non-fiction books, technical books, etc. Books typically have a table of contents, \
chapters, and are many pages long.

A RESEARCH PAPER is a journal article, conference paper, thesis, dissertation, or \
technical report. Research papers typically have an abstract, introduction, methodology, \
results, and references sections.

Respond ONLY with a JSON object in this exact format (no other text):
{"type": "book"} or {"type": "research_paper"} or {"type": "other"}

Use "other" if the document is clearly neither of the above (e.g. invoice, form, \
presentation, user manual without substantial content, etc.).
"""


async def classify_document(
    pages: list[LCDocument],
    provider: BaseChatProvider,
) -> DocType:
    """
    Classify a document as BOOK or RESEARCH_PAPER.

    Uses the first _PAGES_FOR_CLASSIFICATION pages of extracted text.
    Raises ValueError with a user-readable message if the document is neither.
    """
    sample_pages = pages[:_PAGES_FOR_CLASSIFICATION]
    sample_text = "\n\n---\n\n".join(p.page_content for p in sample_pages)

    # Truncate to ~8000 chars to stay well within token limits
    if len(sample_text) > 8000:
        sample_text = sample_text[:8000]

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Classify this document:\n\n{sample_text}"},
    ]

    try:
        response = await provider.complete(messages, temperature=0.0)
        result = json.loads(response.strip())
        doc_type_str = result.get("type", "other")
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Classifier returned unparseable response: %s", exc)
        # Attempt to extract type from raw text as fallback
        raw = response.strip().lower() if "response" in dir() else ""
        if "book" in raw and "research" not in raw:
            doc_type_str = "book"
        elif "research_paper" in raw or "research paper" in raw:
            doc_type_str = "research_paper"
        else:
            doc_type_str = "other"

    if doc_type_str == "book":
        return DocType.BOOK
    if doc_type_str == "research_paper":
        return DocType.RESEARCH_PAPER

    raise ValueError(
        "This document does not appear to be a book or research paper. "
        "Only books and research papers are supported. Please upload a "
        "textbook, academic book, journal article, conference paper, or thesis."
    )
