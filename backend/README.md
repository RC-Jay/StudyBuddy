# StudyBuddy — Backend

FastAPI backend for StudyBuddy, an AI-powered study assistant for college students. Handles authentication (Google and LinkedIn OAuth), document ingestion, retrieval-augmented generation (RAG), chat, quiz generation, and summarisation.

---

## Tech Stack

| Concern | Choice |
|---|---|
| Framework | FastAPI |
| Language | Python 3.14 |
| ORM | SQLAlchemy 2.0 |
| Database | PostgreSQL 18 + pgvector |
| Migrations | Alembic |
| LLM | Azure OpenAI GPT-4o-mini (swappable via `LLM_PROVIDER`) |
| Embeddings | Azure OpenAI text-embedding-3-large, 3072-dim (swappable) |
| Document ingestion | LangChain (pymupdf4llm for PDF, Docx2txtLoader for DOCX) |
| Video ingestion | youtube-transcript-api (transcripts), yt-dlp (metadata), httpx (TED scraping) |
| Vector store | LangChain PGVector — langchain-postgres (swappable) |
| File storage | Local filesystem (dev) — swap to Azure Blob via env var |
| Auth | Google / LinkedIn OAuth → StudyBuddy-issued JWT sessions |
| Package manager | uv |

---

## Prerequisites

- Python 3.14
- PostgreSQL 18 with the `pgvector` extension installed
- `uv` — install via `brew install uv` or `pip install uv`
- A Google OAuth 2.0 Client ID (see setup below)
- An Azure OpenAI resource with two deployments:
  - `gpt-4o-mini` for chat and quiz evaluation
  - `text-embedding-3-large` for document embeddings

