from __future__ import annotations

from pydantic import BaseModel

from app.enums import Difficulty, QuizFormat, QuizMode, ScopeType


class QuizCreate(BaseModel):
    mode: QuizMode
    scope_type: ScopeType
    scope_id: str
    format: QuizFormat
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    question_count: int = 10
    topic_focus: str | None = None
    time_limit_seconds: int | None = None


class AnswerSubmit(BaseModel):
    answers: list[dict]


class QuestionOut(BaseModel):
    id: str
    format: QuizFormat
    difficulty: Difficulty
    stem: str
    options: list | None


class QuizOut(BaseModel):
    id: str
    mode: QuizMode
    scope_type: ScopeType
    scope_id: str
    config: dict
    question_ids: list
    score: int | None
    started_at: str
    completed_at: str | None
    time_limit_seconds: int | None
