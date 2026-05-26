from __future__ import annotations

from pydantic import BaseModel

from app.enums import ScopeType, SummaryGranularity


class SummaryRequest(BaseModel):
    scope_type: ScopeType
    scope_id: str
    granularity: SummaryGranularity
    section_hint: str | None = None


class SummaryOut(BaseModel):
    id: str
    scope_type: ScopeType
    scope_id: str
    granularity: SummaryGranularity
    section_hint: str | None
    content: str
    created_at: str