---

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, router registration
│   ├── config.py            # Pydantic settings (reads from .env)
│   ├── database.py          # SQLAlchemy engine, session, Base
│   ├── enums.py             # All discriminated-field enumerations (ProcessingStatus, QuizFormat…)
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── user.py          # User, RefreshToken
│   │   ├── document.py      # Document metadata (embeddings live in LangChain's tables)
│   │   ├── collection.py    # Collection, CollectionDocument
│   │   ├── chat.py          # ChatSession, ChatMessage
│   │   ├── quiz.py          # Question, QuestionFeedback, QuizSession
│   │   └── summary.py       # Summary
│   ├── schemas/             # Pydantic request/response models (one file per domain)
│   │   ├── auth.py          # OAuthLoginBody, TokenResponse
│   │   ├── document.py      # DocumentOut, DocumentStatusOut
│   │   ├── collection.py    # CollectionIn, CollectionOut
│   │   ├── chat.py          # SessionCreate, SessionOut, MessageIn, MessageOut
│   │   ├── quiz.py          # QuizCreate, QuizOut, QuestionOut, AnswerSubmit
│   │   └── summary.py       # SummaryRequest, SummaryOut
│   ├── repositories/        # Data access layer — all SQLAlchemy queries live here
│   │   ├── document.py      # DocumentRepository
│   │   ├── collection.py    # CollectionRepository
│   │   ├── chat.py          # ChatRepository
│   │   ├── quiz.py          # QuizRepository
│   │   └── summary.py       # SummaryRepository
│   ├── routers/             # HTTP layer — thin: validate input, call repo/service, return schema
│   │   ├── auth.py
│   │   ├── documents.py
│   │   ├── videos.py
│   │   ├── collections.py
│   │   ├── chat.py
│   │   ├── quiz.py
│   │   └── summaries.py
│   ├── services/            # Business logic layer
│   │   ├── oauth/                 # OAuth provider abstraction (Strategy Pattern)
│   │   │   ├── base.py            #   OAuthUser, ProviderNotConfiguredError, BaseOAuthProvider
│   │   │   ├── google.py          #   GoogleOAuthProvider
│   │   │   ├── linkedin.py        #   LinkedInOAuthProvider
│   │   │   └── __init__.py        #   Registry: get_oauth_provider(), register_oauth_provider()
│   │   ├── llm/                   # Chat provider abstraction (Strategy Pattern)
│   │   │   ├── base.py            #   BaseChatProvider — abstract interface
│   │   │   └── azure_openai.py    #   AzureOpenAIChatProvider — concrete impl
│   │   ├── video/                 # Video loader abstraction (Strategy Pattern)
│   │   │   ├── base.py            #   VideoContent, VideoChapter, BaseVideoLoader
│   │   │   ├── youtube.py         #   YouTubeLoader — transcript API + oEmbed + yt-dlp
│   │   │   ├── ted.py             #   TEDLoader — scrapes __NEXT_DATA__ from ted.com
│   │   │   ├── registry.py        #   get_video_loader(url), register_video_loader()
│   │   │   └── __init__.py
│   │   ├── auth.py                # JWT + refresh token management, upsert_user
│   │   ├── auto_summariser.py     # summarise_book, summarise_paper, summarise_video
│   │   ├── document_classifier.py # LLM: classify doc as book/research_paper; reject non-academic
│   │   ├── document_loader.py     # Strategy pattern: file-type loaders (PDF, DOCX, extensible)
│   │   ├── document_processor.py  # Document ingestion pipeline orchestrator
│   │   ├── video_classifier.py    # LLM: classify video as academic; reject entertainment/news
│   │   ├── video_processor.py     # Video ingestion pipeline orchestrator
│   │   ├── langchain_setup.py     # Embeddings + vector store singletons (LangChain base types)
│   │   ├── rag.py                 # pgvector retrieval, context + citation building
│   │   ├── quiz_engine.py         # Question bank, generation, short-answer eval
│   │   └── storage.py             # File storage — Strategy Pattern (Local, Azure Blob, extensible)
│   └── middleware/
│       └── auth.py          # get_current_user FastAPI dependency
├── alembic/                 # Migration scripts
├── alembic.ini
├── pyproject.toml
└── .env.example
```

---

## Provider Architecture

Four concerns are deliberately kept behind stable interfaces so any implementation can be swapped without touching callers:

| Concern | Interface | Current impl | How to add a new one |
|---|---|---|---|
| **OAuth** | `BaseOAuthProvider` (`services/oauth/base.py`) | Google, LinkedIn | Subclass `BaseOAuthProvider`, call `register_oauth_provider(MyProvider())` |
| **Chat LLM** | `BaseChatProvider` (`services/llm/base.py`) | `AzureOpenAIChatProvider` | Subclass `BaseChatProvider`, add `elif` in `services/llm/__init__.py`, set `LLM_PROVIDER=<key>` |
| **File storage** | `BaseStorageBackend` (`services/storage.py`) | Local / Azure Blob | Subclass `BaseStorageBackend`, add `elif` in `get_storage_backend()`, set `STORAGE_BACKEND=<key>` |
| **Document loaders** | `BaseDocumentLoader` (`services/document_loader.py`) | PDF, DOCX | `register_loader("ext", MyLoader())` |
| **Video loaders** | `BaseVideoLoader` (`services/video/base.py`) | YouTube, TED | `register_video_loader(MyLoader())` — checked in registration order via `can_handle(url)` |
| **Embeddings** | LangChain `Embeddings` | `AzureOpenAIEmbeddings` | Replace return value in `langchain_setup.get_embeddings()` |
| **Vector store** | LangChain `VectorStore` | `PGVector` | Replace return value in `langchain_setup.get_vectorstore()` |

---

## Local Setup

### 1. Clone and enter the directory

```bash
cd backend
```

### 2. Create a virtual environment and install dependencies

```bash
uv venv
uv sync
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
DATABASE_URL=postgresql://localhost/studybuddy
JWT_SECRET_KEY=<a long random string>

# Google OAuth — https://console.cloud.google.com → Credentials → OAuth 2.0 Client IDs
GOOGLE_CLIENT_ID=<your-client-id>.apps.googleusercontent.com

# LinkedIn OAuth (optional — leave blank to disable LinkedIn login)
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_REDIRECT_URI=http://localhost:3000/auth/callback

AZURE_OPENAI_API_KEY=<your key>
AZURE_OPENAI_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large

STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./uploads
```

### 4. Prepare the database

Create the database and enable pgvector:

```bash
createdb studybuddy
psql studybuddy -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Run all migrations:

```bash
.venv/bin/alembic upgrade head
```

### 5. Start the development server

```bash
.venv/bin/uvicorn app.main:app --reload
```

The API is now running at `http://localhost:8000`.  
Interactive docs (Swagger UI) are at `http://localhost:8000/docs`.

---

## API Reference

All routes are prefixed with `/api/v1`. Protected routes require an `Authorization: Bearer <access_token>` header.

### Auth — `/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/{provider}` | No | Exchange an OAuth credential for a StudyBuddy access token. `provider` is `google` or `linkedin`. |
| `POST` | `/auth/refresh` | Cookie | Rotate the refresh token and issue a new access token. |
| `POST` | `/auth/logout` | Cookie | Revoke the refresh token. |

**Login flow:**
1. **Google** — frontend obtains an ID token from the `GoogleLogin` component, posts `{"credential": "<id_token>"}` to `/auth/google`
2. **LinkedIn** — frontend redirects to LinkedIn's auth URL, LinkedIn redirects back to `/auth/callback?code=...`, the callback page posts `{"credential": "<code>"}` to `/auth/linkedin`
3. On success, you receive a short-lived **access token** (15 min) in the response body and a **refresh token** in an httpOnly cookie (7-day rolling)
4. Use the access token in the `Authorization` header for all protected requests
5. When the access token expires, call `/auth/refresh` — the cookie is sent automatically

**Error codes:**
- `404` — unknown provider name
- `401` — credential is invalid, expired, or rejected by the provider
- `500` — provider is not configured on the server (missing env vars)

**Adding a new OAuth provider:**  
Create a class in `services/oauth/` that subclasses `BaseOAuthProvider` and implements `name` + `get_user_info(credential)`. Register it via `register_oauth_provider(MyProvider())`. No other files need changing.

---

### Documents — `/documents`

| Method | Path | Description |
|---|---|---|
| `POST` | `/documents` | Upload a PDF or DOCX (max 50 MB). Processing starts immediately in the background. Returns `202 Accepted`. |
| `GET` | `/documents` | List all documents for the current user (excludes deleted). |
| `GET` | `/documents/{id}` | Get metadata for a single document. |
| `GET` | `/documents/{id}/status` | Poll processing status: `pending` → `processing` → `ready` \| `failed`. |
| `DELETE` | `/documents/{id}` | Delete document — removes chunks, embeddings, and the file. |

**Document processing pipeline (runs as a background task):**
1. Raw file bytes are loaded from storage
2. A **loader strategy** is resolved for the file type (`document_loader.py`):
   - PDF → `pymupdf4llm.LangChainPDFLoader` — one `Document` per page, content as Markdown (preserves headings, tables, lists)
   - DOCX → `langchain-community` `Docx2txtLoader` — returns the full document as a single `Document`
3. Pages are split into ~512-token chunks with 64-token overlap using LangChain's `RecursiveCharacterTextSplitter` (token count is exact via tiktoken `cl100k_base`)
4. Each chunk's metadata is enriched with `document_id`, `document_title`, `chunk_index`, and `page`
5. Chunks are embedded and persisted to pgvector via LangChain `PGVector` (`add_documents`)
6. `document.processing_status` is updated to `ready` on success or `failed` on error

**LangChain-managed tables:** embeddings live in `langchain_pg_collection` and `langchain_pg_embedding` — these are created automatically by LangChain and excluded from Alembic autogenerate.

**Adding a new file type** (e.g. `.txt`, `.pptx`): subclass `BaseDocumentLoader` in `document_loader.py` and call `register_loader("ext", MyLoader())`. No changes needed in `document_processor.py`.

Poll `/documents/{id}/status` to know when a document is ready to query.

---

### Videos — `/videos`

| Method | Path | Description |
|---|---|---|
| `POST` | `/videos` | Submit a video URL for ingestion. Processing starts immediately in the background. Returns `202 Accepted`. |

