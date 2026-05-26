"""
Generates, persists, and evaluates quiz questions.
Questions are stored in the question bank and reused across sessions.
"""
import json
import uuid

from sqlalchemy.orm import Session

from app.models.quiz import Question, QuestionFeedback
from app.services.llm import get_chat_provider
from app.services.rag import build_context, retrieve

SYSTEM_PROMPT = """You are an exam question writer. Generate questions ONLY from the provided source material.
Respond with a valid JSON array of question objects — no markdown, no commentary, only the JSON array.
Each object must have these fields:
  format: "mcq" | "short_answer" | "true_false"
  stem: string
  options: array of 4 strings (MCQ only, null otherwise)
  correct_answer: string
  explanation: string (cite document and page)
  topic_tags: array of strings
  source_page_range: string like "12-14" or "7"
"""


async def generate_questions(
    db: Session,
    scope_type: str,
    scope_id: uuid.UUID,
    format: str,
    difficulty: str,
    count: int,
    topic_focus: str | None,
) -> list[Question]:
    # First try to serve from the bank
    flagged_subquery = db.query(QuestionFeedback.question_id).filter_by(flagged_bad_quality=True)
    existing = (
        db.query(Question)
        .filter(
            Question.scope_type == scope_type,
            Question.scope_id == scope_id,
            Question.format == format,
            Question.difficulty == difficulty,
            Question.id.notin_(flagged_subquery),
        )
        .all()
    )

    if len(existing) >= count:
        return existing[:count]

    needed = count - len(existing)
    query = topic_focus or f"{difficulty} level {format} questions"
    chunks = await retrieve(db, query, scope_type, scope_id, top_k=8)
    if not chunks:
        return existing

    context = build_context(chunks)
    difficulty_desc = {
        "introductory": "recall and comprehension (Bloom's L1-L2)",
        "intermediate": "application and analysis (Bloom's L3-L4)",
        "advanced": "evaluation and synthesis (Bloom's L5-L6)",
    }.get(difficulty, "intermediate")

    focus_note = f" Focus specifically on: {topic_focus}." if topic_focus else ""

    user_prompt = f"""Generate exactly {needed} {format.replace('_', ' ')} questions at {difficulty_desc} difficulty.{focus_note}

SOURCE MATERIAL:
{context}

Rules:
- MCQ: 4 options, exactly one correct, plausible distractors drawn from the material
- short_answer: open-ended, requires 2-4 sentence answer
- true_false: clear true or false statement from the material
- Every explanation must cite the source document and page
"""

    raw = await get_chat_provider().complete(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,
    )

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        items = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        return existing

    new_questions = []
    for item in items[:needed]:
        q = Question(
            scope_type=scope_type,
            scope_id=scope_id,
            format=item.get("format", format),
            difficulty=difficulty,
            topic_tags=item.get("topic_tags", []),
            stem=item["stem"],
            options=item.get("options"),
            correct_answer=item["correct_answer"],
            explanation=item["explanation"],
            source_page_range=item.get("source_page_range"),
        )
        db.add(q)
        new_questions.append(q)

    db.commit()
    for q in new_questions:
        db.refresh(q)

    return existing + new_questions


async def evaluate_short_answer(question: Question, user_answer: str, context_chunks_text: str) -> dict:
    prompt = f"""Question: {question.stem}
Correct answer guidance: {question.correct_answer}
Source context: {context_chunks_text[:2000]}

Student's answer: {user_answer}

Evaluate the student's answer. Respond with JSON:
{{
  "is_correct": true/false,
  "score": 0-100,
  "feedback": "specific feedback referencing the source material",
  "correct_answer_summary": "concise correct answer"
}}
"""
    raw = await get_chat_provider().complete(
        [
            {"role": "system", "content": "You are a fair and constructive exam grader. Respond only with the JSON object."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    try:
        raw = raw.strip().lstrip("```json").rstrip("```").strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"is_correct": False, "score": 0, "feedback": raw, "correct_answer_summary": question.correct_answer}
