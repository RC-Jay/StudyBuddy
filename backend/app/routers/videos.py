"""
Videos router.

POST /videos   — submit a video URL for ingestion.
                 Validates the URL, creates a Document record, and queues
                 the background processing pipeline.

The response is a DocumentOut (same shape as document uploads) so the
frontend can treat videos and documents uniformly in polling / display.
"""
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from app.enums import ProcessingStatus
from app.middleware.auth import get_current_user
from app.models.document import Document
from app.models.user import User
from app.repositories.document import DocumentRepository, get_document_repo
from app.schemas.document import DocumentOut
from app.services.video import get_video_loader
from app.services.video_processor import process_video

router = APIRouter(prefix="/videos", tags=["videos"])


class VideoSubmitIn(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL must start with http:// or https://")
        if not parsed.netloc:
            raise ValueError("Invalid URL — no host found")
        return v


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_video(
    body: VideoSubmitIn,
    background_tasks: BackgroundTasks,
    repo: DocumentRepository = Depends(get_document_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Submit a video URL for ingestion.

    Validates that a registered loader can handle the URL, then creates a
    Document record and starts the background processing pipeline.
    The transcript, title, and metadata are fetched asynchronously.
    """
    # Validate that we have a loader for this URL before accepting the request.
    # Keep the loader reference so we can record source_name without re-parsing the URL.
    try:
        loader = get_video_loader(body.url)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported video URL. Currently supported sources: "
                "YouTube (youtube.com, youtu.be) and TED (ted.com)."
            ),
        )

    # Create a placeholder Document row — title and metadata will be filled in
    # by the background pipeline once the video is fetched.
    placeholder_title = _url_to_placeholder_title(body.url)
    doc = repo.create(Document(
        user_id=current_user.id,
        file_name=body.url,          # use URL as the "filename" for videos
        title=placeholder_title,
        file_type="video",
        file_size_bytes=0,           # unknown until transcript is fetched
        blob_path="",                # no blob — transcript stored in vectorstore
        source_url=body.url,
        video_source=loader.source_name,  # "youtube" | "ted" | … — stored immediately
        processing_status=ProcessingStatus.PENDING,
    ))

    background_tasks.add_task(process_video, doc.id)
    return DocumentOut.from_orm(doc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _url_to_placeholder_title(url: str) -> str:
    """Generate a human-readable placeholder title from a video URL."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    if "youtube" in host or "youtu.be" in host:
        return "YouTube Video (loading…)"
    if "ted.com" in host:
        slug = parsed.path.rstrip("/").split("/")[-1]
        return slug.replace("_", " ").replace("-", " ").title() + " — TED Talk"
    return f"Video from {host} (loading…)"
