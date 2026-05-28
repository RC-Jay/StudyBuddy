"""
TED Talk video loader.

Transcript strategy:
  1. TED website scraping via httpx — TED embeds the full transcript as JSON-LD
     or in a <script> tag on the talk page. We parse the `__NEXT_DATA__` JSON
     that Next.js pages hydrate with, which includes paragraphs with cue times.
  2. If scraping fails, falls back to yt-dlp (many TED talks are also on YouTube).

Metadata:
  - Title, speaker, description, duration, thumbnail — all from __NEXT_DATA__.

Chapter / section detection:
  TED talks don't have creator-defined chapters. The processor will always call
  the LLM segmenter to detect 3–5 logical sections (intro, problem, insight,
  solution, call to action are typical patterns).

Supported URL patterns:
  - https://www.ted.com/talks/<slug>
  - https://ted.com/talks/<slug>
"""
import json
import logging
import re

import httpx

from app.services.video.base import BaseVideoLoader, VideoContent

logger = logging.getLogger(__name__)

_TED_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?ted\.com/talks/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

# TED's Next.js data is embedded in a <script id="__NEXT_DATA__" ...> tag
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)


def _extract_slug(url: str) -> str | None:
    m = _TED_URL_RE.search(url)
    return m.group(1) if m else None


def _extract_transcript_from_next_data(data: dict) -> tuple[str, int | None]:
    """
    Parse __NEXT_DATA__ JSON to extract:
      - full transcript text (paragraphs joined)
      - duration in seconds

    TED's data structure varies by page version. We try several known paths.
    Returns (transcript_text, duration_seconds).
    """
    transcript_parts: list[str] = []
    duration: int | None = None

    # Walk into known paths
    try:
        props = data.get("props", {})
        page_props = props.get("pageProps", {})

        # Path 1: talk.videoData.playerData (common in 2023+)
        talk = page_props.get("talk") or page_props.get("talkData", {})

        # Duration
        raw_duration = (
            talk.get("duration")
            or (talk.get("videoData") or {}).get("duration")
        )
        if raw_duration:
            duration = int(raw_duration)

        # Transcript paragraphs
        # TED stores transcript as a list of {text, cueId, startTime} objects
        # under talk.transcript.paragraphs[].cues[].text
        transcript_data = (
            talk.get("transcript")
            or page_props.get("transcript")
            or {}
        )
        paragraphs = transcript_data.get("paragraphs", [])
        for para in paragraphs:
            cues = para.get("cues", [])
            para_text = " ".join(c.get("text", "") for c in cues).strip()
            if para_text:
                transcript_parts.append(para_text)

        if not transcript_parts:
            # Path 2: some pages nest differently
            cues = talk.get("transcriptCues") or []
            transcript_parts = [c.get("text", "") for c in cues if c.get("text")]

    except Exception as exc:
        logger.debug("Error parsing TED __NEXT_DATA__: %s", exc)

    return "\n\n".join(transcript_parts), duration


def _extract_metadata_from_next_data(data: dict) -> dict:
    """Extract title, speaker, description, thumbnail from __NEXT_DATA__."""
    try:
        page_props = data.get("props", {}).get("pageProps", {})
        talk = page_props.get("talk") or page_props.get("talkData", {})

        title = talk.get("title") or talk.get("name") or ""
        description = talk.get("description") or ""

        # Speaker name
        speakers = talk.get("speakers") or []
        if speakers:
            s = speakers[0]
            speaker = f"{s.get('firstname', '')} {s.get('lastname', '')}".strip()
        else:
            speaker = talk.get("presenterDisplayName") or None

        # Thumbnail
        image = talk.get("primaryImageSet") or []
        thumbnail = image[0].get("url") if image else talk.get("socialImageUrl")

        return {
            "title": title,
            "speaker": speaker,
            "description": description,
            "thumbnail": thumbnail,
        }
    except Exception as exc:
        logger.debug("Error extracting TED metadata: %s", exc)
        return {}


class TEDLoader(BaseVideoLoader):
    """
    Loads TED talks by scraping ted.com for transcript and metadata.
    No API key required.
    """

    @property
    def source_name(self) -> str:
        return "ted"

    def can_handle(self, url: str) -> bool:
        return bool(_extract_slug(url))

    async def load(self, url: str) -> VideoContent:
        slug = _extract_slug(url)
        if not slug:
            raise ValueError(f"Not a valid TED talk URL: {url}")

        canonical_url = f"https://www.ted.com/talks/{slug}"

        async with httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": "StudyBuddy/1.0 (academic study tool)"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(canonical_url)
            resp.raise_for_status()
            html = resp.text

        # Parse __NEXT_DATA__
        next_data: dict = {}
        m = _NEXT_DATA_RE.search(html)
        if m:
            try:
                next_data = json.loads(m.group(1))
            except json.JSONDecodeError as exc:
                logger.warning("Could not parse TED __NEXT_DATA__ for %s: %s", slug, exc)

        transcript, duration = _extract_transcript_from_next_data(next_data)
        meta = _extract_metadata_from_next_data(next_data)

        if not transcript:
            raise ValueError(
                "Could not retrieve a transcript for this TED talk. "
                "The talk may not have captions available yet."
            )

        title = meta.get("title") or slug.replace("_", " ").title()

        # TED talks never have creator-defined chapters — the processor will
        # segment them with the LLM.
        return VideoContent(
            url=canonical_url,
            title=title,
            transcript=transcript,
            chapters=[],  # always LLM-segmented downstream
            channel_name=meta.get("speaker"),
            description=meta.get("description", "")[:2000] or None,
            duration_seconds=duration,
            thumbnail_url=meta.get("thumbnail"),
            language="en",
        )
