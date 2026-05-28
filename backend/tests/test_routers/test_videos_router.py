"""
Tests for POST /videos endpoint.

Background pipeline and loader network calls are mocked.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSubmitVideo:
    def test_submit_youtube_url_accepted(self, client):
        with patch("app.routers.videos.process_video") as mock_task, \
             patch("app.routers.videos.get_video_loader") as mock_get_loader:
            mock_get_loader.return_value = MagicMock(source_name="youtube")
            resp = client.post("/api/v1/videos", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})

        assert resp.status_code == 202
        data = resp.json()
        assert data["file_type"] == "video"
        assert data["processing_status"] == "pending"
        assert "id" in data

    def test_submit_ted_url_accepted(self, client):
        with patch("app.routers.videos.process_video"), \
             patch("app.routers.videos.get_video_loader") as mock_get_loader:
            mock_get_loader.return_value = MagicMock(source_name="ted")
            resp = client.post("/api/v1/videos", json={"url": "https://www.ted.com/talks/ken_robinson_says_schools_kill_creativity"})

        assert resp.status_code == 202
        data = resp.json()
        assert data["file_type"] == "video"

    def test_unsupported_url_returns_400(self, client):
        with patch("app.routers.videos.get_video_loader") as mock_get_loader:
            mock_get_loader.side_effect = ValueError("No video loader registered")
            resp = client.post("/api/v1/videos", json={"url": "https://vimeo.com/12345"})

        assert resp.status_code == 400
        assert "Unsupported video URL" in resp.json()["detail"]

    def test_invalid_url_scheme_returns_422(self, client):
        resp = client.post("/api/v1/videos", json={"url": "ftp://not-a-video.com"})
        assert resp.status_code == 422

    def test_missing_url_returns_422(self, client):
        resp = client.post("/api/v1/videos", json={})
        assert resp.status_code == 422

    def test_empty_url_returns_422(self, client):
        resp = client.post("/api/v1/videos", json={"url": ""})
        assert resp.status_code == 422

    def test_video_appears_in_document_list(self, client):
        with patch("app.routers.videos.process_video"), \
             patch("app.routers.videos.get_video_loader") as mock_get_loader:
            mock_get_loader.return_value = MagicMock(source_name="youtube")
            submit_resp = client.post(
                "/api/v1/videos",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )
        assert submit_resp.status_code == 202
        video_id = submit_resp.json()["id"]

        # Video should appear in the documents list
        list_resp = client.get("/api/v1/documents")
        assert list_resp.status_code == 200
        ids = [d["id"] for d in list_resp.json()]
        assert video_id in ids

    def test_video_document_has_source_url(self, client):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        with patch("app.routers.videos.process_video"), \
             patch("app.routers.videos.get_video_loader") as mock_get_loader:
            mock_get_loader.return_value = MagicMock(source_name="youtube")
            resp = client.post("/api/v1/videos", json={"url": url})
        assert resp.status_code == 202
        assert resp.json()["source_url"] == url

    def test_video_source_stored_for_youtube(self, client):
        with patch("app.routers.videos.process_video"), \
             patch("app.routers.videos.get_video_loader") as mock_get_loader:
            mock_get_loader.return_value = MagicMock(source_name="youtube")
            resp = client.post("/api/v1/videos", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        assert resp.status_code == 202
        assert resp.json()["video_source"] == "youtube"

    def test_video_source_stored_for_ted(self, client):
        with patch("app.routers.videos.process_video"), \
             patch("app.routers.videos.get_video_loader") as mock_get_loader:
            mock_get_loader.return_value = MagicMock(source_name="ted")
            resp = client.post("/api/v1/videos", json={"url": "https://www.ted.com/talks/some_talk"})
        assert resp.status_code == 202
        assert resp.json()["video_source"] == "ted"
