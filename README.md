# StudyBuddy

An AI-powered study assistant for college students. Upload your textbooks, research papers, and lecture notes — then interact with them through an intelligent agent that helps you understand, retain, and test your knowledge.

---

## What it does

**Supported content types**  
Only academic/technical material is accepted. An LLM classifies each submission on upload. Rejected content receives a specific error message explaining why:
- *Wrong document type* — invoices, slide decks, forms, manuals, etc.
- *Non-academic book* — fiction, biographies, self-help, comics, cookbooks, and other general-interest books that wouldn't be used as course material.
- *Non-academic video* — entertainment, news, vlogs, and other content not tied to an academic discipline.

Accepted document types: textbooks, technical references, academic monographs, research papers, journal articles, theses, dissertations.  
Accepted video sources: **YouTube** and **TED** talks. Submit by URL — no file upload required. The system is designed to add new sources (Vimeo, direct video files, Coursera) by registering one new loader class with no other code changes.

**Chat with your documents**  
Ask questions about your uploaded material and get answers grounded strictly in the source text, with citations back to the exact document and page number.

**Auto-generated summaries**  
Summaries are generated automatically during document processing — no manual trigger needed.
- *Books* — the pipeline extracts the table of contents using PyMuPDF font-size and coordinate analysis (no LLM required), falling back to an LLM parse, then a regex heading scan, then an equal-split as last resort. The extracted TOC is stored against the document and immediately rendered as a **Book Outline** in the Summaries tab — showing the full Part → Chapter → Section hierarchy before any summaries are generated. Summaries are then generated section by section and appear progressively as each one completes.
- *Research papers* — generates a full prose summary and a numbered key-concepts list.
- *Videos* — segments the transcript into logical sections (using creator-defined chapters if available, LLM detection for short videos ≤20 min, or fixed time windows for longer ones), then summarises each segment. A key-concepts list is also generated for the full transcript. The **Video Outline** appears in the Summaries tab with the same progressive overlay as books.

**Quiz yourself**  
Generate multiple choice, short answer, or true/false questions from your material. Questions are stored in a bank and reused across sessions. Difficulty levels map to Bloom's taxonomy — from recall all the way up to evaluation and synthesis.

**Exam mode**  
A closed-book, timed quiz that simulates real exam conditions. Source documents are inaccessible during the session. A full debrief with scores, correct answers, and explanations is shown at the end.

**Collections**  
Organise documents into named collections (e.g. "Organic Chemistry Midterm") and query across all of them in a single chat or quiz session. Documents can be added or removed from collections directly in the workspace.

---

## How it's built

The project is a monorepo with two packages:

| Package | Stack |
|---|---|
| `backend/` | Python · FastAPI · PostgreSQL + pgvector · Azure OpenAI |
| `frontend/` | TypeScript · Next.js 16 · Tailwind CSS |

**AI layer** — All AI workloads run through Azure OpenAI. GPT-4o-mini handles chat, quiz generation, short-answer evaluation, summarisation, and video classification. text-embedding-3-large (3072 dimensions) handles embeddings for both documents and video transcripts.

**RAG pipeline** — Documents and video transcripts are classified, extracted/fetched, split into overlapping 512-token chunks (tiktoken cl100k_base), and embedded. At query time the most relevant chunks are retrieved from pgvector using cosine similarity and injected as source context into the LLM prompt. Embedding is rate-limit-aware: chunks are batched at ~200K tokens per batch with a 65-second pause between batches, and a process-level semaphore serialises concurrent uploads to stay within Azure's 250K tokens/minute cap.

**Processing pipeline** — Documents move through four statuses: `pending` → `processing` (text extraction + embedding) → `summarising` (auto-summary generation) → `ready`. The workspace unlocks for Chat and Quiz as soon as the `summarising` phase begins; summaries appear in the Summaries tab progressively as each chapter completes.

**Auth** — Users sign in with Google or LinkedIn via OAuth. On success, StudyBuddy issues its own short-lived JWT (15 min) and a rolling refresh token (7 days) stored in an httpOnly cookie. OAuth providers are implemented as a Strategy Pattern — adding a new provider is a single subclass with no changes to the router or auth service.

---

## Repo structure

```
StudyBuddy/
├── backend/      # FastAPI API server
│   └── README.md # Backend setup, API reference, environment variables
└── frontend/     # Next.js web app
    └── README.md # Frontend setup and environment variables
```

See the [backend README](./backend/README.md) for full setup instructions, API documentation, and environment variable reference.
