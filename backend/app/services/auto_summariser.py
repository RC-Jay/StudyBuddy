"""
Auto-generates summaries during the document processing pipeline.

Two public entry points, called from document_processor.py after embeddings
are stored:

  summarise_book(doc, pages, db, provider, vectorstore)
    Multi-stage chapter detection:
      1a. PyMuPDF coordinate-based TOC extraction (primary, no LLM required).
          Uses font-size hierarchy on the detected TOC pages to extract a
          2-level structure (Part/Chapter → Chapter/Section).
      1b. LLM structured TOC parse (fallback when 1a finds nothing).
          The LLM returns a structured TOC distinguishing Parts from Chapters
          and filtering out non-technical sections (Further Reading, Exercises…).
         Summary plan (ordered flat list of hints):
           - Part gets its own summary entry first.
           - Chapters with technical subsections → one entry per subsection.
           - Chapters without subsections → one entry for the chapter itself.
         section_hint format (up to 3 levels, " > " separator):
           "Part I. Data Structures"
           "Part I. Data Structures > 1. The Python Data Model"
           "Preface"
           "Preface > Background"
      2. Regex heading scan across all pages (fallback — flat chapter list).
      3. Equal-split fallback (4 parts).

  summarise_paper(doc, pages, db, provider, vectorstore)
    Full text (first 50 pages) → two LLM calls:
      granularity=FULL    – main summary
      granularity=CONCEPTS – key concepts
"""
import asyncio
import json
import logging
import os
import re
import tempfile
import uuid
from collections import Counter, defaultdict

import fitz  # PyMuPDF
from langchain_core.documents import Document as LCDocument
from langchain_core.vectorstores import VectorStore
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from sqlalchemy.orm import Session

from app.enums import SummaryGranularity
from app.models.document import Document
from app.models.summary import Summary
from app.services.llm.base import BaseChatProvider
from app.services.storage import load_file

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

_TOC_SEARCH_LIMIT = 50       # max pages to scan when locating the TOC
_TOC_MAX_SPAN = 25           # max pages a TOC section is allowed to span
_PAPER_MAX_PAGES = 50        # max pages used for paper summarisation

# Retrieval k values by hint depth (number of " > " separators)
_K_BY_DEPTH = {0: 80, 1: 50, 2: 30}

# Stage 2: chapter-level heading patterns
_CH_PATTERNS = [
    re.compile(r"^chapter\s+\d+", re.IGNORECASE),          # "Chapter 1", "CHAPTER 1"
    re.compile(r"^part\s+[IVX\d]+\b", re.IGNORECASE),      # "Part I", "Part II.", "Part 1"
    re.compile(r"^\d{1,2}\s+[A-Z][a-z]"),                  # "1 Escaping monolithic hell"
]

# Stage 2: section-level heading patterns (subsections within a chapter)
_SEC_PATTERNS = [
    re.compile(r"^\d{1,2}\.\d+\s+\S"),                     # "1.1 Something", "12.3 Topic"
]

# ─── LLM retry helper ────────────────────────────────────────────────────────

_RETRYABLE_EXC = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)
_MAX_LLM_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # seconds; doubled on each attempt (2 → 4 → 8)


async def _complete_with_retry(
    provider: BaseChatProvider,
    messages: list[dict],
    temperature: float = 0.3,
) -> str:
    """Call provider.complete with exponential backoff on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_LLM_RETRIES):
        try:
            return await provider.complete(messages, temperature=temperature)
        except _RETRYABLE_EXC as exc:
            last_exc = exc
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "LLM call failed (attempt %d/%d): %s — retrying in %.0fs",
                attempt + 1, _MAX_LLM_RETRIES, exc, delay,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ─── Deletion guard ───────────────────────────────────────────────────────────

def _is_deleted(doc: Document, db: Session) -> bool:
    """Refresh the document from DB and return True if it has been soft-deleted."""
    db.refresh(doc)
    return doc.deleted_at is not None


# ─── Prompts ──────────────────────────────────────────────────────────────────

_TOC_EXTRACTION_SYSTEM = """\
You are a document structure analyst. Extract the table of contents from the provided pages.

Return ONLY a JSON object in this exact format:

{
  "items": [
    {
      "type": "chapter",
      "title": "Preface",
      "sections": []
    },
    {
      "type": "part",
      "title": "Part I. Data Structures",
      "chapters": [
        {
          "title": "1. The Python Data Model",
          "sections": ["A Pythonic Card Deck", "How Special Methods Are Used"]
        },
        {
          "title": "2. An Array of Sequences",
          "sections": []
        }
      ]
    }
  ]
}

