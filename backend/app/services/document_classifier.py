"""
LLM-based document type classifier.

Classifies documents as BOOK or RESEARCH_PAPER using the first 10 pages of
extracted text. Raises ValueError for anything else so the processor can mark
the document as FAILED with a user-readable message.

Accepted documents:
  - book (academic/technical) → textbook, technical reference, academic monograph,
                                 course material — anything a student would study
  - research_paper            → journal article, conference paper, thesis,
                                 dissertation, technical report

Rejected:
  - Non-academic books: fiction, novels, biographies, self-help, cookbooks,
    travel, comics, children's books, popular non-fiction, etc.
  - Anything that isn't a book or research paper: invoices, slide decks,
    forms, manuals without substantial content, etc.
"""
import json
import logging

from langchain_core.documents import Document as LCDocument

from app.enums import DocType
from app.services.llm.base import BaseChatProvider

logger = logging.getLogger(__name__)

_PAGES_FOR_CLASSIFICATION = 10

_SYSTEM_PROMPT = """\
You are a document classifier for an academic study tool. Determine the type \
and academic relevance of the provided document.

DOCUMENT TYPES:

book
  A full-length work with chapters — textbook, technical reference, academic \
monograph, or any book a student would use as course material. Covers any academic \
subject: STEM, medicine, law, economics, history, philosophy, social sciences, \
business, humanities, etc.

research_paper
  A journal article, conference paper, thesis, dissertation, or technical report. \
Typically has an abstract, introduction, methodology, results, and references.

other
  Anything that is not a book or research paper (invoice, form, slide deck, \
user manual, etc.).

ACADEMIC FLAG (books only):
Set "academic": true if the book is something a school or college student would \
genuinely use for studying — textbooks, course reading, technical/professional \
references, academic monographs.

Set "academic": false for books that are primarily for entertainment or general \
interest: fiction (novels, short stories, fantasy, sci-fi), popular non-fiction \
(biographies, memoirs, travel, self-help, wellness), comics, graphic novels, \
children's books, cookbooks, or any book not tied to an academic discipline.

When in doubt, lean towards "academic": true — a business management book, a \
popular-science book used in a course, or a coding tutorial book all count.

Respond ONLY with a JSON object (no other text):
  {"type": "book", "academic": true}
  {"type": "book", "academic": false}
  {"type": "research_paper"}
  {"type": "other"}
"""

# User-facing rejection messages
_MSG_NOT_ACADEMIC = (
    "This book does not appear to be academic or technical material. "
    "StudyBuddy only accepts textbooks, technical books, and academic references — "
    "not fiction, biographies, self-help, or other general-interest books."
)
_MSG_NOT_SUPPORTED = (
    "This document does not appear to be a book or research paper. "
    "Please upload a textbook, academic book, journal article, conference paper, or thesis."
)


async def classify_document(
    pages: list[LCDocument],
    provider: BaseChatProvider,
) -> DocType:
    """
    Classify a document as BOOK or RESEARCH_PAPER.

    Uses the first _PAGES_FOR_CLASSIFICATION pages of extracted text.
    Raises ValueError with a user-readable message if the document is:
      - not a book or research paper, or
      - a book that is not academic/technical material.
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

    response = ""
    try:
        response = await provider.complete(messages, temperature=0.0)
        result = json.loads(response.strip())
        doc_type_str = result.get("type", "other")
        is_academic = result.get("academic", True)  # research papers have no flag → default True
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Classifier returned unparseable response: %s — raw: %s", exc, response[:200])
        # Best-effort fallback: scan raw text
        raw = response.strip().lower()
        if "research_paper" in raw or "research paper" in raw:
            doc_type_str, is_academic = "research_paper", True
        elif "book" in raw:
            doc_type_str = "book"
            is_academic = "false" not in raw  # if "academic": false appears anywhere, reject
        else:
            doc_type_str, is_academic = "other", False

    logger.info("Document classified as type=%r academic=%r", doc_type_str, is_academic)

    if doc_type_str == "research_paper":
        return DocType.RESEARCH_PAPER

    if doc_type_str == "book":
        if not is_academic:
            raise ValueError(_MSG_NOT_ACADEMIC)
        return DocType.BOOK

    raise ValueError(_MSG_NOT_SUPPORTED)
