import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.quiz import Question, QuestionFeedback, QuizSession
from app.models.user import User
from app.services.quiz_engine import evaluate_short_answer, generate_questions
from app.services.rag import build_context, retrieve

router = APIRouter(prefix="/quiz", tags=["quiz"])


class QuizCreate(BaseModel):
    mode: str  # "practice" | "exam"
    scope_type: str
    scope_id: str
    format: str  # "mcq" | "short_answer" | "true_false"
    difficulty: str = "intermediate"
    question_count: int = 10
    topic_focus: str | None = None
    time_limit_seconds: int | None = None


class AnswerSubmit(BaseModel):
    answers: list[dict]  # [{"question_id": "...", "answer": "..."}]


class QuizOut(BaseModel):
    id: str
    mode: str
    scope_type: str
    scope_id: str
    config: dict
    question_ids: list
    score: int | None
    started_at: str
    completed_at: str | None
    time_limit_seconds: int | None


class QuestionOut(BaseModel):
    id: str
    format: str
    difficulty: str
    stem: str
    options: list | None


@router.post("/sessions", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_quiz_session(
    body: QuizCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    questions = await generate_questions(
        db=db,
        scope_type=body.scope_type,
        scope_id=uuid.UUID(body.scope_id),
        format=body.format,
        difficulty=body.difficulty,
        count=body.question_count,
        topic_focus=body.topic_focus,
    )

    session = QuizSession(
        user_id=current_user.id,
        mode=body.mode,
        scope_type=body.scope_type,
        scope_id=uuid.UUID(body.scope_id),
        config={
            "format": body.format,
            "difficulty": body.difficulty,
            "question_count": body.question_count,
            "topic_focus": body.topic_focus,
        },
        question_ids=[str(q.id) for q in questions],
        time_limit_seconds=body.time_limit_seconds,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # In exam mode, strip correct answers from the question payload
    question_list = [
        QuestionOut(id=str(q.id), format=q.format, difficulty=q.difficulty, stem=q.stem, options=q.options)
        for q in questions
    ]

    return {"session": _quiz_out(session), "questions": [q.model_dump() for q in question_list]}


@router.get("/sessions", response_model=list[QuizOut])
def list_quiz_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sessions = db.query(QuizSession).filter_by(user_id=current_user.id).order_by(QuizSession.started_at.desc()).all()
    return [_quiz_out(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=dict)
def get_quiz_session(session_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    session = _get_owned_session(db, session_id, current_user.id)
    questions = db.query(Question).filter(Question.id.in_([uuid.UUID(qid) for qid in session.question_ids])).all()

    is_completed = session.completed_at is not None
    question_data = []
    for q in questions:
        q_dict = QuestionOut(id=str(q.id), format=q.format, difficulty=q.difficulty, stem=q.stem, options=q.options).model_dump()
        # Only include answers/explanations after completion
        if is_completed or session.mode == "practice":
            q_dict["correct_answer"] = q.correct_answer
            q_dict["explanation"] = q.explanation
        question_data.append(q_dict)

    return {"session": _quiz_out(session), "questions": question_data, "answers": session.answers}


@router.post("/sessions/{session_id}/submit", response_model=dict)
async def submit_quiz(
    session_id: uuid.UUID,
    body: AnswerSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _get_owned_session(db, session_id, current_user.id)
    if session.completed_at:
        raise HTTPException(status_code=400, detail="Quiz already submitted")

    questions = {str(q.id): q for q in db.query(Question).filter(Question.id.in_([uuid.UUID(qid) for qid in session.question_ids])).all()}
    results = []
    total_score = 0

    for answer in body.answers:
        qid = answer["question_id"]
        user_answer = answer["answer"]
        q = questions.get(qid)
        if not q:
            continue

        if q.format == "short_answer":
            chunks = await retrieve(db, q.stem, session.scope_type, session.scope_id, top_k=4)
            context_text = build_context(chunks)
            eval_result = await evaluate_short_answer(q, user_answer, context_text)
            is_correct = eval_result.get("is_correct", False)
            score_contribution = eval_result.get("score", 0)
            feedback = eval_result.get("feedback", "")
            correct_answer = eval_result.get("correct_answer_summary", q.correct_answer)
        else:
            is_correct = user_answer.strip().lower() == q.correct_answer.strip().lower()
            score_contribution = 100 if is_correct else 0
            feedback = None
            correct_answer = q.correct_answer

        total_score += score_contribution
        results.append({
            "question_id": qid,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "score": score_contribution,
            "feedback": feedback,
            "explanation": q.explanation,
        })

    session.answers = results
    session.score = total_score // len(results) if results else 0
    session.completed_at = datetime.now(timezone.utc)
    db.commit()

    return {"session": _quiz_out(session), "results": results, "overall_score": session.score}


@router.post("/questions/{question_id}/flag", status_code=status.HTTP_204_NO_CONTENT)
def flag_question(question_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.get(Question, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    existing = db.query(QuestionFeedback).filter_by(question_id=question_id, user_id=current_user.id).first()
    if existing:
        existing.flagged_bad_quality = True
    else:
        db.add(QuestionFeedback(question_id=question_id, user_id=current_user.id, flagged_bad_quality=True))
    db.commit()


def _get_owned_session(db: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> QuizSession:
    session = db.query(QuizSession).filter_by(id=session_id, user_id=user_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Quiz session not found")
    return session


def _quiz_out(s: QuizSession) -> QuizOut:
    return QuizOut(
        id=str(s.id),
        mode=s.mode,
        scope_type=s.scope_type,
        scope_id=str(s.scope_id),
        config=s.config,
        question_ids=s.question_ids,
        score=s.score,
        started_at=s.started_at.isoformat(),
        completed_at=s.completed_at.isoformat() if s.completed_at else None,
        time_limit_seconds=s.time_limit_seconds,
    )
