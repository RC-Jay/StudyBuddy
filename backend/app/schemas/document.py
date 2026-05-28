from __future__ import annotations

from pydantic import BaseModel

from app.enums import ProcessingStatus


class DocumentOut(BaseModel):
    id: str
    file_name: str
    title: str
    file_type: str
    page_count: int | None
    file_size_bytes: int
    processing_status: ProcessingStatus
    processing_error: str | None
    doc_type: str | None
    expected_summary_count: int | None
    toc: list | None
    # Video-specific fields (None for documents)
    source_url: str | None
    video_source: str | None   # "youtube" | "ted" | … — set at submission time
    duration_seconds: int | None
    thumbnail_url: str | None
    created_at: str

    @classmethod
    def from_orm(cls, doc) -> DocumentOut:
        return cls(
            id=str(doc.id),
            file_name=doc.file_name,
            title=doc.title,
            file_type=doc.file_type,
            page_count=doc.page_count,
            file_size_bytes=doc.file_size_bytes,
            processing_status=doc.processing_status,
            processing_error=doc.processing_error,
            doc_type=doc.doc_type,
            expected_summary_count=doc.expected_summary_count,
            toc=doc.toc,
            source_url=getattr(doc, "source_url", None),
            video_source=getattr(doc, "video_source", None),
            duration_seconds=getattr(doc, "duration_seconds", None),
            thumbnail_url=getattr(doc, "thumbnail_url", None),
            created_at=doc.created_at.isoformat(),
        )


class DocumentRenameIn(BaseModel):
    title: str


class DocumentStatusOut(BaseModel):
    status: ProcessingStatus
    error: str | None
