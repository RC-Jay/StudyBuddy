"""
Tests for video_classifier.classify_video.

All LLM calls are mocked — no live API calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.video_classifier import classify_video


def _provider(response: str) -> MagicMock:
    p = MagicMock()
    p.complete = AsyncMock(return_value=response)
    return p


LECTURE_TRANSCRIPT = "Today we'll be covering the fundamentals of quantum mechanics..."
VLOG_TRANSCRIPT = "Hey guys, welcome back to my channel! Today I'm unboxing the latest..."


# ─── Accepted videos ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_academic_lecture_accepted():
    await classify_video(LECTURE_TRANSCRIPT, _provider('{"academic": true}'))


@pytest.mark.asyncio
async def test_ted_talk_accepted():
    await classify_video(LECTURE_TRANSCRIPT, _provider('{"academic": true}'))


@pytest.mark.asyncio
async def test_no_academic_key_defaults_to_accepted():
    """Missing 'academic' key defaults to True — accept when uncertain."""
    await classify_video(LECTURE_TRANSCRIPT, _provider('{}'))


# ─── Rejected videos ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_entertainment_vlog_rejected():
    with pytest.raises(ValueError, match="does not appear to be academic"):
        await classify_video(VLOG_TRANSCRIPT, _provider('{"academic": false, "reason": "entertainment vlog"}'))


@pytest.mark.asyncio
async def test_cooking_rejected():
    with pytest.raises(ValueError, match="does not appear to be academic"):
        await classify_video("Welcome to today's recipe!", _provider('{"academic": false}'))


# ─── Error handling ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_json_accepts_by_default():
    """Unparseable response → accept (err on side of inclusion)."""
    await classify_video(LECTURE_TRANSCRIPT, _provider("I'm not sure, maybe academic"))


@pytest.mark.asyncio
async def test_malformed_json_with_false_rejects():
    """Raw text with 'false' → reject."""
    with pytest.raises(ValueError):
        await classify_video(VLOG_TRANSCRIPT, _provider("this is false, not academic, entertainment"))


@pytest.mark.asyncio
async def test_empty_response_accepts_by_default():
    """Empty response → accept (safe default)."""
    await classify_video(LECTURE_TRANSCRIPT, _provider(""))


@pytest.mark.asyncio
async def test_truncates_long_transcript():
    """Long transcripts don't crash — 8000-char truncation exercised."""
    long_transcript = "word " * 5000
    await classify_video(long_transcript, _provider('{"academic": true}'))
