from __future__ import annotations

from pydantic import BaseModel

from app.enums import ProcessingStatus


class DocumentOut(BaseModel):
    id: str
    title: str
    file_type: str
    page_count: int | None
    file_size_bytes: int
    processing_status: ProcessingStatus
    processing_error: str | None
    doc_type: str | None
    created_at: str

    @classmethod
    def from_orm(cls, doc) -> DocumentOut:
        return cls(
            id=str(doc.id),
            title=doc.title,
            file_type=doc.file_type,
            page_count=doc.page_count,
            file_size_bytes=doc.file_size_bytes,
            processing_status=doc.processing_status,
            processing_error=doc.processing_error,
            doc_type=doc.doc_type,
            created_at=doc.created_at.isoformat(),
        )


class DocumentStatusOut(BaseModel):
    status: ProcessingStatus
    error: str | None
