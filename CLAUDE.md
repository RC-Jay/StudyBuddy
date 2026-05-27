# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Monorepo layout

```
StudyBuddy/
├── backend/   Python · FastAPI · PostgreSQL + pgvector · Azure OpenAI
└── frontend/  TypeScript · Next.js 16 · Tailwind CSS v4
```

---

## Backend (`backend/`)

### Commands

```bash
# All commands run from backend/

# Install / sync dependencies
uv sync

# Run dev server (hot-reload)
.venv/bin/uvicorn app.main:app --reload

# Run full test suite
.venv/bin/pytest

# Run a single test file
.venv/bin/pytest tests/test_routers/test_chat_router.py -v

# Run a single test by name
.venv/bin/pytest -k "test_submit_scores_correctly" -v

# Database migrations
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "describe change"
.venv/bin/alembic downgrade -1
```

**Test database setup (one-time):**
```bash
createdb studybuddy_test
psql studybuddy_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
```
Tests use `studybuddy_test` — override via `TEST_DATABASE_URL` env var. Each test runs in a transaction that rolls back on teardown (`join_transaction_mode="create_savepoint"`).

### Architecture

**Layers (strict top-down dependency):**
1. **Routers** (`app/routers/`) — HTTP only: parse request, call repository/service, return schema. No SQL.
2. **Repositories** (`app/repositories/`) — all SQLAlchemy queries. Instantiated per-request via `Depends(get_xxx_repo)`. Expose a `.db` property when services need the session directly.
3. **Services** (`app/services/`) — business logic. Never import from routers.
4. **Models** (`app/models/`) — SQLAlchemy ORM models. Never import from routers or services.
5. **Schemas** (`app/schemas/`) — Pydantic request/response models, one file per domain.

**Provider Strategy Pattern — concerns are swappable behind stable interfaces:**

| Concern | Interface | Registry/Factory | Test doubles |
|---|---|---|---|
| OAuth providers | `BaseOAuthProvider` (`services/oauth/base.py`) | `_REGISTRY` dict + `get_oauth_provider(name)` / `register_oauth_provider()` | `MockOAuthProvider` subclass |
| Chat LLM | `BaseChatProvider` (`services/llm/base.py`) | `get_chat_provider()` + `get_provider_dep()` DI wrapper | `MockChatProvider` + `dependency_overrides` |
| Embeddings | LangChain `Embeddings` | `get_embeddings()` | — |
| Vector store | LangChain `VectorStore` | `get_vectorstore()` + `get_vectorstore_dep()` DI wrapper | `MagicMock` + `dependency_overrides` |
| File storage | `BaseStorageBackend` (`services/storage.py`) | `get_storage_backend()` | real filesystem (`tmp_path`) |
| Document loaders | `BaseDocumentLoader` (`services/document_loader.py`) | `get_loader(ext)` / `register_loader()` | `DebugPDFLoader`, `DebugDocxLoader` |

LLM/storage/vectorstore factories use `@lru_cache(maxsize=1)` — process-level singletons. OAuth and document loaders use a module-level `_REGISTRY` dict (no cache) so entries can be swapped at test time via `register_*()`.

**Auth flow:**
- **Google**: frontend `GoogleLogin` component → ID token → `POST /auth/google {"credential": id_token}` → `GoogleOAuthProvider.get_user_info()` verifies via `https://oauth2.googleapis.com/tokeninfo`
- **LinkedIn**: frontend redirects to LinkedIn → LinkedIn redirects to `/auth/callback?code=...` → `POST /auth/linkedin {"credential": code}` → `LinkedInOAuthProvider.get_user_info()` exchanges code for access token then fetches `/v2/userinfo`
- Both providers return `OAuthUser`; `upsert_user()` matches by `(oauth_provider, oauth_provider_id)`
- Router `POST /auth/{provider}` resolves the provider from the registry; `KeyError` → 404, `ProviderNotConfiguredError` → 500, `ValueError` → 401
- StudyBuddy issues its own short-lived JWT (15 min, in response body) and a rolling refresh token (7 days, httpOnly cookie `sb_refresh`)
- `get_current_user` FastAPI dependency (`middleware/auth.py`) validates the JWT on every protected request
- `RefreshToken` rows are stored hashed (SHA-256); rotation revokes the old token and issues a new one

