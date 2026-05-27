"""
Auto-generates summaries during the document processing pipeline.

Two public entry points, called from document_processor.py after embeddings
are stored:

  summarise_book(doc, pages, db, provider, vectorstore)
    Three-stage chapter detection:
      1. Hierarchical LLM TOC extraction from pages 0–20
      2. Regex heading scan across all pages
      3. Equal-split fallback (4 parts)
    Produces one Summary row per section/chapter with granularity=CHAPTER.
    section_hint uses ">" separator for hierarchy:
      "Chapter 1: Introduction > 1.1 Background"

  summarise_paper(doc, pages, db, provider, vectorstore)
    Full text (first 50 pages) → two LLM calls:
      granularity=FULL    – main summary
      granularity=CONCEPTS – key concepts
"""
import json
import logging
import re
import uuid

from langchain_core.documents import Document as LCDocument
from langchain_core.vectorstores import VectorStore
from sqlalchemy.orm import Session

from app.enums import SummaryGranularity
from app.models.document import Document
from app.models.summary import Summary
from app.services.llm.base import BaseChatProvider

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

_TOC_SCAN_PAGES = 20         # pages fed to LLM for TOC extraction
_PAPER_MAX_PAGES = 50        # max pages used for paper summarisation
_RETRIEVAL_TOP_K_CHAPTER = 50
_RETRIEVAL_TOP_K_SECTION = 30

# Regex patterns for heading detection (fallback stage 2)
_HEADING_PATTERNS = [
    re.compile(r"^chapter\s+\d+", re.IGNORECASE),
    re.compile(r"^part\s+\d+", re.IGNORECASE),
    re.compile(r"^\d+\.\s+[A-Z]"),
    re.compile(r"^[A-Z][A-Z\s]{4,}$"),   # ALL-CAPS headings ≥ 5 chars
]

# ─── Prompts ──────────────────────────────────────────────────────────────────

_TOC_EXTRACTION_SYSTEM = """\
You are a document structure analyst. Extract the full table of contents from the \
provided pages. Return ONLY a JSON object in this exact format:

{
  "chapters": [
    {
      "title": "Chapter 1: Introduction",
      "sections": ["1.1 Background", "1.2 Motivation", "1.3 Outline"]
    },
    {
      "title": "Chapter 2: Related Work",
      "sections": []
    }
  ]
}

Rules:
- Include all chapters and top-level sections visible in the table of contents.
- If a chapter has no sub-sections listed, use an empty "sections" array.
- Preserve the original numbering and titles exactly as they appear.
- If you cannot find a table of contents, return {"chapters": []}.
- Return ONLY the JSON — no extra text, no markdown fences.
"""

_CHAPTER_SUMMARY_SYSTEM = """\
You are an expert summariser. Write a clear, concise summary of the provided \
book section. Focus on the key ideas, arguments, and conclusions. \
Write in prose (3–6 paragraphs). Do not include headings.
"""

_PAPER_SUMMARY_SYSTEM = """\
You are an expert academic summariser. Write a clear, concise summary of the \
provided research paper. Cover: the research question, methodology, key findings, \
and conclusions. Write in prose (3–5 paragraphs). Do not include headings.
"""

_PAPER_CONCEPTS_SYSTEM = """\
You are an expert at extracting key concepts from academic papers. \
From the provided paper text, extract the most important concepts, terms, \
and ideas. Format your response as a numbered list where each item is:
  <concept name>: <one-sentence explanation>
Include 8–15 concepts. Cover both technical terms and high-level themes.
"""


# ─── TOC Detection ────────────────────────────────────────────────────────────

async def _extract_toc_llm(
    pages: list[LCDocument],
    provider: BaseChatProvider,
) -> list[dict]:
    """
    Stage 1: Ask the LLM to extract a hierarchical TOC from pages 0–_TOC_SCAN_PAGES.
    Returns list of {"title": ..., "sections": [...]} dicts, or [] on failure.
    """
    sample = pages[:_TOC_SCAN_PAGES]
    text = "\n\n---\n\n".join(p.page_content for p in sample)
    if len(text) > 12000:
        text = text[:12000]

    messages = [
        {"role": "system", "content": _TOC_EXTRACTION_SYSTEM},
        {"role": "user", "content": text},
    ]
    try:
        response = await provider.complete(messages, temperature=0.0)
        data = json.loads(response.strip())
        chapters = data.get("chapters", [])
        if isinstance(chapters, list) and chapters:
            return chapters
    except (json.JSONDecodeError, KeyError, Exception) as exc:
        logger.warning("TOC LLM extraction failed: %s", exc)
    return []


