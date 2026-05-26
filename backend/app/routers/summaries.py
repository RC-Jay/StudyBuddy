import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.enums import SummaryGranularity
from app.middleware.auth import get_current_user
from app.models.summary import Summary
from app.models.user import User
from app.repositories.summary import SummaryRepository, get_summary_repo
from app.schemas.summary import SummaryOut, SummaryRequest
from app.services.llm import get_chat_provider
from app.services.rag import build_context, retrieve

router = APIRouter(prefix="/summaries", tags=["summaries"])

_PROMPTS: dict[SummaryGranularity, str] = {
    SummaryGranularity.FULL: "Write a comprehensive summary of the entire material, covering all major themes, arguments, and conclusions.",
    SummaryGranularity.CONCEPTS: "Extract and list the key concepts, terms, and ideas from the material as a structured bullet-point list.",
    SummaryGranularity.TLDR: "Write a single concise paragraph (3-5 sentences) summarising the most important point of the material.",
    SummaryGranularity.SECTION: "Summarise the following specific section or topic from the material: {section_hint}",
}


@router.post("", response_model=SummaryOut, status_code=201)
async def generate_summary(
    body: SummaryRequest,
    repo: SummaryRepository = Depends(get_summary_repo),
    current_user: User = Depends(get_current_user),
):
    if body.granularity == SummaryGranularity.SECTION and not body.section_hint:
        raise HTTPException(status_code=422, detail="section_hint is required when granularity is 'section'.")

    query = body.section_hint or f"{body.granularity} summary"
    chunks = await retrieve(repo._db, query, body.scope_type, uuid.UUID(body.scope_id), top_k=10)
    if not chunks:
        raise HTTPException(
            status_code=422,
            detail="No content found for the selected scope. Ensure documents are fully processed.",
        )

    instruction = _PROMPTS[body.granularity].format(section_hint=body.section_hint or "")
    content = await get_chat_provider().complete(
        [
            {
                "role": "system",
                "content": "You are an academic summariser. Summarise ONLY from the provided source material. Do not add outside knowledge.",
            },
            {
                "role": "user",
                "content": f"{instruction}\n\nSOURCE MATERIAL:\n{build_context(chunks)}",
            },
        ],
        temperature=0.2,
    )

    summary = repo.create(Summary(
        user_id=current_user.id,
        scope_type=body.scope_type,
        scope_id=uuid.UUID(body.scope_id),
        granularity=body.granularity,
        section_hint=body.section_hint,
        content=content,
    ))
    return _summary_out(summary)


@router.get("", response_model=list[SummaryOut])
def list_summaries(
    repo: SummaryRepository = Depends(get_summary_repo),
    current_user: User = Depends(get_current_user),
):
    return [_summary_out(s) for s in repo.list_for_user(current_user.id)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