**RAG pipeline (document upload → query):**
1. Upload → `save_file()` → create `Document` row with `processing_status=pending`
2. Background task: load bytes → `get_loader(file_type).load()` → `RecursiveCharacterTextSplitter` (512 tokens, 64 overlap, tiktoken `cl100k_base`) → `PGVector.add_documents()` → set status `ready`
3. Query: `rag.retrieve(db, query, scope_type, scope_id, vectorstore=...)` fetches top-k chunks via cosine similarity; for collection scope it first resolves document IDs from `CollectionDocument`
4. Chunks → `build_context()` for LLM prompt, `build_citations()` for response metadata

**Key design notes:**
- `rag.retrieve()` accepts an optional `vectorstore` keyword argument — always pass it from routers (injected via `get_vectorstore_dep`) so tests can override without touching the singleton
- LangChain manages its own tables (`langchain_pg_collection`, `langchain_pg_embedding`) — exclude from Alembic autogenerate
- Quiz question bank: questions are persisted and reused per `(scope_type, scope_id, format, difficulty)`. Flag filtering is **per-user** — `QuizRepository.get_bank_questions()` filters by `user_id`
- `User.id` is a UUID auto-generated on creation; identity is matched by `(oauth_provider, oauth_provider_id)` — a composite unique constraint on the `users` table

**Testing conventions:**
- No live LLM, embedding, blob, or OAuth calls in any test
- Router tests use the `client` fixture (`app.dependency_overrides` with `MockChatProvider` + mock vectorstore)
- OAuth router tests: register `MockOAuthProvider` via `register_oauth_provider()` — exercises the real registry path, no `patch()` on import paths
- Service tests patch `get_chat_provider` at call site; pass mock vectorstore directly
- For document loader tests, use `DebugPDFLoader` / `DebugDocxLoader` — strategy doubles registered via `register_loader()`, no mocking of internal library imports

### Key env vars

```env
DATABASE_URL=postgresql://localhost/studybuddy
JWT_SECRET_KEY=<long random string>
GOOGLE_CLIENT_ID=<your-google-client-id>.apps.googleusercontent.com
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_ENDPOINT=https://<resource>.cognitiveservices.azure.com/
STORAGE_BACKEND=local          # or "azure"
LLM_PROVIDER=azure_openai      # default
CORS_ORIGINS=http://localhost:3000
```

Azure API key goes in `.env` only — never in `.env.example` or committed files.

---

## Frontend (`frontend/`)

> ⚠️ This is **Next.js 16** — APIs and conventions differ from earlier versions. Read `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.

### Commands

```bash
# All commands run from frontend/

npm run dev      # dev server at http://localhost:3000
npm run build    # production build
npm run lint     # ESLint
```

### Architecture

**Route groups:**
- `src/app/(app)/library/` — unified workspace (two-column: library sidebar + workspace panel with Chat/Summarise/Quiz tabs); protected by `(app)/layout.tsx` auth guard
- `src/app/(app)/chat|quiz|summaries/` — redirect to `/library`
- `src/app/login/` — public login page (Google Sign-In button + LinkedIn button)
- `src/app/auth/callback/` — OAuth redirect handler; reads `?code=` from LinkedIn and posts to `/auth/linkedin`
- `src/app/page.tsx` — root redirect to `/library`

**Unified workspace layout:**
- Left: `LibrarySidebar` — documents + collections + upload; clicking an item sets `scope` in Zustand
- Right: tab switcher (Chat / Summarise / Quiz) — reads `scope` from Zustand; tab components are keyed by `scope.id` so they remount cleanly on scope change

**State and auth:**
- `src/lib/store.ts` — Zustand store; holds `user`, `isLoading`, `scope: WorkspaceScope | null`, `activeTab`
- `src/components/auth/AuthProvider.tsx` — on mount calls `refreshSession()` to rehydrate from the httpOnly refresh cookie; wraps the root layout
- `src/lib/auth.ts` — thin wrappers around the backend auth endpoints; calls `setAccessToken()` on successful login
- `src/lib/api.ts` — axios instance; attaches `Authorization` header from in-memory `accessToken`; 401 interceptor auto-calls `/auth/refresh` and retries once before redirecting to `/login`

**API client (`src/lib/api.ts`):**
- `NEXT_PUBLIC_API_URL` env var sets the backend base URL (default `http://localhost:8000`)
- `withCredentials: true` on all requests so the `sb_refresh` httpOnly cookie is sent
- Access token lives **in memory only** (not localStorage) — survives page navigation, not hard refresh (refresh cookie handles rehydration)

**Types:** `src/lib/types.ts` is the single source of truth for shared TypeScript interfaces.