Rules:
- Each item is either type "part" (a named group of chapters, e.g. "Part I") or \
type "chapter" (a standalone chapter not inside any part).
- Preserve the original document order — items must appear in the same sequence as the TOC.
- For each chapter, include ONLY technical sections that are worth summarising independently.
- OMIT meta / non-technical sections such as: "Summary", "What's New in This Chapter", \
"Further Reading", "References", "Exercises", "Review Questions", "Soapbox", "Notes", \
"Credits", "Afterword", "Foreword", "Acknowledgements".
- If a chapter has no meaningful technical sections, use an empty "sections": [].
- Preserve original numbering and titles exactly as they appear.
- If you cannot find a table of contents, return {"items": []}.
- Return ONLY the JSON — no extra text, no markdown fences.
"""

_CHAPTER_SUMMARY_SYSTEM = """\
You are an expert summariser. Write a clear, concise summary of the provided \
book section. Focus on the key ideas, arguments, and conclusions. \
Write in prose (3–6 paragraphs). Do not include headings.
"""

_PART_SUMMARY_SYSTEM = """\
You are an expert summariser. Write a high-level overview of this book part, \
capturing the themes that connect its chapters and what a reader will learn. \
Write in prose (2–4 paragraphs). Do not include headings.
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


# ─── TOC page detection ───────────────────────────────────────────────────────

