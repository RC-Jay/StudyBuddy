"""
Tests for the video loader registry and base behaviour.

Network calls are mocked — no live HTTP requests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.video.base import BaseVideoLoader, VideoChapter, VideoContent
from app.services.video.registry import get_video_loader, register_video_loader
from app.services.video.youtube import (
    YouTubeLoader,
    _extract_video_id,
    _parse_chapters_from_description,
    _build_chapters,
)
from app.services.video.ted import TEDLoader, _extract_slug


# ─── Video ID / slug extraction ───────────────────────────────────────────────

def test_youtube_extract_id_standard():
    assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_youtube_extract_id_short():
    assert _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_youtube_extract_id_with_extra_params():
    assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s") == "dQw4w9WgXcQ"


def test_youtube_extract_id_invalid():
    assert _extract_video_id("https://vimeo.com/12345") is None


def test_ted_extract_slug():
    assert _extract_slug("https://www.ted.com/talks/ken_robinson_says_schools_kill_creativity") == \
        "ken_robinson_says_schools_kill_creativity"


def test_ted_extract_slug_invalid():
    assert _extract_slug("https://youtube.com/watch?v=abc") is None


# ─── Chapter parsing from description ────────────────────────────────────────

def test_parse_chapters_standard():
    desc = "0:00 Introduction\n3:24 Main Content\n10:05 Summary"
    chapters = _parse_chapters_from_description(desc)
    assert len(chapters) == 3
    assert chapters[0] == (0, "Introduction")
    assert chapters[1] == (204, "Main Content")
    assert chapters[2] == (605, "Summary")


def test_parse_chapters_with_hours():
    desc = "0:00 Intro\n1:00:00 Second Hour"
    chapters = _parse_chapters_from_description(desc)
    assert chapters[1] == (3600, "Second Hour")


def test_parse_chapters_no_timestamps():
    assert _parse_chapters_from_description("No timestamps here") == []


def test_parse_chapters_not_starting_at_zero():
    """Chapter list that doesn't start at 0:00 is not a valid chapter list."""
    desc = "1:00 Something\n5:00 Another"
    assert _parse_chapters_from_description(desc) == []


def test_parse_chapters_single_chapter_ignored():
    """Single chapter is not useful — should return empty."""
    desc = "0:00 Only Chapter"
    assert _parse_chapters_from_description(desc) == []


# ─── Chapter building ─────────────────────────────────────────────────────────

def test_build_chapters_proportional_slice():
    transcript = "A" * 1000
    timestamps = [(0, "Intro"), (300, "Main"), (600, "Outro")]
    chapters = _build_chapters(timestamps, transcript, duration=900)
    assert len(chapters) == 3
    assert chapters[0].title == "Intro"
    assert chapters[0].start_seconds == 0
    assert chapters[0].end_seconds == 300
    # Proportional: 0/900 * 1000 to 300/900 * 1000 = 0 to 333
    assert len(chapters[0].transcript) > 0


def test_build_chapters_empty_timestamps():
    assert _build_chapters([], "some transcript", 600) == []


# ─── Registry ────────────────────────────────────────────────────────────────

def test_get_loader_youtube():
    loader = get_video_loader("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert isinstance(loader, YouTubeLoader)


def test_get_loader_youtu_be():
    loader = get_video_loader("https://youtu.be/dQw4w9WgXcQ")
    assert isinstance(loader, YouTubeLoader)


def test_get_loader_ted():
    loader = get_video_loader("https://www.ted.com/talks/some_talk")
    assert isinstance(loader, TEDLoader)


def test_get_loader_unsupported_raises():
    with pytest.raises(ValueError, match="No video loader"):
        get_video_loader("https://vimeo.com/12345")


def test_register_custom_loader():
    """Custom loaders registered via register_video_loader are found."""
    class MockLoader(BaseVideoLoader):
        @property
        def source_name(self) -> str:
            return "custom"

        def can_handle(self, url: str) -> bool:
            return "customvideo.example" in url

        async def load(self, url: str) -> VideoContent:
            return VideoContent(url=url, title="Test", transcript="test")

    register_video_loader(MockLoader())
    loader = get_video_loader("https://customvideo.example/watch/123")
    assert isinstance(loader, MockLoader)


def test_can_handle_youtube():
    assert YouTubeLoader().can_handle("https://www.youtube.com/watch?v=abc123def45")
    assert not YouTubeLoader().can_handle("https://vimeo.com/12345")


def test_can_handle_ted():
    assert TEDLoader().can_handle("https://ted.com/talks/some_slug")
    assert not TEDLoader().can_handle("https://youtube.com/watch?v=abc")
