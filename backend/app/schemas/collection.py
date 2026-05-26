from __future__ import annotations

from pydantic import BaseModel


class CollectionIn(BaseModel):
    name: str


class CollectionOut(BaseModel):
    id: str
    name: str
    created_at: str
    document_count: int

    @classmethod
    def from_orm(cls, col) -> CollectionOut:
        return cls(
            id=str(col.id),
            name=col.name,
            created_at=col.created_at.isoformat(),
            document_count=len(col.document_links),
        )
