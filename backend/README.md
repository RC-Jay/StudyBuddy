# StudyBuddy — Backend

FastAPI backend for StudyBuddy, an AI-powered study assistant for college students. Handles authentication (via ChangePay), document ingestion, retrieval-augmented generation (RAG), chat, quiz generation, and summarisation.

---

## Tech Stack

| Concern | Choice |
|---|---|
| Framework | FastAPI |
| Language | Python 3.14 |
| ORM | SQLAlchemy 2.0 |
| Database | PostgreSQL 18 + pgvector |
| Migrations | Alembic |
| LLM | Azure OpenAI (GPT-4o-mini) |
| Embeddings | Azure OpenAI (text-embedding-3-large, 3072-dim) |
| Document parsing | PyMuPDF (PDF), python-docx (DOCX) |
| File storage | Local filesystem (dev) — swap to Azure Blob via env var |
| Auth | ChangePay credential APIs + StudyBuddy-issued JWT sessions |
| Package manager | uv |

---

## Prerequisites

- Python 3.14
- PostgreSQL 18 with the `pgvector` extension installed
- `uv` — install via `brew install uv` or `pip install uv`
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
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── user.py          # User, RefreshToken
│   │   ├── document.py      # Document, DocumentChunk (+ pgvector embedding)
│   │   ├── collection.py    # Collection, CollectionDocument
│   │   ├── chat.py          # ChatSession, ChatMessage
│   │   ├── quiz.py          # Question, QuestionFeedback, QuizSession
│   │   └── summary.py       # Summary
│   ├── routers/             # HTTP layer — one file per domain
│   │   ├── auth.py
│   │   ├── documents.py
│   │   ├── collections.py
│   │   ├── chat.py
│   │   ├── quiz.py
│   │   └── summaries.py
│   ├── services/            # Business logic layer
│   │   ├── changepay.py     # ChangePay auth API client
│   │   ├── auth.py          # JWT + refresh token management
│   │   ├── azure_openai.py  # Embedding + chat completion wrappers
│   │   ├── document_processor.py  # Text extraction, chunking, embedding
│   │   ├── rag.py           # pgvector retrieval, context + citation building
│   │   ├── quiz_engine.py   # Question bank, generation, short-answer eval
│   │   └── storage.py       # File storage abstraction (local / Azure Blob)
│   └── middleware/
│       └── auth.py          # get_current_user FastAPI dependency
├── alembic/                 # Migration scripts
├── alembic.ini
├── pyproject.toml
└── .env.example
```

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

CHANGEPAY_BASE_URL=https://api.test.changepay.in
CHANGEPAY_TPID=<your third-party ID>

AZURE_OPENAI_API_KEY=<your key>
AZURE_OPENAI_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_OPENAI_API_VERSION=2025-01-01-preview
AZURE_OPENAI_EMBEDDING_API_VERSION=2023-05-15

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
| `GET` | `/auth/otp/request?phone=` | No | Trigger an OTP SMS via ChangePay. In staging, the OTP is returned in the response body. |
| `POST` | `/auth/login/otp` | No | Submit phone + OTP. Returns access token + sets refresh cookie. |
| `POST` | `/auth/login/password` | No | Submit phone + password. Returns access token + sets refresh cookie. |
| `POST` | `/auth/refresh` | Cookie | Rotate the refresh token and issue a new access token. |
| `POST` | `/auth/logout` | Cookie | Revoke the refresh token. |

**Login flow:**
1. Call `/auth/otp/request` or go straight to `/auth/login/password`
2. On success, you receive a short-lived **access token** (15 min) in the response body and a **refresh token** in an httpOnly cookie (7-day rolling)
3. Use the access token in the `Authorization` header for all protected requests
4. When the access token expires, call `/auth/refresh` — the cookie is sent automatically

**User eligibility:** ChangePay accounts must have a `CUSTOMER` profile. Accounts without one are rejected at login.

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
1. File content is read from storage
2. Text is extracted page-by-page (PyMuPDF for PDF, python-docx for DOCX)
3. Text is split into ~512-token chunks with 64-token overlap, respecting sentence boundaries
4. Each chunk is embedded via Azure `text-embedding-3-large` (3072 dimensions)
5. Chunks and embeddings are stored in `document_chunks` (pgvector column)
6. `document.processing_status` is updated to `ready` on success or `failed` on error

Large documents (500+ pages) are supported — processing is batched to avoid memory issues. Poll `/status` to know when a document is ready to query.

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
| `CHANGEPAY_BASE_URL` | Yes | — | `https://api.test.changepay.in` (staging) or `https://api.changepay.in` (prod) |
| `CHANGEPAY_TPID` | Yes | — | Third-party ID issued by ChangePay |
| `AZURE_OPENAI_API_KEY` | Yes | — | Azure OpenAI API key |
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
