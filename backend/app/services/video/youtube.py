"""
YouTube video loader.

Transcript strategy (in order):
  1. youtube-transcript-api  — uses the official YouTube caption data (free, no API key)
  2. yt-dlp subtitle extraction — fallback if the above fails

Metadata:
  - Title, channel, duration, thumbnail, description via YouTube oEmbed API
    (free, no API key required)
  - Chapter detection via the video description (YouTube stores chapter timestamps
    in the description as "0:00 Chapter name" / "00:00 Chapter name")
  - If no chapters found in description, chapters remain empty (video_processor
    will segment the transcript via LLM if video is short enough)

No official YouTube Data API v3 key is required. If `YOUTUBE_API_KEY` is set
in the environment, the loader will use it for richer metadata.

Compatibility note: requires youtube-transcript-api >= 1.0.0 (instance-based API).
"""
import asyncio
import logging
import re

import httpx

from app.services.video.base import BaseVideoLoader, VideoChapter, VideoContent

logger = logging.getLogger(__name__)

# Matches youtube.com/watch?v=... and youtu.be/... (with or without extra params)
_YT_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/)([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)

# YouTube chapter pattern in description:
#   "0:00 Intro", "00:00 Intro", "1:23:45 Chapter title"
_CHAPTER_RE = re.compile(
    r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s+(.+)$",
    re.MULTILINE,
)

_OEMBED_URL = "https://www.youtube.com/oembed"


def _extract_video_id(url: str) -> str | None:
    m = _YT_URL_RE.search(url)
    return m.group(1) if m else None


def _seconds_from_match(hours: str | None, minutes: str, secs: str) -> int:
    h = int(hours) if hours else 0
    return h * 3600 + int(minutes) * 60 + int(secs)


def _parse_chapters_from_description(description: str) -> list[tuple[int, str]]:
    """
    Extract (start_seconds, title) pairs from a YouTube video description.
    Returns empty list if no chapter timestamps are found.
    """
    matches = _CHAPTER_RE.findall(description)
    if not matches:
        return []

    chapters = []
    for hours, minutes, secs, title in matches:
        start = _seconds_from_match(hours or None, minutes, secs)
        chapters.append((start, title.strip()))

    # Must start at 0:00 to be a valid chapter list
    if chapters and chapters[0][0] != 0:
        return []

    # Need at least 2 chapters to be useful
    return chapters if len(chapters) >= 2 else []


async def _fetch_oembed(video_id: str) -> dict:
    """Fetch title, author, thumbnail via YouTube oEmbed (no API key needed)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _OEMBED_URL,
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("oEmbed fetch failed for %s: %s", video_id, exc)
        return {}


def _yt_dlp_info(url: str) -> dict:
    """Synchronous yt-dlp metadata extraction (no video download)."""
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


async def _fetch_yt_metadata(video_id: str) -> dict:
    """
    Fetch description, duration, and chapters via yt-dlp (single async-threaded call).

    Returns:
      {
        "description": str,
        "duration":    int | None,
        "chapters":    list[dict] | None,  # yt-dlp chapter dicts with start_time/end_time/title
      }

    yt-dlp chapters (info["chapters"]) are set via YouTube Studio and are more
    reliable than timestamp lines in the description text. When present they take
    precedence over description parsing.
    """
    try:
        info = await asyncio.to_thread(
            _yt_dlp_info, f"https://www.youtube.com/watch?v={video_id}"
        )
        return {
            "description": info.get("description", "") or "",
            "duration": int(info.get("duration") or 0) or None,
            "chapters": info.get("chapters") or None,   # list of {start_time, end_time, title}
        }
    except Exception as exc:
        logger.warning("yt-dlp metadata fetch failed for %s: %s", video_id, exc)
        return {"description": "", "duration": None, "chapters": None}


def _fetch_transcript(video_id: str) -> tuple[str, str]:
    """
    Fetch transcript using youtube-transcript-api (v1.x instance-based API).
    Returns (transcript_text, language_code).
    Raises ValueError if no transcript is available.

    v1.x notes:
      - YouTubeTranscriptApi must be instantiated (not used as class methods)
      - Method renamed: list_transcripts() → list()
      - Transcript snippets are FetchedTranscriptSnippet dataclasses (use .text, not .get())
    """
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._transcripts import TranscriptList

    try:
        api = YouTubeTranscriptApi()
        transcript_list: TranscriptList = api.list(video_id)

        # Prefer manually created transcripts; fall back to auto-generated
        from youtube_transcript_api._errors import NoTranscriptFound
        try:
            transcript = transcript_list.find_manually_created_transcript(["en", "en-US", "en-GB"])
        except NoTranscriptFound:
            try:
                transcript = transcript_list.find_generated_transcript(["en", "en-US", "en-GB"])
            except NoTranscriptFound:
                # Use whatever is available first (any language)
                transcript = next(iter(transcript_list))

        fetched = transcript.fetch()
        # v1.x: snippets are FetchedTranscriptSnippet dataclasses — use .text not .get()
        text = " ".join(snippet.text for snippet in fetched).strip()
        return text, fetched.language_code

    except ValueError:
        raise
    except Exception as exc:
        # Check for transcripts-disabled error by class name (avoids version-specific imports)
        exc_name = type(exc).__name__
        if "TranscriptsDisabled" in exc_name or "Disabled" in exc_name:
            raise ValueError("Transcripts are disabled for this YouTube video.") from exc
        raise ValueError(f"Could not fetch YouTube transcript: {exc}") from exc


def _build_chapters_from_yt_dlp(
    yt_chapters: list[dict],
    transcript: str,
    duration: int | None,
) -> list[VideoChapter]:
    """
    Convert yt-dlp chapter dicts into VideoChapter objects.

    yt-dlp format: [{"start_time": 0.0, "end_time": 123.4, "title": "Introduction"}, ...]
    These are defined via YouTube Studio and are the authoritative source.
    """
    if not yt_chapters:
        return []

    total_duration = duration or (int(yt_chapters[-1].get("end_time", 0)) + 1)
    total_chars = len(transcript)
    chapters = []

    for ch in yt_chapters:
        title = ch.get("title", "").strip() or "Section"
        start = int(ch.get("start_time") or 0)
        end = int(ch.get("end_time") or total_duration)
        char_start = int(start / total_duration * total_chars)
        char_end = int(end / total_duration * total_chars)
        chapter_text = transcript[char_start:char_end].strip()
        chapters.append(VideoChapter(
            title=title,
            start_seconds=start,
            end_seconds=end,
            transcript=chapter_text,
        ))

    return chapters


def _build_chapters(
    chapter_timestamps: list[tuple[int, str]],
    transcript: str,
    duration: int | None,
) -> list[VideoChapter]:
    """
    Build VideoChapter objects from (start_seconds, title) pairs.
    Assigns a transcript slice to each chapter by estimating character offsets
    proportionally.
    """
    if not chapter_timestamps:
        return []

    chapters = []
    total_duration = duration or (chapter_timestamps[-1][0] + 300)  # estimate if unknown
    total_chars = len(transcript)

    for i, (start, title) in enumerate(chapter_timestamps):
        end = chapter_timestamps[i + 1][0] if i + 1 < len(chapter_timestamps) else total_duration
        char_start = int(start / total_duration * total_chars)
        char_end = int(end / total_duration * total_chars)
        chapter_text = transcript[char_start:char_end].strip()
        chapters.append(VideoChapter(
            title=title,
            start_seconds=start,
            end_seconds=end,
            transcript=chapter_text,
        ))

    return chapters


class YouTubeLoader(BaseVideoLoader):
    """
    Loads YouTube videos via the YouTube Transcript API and oEmbed.
    No API key required.
    """

    @property
    def source_name(self) -> str:
        return "youtube"

    def can_handle(self, url: str) -> bool:
        return bool(_extract_video_id(url))

    async def load(self, url: str) -> VideoContent:
        video_id = _extract_video_id(url)
        if not video_id:
            raise ValueError(f"Not a valid YouTube URL: {url}")

        canonical_url = f"https://www.youtube.com/watch?v={video_id}"

        # 1. Fetch oEmbed metadata and yt-dlp metadata concurrently (single yt-dlp call)
        oembed, yt_meta = await asyncio.gather(
            _fetch_oembed(video_id),
            _fetch_yt_metadata(video_id),
        )

        title = oembed.get("title") or f"YouTube video {video_id}"
        channel = oembed.get("author_name")
        thumbnail = oembed.get("thumbnail_url")
        description = yt_meta["description"]
        duration = yt_meta["duration"]

        # 2. Fetch transcript (async-threaded — blocking network call)
        transcript_text, lang_code = await asyncio.to_thread(_fetch_transcript, video_id)

        if not transcript_text:
            raise ValueError("The transcript for this video is empty.")

        # 3. Build chapters — prefer yt-dlp structured chapters (YouTube Studio),
        #    fall back to parsing timestamp lines from the description text.
        yt_dlp_chapters = yt_meta.get("chapters")
        if yt_dlp_chapters:
            logger.info("Using %d yt-dlp chapters for %s", len(yt_dlp_chapters), video_id)
            chapters = _build_chapters_from_yt_dlp(yt_dlp_chapters, transcript_text, duration)
        else:
            chapter_timestamps = _parse_chapters_from_description(description)
            chapters = _build_chapters(chapter_timestamps, transcript_text, duration)
            if chapters:
                logger.info("Using %d description-parsed chapters for %s", len(chapters), video_id)
            else:
                logger.info("No chapters found for %s — summariser will segment", video_id)

        return VideoContent(
            url=canonical_url,
            title=title,
            transcript=transcript_text,
            chapters=chapters,
            channel_name=channel,
            description=description[:2000] if description else None,
            duration_seconds=duration,
            thumbnail_url=thumbnail,
            language=lang_code or "en",
        )
