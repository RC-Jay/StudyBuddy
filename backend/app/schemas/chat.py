from __future__ import annotations

from pydantic import BaseModel

from app.enums import MessageRole, ScopeType


class SessionCreate(BaseModel):
    scope_type: ScopeType
    scope_id: str
    title: str | None = None


class MessageIn(BaseModel):
    content: str


class SessionOut(BaseModel):
    id: str
    scope_type: ScopeType
    scope_id: str
    title: str | None
    created_at: str
    message_count: int


class MessageOut(BaseModel):
    id: str
    role: MessageRole
    content: str
    citations: list | None
    created_at: str
