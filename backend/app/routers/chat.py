import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.vectorstores import VectorStore

from app.middleware.auth import get_current_user
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.repositories.chat import ChatRepository, get_chat_repo
from app.schemas.chat import MessageIn, MessageOut, SessionCreate, SessionOut
from app.services.langchain_setup import get_vectorstore_dep
from app.services.llm import BaseChatProvider, get_provider_dep
from app.services.rag import build_citations, build_context, retrieve

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = """You are StudyBuddy, an AI study assistant. Answer questions ONLY using the provided source material.
Always cite the document name and page number when referencing specific content, like: [Source: "Document Title", p.12].
If the answer is not in the source material, say so clearly — do not invent information."""


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(
    body: SessionCreate,
    repo: ChatRepository = Depends(get_chat_repo),
    current_user: User = Depends(get_current_user),
):
    session = repo.create_session(ChatSession(
        user_id=current_user.id,
        scope_type=body.scope_type,
        scope_id=uuid.UUID(body.scope_id),
        title=body.title,
    ))
    return _session_out(session)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    repo: ChatRepository = Depends(get_chat_repo),
    current_user: User = Depends(get_current_user),
):
    return [_session_out(s) for s in repo.list_sessions_for_user(current_user.id)]


@router.get("/sessions/{session_id}", response_model=dict)
def get_session(
    session_id: uuid.UUID,
    repo: ChatRepository = Depends(get_chat_repo),
    current_user: User = Depends(get_current_user),
):
    session = _require_owned(repo, session_id, current_user.id)
    return {
        **_session_out(session).model_dump(),
        "messages": [_msg_out(m) for m in session.messages],
    }


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: uuid.UUID,
    body: MessageIn,
    repo: ChatRepository = Depends(get_chat_repo),
    provider: BaseChatProvider = Depends(get_provider_dep),
    vectorstore: VectorStore = Depends(get_vectorstore_dep),
    current_user: User = Depends(get_current_user),
):
    session = _require_owned(repo, session_id, current_user.id)

    # Persist user message
    repo.add_message(ChatMessage(session_id=session.id, role="user", content=body.content))

    # Retrieve relevant chunks
    chunks = await retrieve(
        repo.db, body.content, session.scope_type, session.scope_id,
        vectorstore=vectorstore,
    )
    context = build_context(chunks)
    citations = build_citations(chunks)

    # Build message history (last 20 messages for context)
    history = session.messages[-20:]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append({"role": "system", "content": f"SOURCE MATERIAL:\n\n{context}"})
    for msg in history[:-1]:  # exclude the user message we just added
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": body.content})

    # Stream response and persist the completed message
    async def stream_and_save():
        full_response: list[str] = []
        async for chunk in provider.stream(messages):
            full_response.append(chunk)
            yield f"data: {json.dumps({'delta': chunk})}\n\n"

        assistant_msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content="".join(full_response),
            citations=citations,
        )
        repo.add_message_no_flush(assistant_msg)
        repo.commit()

        yield f"data: {json.dumps({'done': True, 'citations': citations, 'message_id': str(assistant_msg.id)})}\n\n"

    return StreamingResponse(stream_and_save(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_owned(
    repo: ChatRepository, session_id: uuid.UUID, user_id: uuid.UUID
) -> ChatSession:
    session = repo.get_owned_session(session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _session_out(s: ChatSession) -> SessionOut:
    return SessionOut(
        id=str(s.id),
        scope_type=s.scope_type,
        scope_id=str(s.scope_id),
        title=s.title,
        created_at=s.created_at.isoformat(),
        message_count=len(s.messages),
    )


def _msg_out(m: ChatMessage) -> MessageOut:
    return MessageOut(
        id=str(m.id),
        role=m.role,
        content=m.content,
        citations=m.citations,
        created_at=m.created_at.isoformat(),
    )
