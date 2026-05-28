"""
Abstract base classes and shared data models for video loaders.

VideoContent is the standard output every loader must return.
BaseVideoLoader is the strategy interface — subclass it to add a new video source.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VideoChapter:
    """A named section of a video, either creator-defined or LLM-segmented."""
    title: str
    start_seconds: int
    end_seconds: int | None  # None means "until the next chapter / end of video"
    transcript: str          # raw transcript text for this segment


@dataclass
class VideoContent:
    """
    Everything a video loader knows about a video.

    Mandatory fields every loader must populate:
      - url            : canonical URL of the video
      - title          : human-readable video title
      - transcript     : full transcript text (plain text, no timestamps)
      - chapters       : list of VideoChapter segments (may be empty)

    Optional metadata (populate when available):
      - channel_name   : uploader / channel / speaker name
      - description    : video description or abstract
      - duration_seconds
      - thumbnail_url
      - published_date : ISO-8601 date string, e.g. "2023-11-14"
      - language       : BCP-47 language code, e.g. "en"
    """
    # Required
    url: str
    title: str
    transcript: str
    chapters: list[VideoChapter] = field(default_factory=list)

    # Optional metadata
    channel_name: str | None = None
    description: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None
    published_date: str | None = None
    language: str = "en"


class BaseVideoLoader(ABC):
    """
    Strategy interface for video loading.

    Each concrete loader knows how to:
      1. Fetch the video's metadata (title, duration, thumbnail, …)
      2. Retrieve or generate a transcript
      3. Detect or infer chapter/section boundaries
    and returns a VideoContent dataclass.

    The loader must NOT download video files unless absolutely necessary.
    Prefer official transcript APIs, then caption files, then Whisper.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Short lowercase identifier for this video source.
        Stored in Document.video_source so the frontend can display
        the correct badge/icon without re-parsing the URL.

        Examples: "youtube", "ted"
        """
        ...

    @abstractmethod
    async def load(self, url: str) -> VideoContent:
        """
        Load and return a VideoContent for the given URL.

        Raises:
          ValueError  — if the URL is unsupported or the video has no transcript.
          RuntimeError — for unrecoverable network / API errors.
        """
        ...

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this loader knows how to handle the given URL."""
        ...
