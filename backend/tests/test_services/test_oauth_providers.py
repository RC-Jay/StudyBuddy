"""
Tests for app.services.oauth

Covers:
  - Registry: get_oauth_provider, register_oauth_provider
  - GoogleOAuthProvider: token verification via mocked httpx
  - LinkedInOAuthProvider: code exchange + profile fetch via mocked httpx

No live network calls are made.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.oauth import _REGISTRY, get_oauth_provider, register_oauth_provider
from app.services.oauth.base import BaseOAuthProvider, OAuthUser, ProviderNotConfiguredError
from app.services.oauth.google import GoogleOAuthProvider
from app.services.oauth.linkedin import LinkedInOAuthProvider


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestGetOAuthProvider:
    def test_returns_google_provider(self):
        p = get_oauth_provider("google")
        assert isinstance(p, GoogleOAuthProvider)

    def test_returns_linkedin_provider(self):
        p = get_oauth_provider("linkedin")
        assert isinstance(p, LinkedInOAuthProvider)

    def test_case_insensitive(self):
        assert get_oauth_provider("Google") is get_oauth_provider("google")
        assert get_oauth_provider("LinkedIn") is get_oauth_provider("linkedin")

    def test_unknown_provider_raises_key_error(self):
        with pytest.raises(KeyError):
            get_oauth_provider("github")

    def test_error_message_contains_supported_providers(self):
        with pytest.raises(KeyError, match="google"):
            get_oauth_provider("unknown")


class TestRegisterOAuthProvider:
    def test_register_new_provider(self):
        class _DummyProvider(BaseOAuthProvider):
            @property
            def name(self) -> str:
                return "dummy-test"
            async def get_user_info(self, credential: str) -> OAuthUser:
                raise NotImplementedError

        p = _DummyProvider()
        register_oauth_provider(p)
        try:
            assert get_oauth_provider("dummy-test") is p
        finally:
            del _REGISTRY["dummy-test"]

    def test_override_existing_provider_and_restore(self):
        original = get_oauth_provider("google")

        class _FakeGoogle(BaseOAuthProvider):
            @property
            def name(self) -> str:
                return "google"
            async def get_user_info(self, credential: str) -> OAuthUser:
                raise NotImplementedError

        fake = _FakeGoogle()
        register_oauth_provider(fake)
        try:
            assert get_oauth_provider("google") is fake
        finally:
            register_oauth_provider(original)

        assert get_oauth_provider("google") is original


# ---------------------------------------------------------------------------
# GoogleOAuthProvider
# ---------------------------------------------------------------------------

class TestGoogleOAuthProvider:
    async def test_valid_token_returns_oauth_user(self):
        mock_response = {
            "sub": "123456789",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Test Person",
            "picture": "https://lh3.googleusercontent.com/photo.jpg",
            "aud": "test-google-client-id.apps.googleusercontent.com",
        }
        with patch("app.services.oauth.google.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = mock_response
            MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

            result = await GoogleOAuthProvider().get_user_info("fake-id-token")

        assert result.provider == "google"
        assert result.provider_id == "123456789"
        assert result.email == "user@example.com"
        assert result.display_name == "Test Person"
        assert result.picture_url == "https://lh3.googleusercontent.com/photo.jpg"

    async def test_invalid_token_raises(self):
        with patch("app.services.oauth.google.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock(status_code=400)
            mock_resp.json.return_value = {"error": "invalid_token"}
            MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

            with pytest.raises(ValueError, match="Invalid Google ID token"):
                await GoogleOAuthProvider().get_user_info("bad-token")

    async def test_wrong_audience_raises(self):
        mock_response = {
            "sub": "123",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Test",
            "aud": "some-other-app.apps.googleusercontent.com",
        }
        with patch("app.services.oauth.google.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = mock_response
            MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

            with pytest.raises(ValueError, match="audience"):
                await GoogleOAuthProvider().get_user_info("wrong-aud-token")

    async def test_unverified_email_raises(self):
        mock_response = {
            "sub": "123",
            "email": "user@example.com",
            "email_verified": False,
            "name": "Test",
            "aud": "test-google-client-id.apps.googleusercontent.com",
        }
        with patch("app.services.oauth.google.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = mock_response
            MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

            with pytest.raises(ValueError, match="not verified"):
                await GoogleOAuthProvider().get_user_info("unverified-token")

    async def test_falls_back_to_email_prefix_when_no_name(self):
        mock_response = {
            "sub": "123",
            "email": "myname@example.com",
            "email_verified": True,
            "aud": "test-google-client-id.apps.googleusercontent.com",
        }
        with patch("app.services.oauth.google.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = mock_response
            MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

            result = await GoogleOAuthProvider().get_user_info("no-name-token")

        assert result.display_name == "myname"


# ---------------------------------------------------------------------------
# LinkedInOAuthProvider
# ---------------------------------------------------------------------------

class TestLinkedInOAuthProvider:
    async def test_valid_code_returns_oauth_user(self):
        token_payload = {"access_token": "li-access-token-abc"}
        profile_payload = {
            "sub": "linkedin-user-id",
            "email": "li@example.com",
            "email_verified": True,
            "name": "LinkedIn User",
            "picture": "https://media.licdn.com/photo.jpg",
        }

        with patch("app.services.oauth.linkedin.settings") as mock_settings, \
             patch("app.services.oauth.linkedin.httpx.AsyncClient") as MockClient:

            mock_settings.linkedin_client_id = "li-client-id"
            mock_settings.linkedin_client_secret = "li-secret"
            mock_settings.linkedin_redirect_uri = "http://localhost:3000/auth/callback"

            token_resp = MagicMock(status_code=200)
            token_resp.json.return_value = token_payload
            profile_resp = MagicMock(status_code=200)
            profile_resp.json.return_value = profile_payload

            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=token_resp)
            mock_client.get = AsyncMock(return_value=profile_resp)
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await LinkedInOAuthProvider().get_user_info("li-auth-code")

        assert result.provider == "linkedin"
        assert result.provider_id == "linkedin-user-id"
        assert result.email == "li@example.com"
        assert result.display_name == "LinkedIn User"

    async def test_failed_token_exchange_raises(self):
        with patch("app.services.oauth.linkedin.settings") as mock_settings, \
             patch("app.services.oauth.linkedin.httpx.AsyncClient") as MockClient:

            mock_settings.linkedin_client_id = "li-client-id"
            mock_settings.linkedin_client_secret = "li-secret"
            mock_settings.linkedin_redirect_uri = "http://localhost:3000/auth/callback"

            token_resp = MagicMock(status_code=400)
            token_resp.json.return_value = {"error": "invalid_grant"}

            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=token_resp)
            MockClient.return_value.__aenter__.return_value = mock_client

            with pytest.raises(ValueError, match="Failed to obtain LinkedIn access token"):
                await LinkedInOAuthProvider().get_user_info("bad-code")

    async def test_unverified_email_raises(self):
        token_payload = {"access_token": "li-access-token"}
        profile_payload = {
            "sub": "li-user",
            "email": "li@example.com",
            "email_verified": False,
            "name": "LinkedIn User",
        }

        with patch("app.services.oauth.linkedin.settings") as mock_settings, \
             patch("app.services.oauth.linkedin.httpx.AsyncClient") as MockClient:

            mock_settings.linkedin_client_id = "li-client-id"
            mock_settings.linkedin_client_secret = "li-secret"
            mock_settings.linkedin_redirect_uri = "http://localhost:3000/auth/callback"

            token_resp = MagicMock(status_code=200)
            token_resp.json.return_value = token_payload
            profile_resp = MagicMock(status_code=200)
            profile_resp.json.return_value = profile_payload

            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=token_resp)
            mock_client.get = AsyncMock(return_value=profile_resp)
            MockClient.return_value.__aenter__.return_value = mock_client

            with pytest.raises(ValueError, match="not verified"):
                await LinkedInOAuthProvider().get_user_info("code")

    async def test_not_configured_raises_provider_not_configured_error(self):
        with patch("app.services.oauth.linkedin.settings") as mock_settings:
            mock_settings.linkedin_client_id = None
            mock_settings.linkedin_client_secret = None
            mock_settings.linkedin_redirect_uri = None

            with pytest.raises(ProviderNotConfiguredError):
                await LinkedInOAuthProvider().get_user_info("any-code")

    async def test_falls_back_to_email_prefix_when_no_name(self):
        token_payload = {"access_token": "li-access-token"}
        profile_payload = {
            "sub": "li-user",
            "email": "myname@example.com",
            "email_verified": True,
        }

        with patch("app.services.oauth.linkedin.settings") as mock_settings, \
             patch("app.services.oauth.linkedin.httpx.AsyncClient") as MockClient:

            mock_settings.linkedin_client_id = "li-client-id"
            mock_settings.linkedin_client_secret = "li-secret"
            mock_settings.linkedin_redirect_uri = "http://localhost:3000/auth/callback"

            token_resp = MagicMock(status_code=200)
            token_resp.json.return_value = token_payload
            profile_resp = MagicMock(status_code=200)
            profile_resp.json.return_value = profile_payload

            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=token_resp)
            mock_client.get = AsyncMock(return_value=profile_resp)
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await LinkedInOAuthProvider().get_user_info("code")

        assert result.display_name == "myname"
