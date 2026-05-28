import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, chat, collections, documents, quiz, summaries, videos
from app.services.document_processor import recover_interrupted_documents
from app.services.video_processor import resume_video_summarisation


@asynccontextmanager
async def lifespan(app: FastAPI):
    await recover_interrupted_documents()
    await _recover_interrupted_videos()
    yield


async def _recover_interrupted_videos() -> None:
    """Resume any video documents left mid-flight by a previous server restart."""
    import asyncio

    from app.database import SessionLocal
    from app.enums import DocType, ProcessingStatus
    from app.models.document import Document

    db = SessionLocal()
    try:
        stuck = (
            db.query(Document)
            .filter(
                Document.doc_type == DocType.VIDEO.value,
                Document.processing_status.in_([
                    ProcessingStatus.PROCESSING,
                    ProcessingStatus.SUMMARISING,
                ]),
                Document.deleted_at.is_(None),
            )
            .all()
        )
        for doc in stuck:
            if doc.processing_status == ProcessingStatus.SUMMARISING:
                asyncio.create_task(resume_video_summarisation(doc.id))
            # PROCESSING videos: re-run full pipeline
            elif doc.processing_status == ProcessingStatus.PROCESSING:
                from app.services.langchain_setup import delete_document_embeddings
                from app.services.video_processor import process_video
                delete_document_embeddings(doc.id)
                doc.processing_status = ProcessingStatus.PENDING
                db.commit()
                asyncio.create_task(process_video(doc.id))
    finally:
        db.close()


app = FastAPI(title="StudyBuddy API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(videos.router, prefix="/api/v1")
app.include_router(collections.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(quiz.router, prefix="/api/v1")
app.include_router(summaries.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
