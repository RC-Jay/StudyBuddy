import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.services.azure_openai import chat_completion_stream
from app.services.rag import build_citations, build_context, retrieve

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = """You are StudyBuddy, an AI study assistant. Answer questions ONLY using the provided source material.
Always cite the document name and page number when referencing specific content, like: [Source: "Document Title", p.12].
If the answer is not in the source material, say so clearly — do not invent information."""


class SessionCreate(BaseModel):
    scope_type: str  # "document" | "collection"
    scope_id: str
    title: str | None = None


class MessageIn(BaseModel):
    content: str


class SessionOut(BaseModel):
    id: str
    scope_type: str
    scope_id: str
    title: str | None
    created_at: str
    message_count: int


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list | None
    created_at: str


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    session = ChatSession(
        user_id=current_user.id,
        scope_type=body.scope_type,
        scope_id=uuid.UUID(body.scope_id),
        title=body.title,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(session)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sessions = db.query(ChatSession).filter_by(user_id=current_user.id).order_by(ChatSession.created_at.desc()).all()
    return [_session_out(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=dict)
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    session = _get_owned_session(db, session_id, current_user.id)
    return {
        **_session_out(session).model_dump(),
        "messages": [_msg_out(m) for m in session.messages],
    }


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: uuid.UUID,
    body: MessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _get_owned_session(db, session_id, current_user.id)

    # Persist user message
    user_msg = ChatMessage(session_id=session.id, role="user", content=body.content)
    db.add(user_msg)
    db.commit()

    # Retrieve relevant chunks
    chunks = await retrieve(db, body.content, session.scope_type, session.scope_id)
    context = build_context(chunks)
    citations = build_citations(chunks)

    # Build message history for the LLM (last 10 turns for context)
    history = session.messages[-20:]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append({"role": "system", "content": f"SOURCE MATERIAL:\n\n{context}"})
    for msg in history[:-1]:  # exclude the message we just added
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": body.content})

    # Stream response and collect full text for persistence
    async def stream_and_save():
        full_response = []
        async for chunk in chat_completion_stream(messages):
            full_response.append(chunk)
            yield f"data: {json.dumps({'delta': chunk})}\n\n"

        # Persist assistant message after stream completes
        assistant_content = "".join(full_response)
        assistant_msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=assistant_content,
            citations=citations,
        )
        db.add(assistant_msg)
        db.commit()

        yield f"data: {json.dumps({'done': True, 'citations': citations, 'message_id': str(assistant_msg.id)})}\n\n"

    return StreamingResponse(stream_and_save(), media_type="text/event-stream")


def _get_owned_session(db: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> ChatSession:
    session = db.query(ChatSession).filter_by(id=session_id, user_id=user_id).first()
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
