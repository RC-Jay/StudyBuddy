import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.middleware.auth import get_current_user
from app.models.quiz import QuizSession
from app.models.user import User
from app.repositories.quiz import QuizRepository, get_quiz_repo
from app.schemas.quiz import AnswerSubmit, QuestionOut, QuizCreate, QuizOut
from app.services.quiz_engine import evaluate_short_answer, generate_questions
from app.services.rag import build_context, retrieve

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/sessions", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_quiz_session(
    body: QuizCreate,
    repo: QuizRepository = Depends(get_quiz_repo),
    current_user: User = Depends(get_current_user),
):
    questions = await generate_questions(
        quiz_repo=repo,
        user_id=current_user.id,
        scope_type=body.scope_type,
        scope_id=uuid.UUID(body.scope_id),
        format=body.format,
        difficulty=body.difficulty,
        count=body.question_count,
        topic_focus=body.topic_focus,
    )

    session = repo.create_session(QuizSession(
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
    ))

    question_list = [
        QuestionOut(id=str(q.id), format=q.format, difficulty=q.difficulty, stem=q.stem, options=q.options)
        for q in questions
    ]
    return {"session": _quiz_out(session), "questions": [q.model_dump() for q in question_list]}


@router.get("/sessions", response_model=list[QuizOut])
def list_quiz_sessions(
    repo: QuizRepository = Depends(get_quiz_repo),
    current_user: User = Depends(get_current_user),
):
    return [_quiz_out(s) for s in repo.list_sessions_for_user(current_user.id)]


@router.get("/sessions/{session_id}", response_model=dict)
def get_quiz_session(
    session_id: uuid.UUID,
    repo: QuizRepository = Depends(get_quiz_repo),
    current_user: User = Depends(get_current_user),
):
    session = _require_owned(repo, session_id, current_user.id)
    questions = repo.get_questions_by_ids(
        [uuid.UUID(qid) for qid in session.question_ids]
    )

    is_completed = session.completed_at is not None
    question_data = []
    for q in questions:
        q_dict = QuestionOut(
            id=str(q.id), format=q.format, difficulty=q.difficulty, stem=q.stem, options=q.options
        ).model_dump()
        if is_completed or session.mode == "practice":
            q_dict["correct_answer"] = q.correct_answer
            q_dict["explanation"] = q.explanation
        question_data.append(q_dict)

    return {"session": _quiz_out(session), "questions": question_data, "answers": session.answers}


@router.post("/sessions/{session_id}/submit", response_model=dict)
async def submit_quiz(
    session_id: uuid.UUID,
    body: AnswerSubmit,
    repo: QuizRepository = Depends(get_quiz_repo),
    current_user: User = Depends(get_current_user),
):
    session = _require_owned(repo, session_id, current_user.id)
    if session.completed_at:
        raise HTTPException(status_code=400, detail="Quiz already submitted")

    questions = {
        str(q.id): q
        for q in repo.get_questions_by_ids([uuid.UUID(qid) for qid in session.question_ids])
    }
    results = []
    total_score = 0

    for answer in body.answers:
        qid = answer["question_id"]
        user_answer = answer["answer"]
        q = questions.get(qid)
        if not q:
            continue

        if q.format == "short_answer":
            chunks = await retrieve(repo.db, q.stem, session.scope_type, session.scope_id, top_k=4)
            eval_result = await evaluate_short_answer(q, user_answer, build_context(chunks))
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

    overall_score = total_score // len(results) if results else 0
    repo.complete_session(session, results, overall_score)

    return {"session": _quiz_out(session), "results": results, "overall_score": session.score}


@router.post("/questions/{question_id}/flag", status_code=status.HTTP_204_NO_CONTENT)
def flag_question(
    question_id: uuid.UUID,
    repo: QuizRepository = Depends(get_quiz_repo),
    current_user: User = Depends(get_current_user),
):
    if not repo.get_question(question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    repo.upsert_flag(question_id, current_user.id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_owned(
    repo: QuizRepository, session_id: uuid.UUID, user_id: uuid.UUID
) -> QuizSession:
    session = repo.get_owned_session(session_id, user_id)
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