def _extract_toc_regex(pages: list[LCDocument]) -> list[tuple[str, list[LCDocument]]]:
    """
    Stage 2: Scan all pages for heading-like lines using regex patterns.
    Returns list of (heading_title, [pages]) pairs.
    """
    sections: list[tuple[str, list[LCDocument]]] = []
    current_heading: str | None = None
    current_pages: list[LCDocument] = []

    for page in pages:
        lines = page.page_content.splitlines()
        matched_heading = None
        for line in lines:
            line_stripped = line.strip()
            if len(line_stripped) < 4 or len(line_stripped) > 120:
                continue
            for pattern in _HEADING_PATTERNS:
                if pattern.match(line_stripped):
                    matched_heading = line_stripped
                    break
            if matched_heading:
                break

        if matched_heading:
            if current_heading and current_pages:
                sections.append((current_heading, current_pages))
            current_heading = matched_heading
            current_pages = [page]
        elif current_heading is not None:
            current_pages.append(page)

    if current_heading and current_pages:
        sections.append((current_heading, current_pages))

    return sections


def _equal_split_fallback(pages: list[LCDocument], n_parts: int = 4) -> list[tuple[str, list[LCDocument]]]:
    """Stage 3: Divide pages evenly into n_parts labelled 'Part 1'…'Part N'."""
    total = len(pages)
    chunk = max(1, total // n_parts)
    result = []
    for i in range(n_parts):
        start = i * chunk
        end = start + chunk if i < n_parts - 1 else total
        part_pages = pages[start:end]
        if part_pages:
            result.append((f"Part {i + 1}", part_pages))
    return result


def _toc_to_sections(chapters: list[dict]) -> list[tuple[str, str]]:
    """
    Convert LLM TOC structure to (section_hint, query) pairs.

    If sections exist → one pair per section, hint = "Chapter > Section".
    If only chapter titles → one pair per chapter, hint = "Chapter title".
    """
    result = []
    for ch in chapters:
        ch_title = ch.get("title", "").strip()
        if not ch_title:
            continue
        sections = ch.get("sections", [])
        if sections:
            for sec in sections:
                sec_stripped = sec.strip()
                if sec_stripped:
                    hint = f"{ch_title} > {sec_stripped}"
                    result.append((hint, sec_stripped))
        else:
            result.append((ch_title, ch_title))
    return result


# ─── Summary persistence ─────────────────────────────────────────────────────

def _save_summary(
    db: Session,
    doc: Document,
    granularity: SummaryGranularity,
    content: str,
    section_hint: str | None = None,
) -> None:
    summary = Summary(
        id=uuid.uuid4(),
        user_id=doc.user_id,
        scope_type="document",
        scope_id=doc.id,
        granularity=granularity.value,
        section_hint=section_hint,
        content=content,
    )
    db.add(summary)
    db.commit()


# ─── Book summarisation ───────────────────────────────────────────────────────

async def summarise_book(
    doc: Document,
    pages: list[LCDocument],
    db: Session,
    provider: BaseChatProvider,
    vectorstore: VectorStore,
) -> None:
    """
    Generate chapter/section summaries for a book.

    Three-stage detection for chapter structure, then one LLM call per section.
    Each summary is persisted as a Summary row with granularity=CHAPTER.
    """
    logger.info("Starting book summarisation for document %s", doc.id)

    # Stage 1: LLM hierarchical TOC
    chapters = await _extract_toc_llm(pages, provider)
    if chapters:
        logger.info("TOC stage 1 succeeded: %d chapters", len(chapters))
        sections_with_queries = _toc_to_sections(chapters)
        # Retrieve relevant chunks for each section via vector search
        for section_hint, query in sections_with_queries:
            try:
                results = vectorstore.similarity_search(
                    query,
                    k=_RETRIEVAL_TOP_K_SECTION if ">" in section_hint else _RETRIEVAL_TOP_K_CHAPTER,
                    filter={"document_id": str(doc.id)},
                )
                context = "\n\n".join(r.page_content for r in results)
                if not context.strip():
                    continue
                summary_text = await provider.complete(
                    [
                        {"role": "system", "content": _CHAPTER_SUMMARY_SYSTEM},
                        {"role": "user", "content": f"Section: {section_hint}\n\n{context}"},
                    ],
                    temperature=0.3,
                )
                _save_summary(db, doc, SummaryGranularity.CHAPTER, summary_text, section_hint)
            except Exception as exc:
                logger.warning("Failed to summarise section '%s': %s", section_hint, exc)
        return

    # Stage 2: Regex heading scan
    regex_sections = _extract_toc_regex(pages)
    if regex_sections:
        logger.info("TOC stage 2 (regex) succeeded: %d sections", len(regex_sections))
        for heading, section_pages in regex_sections:
            try:
                context = "\n\n".join(p.page_content for p in section_pages)
                if len(context) > 15000:
                    context = context[:15000]
                if not context.strip():
                    continue
                summary_text = await provider.complete(
                    [
                        {"role": "system", "content": _CHAPTER_SUMMARY_SYSTEM},
                        {"role": "user", "content": f"Section: {heading}\n\n{context}"},
                    ],
                    temperature=0.3,
                )
                _save_summary(db, doc, SummaryGranularity.CHAPTER, summary_text, heading)
            except Exception as exc:
                logger.warning("Failed to summarise section '%s': %s", heading, exc)
        return

    # Stage 3: Equal-split fallback
    logger.info("TOC stage 3 (equal split) for document %s", doc.id)
    fallback_sections = _equal_split_fallback(pages)
    for part_label, part_pages in fallback_sections:
        try:
            context = "\n\n".join(p.page_content for p in part_pages)
            if len(context) > 15000:
                context = context[:15000]
            if not context.strip():
                continue
            summary_text = await provider.complete(
                [
                    {"role": "system", "content": _CHAPTER_SUMMARY_SYSTEM},
                    {"role": "user", "content": f"Section: {part_label}\n\n{context}"},
                ],
                temperature=0.3,
            )
            _save_summary(db, doc, SummaryGranularity.CHAPTER, summary_text, part_label)
        except Exception as exc:
            logger.warning("Failed to summarise fallback section '%s': %s", part_label, exc)


# ─── Research paper summarisation ────────────────────────────────────────────

async def summarise_paper(
    doc: Document,
    pages: list[LCDocument],
    db: Session,
    provider: BaseChatProvider,
    vectorstore: VectorStore,  # kept for interface consistency; not used for papers
) -> None:
    """
    Generate a full summary and key concepts for a research paper.

    Uses the raw page text directly (more complete than retrieval for short papers).
    Persists two Summary rows: granularity=FULL and granularity=CONCEPTS.
    """
    logger.info("Starting paper summarisation for document %s", doc.id)

    paper_pages = pages[:_PAPER_MAX_PAGES]
    full_text = "\n\n".join(p.page_content for p in paper_pages)

    # Truncate to ~20000 chars — well within GPT-4o context
    if len(full_text) > 20000:
        full_text = full_text[:20000]

    # Full summary
    try:
        summary_text = await provider.complete(
            [
                {"role": "system", "content": _PAPER_SUMMARY_SYSTEM},
                {"role": "user", "content": full_text},
            ],
            temperature=0.3,
        )
        _save_summary(db, doc, SummaryGranularity.FULL, summary_text)
    except Exception as exc:
        logger.error("Failed to generate paper summary for %s: %s", doc.id, exc)

    # Key concepts
    try:
        concepts_text = await provider.complete(
            [
                {"role": "system", "content": _PAPER_CONCEPTS_SYSTEM},
                {"role": "user", "content": full_text},
            ],
            temperature=0.3,
        )
        _save_summary(db, doc, SummaryGranularity.CONCEPTS, concepts_text)
    except Exception as exc:
        logger.error("Failed to generate paper concepts for %s: %s", doc.id, exc)