_TOC_HEADER_RE = re.compile(
    r"table\s+of\s+contents|^\s*contents\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# TOC entry line: text followed by a page number.
# e.g. "1. The Python Data Model ........ 5"  or  "Chapter 1   3"
# Separator is {2,} (unbounded) to handle PDF TOC padding of 50+ dots/spaces.
_TOC_ENTRY_RE = re.compile(
    r"^.{3,80}[\s.\-]{2,}\d{1,4}\s*$",
    re.MULTILINE,
)


def _locate_toc_pages(pages: list[LCDocument]) -> list[LCDocument]:
    """
    Scan front matter for the Table of Contents, return only those pages.

    1. Find the first page (within _TOC_SEARCH_LIMIT) containing a TOC header.
    2. Collect consecutive pages with TOC-entry lines (text + trailing page number).
    3. Stop when a page has no entries or _TOC_MAX_SPAN is exceeded.
    4. If no header found, return [] so Stage 1 is skipped entirely.
    """
    scan_limit = min(_TOC_SEARCH_LIMIT, len(pages))
    toc_start: int | None = None

    for i, page in enumerate(pages[:scan_limit]):
        if _TOC_HEADER_RE.search(page.page_content):
            toc_start = i
            break

    if toc_start is None:
        logger.debug("No TOC header found in first %d pages", scan_limit)
        return []

    # The header may have been detected from a running footer (e.g. "vi | Table of
    # Contents") rather than the actual first TOC page. Scan backward up to 5 pages
    # to find earlier pages that also contain TOC-entry lines.
    actual_start = toc_start
    for i in range(toc_start - 1, max(-1, toc_start - 6), -1):
        if _TOC_ENTRY_RE.search(pages[i].page_content):
            actual_start = i
        else:
            break
    if actual_start < toc_start:
        logger.info("TOC start adjusted back from page %d to page %d", toc_start, actual_start)

    toc_pages: list[LCDocument] = []
    gap = 0
    _MAX_TOC_GAP = 2  # consecutive non-entry pages allowed before stopping

    for page in pages[actual_start : actual_start + _TOC_MAX_SPAN]:
        if _TOC_ENTRY_RE.search(page.page_content):
            toc_pages.append(page)
            gap = 0
        elif toc_pages:
            # Allow a short gap (e.g. part-header pages with no page numbers)
            gap += 1
            toc_pages.append(page)  # include so LLM sees full context
            if gap > _MAX_TOC_GAP:
                # Strip the trailing gap pages — they're past the TOC
                toc_pages = toc_pages[:-gap]
                break

    if not toc_pages:
        # Header found but entries not parseable — let the LLM try with a few pages
        toc_pages = pages[toc_start : toc_start + 5]

    logger.info("TOC located at page %d, spanning %d page(s)", actual_start, len(toc_pages))
    return toc_pages


# ─── Coordinate-based TOC extraction (Stage 1) ───────────────────────────────

# Titles to filter out of the extracted TOC
_COORD_SKIP_TITLES = re.compile(
    r"what.s new|chapter summary|further reading|references|exercises|"
    r"review questions|soapbox|afterword|foreword|acknowledgement|"
    r"about this book|about the cover|preface|index",
    re.IGNORECASE,
)
_COORD_NOISE_HEADERS = frozenset({
    "CONTENTS", "TABLE OF CONTENTS",
    "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII",
})
_COORD_PAGENUM_RE = re.compile(r"[\s.\-]{2,}\d{1,4}\s*$")
_COORD_TRAILING_CONNECTOR_RE = re.compile(
    # Negative lookbehind prevents matching "In" inside "Built-In" etc.
    r"(?<!\-)\b(the|a|an|of|in|for|with|by|from|to|at|and|or|using|that|which|its|their)\s*$",
    re.IGNORECASE,
)
_COORD_PART_RE = re.compile(r"^(Part|Unit|Section|Volume)\s", re.IGNORECASE)


def _coord_strip_pagenum(text: str) -> str:
    return _COORD_PAGENUM_RE.sub("", text).strip()


def _coord_extract_structure(pdf_bytes: bytes, toc_pages: list[LCDocument]) -> list[tuple[int, str]]:
    """
    Use PyMuPDF to extract up to a 3-level TOC structure from the given pages.

    Returns a list of (level, title) tuples where:
      - level 0 → Part or Chapter (top-level)
      - level 1 → Chapter or Section (nested under level 0)
      - level 2 → Section or Sub-section (nested under level 1)

    Algorithm:
      1. Group PDF spans by y-coordinate per page to reconstruct lines.
      2. Detect font-size hierarchy: top-3 significant sizes map to levels 0/1/2.
         Use the minimum x-coordinate of level-2 items as a threshold — items
         indented deeper than min_x + 5pt are sub-sub-sections and skipped.
      3. Merge isolated large numeric spans (chapter number glyphs) with the
         adjacent title span.
      4. Strip dot-leaders and trailing page numbers from every title.
      5. Join multi-line title continuations:
           - current line starts lowercase → clear continuation word
           - previous line ends with a dangling connector word (the, a, of…)
    """
    if not toc_pages:
        return []

    start_page = toc_pages[0].metadata.get("page", 0)
    n = len(toc_pages)

    pdf = fitz.open(stream=pdf_bytes, filetype="pdf")

    # ── Phase 1: collect raw spans grouped by (page, y) ─────────────────────
    raw_lines: list[tuple[float, float, str, int, float]] = []  # (x_min, size_max, text, page_idx, y)

    for page_idx in range(start_page, start_page + n):
        if page_idx >= len(pdf):
            break
        page = pdf[page_idx]
        line_map: dict[float, list[tuple[float, float, str]]] = defaultdict(list)

        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for line in b["lines"]:
                y = round(line["bbox"][1], 0)
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text:
                        continue
                    line_map[y].append((span["bbox"][0], span["size"], text))

        for y, spans in sorted(line_map.items()):
            # Drop tiny text and pure bullet / page-number spans
            spans = [(x, s, t) for x, s, t in spans if s >= 9 and not re.match(r"^[■\d\s]+$", t)]
            if not spans:
                continue
            x_min = min(x for x, s, t in spans)
            size_max = max(s for x, s, t in spans)
            full_text = " ".join(t for x, s, t in sorted(spans, key=lambda sp: sp[0]))
            if re.match(r"^[\d\s]+$", full_text) or len(full_text) <= 2:
                continue
            raw_lines.append((x_min, size_max, full_text, page_idx, y))

    pdf.close()

    # ── Phase 2: merge isolated chapter-number glyphs with adjacent title ────
    # Some PDFs print the chapter number (e.g. "1") as a large separate span.
    merged: list[tuple[float, float, str]] = []
    i = 0
    while i < len(raw_lines):
        x, sz, text, pg, y = raw_lines[i]
        if sz >= 20 and re.match(r"^\d{1,3}$", text.strip()):
            if i + 1 < len(raw_lines):
                nx, nsz, ntext, npg, ny = raw_lines[i + 1]
                if npg == pg and abs(ny - y) < 30:
                    merged.append((min(x, nx), max(sz, nsz), text.strip() + " " + ntext))
                    i += 2
                    continue
        merged.append((x, sz, text))
        i += 1

    # ── Phase 3: determine up to 3-level hierarchy from font sizes ─────────
    size_counts: Counter = Counter(round(sz, 0) for _, sz, _ in merged)
    sig_sizes = sorted([s for s, c in size_counts.items() if c >= 2], reverse=True)

    # Drop a header-only size (very large, few occurrences)
    if sig_sizes and sig_sizes[0] > 20 and size_counts[sig_sizes[0]] < 5:
        sig_sizes = sig_sizes[1:]

    if not sig_sizes:
        return []

    level0_size = sig_sizes[0]
    # Single significant size → flat chapter list (no sections)
    level1_size = sig_sizes[1] if len(sig_sizes) >= 2 else None
    level2_size = sig_sizes[2] if len(sig_sizes) >= 3 else None

    # For level 2: use the minimum x-coordinate as a threshold so that items
    # indented deeper (sub-sub-sections) are excluded.
    x_threshold: float | None = None
    if level2_size:
        level2_xs = sorted(set(round(x) for x, s, _ in merged if round(s, 0) == level2_size))
        x_threshold = (level2_xs[0] + 5) if len(level2_xs) >= 2 else 9999.0

    # ── Phase 4: classify and clean ─────────────────────────────────────────
    structure: list[tuple[int, str]] = []
    for x, size, text in merged:
        sz = round(size, 0)
        if _COORD_SKIP_TITLES.search(text):
            continue
        if text.upper().strip() in _COORD_NOISE_HEADERS:
            continue
        if sz == level0_size:
            clean = _coord_strip_pagenum(text)
            if clean:
                structure.append((0, clean))
        elif level1_size and sz == level1_size:
            clean = _coord_strip_pagenum(text)
            if clean:
                structure.append((1, clean))
        elif level2_size and sz == level2_size:
            if x_threshold is None or x <= x_threshold:
                clean = _coord_strip_pagenum(text)
                if clean:
                    structure.append((2, clean))

    # ── Phase 5: join multi-line title continuations ─────────────────────────
    # Only join within the same level. A continuation line either starts with
    # a lowercase word (e.g. "architecture" completing a wrapped title) or the
    # previous line ends with a dangling connector (the, a, of, using…).
    joined: list[list] = []
    for level, text in structure:
        prev_text = joined[-1][1] if joined else ""
        is_continuation = (
            joined
            and joined[-1][0] == level
            and text
            and (
                # Short lowercase fragment → likely a wrapped word (e.g. "architecture").
                # The 25-char limit prevents method names like "list.sort Versus…" (37 chars)
                # from being mistaken for continuations.
                (text[0].islower() and len(text) < 25)
                # OR the previous line ends with a dangling connector word.
                # The negative lookbehind in the regex prevents "Built-In" → "In" matching.
                or bool(_COORD_TRAILING_CONNECTOR_RE.search(prev_text))
            )
        )
        if is_continuation:
            joined[-1][1] = prev_text + " " + text
        else:
            joined.append([level, text])

    return [(lvl, txt) for lvl, txt in joined]


async def _extract_toc_coordinate(
    doc: Document,
    pages: list[LCDocument],
) -> list[dict]:
    """
    Stage 1 (primary): coordinate-based TOC extraction using PyMuPDF.

    Locates TOC pages via _locate_toc_pages, then uses font-size hierarchy
    to extract a 2-level structure (Part/Chapter → Chapter/Section) without
    any LLM call.

    Returns a list[dict] in the same format expected by _build_summary_plan,
    or [] if the TOC cannot be found / extracted.
    """
    toc_pages = _locate_toc_pages(pages)
    if not toc_pages:
        return []

    try:
        pdf_bytes = await load_file(doc.blob_path)
        structure = _coord_extract_structure(pdf_bytes, toc_pages)
    except Exception as exc:
        logger.warning("Coordinate TOC extraction failed: %s", exc)
        return []

    if not structure:
        logger.info("Coordinate TOC extraction found no structure")
        return []

    # Determine whether level-0 entries are Parts or top-level Chapters.
    level0_items = [text for lvl, text in structure if lvl == 0]
    has_parts = any(_COORD_PART_RE.match(t) for t in level0_items)

    items: list[dict] = []
    current_top: dict | None = None   # the current Part or Chapter item

    for level, text in structure:
        if level == 0:
            if has_parts:
                # Part — accumulates chapters as level-1, sections as level-2
                current_top = {"type": "part", "title": text, "chapters": []}
            else:
                # Chapter — accumulates sections as level-1 (no level-2 used)
                current_top = {"type": "chapter", "title": text, "sections": []}
            items.append(current_top)

        elif level == 1:
            if current_top is None:
                # Orphan level-1 before any level-0: treat as standalone chapter
                current_top = {"type": "chapter", "title": text, "sections": []}
                items.append(current_top)
            elif has_parts:
                # Chapter within a Part
                current_top["chapters"].append({"title": text, "sections": []})
            else:
                # Section within a standalone Chapter
                current_top["sections"].append(text)

        elif level == 2 and has_parts:
            # Section within the most-recently-added chapter of the current Part.
            # (Level-2 entries are ignored for books without Parts — those books
            #  already have a clean Chapter → Section structure at levels 0/1.)
            if current_top and current_top.get("chapters"):
                current_top["chapters"][-1]["sections"].append(text)

    logger.info(
        "Coordinate TOC extraction succeeded: %d top-level items, %d total entries",
        len(items),
        len(structure),
    )
    return items


# ─── TOC LLM extraction (Stage 1 fallback) ───────────────────────────────────

async def _extract_toc_llm(
    pages: list[LCDocument],
    provider: BaseChatProvider,
) -> list[dict]:
    """
    Stage 1: Detect TOC pages, then ask the LLM to parse the structured TOC.
    Returns the raw 'items' list from the LLM response, or [] on failure/no TOC.
    """
    toc_pages = _locate_toc_pages(pages)
    if not toc_pages:
        logger.info("No TOC pages found — skipping LLM extraction, proceeding to Stage 2")
        return []

    # Collapse whitespace padding (e.g. "Slicing ........ 47" → "Slicing")
    # and drop trailing page numbers — the LLM only needs titles and hierarchy.
    _WS_RE = re.compile(r"[ \t]{2,}")
    _PAGENUM_RE = re.compile(r"[\s.\-]{2,}\d{1,4}\s*$")

    def _clean_toc_line(line: str) -> str:
        line = _PAGENUM_RE.sub("", line)
        line = _WS_RE.sub(" ", line)
        return line.strip()

    cleaned_pages = []
    for p in toc_pages:
        lines = [_clean_toc_line(l) for l in p.page_content.splitlines()]
        cleaned_pages.append("\n".join(l for l in lines if l))

    text = "\n\n---\n\n".join(cleaned_pages)
    logger.info("TOC text: %d chars (~%d tokens) after cleaning", len(text), len(text) // 4)

    try:
        response = await _complete_with_retry(
            provider,
            [
                {"role": "system", "content": _TOC_EXTRACTION_SYSTEM},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
        )
        data = json.loads(response.strip())
        items = data.get("items", [])
        if isinstance(items, list) and items:
            logger.info("TOC stage 1 succeeded: %d top-level items", len(items))
            return items
    except (json.JSONDecodeError, KeyError, Exception) as exc:
        logger.warning("TOC LLM extraction failed: %s", exc)
    return []


# ─── Summary plan ─────────────────────────────────────────────────────────────

def _build_summary_plan(toc_items: list[dict]) -> list[tuple[str, str, int]]:
    """
    Convert the structured LLM TOC into an ordered flat list of
    (section_hint, retrieval_query, sort_order) tuples.

    Structure produced:
      - Part       → hint = "Part I. Data Structures"
      - Chapter under part, no sections  → hint = "Part I > 1. Chapter"
      - Section under chapter under part → hint = "Part I > 1. Chapter > Section"
      - Standalone chapter, no sections  → hint = "Preface"
      - Section under standalone chapter → hint = "Preface > Background"

    sort_order is a global running index preserving TOC order.
    """
    plan: list[tuple[str, str, int]] = []
    idx = 0

    for item in toc_items:
        item_type = item.get("type", "chapter")

        if item_type == "part":
            part_title = item.get("title", "").strip()
            if not part_title:
                continue
            chapters = item.get("chapters", [])

            # Part summary — query uses part title + all its chapter titles
            ch_titles = " ".join(ch.get("title", "") for ch in chapters if ch.get("title"))
            plan.append((part_title, f"{part_title} {ch_titles}".strip(), idx))
            idx += 1

            for ch in chapters:
                ch_title = ch.get("title", "").strip()
                if not ch_title:
                    continue
                sections = [s.strip() for s in ch.get("sections", []) if s.strip()]

                if sections:
                    for sec in sections:
                        plan.append((f"{part_title} > {ch_title} > {sec}", sec, idx))
                        idx += 1
                else:
                    plan.append((f"{part_title} > {ch_title}", ch_title, idx))
                    idx += 1

        else:  # standalone chapter
            ch_title = item.get("title", "").strip()
            if not ch_title:
                continue
            sections = [s.strip() for s in item.get("sections", []) if s.strip()]

            if sections:
                for sec in sections:
                    plan.append((f"{ch_title} > {sec}", sec, idx))
                    idx += 1
            else:
                plan.append((ch_title, ch_title, idx))
                idx += 1

    return plan


# ─── Stage 2: Regex heading scan ─────────────────────────────────────────────

def _extract_toc_regex(pages: list[LCDocument]) -> list[tuple[str, str]]:
    """
    Stage 2: Two-level heading scan across all pages.

    Produces (section_hint, query) pairs using the same format as Stage 1:
      - Chapter with subsections  → one entry per subsection:
          ("1 Escaping monolithic hell > 1.1 The slow march...", "1.1 The slow march...")
      - Chapter without subsections → one entry for the chapter:
          ("2 Decomposition strategies", "2 Decomposition strategies")

    Retrieval query is always the leaf title so vectorstore finds relevant chunks.
    Deduplication ensures the same heading encountered on multiple pages (e.g.
    running headers) only produces one entry.
    """
    plan: list[tuple[str, str]] = []
    seen: set[str] = set()
    current_chapter: str | None = None
    chapter_has_sections: bool = False

    def _add(hint: str, query: str) -> None:
        if hint not in seen:
            seen.add(hint)
            plan.append((hint, query))

    for page in pages:
        ch_heading: str | None = None
        sec_heading: str | None = None

        for line in page.page_content.splitlines():
            stripped = line.strip()
            if len(stripped) < 3 or len(stripped) > 120:
                continue

            # Check chapter-level patterns first
            for pat in _CH_PATTERNS:
                if pat.match(stripped):
                    ch_heading = stripped
                    break
            if ch_heading:
                break

            # Check section-level patterns (only meaningful inside a chapter)
            if current_chapter is not None:
                for pat in _SEC_PATTERNS:
                    if pat.match(stripped):
                        sec_heading = stripped
                        break
                if sec_heading:
                    break

        if ch_heading:
            # Flush previous chapter if it had no sections
            if current_chapter and not chapter_has_sections:
                _add(current_chapter, current_chapter)
            current_chapter = ch_heading
            chapter_has_sections = False

        elif sec_heading and current_chapter:
            hint = f"{current_chapter} > {sec_heading}"
            _add(hint, sec_heading)
            chapter_has_sections = True

    # Flush last chapter
    if current_chapter and not chapter_has_sections:
        _add(current_chapter, current_chapter)

    return plan


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


# ─── Summary persistence ──────────────────────────────────────────────────────

def _save_summary(
    db: Session,
    doc: Document,
    granularity: SummaryGranularity,
    content: str,
    section_hint: str | None = None,
    sort_order: int = 0,
) -> None:
    db.add(Summary(
        id=uuid.uuid4(),
        user_id=doc.user_id,
        scope_type="document",
        scope_id=doc.id,
        granularity=granularity.value,
        section_hint=section_hint,
        sort_order=sort_order,
        content=content,
    ))
    db.commit()


# ─── Book summarisation ───────────────────────────────────────────────────────

def _retrieval_k(section_hint: str) -> int:
    depth = section_hint.count(" > ")
    return _K_BY_DEPTH.get(depth, 30)


async def _summarise_one(
    section_hint: str,
    query: str,
    sort_order: int,
    doc: Document,
    db: Session,
    provider: BaseChatProvider,
    vectorstore: VectorStore,
    skip: set[str],
) -> bool:
    """Retrieve context and generate one summary. Returns True if saved."""
    if section_hint in skip:
        logger.debug("Skipping already-done: '%s'", section_hint)
        return False
    try:
        results = vectorstore.similarity_search(
            query,
            k=_retrieval_k(section_hint),
            filter={"document_id": str(doc.id)},
        )
        context = "\n\n".join(r.page_content for r in results)
        if not context.strip():
            logger.warning("No context retrieved for '%s' — skipping", section_hint)
            return False

        depth = section_hint.count(" > ")
        system = _PART_SUMMARY_SYSTEM if depth == 0 and " > " not in section_hint else _CHAPTER_SUMMARY_SYSTEM
        summary_text = await _complete_with_retry(
            provider,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Section: {section_hint}\n\n{context}"},
            ],
            temperature=0.3,
        )
        _save_summary(db, doc, SummaryGranularity.CHAPTER, summary_text, section_hint, sort_order)
        return True
    except Exception as exc:
        logger.warning("Failed to summarise '%s': %s", section_hint, exc)
        return False


async def summarise_book(
    doc: Document,
    pages: list[LCDocument],
    db: Session,
    provider: BaseChatProvider,
    vectorstore: VectorStore,
    done_hints: set[str] | None = None,
) -> None:
    """
    Generate summaries for a book using a three-stage chapter detection strategy.

    Stage 1 (LLM structured TOC):
      Detects TOC pages, extracts Parts/Chapters/Sections, filters non-technical
      sections, then summarises: Part overview → chapter or section summaries.

    Stage 2 (regex heading scan):
      Flat chapter list extracted from heading patterns across all pages.

    Stage 3 (equal split):
      Last resort — divides the book into 4 equal parts.

    done_hints: section_hints already stored — skipped on resume.
    """
    skip = done_hints or set()
    logger.info("Starting book summarisation for %s (skipping %d done)", doc.id, len(skip))

    # ── Stage 1a: coordinate-based TOC (no LLM, fast) ────────────────────────
    toc_items = await _extract_toc_coordinate(doc, pages)

    # ── Stage 1b: LLM structured TOC (fallback) ───────────────────────────────
    if not toc_items:
        toc_items = await _extract_toc_llm(pages, provider)

    if toc_items:
        # Persist the extracted TOC so the frontend can render the book outline
        # independently of whether summaries have been generated yet.
        doc.toc = toc_items
        db.commit()
        plan = _build_summary_plan(toc_items)
        logger.info("Summary plan: %d items", len(plan))
        doc.expected_summary_count = len(plan)
        db.commit()

        for section_hint, query, sort_order in plan:
            if _is_deleted(doc, db):
                logger.info("Document %s was deleted — stopping summarisation", doc.id)
                return
            await _summarise_one(section_hint, query, sort_order, doc, db, provider, vectorstore, skip)
        return

    # ── Stage 2: Regex heading scan ───────────────────────────────────────────
    regex_plan = _extract_toc_regex(pages)
    if regex_plan:
        logger.info("TOC stage 2 (regex) succeeded: %d items", len(regex_plan))
        doc.expected_summary_count = len(regex_plan)
        db.commit()
        for idx, (section_hint, query) in enumerate(regex_plan):
            if _is_deleted(doc, db):
                logger.info("Document %s was deleted — stopping summarisation", doc.id)
                return
            await _summarise_one(section_hint, query, idx, doc, db, provider, vectorstore, skip)
        return

    # ── Stage 3: Equal-split fallback ─────────────────────────────────────────
    logger.info("TOC stage 3 (equal split) for %s", doc.id)
    fallback_sections = _equal_split_fallback(pages)
    doc.expected_summary_count = len(fallback_sections)
    db.commit()
    for idx, (part_label, part_pages) in enumerate(fallback_sections):
        if _is_deleted(doc, db):
            logger.info("Document %s was deleted — stopping summarisation", doc.id)
            return
        if part_label in skip:
            continue
        try:
            context = "\n\n".join(p.page_content for p in part_pages)
            if len(context) > 15000:
                context = context[:15000]
            if not context.strip():
                continue
            summary_text = await _complete_with_retry(
                provider,
                [
                    {"role": "system", "content": _CHAPTER_SUMMARY_SYSTEM},
                    {"role": "user", "content": f"Section: {part_label}\n\n{context}"},
                ],
                temperature=0.3,
            )
            _save_summary(db, doc, SummaryGranularity.CHAPTER, summary_text, part_label, sort_order=idx)
        except Exception as exc:
            logger.warning("Failed to summarise fallback '%s': %s", part_label, exc)


# ─── Research paper summarisation ────────────────────────────────────────────

async def summarise_paper(
    doc: Document,
    pages: list[LCDocument],
    db: Session,
    provider: BaseChatProvider,
    vectorstore: VectorStore,  # kept for interface consistency; not used for papers
    done_granularities: set[str] | None = None,
) -> None:
    """
    Generate a full summary and key concepts for a research paper.

    Uses raw page text (more complete than retrieval for short papers).
    Persists two Summary rows: granularity=FULL and granularity=CONCEPTS.
    done_granularities: skip already-completed entries on resume.
    """
    skip = done_granularities or set()
    logger.info("Starting paper summarisation for %s", doc.id)

    doc.expected_summary_count = 2
    db.commit()

    paper_pages = pages[:_PAPER_MAX_PAGES]
    full_text = "\n\n".join(p.page_content for p in paper_pages)
    if len(full_text) > 20000:
        full_text = full_text[:20000]

    if SummaryGranularity.FULL.value not in skip:
        if _is_deleted(doc, db):
            logger.info("Document %s was deleted — stopping summarisation", doc.id)
            return
        try:
            summary_text = await _complete_with_retry(
                provider,
                [{"role": "system", "content": _PAPER_SUMMARY_SYSTEM},
                 {"role": "user", "content": full_text}],
                temperature=0.3,
            )
            _save_summary(db, doc, SummaryGranularity.FULL, summary_text, sort_order=0)
        except Exception as exc:
            logger.error("Failed to generate paper summary for %s: %s", doc.id, exc)

    if SummaryGranularity.CONCEPTS.value not in skip:
        if _is_deleted(doc, db):
            logger.info("Document %s was deleted — stopping summarisation", doc.id)
            return
        try:
            concepts_text = await _complete_with_retry(
                provider,
                [{"role": "system", "content": _PAPER_CONCEPTS_SYSTEM},
                 {"role": "user", "content": full_text}],
                temperature=0.3,
            )
            _save_summary(db, doc, SummaryGranularity.CONCEPTS, concepts_text, sort_order=1)
        except Exception as exc:
            logger.error("Failed to generate paper concepts for %s: %s", doc.id, exc)


# ─── Video summarisation ──────────────────────────────────────────────────────

_VIDEO_SECTION_SYSTEM = """\
You are an expert at analysing educational video transcripts. You will be given a
transcript of an educational video. Your job is to identify 3–5 logical sections
(like a table of contents for the video) based on topic transitions.

Return ONLY a JSON object in this exact format:
{
  "sections": [
    {"title": "Introduction and Motivation", "start_char": 0},
    {"title": "Core Concepts", "start_char": 450},
    {"title": "Practical Examples", "start_char": 1200},
    {"title": "Summary and Key Takeaways", "start_char": 1900}
  ]
}

Rules:
- 3–5 sections only. Do not over-segment.
- start_char is the approximate character offset in the transcript where the section begins.
- The first section must always have start_char: 0.
- Titles should be concise and descriptive (3–8 words).
- Return ONLY the JSON — no extra text, no markdown fences.
"""

_VIDEO_SEGMENT_SUMMARY_SYSTEM = """\
You are an expert summariser. Write a clear, concise summary of the provided
video segment transcript. Focus on the key ideas, concepts, and explanations
presented. Write in prose (2–4 paragraphs). Do not include headings.
"""

_VIDEO_CONCEPTS_SYSTEM = """\
You are an expert at extracting key concepts from educational video transcripts.
From the provided transcript, extract the most important concepts, terms,
and ideas. Format your response as a numbered list where each item is:
  <concept name>: <one-sentence explanation>
Include 6–12 concepts.
"""

_SHORT_VIDEO_THRESHOLD = 1200   # 20 minutes — use LLM segmentation below this
_FIXED_WINDOW_CHARS = 3000      # ~5 min equivalent at average speech rate


async def _llm_segment_transcript(
    transcript: str,
    provider: BaseChatProvider,
) -> list[tuple[str, str]]:
    """
    Use the LLM to detect 3–5 logical sections in the transcript.
    Returns list of (title, segment_text) pairs.
    Falls back to a two-part split on parse error.
    """
    sample = transcript[:12000]  # send a representative sample
    try:
        response = await _complete_with_retry(
            provider,
            [
                {"role": "system", "content": _VIDEO_SECTION_SYSTEM},
                {"role": "user", "content": sample},
            ],
            temperature=0.2,
        )
        import json as _json
        data = _json.loads(response.strip())
        sections = data.get("sections", [])
        if not sections or len(sections) < 2:
            raise ValueError("Too few sections returned")

        # Build (title, text) pairs using char offsets
        result = []
        total = len(transcript)
        for i, sec in enumerate(sections):
            start = int(sec.get("start_char", 0))
            end = int(sections[i + 1]["start_char"]) if i + 1 < len(sections) else total
            text = transcript[start:end].strip()
            if text:
                result.append((sec["title"], text))
        return result
    except Exception as exc:
        logger.warning("LLM segmentation failed: %s — using half split", exc)
        mid = len(transcript) // 2
        return [
            ("First Half", transcript[:mid]),
            ("Second Half", transcript[mid:]),
        ]


def _fixed_window_segments(transcript: str) -> list[tuple[str, str]]:
    """Divide a long transcript into fixed-size windows."""
    segments = []
    total = len(transcript)
    i = 0
    part = 1
    while i < total:
        text = transcript[i : i + _FIXED_WINDOW_CHARS].strip()
        if text:
            segments.append((f"Part {part}", text))
            part += 1
        i += _FIXED_WINDOW_CHARS
    return segments


async def summarise_video(
    doc: Document,
    content,  # VideoContent dataclass
    db: Session,
    provider: BaseChatProvider,
    vectorstore: VectorStore,
    done_hints: set[str] | None = None,
) -> None:
    """
    Generate summaries for a video.

    Segmentation strategy:
      1. Creator-defined chapters  — use directly (YouTube chapters from description)
      2. No chapters, short video (≤20 min) — LLM detects 3–5 logical sections
      3. No chapters, long video (>20 min)  — fixed 5-min character windows

    Always generates:
      - One CHAPTER summary per segment (section_hint = segment title)
      - One CONCEPTS summary for the full transcript

    done_hints: section_hints already stored — skipped on resume.
    """
    from app.services.video.base import VideoContent as VC  # avoid circular import

    skip = done_hints or set()
    transcript = content.transcript
    duration = content.duration_seconds or 0

    logger.info("Starting video summarisation for %s (%s)", doc.id, doc.title)

    # ── Determine segments ────────────────────────────────────────────────────
    if content.chapters:
        segments = [(ch.title, ch.transcript) for ch in content.chapters if ch.transcript.strip()]
        logger.info("Using %d creator-defined chapters", len(segments))
    elif duration <= _SHORT_VIDEO_THRESHOLD:
        segments = await _llm_segment_transcript(transcript, provider)
        logger.info("LLM segmented into %d sections", len(segments))
    else:
        segments = _fixed_window_segments(transcript)
        logger.info("Fixed-window segmented into %d parts", len(segments))

    # ── Persist TOC so frontend can render outline immediately ────────────────
    toc_items = [
        {"type": "chapter", "title": title, "sections": []}
        for title, _ in segments
    ]
    doc.toc = toc_items
    doc.expected_summary_count = len(segments) + 1  # +1 for concepts
    db.commit()

    # ── Summarise each segment ────────────────────────────────────────────────
    for idx, (title, text) in enumerate(segments):
        if _is_deleted(doc, db):
            logger.info("Document %s was deleted — stopping summarisation", doc.id)
            return
        if title in skip:
            continue
        try:
            if len(text) > 15000:
                text = text[:15000]
            summary_text = await _complete_with_retry(
                provider,
                [
                    {"role": "system", "content": _VIDEO_SEGMENT_SUMMARY_SYSTEM},
                    {"role": "user", "content": f"Section: {title}\n\n{text}"},
                ],
                temperature=0.3,
            )
            _save_summary(db, doc, SummaryGranularity.CHAPTER, summary_text, title, sort_order=idx)
        except Exception as exc:
            logger.warning("Failed to summarise video segment '%s': %s", title, exc)

    # ── Key concepts from the full transcript ────────────────────────────────
    if SummaryGranularity.CONCEPTS.value not in skip:
        if _is_deleted(doc, db):
            logger.info("Document %s was deleted — stopping summarisation", doc.id)
            return
        try:
            full_sample = transcript[:20000]
            concepts_text = await _complete_with_retry(
                provider,
                [
                    {"role": "system", "content": _VIDEO_CONCEPTS_SYSTEM},
                    {"role": "user", "content": full_sample},
                ],
                temperature=0.3,
            )
            _save_summary(
                db, doc, SummaryGranularity.CONCEPTS, concepts_text,
                section_hint=None, sort_order=len(segments),
            )
        except Exception as exc:
            logger.error("Failed to generate video concepts for %s: %s", doc.id, exc)
