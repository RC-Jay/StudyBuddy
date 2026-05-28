"""
Video loader registry.

Mirrors document_loader.py's design:
  _REGISTRY    ordered list of (loader, priority) so loaders are checked in a
               defined order — more specific loaders (TED) before catch-alls
               (YouTube generic). Each loader's can_handle() is tried in order.
  get_video_loader(url)         returns the first loader that can handle the URL
  register_video_loader(loader) prepends a loader (higher priority than built-ins)

Adding a new video source:
  1. Create a subclass of BaseVideoLoader
  2. Call register_video_loader(MyLoader()) somewhere at module load time
  No other files need changing.
"""
import logging

from app.services.video.base import BaseVideoLoader
from app.services.video.ted import TEDLoader
from app.services.video.youtube import YouTubeLoader

logger = logging.getLogger(__name__)

# Ordered list — loaders tried top-to-bottom via can_handle()
# TED must come before YouTube because some ted.com talks are also mirrored
# on YouTube, and we prefer the authoritative TED transcript.
_REGISTRY: list[BaseVideoLoader] = [
    TEDLoader(),
    YouTubeLoader(),
]


def get_video_loader(url: str) -> BaseVideoLoader:
    """
    Return the loader strategy for the given URL.

    Raises ValueError if no registered loader can handle the URL.
    """
    for loader in _REGISTRY:
        if loader.can_handle(url):
            return loader

    raise ValueError(
        f"No video loader registered for URL: {url!r}. "
        "Currently supported sources: YouTube (youtube.com, youtu.be), "
        "TED (ted.com)."
    )


def register_video_loader(loader: BaseVideoLoader, *, prepend: bool = True) -> None:
    """
    Register a custom loader strategy.

    By default the new loader is prepended (highest priority). Pass
    prepend=False to append (lowest priority, checked last).
    """
    if prepend:
        _REGISTRY.insert(0, loader)
    else:
        _REGISTRY.append(loader)
