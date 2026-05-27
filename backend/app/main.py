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
from app.routers import auth, chat, collections, documents, quiz, summaries
from app.services.document_processor import recover_interrupted_documents


@asynccontextmanager
async def lifespan(app: FastAPI):
    await recover_interrupted_documents()
    yield


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
app.include_router(collections.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(quiz.router, prefix="/api/v1")
app.include_router(summaries.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