Video resources are stored as `Document` rows (`file_type="video"`) and appear in `GET /documents` alongside uploaded files. All downstream endpoints (chat, quiz, summaries) work the same way — scope by the returned document ID.

**Supported sources:**
- **YouTube** (`youtube.com/watch?v=...`, `youtu.be/...`) — transcript fetched via the YouTube Transcript API (no API key required); metadata via oEmbed + yt-dlp; creator-defined chapters parsed from the video description
- **TED** (`ted.com/talks/...`) — transcript and metadata scraped from the talk page's embedded `__NEXT_DATA__` JSON (no API key required)

**Request body:**
```json
{ "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }
```

**Video ingestion pipeline (runs as a background task):**
1. `get_video_loader(url)` resolves the right loader strategy (TED checked before YouTube)
2. Loader fetches transcript + metadata — no video file is downloaded
3. LLM classifies the transcript as academic/educational; rejects entertainment, news, vlogs, etc.
4. Transcript is segmented: creator chapters → LLM detection (≤20 min) → fixed windows (>20 min)
5. Transcript segments become LangChain `Document` objects and are chunked + embedded like text documents
6. `summarise_video()` generates one summary per segment plus a key-concepts summary
7. `doc.toc` is stored as a flat chapter list so the frontend can show the Video Outline immediately

**Adding a new video source:** subclass `BaseVideoLoader` in `services/video/`, implement `can_handle(url)` and `load(url) → VideoContent`, then call `register_video_loader(MyLoader())`. No other files need changing.

---

### Collections — `/collections`

| Method | Path | Description |
|---|---|---|
| `POST` | `/collections` | Create a named collection. |
| `GET` | `/collections` | List all collections for the current user. |
| `GET` | `/collections/{id}` | Get a collection. |
| `PUT` | `/collections/{id}` | Rename a collection. |
| `DELETE` | `/collections/{id}` | Delete a collection (does not delete the documents inside). |
| `POST` | `/collections/{id}/documents/{doc_id}` | Add a document to a collection. |
| `DELETE` | `/collections/{id}/documents/{doc_id}` | Remove a document from a collection. |

A document can belong to multiple collections. Deleting a collection removes the grouping only.

---

