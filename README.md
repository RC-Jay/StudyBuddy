# StudyBuddy

An AI-powered study assistant for college students. Upload your textbooks, research papers, and lecture notes — then interact with them through an intelligent agent that helps you understand, retain, and test your knowledge.

StudyBuddy is a companion application to [ChangePay](https://changepay.in), a college eCommerce platform. Users log in with their existing ChangePay credentials — no separate registration required.

---

## What it does

**Chat with your documents**  
Ask questions about your uploaded material and get answers grounded strictly in the source text, with citations back to the exact document and page number.

**Summarise**  
Generate a full summary, a one-paragraph TLDR, a key concepts list, or a summary of a specific chapter or section — on demand.

**Quiz yourself**  
Generate multiple choice, short answer, or true/false questions from your material. Questions are stored in a bank and reused across sessions. Difficulty levels map to Bloom's taxonomy — from recall all the way up to evaluation and synthesis.

**Exam mode**  
A closed-book, timed quiz that simulates real exam conditions. Source documents are inaccessible during the session. A full debrief with scores, correct answers, and explanations is shown at the end.

**Collections**  
Organise documents into named collections (e.g. "Organic Chemistry Midterm") and query across all of them in a single chat or quiz session.

---

## How it's built

The project is a monorepo with two packages:

| Package | Stack |
|---|---|
| `backend/` | Python · FastAPI · PostgreSQL + pgvector · Azure OpenAI |
| `frontend/` | TypeScript · Next.js 16 · Tailwind CSS |

**AI layer** — All AI workloads run through Azure OpenAI. GPT-4o-mini handles chat, quiz generation, short-answer evaluation, and summarisation. text-embedding-3-large (3072 dimensions) handles document embeddings for retrieval.

**RAG pipeline** — Uploaded documents are extracted, split into overlapping chunks, and embedded. At query time the most relevant chunks are retrieved from pgvector using cosine similarity and injected as source context into the LLM prompt.

**Auth** — StudyBuddy has no user database of its own. Login calls the ChangePay credential APIs (password or OTP). On success, StudyBuddy issues its own short-lived JWT (15 min) and a rolling refresh token (7 days) stored in an httpOnly cookie.

---

## Repo structure

```
StudyBuddy/
├── backend/      # FastAPI API server
│   └── README.md # Backend setup, API reference, environment variables
└── frontend/     # Next.js web app
```

See the [backend README](./backend/README.md) for full setup instructions, API documentation, and environment variable reference.
