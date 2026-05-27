from __future__ import annotations

from pydantic import BaseModel


class CollectionIn(BaseModel):
    name: str


class CollectionOut(BaseModel):
    id: str
    name: str
    created_at: str
    document_count: int
    document_ids: list[str]

    @classmethod
    def from_orm(cls, col) -> CollectionOut:
        return cls(
            id=str(col.id),
            name=col.name,
            created_at=col.created_at.isoformat(),
            document_count=len(col.document_links),
            document_ids=[str(link.document_id) for link in col.document_links],
        )
