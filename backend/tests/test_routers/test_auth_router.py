"""
Tests for the /auth router (OAuth provider strategy).

OAuth providers are replaced with MockOAuthProvider via register_oauth_provider()
— no live network calls are made.
"""
import uuid

import pytest

from app.services.oauth import register_oauth_provider
from app.services.oauth.base import BaseOAuthProvider, OAuthUser, ProviderNotConfiguredError


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class MockOAuthProvider(BaseOAuthProvider):
    """Controllable stand-in for any OAuth provider."""

    def __init__(self, name: str, response: OAuthUser | Exception):
        self._name = name
        self._response = response

    @property
    def name(self) -> str:
        return self._name

    async def get_user_info(self, credential: str) -> OAuthUser:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _oauth_user(provider: str = "google", provider_id: str | None = None) -> OAuthUser:
    return OAuthUser(
        provider=provider,
        provider_id=provider_id or f"pid-{uuid.uuid4()}",
        email="auth@example.com",
        display_name="Auth User",
        picture_url="https://lh3.googleusercontent.com/photo",
    )


# ---------------------------------------------------------------------------
# POST /auth/{provider}
# ---------------------------------------------------------------------------

class TestLoginWithOAuth:
    def test_valid_google_credential_returns_access_token(self, client):
        ou = _oauth_user()
        mock = MockOAuthProvider("google", ou)
        orig = register_oauth_provider.__module__
        from app.services.oauth import _REGISTRY
        original_google = _REGISTRY.get("google")
        register_oauth_provider(mock)
        try:
            resp = client.post("/api/v1/auth/google", json={"credential": "valid-id-token"})
        finally:
            if original_google:
                register_oauth_provider(original_google)

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "auth@example.com"
        assert data["user"]["display_name"] == "Auth User"
        assert "sb_refresh" in resp.cookies

    def test_invalid_credential_returns_401(self, client):
        mock = MockOAuthProvider("google", ValueError("Invalid Google ID token"))
        from app.services.oauth import _REGISTRY
        original_google = _REGISTRY.get("google")
        register_oauth_provider(mock)
        try:
            resp = client.post("/api/v1/auth/google", json={"credential": "bad-token"})
        finally:
            if original_google:
                register_oauth_provider(original_google)

        assert resp.status_code == 401
        assert "Invalid Google ID token" in resp.json()["detail"]

    def test_missing_credential_returns_422(self, client):
        resp = client.post("/api/v1/auth/google", json={})
        assert resp.status_code == 422

    def test_unknown_provider_returns_404(self, client):
        resp = client.post("/api/v1/auth/nonexistent", json={"credential": "tok"})
        assert resp.status_code == 404

    def test_unconfigured_provider_returns_500(self, client):
        mock = MockOAuthProvider("google", ProviderNotConfiguredError("LinkedIn OAuth is not configured"))
        from app.services.oauth import _REGISTRY
        original_google = _REGISTRY.get("google")
        register_oauth_provider(mock)
        try:
            resp = client.post("/api/v1/auth/google", json={"credential": "tok"})
        finally:
            if original_google:
                register_oauth_provider(original_google)

        assert resp.status_code == 500

    def test_second_login_with_same_provider_id_returns_same_user(self, client):
        """Logging in twice with the same provider account must not create two users."""
        ou = _oauth_user(provider_id="stable-pid")
        mock = MockOAuthProvider("google", ou)
        from app.services.oauth import _REGISTRY
        original_google = _REGISTRY.get("google")
        register_oauth_provider(mock)
        try:
            r1 = client.post("/api/v1/auth/google", json={"credential": "token-1"})
            r2 = client.post("/api/v1/auth/google", json={"credential": "token-2"})
        finally:
            if original_google:
                register_oauth_provider(original_google)

        assert r1.json()["user"]["id"] == r2.json()["user"]["id"]

    def test_response_contains_picture_url(self, client):
        ou = _oauth_user()
        mock = MockOAuthProvider("google", ou)
        from app.services.oauth import _REGISTRY
        original_google = _REGISTRY.get("google")
        register_oauth_provider(mock)
        try:
            resp = client.post("/api/v1/auth/google", json={"credential": "tok"})
        finally:
            if original_google:
                register_oauth_provider(original_google)

        assert resp.json()["user"]["picture_url"] == "https://lh3.googleusercontent.com/photo"

    def test_linkedin_provider_works_via_same_endpoint(self, client):
        ou = _oauth_user(provider="linkedin")
        mock = MockOAuthProvider("linkedin", ou)
        from app.services.oauth import _REGISTRY
        original_linkedin = _REGISTRY.get("linkedin")
        register_oauth_provider(mock)
        try:
            resp = client.post("/api/v1/auth/linkedin", json={"credential": "auth-code-from-linkedin"})
        finally:
            if original_linkedin:
                register_oauth_provider(original_linkedin)

        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "auth@example.com"


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

class TestRefreshToken:
    def test_refresh_with_valid_cookie_returns_new_token(self, client_with_auth, db, test_user):
        from app.services.auth import create_refresh_token
        c, _ = client_with_auth
        raw_token = create_refresh_token(db, test_user.id)

        resp = c.post("/api/v1/auth/refresh", cookies={"sb_refresh": raw_token})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_refresh_without_cookie_returns_401(self, client):
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401

    def test_refresh_with_invalid_token_returns_401(self, client_with_auth):
        c, _ = client_with_auth
        resp = c.post("/api/v1/auth/refresh", cookies={"sb_refresh": "not-a-real-token"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_returns_204(self, client):
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 204

    def test_logout_revokes_refresh_token(self, client_with_auth, db, test_user):
        from app.services.auth import create_refresh_token, rotate_refresh_token
        c, _ = client_with_auth
        raw_token = create_refresh_token(db, test_user.id)

        c.post("/api/v1/auth/logout", cookies={"sb_refresh": raw_token})

        with pytest.raises(ValueError, match="Invalid or expired"):
            rotate_refresh_token(db, raw_token)


# ---------------------------------------------------------------------------
# Auth middleware (JWT guard)
# ---------------------------------------------------------------------------

class TestAuthMiddleware:
    def test_missing_token_returns_401(self, client_with_auth):
        c, _ = client_with_auth
        resp = c.get("/api/v1/documents")
        assert resp.status_code == 401

    def test_valid_token_allows_access(self, client_with_auth, auth_headers):
        c, headers = client_with_auth
        resp = c.get("/api/v1/documents", headers=headers)
        assert resp.status_code == 200

    def test_malformed_token_returns_401(self, client_with_auth):
        c, _ = client_with_auth
        resp = c.get("/api/v1/documents", headers={"Authorization": "Bearer not.a.real.token"})
        assert resp.status_code == 401