### Chat — `/chat`

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat/sessions` | Create a chat session scoped to a document or collection. |
| `GET` | `/chat/sessions` | List all chat sessions. |
| `GET` | `/chat/sessions/{id}` | Get a session with its full message history. |
| `POST` | `/chat/sessions/{id}/messages` | Send a message. **Streams the response as Server-Sent Events.** |

**Session scope:**  
Pass `scope_type: "document"` + `scope_id: <document_id>` to chat against a single document.  
Pass `scope_type: "collection"` + `scope_id: <collection_id>` to chat across all documents in a collection.

**Streaming message format:**  
Each SSE event is a JSON object. There are two event types:
```
data: {"delta": "partial response text..."}   ← streamed as text arrives
data: {"done": true, "citations": [...], "message_id": "..."}   ← final event
```

**How a message is processed:**
1. User message is persisted
2. The query is embedded and the top 6 most relevant chunks are retrieved from pgvector (cosine similarity)
3. Chunks are assembled into a `SOURCE MATERIAL` context block with `[document, page]` references
4. The last 20 messages of conversation history are included for context
5. A system prompt instructs the model to answer only from the source material and to cite every claim
6. The response streams from Azure GPT-4o-mini back to the client via SSE
7. The full assistant message and citations are persisted once streaming completes

---

### Quiz — `/quiz`

| Method | Path | Description |
|---|---|---|
| `POST` | `/quiz/sessions` | Generate questions and start a quiz session. |
| `GET` | `/quiz/sessions` | List past quiz sessions. |
| `GET` | `/quiz/sessions/{id}` | Get a session. In exam mode, correct answers are hidden until submitted. |
| `POST` | `/quiz/sessions/{id}/submit` | Submit all answers. Returns scored results and explanations. |
| `POST` | `/quiz/questions/{id}/flag` | Flag a question as bad quality — hidden from this user's future sessions. |

**Creating a quiz session — request body:**
```json
{
  "mode": "practice",
  "scope_type": "document",
  "scope_id": "<uuid>",
  "format": "mcq",
  "difficulty": "intermediate",
  "question_count": 10,
  "topic_focus": "Chapter 3 methodology",
  "time_limit_seconds": 1800
}
```

| Field | Options |
|---|---|
| `mode` | `practice` (open-book, explanations visible) \| `exam` (closed-book, timed, debrief at end) |
| `format` | `mcq` \| `short_answer` \| `true_false` |
| `difficulty` | `introductory` (recall/comprehension) \| `intermediate` (apply/analyse) \| `advanced` (evaluate/synthesise) |

**Question bank:**  
Questions are persisted after generation and reused on subsequent requests for the same scope, format, and difficulty. This avoids redundant LLM calls and enables future spaced-repetition features. New questions are only generated to fill any shortfall in the requested count.

**Short-answer evaluation:**  
When a short-answer quiz is submitted, each answer is sent to GPT-4o-mini along with the question, the model answer, and retrieved source context. The model returns a `score` (0–100), `is_correct` (bool), and `feedback` with specific references to the source material.

---

### Summaries — `/summaries`

| Method | Path | Description |
|---|---|---|
| `POST` | `/summaries` | Generate and save a summary. |
| `GET` | `/summaries` | List all saved summaries. |

**Request body:**
```json
{
  "scope_type": "document",
  "scope_id": "<uuid>",
  "granularity": "section",
  "section_hint": "Chapter 4 — Results"
}
```

| Granularity | Description |
|---|---|
| `full` | Comprehensive summary of all major themes and conclusions |
| `tldr` | Single paragraph, the single most important point |
| `concepts` | Structured bullet-point list of key terms and ideas |
| `section` | Summary of a specific chapter or topic (requires `section_hint`) |

All summaries are grounded strictly in the uploaded material via RAG retrieval before calling the LLM.

---

## Adding a Migration

Whenever you change a model, generate and apply a migration:

```bash
.venv/bin/alembic revision --autogenerate -m "describe your change"
.venv/bin/alembic upgrade head
```

To roll back the last migration:

```bash
.venv/bin/alembic downgrade -1
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Yes | — | Secret used to sign access tokens — use a long random string in production |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifetime (rolling) |
| `GOOGLE_CLIENT_ID` | Yes | — | Google OAuth 2.0 client ID — create at console.cloud.google.com |
| `LINKEDIN_CLIENT_ID` | No | — | LinkedIn OAuth client ID — leave blank to disable LinkedIn login |
| `LINKEDIN_CLIENT_SECRET` | No | — | LinkedIn OAuth client secret |
| `LINKEDIN_REDIRECT_URI` | No | — | Must match the redirect URI registered in the LinkedIn app (e.g. `http://localhost:3000/auth/callback`) |
| `LLM_PROVIDER` | No | `azure_openai` | Chat backend. Add a new `BaseChatProvider` subclass in `services/llm/` and register it in `services/llm/__init__.py` |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated list of allowed CORS origins |
| `AZURE_OPENAI_API_KEY` | Yes | — | Azure OpenAI API key — keep in `.env` only, never commit |
| `AZURE_OPENAI_ENDPOINT` | Yes | — | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | No | `gpt-4o-mini` | Chat model deployment name |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | No | `text-embedding-3-large` | Embedding model deployment name |
| `AZURE_OPENAI_API_VERSION` | No | `2025-01-01-preview` | Chat API version |
| `AZURE_OPENAI_EMBEDDING_API_VERSION` | No | `2023-05-15` | Embedding API version |
| `STORAGE_BACKEND` | No | `local` | `local` for dev, `azure` for production |
| `LOCAL_STORAGE_PATH` | No | `./uploads` | Directory for local file storage |
| `AZURE_BLOB_CONNECTION_STRING` | If azure | — | Azure Blob Storage connection string |
| `AZURE_BLOB_CONTAINER` | No | `studybuddy-documents` | Blob container name |
| `ENVIRONMENT` | No | `development` | `development` or `production` |
| `MAX_FILE_SIZE_MB` | No | `50` | Maximum upload file size in MB |
