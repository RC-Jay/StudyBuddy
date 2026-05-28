"""
Video loading and processing strategies.

Architecture — Strategy Pattern (mirrors document_loader.py):
  BaseVideoLoader      abstract strategy interface
  YouTubeLoader        concrete strategy for youtube.com / youtu.be URLs
  TEDLoader            concrete strategy for ted.com URLs

  _REGISTRY            maps URL-pattern → strategy instance
  get_video_loader()   looks up the right strategy by URL
  register_video_loader()  registers a new strategy

Adding a new video source (e.g. Vimeo, Coursera):
  1. Create a subclass of BaseVideoLoader in its own module
  2. Call register_video_loader(pattern, MyLoader()) in registry.py
  That's it — video_processor.py requires zero changes.
"""
from app.services.video.base import BaseVideoLoader, VideoChapter, VideoContent
from app.services.video.registry import get_video_loader, register_video_loader

__all__ = [
    "BaseVideoLoader",
    "VideoChapter",
    "VideoContent",
    "get_video_loader",
    "register_video_loader",
]
