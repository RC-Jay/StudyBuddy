import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.summary import Summary
from app.models.user import User
from app.services.llm import get_chat_provider
from app.services.rag import build_context, retrieve

router = APIRouter(prefix="/summaries", tags=["summaries"])

PROMPTS = {
    "full": "Write a comprehensive summary of the entire material, covering all major themes, arguments, and conclusions.",
    "concepts": "Extract and list the key concepts, terms, and ideas from the material as a structured bullet-point list.",
    "tldr": "Write a single concise paragraph (3-5 sentences) summarising the most important point of the material.",
    "section": "Summarise the following specific section or topic from the material: {section_hint}",
}


class SummaryRequest(BaseModel):
    scope_type: str
    scope_id: str
    granularity: str  # "full" | "section" | "concepts" | "tldr"
    section_hint: str | None = None


class SummaryOut(BaseModel):
    id: str
    scope_type: str
    scope_id: str
    granularity: str
    section_hint: str | None
    content: str
    created_at: str


@router.post("", response_model=SummaryOut, status_code=201)
async def generate_summary(
    body: SummaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.granularity not in PROMPTS:
        raise HTTPException(status_code=400, detail=f"granularity must be one of: {', '.join(PROMPTS)}")

    query = body.section_hint or f"{body.granularity} summary"
    chunks = await retrieve(db, query, body.scope_type, uuid.UUID(body.scope_id), top_k=10)
    if not chunks:
        raise HTTPException(status_code=422, detail="No content found for the selected scope. Ensure documents are fully processed.")

    context = build_context(chunks)
    instruction = PROMPTS[body.granularity].format(section_hint=body.section_hint or "")

    content = await get_chat_provider().complete(
        [
            {
                "role": "system",
                "content": "You are an academic summariser. Summarise ONLY from the provided source material. Do not add outside knowledge.",
            },
            {
                "role": "user",
                "content": f"{instruction}\n\nSOURCE MATERIAL:\n{context}",
            },
        ],
        temperature=0.2,
    )

    summary = Summary(
        user_id=current_user.id,
        scope_type=body.scope_type,
        scope_id=uuid.UUID(body.scope_id),
        granularity=body.granularity,
        section_hint=body.section_hint,
        content=content,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return _summary_out(summary)


@router.get("", response_model=list[SummaryOut])
def list_summaries(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    summaries = db.query(Summary).filter_by(user_id=current_user.id).order_by(Summary.created_at.desc()).all()
    return [_summary_out(s) for s in summaries]


def _summary_out(s: Summary) -> SummaryOut:
    return SummaryOut(
        id=str(s.id),
        scope_type=s.scope_type,
        scope_id=str(s.scope_id),
        granularity=s.granularity,
        section_hint=s.section_hint,
        content=s.content,
        created_at=s.created_at.isoformat(),
    )
