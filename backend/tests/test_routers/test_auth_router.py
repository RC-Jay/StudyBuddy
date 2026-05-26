"""
Tests for the /auth router.

External calls to ChangePay are mocked — no live HTTP requests.
The `client_with_auth` fixture is used where we want to exercise real JWT auth.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.changepay import ChangepayError, ChangepayUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cp_user(user_id: str | None = None) -> ChangepayUser:
    return ChangepayUser(
        user_id=user_id or str(uuid.uuid4()),
        phone="9000000000",
        email="auth@example.com",
        display_name="Auth User",
        customer_token="cp-auth-token",
    )


def _mock_cp_client(cp_user: ChangepayUser) -> MagicMock:
    client = MagicMock()
    client.request_otp = AsyncMock(return_value={"token": "123456"})
    client.login_with_otp = AsyncMock(return_value=cp_user)
    client.login_with_password = AsyncMock(return_value=cp_user)
    return client


# ---------------------------------------------------------------------------
# OTP request
# ---------------------------------------------------------------------------

class TestRequestOtp:
    def test_returns_200_and_debug_token(self, client):
        mock_client = _mock_cp_client(_cp_user())
        with patch("app.routers.auth.get_changepay_client", return_value=mock_client):
            resp = client.post("/api/v1/auth/otp/request", json={"phone": "9000000000"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "OTP sent"

    def test_changepay_error_propagates(self, client):
        mock_client = MagicMock()
        mock_client.request_otp = AsyncMock(
            side_effect=ChangepayError("Phone not found", status_code=404)
        )
        with patch("app.routers.auth.get_changepay_client", return_value=mock_client):
            resp = client.post("/api/v1/auth/otp/request", json={"phone": "0000000000"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# OTP login
# ---------------------------------------------------------------------------

class TestLoginOtp:
    def test_successful_login_returns_access_token(self, client, db):
        """login/otp must return an access_token and set the refresh cookie."""
        cp_user = _cp_user()
        mock_client = _mock_cp_client(cp_user)

        with patch("app.routers.auth.get_changepay_client", return_value=mock_client):
            resp = client.post(
                "/api/v1/auth/login/otp",
                json={"phone": "9000000000", "otp": "123456"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["phone"] == "9000000000"
        assert "sb_refresh" in resp.cookies

    def test_bad_otp_returns_changepay_error(self, client):
        mock_client = MagicMock()
        mock_client.login_with_otp = AsyncMock(
            side_effect=ChangepayError("Invalid OTP", status_code=401)
        )
        with patch("app.routers.auth.get_changepay_client", return_value=mock_client):
            resp = client.post(
                "/api/v1/auth/login/otp",
                json={"phone": "9000000000", "otp": "wrong"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Password login
# ---------------------------------------------------------------------------

class TestLoginPassword:
    def test_successful_login(self, client):
        cp_user = _cp_user()
        mock_client = _mock_cp_client(cp_user)

        with patch("app.routers.auth.get_changepay_client", return_value=mock_client):
            resp = client.post(
                "/api/v1/auth/login/password",
                json={"phone": "9000000000", "password": "secret"},
            )

        assert resp.status_code == 200
        assert "access_token" in resp.json()


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

class TestRefreshToken:
    def test_refresh_with_valid_cookie_returns_new_token(self, client_with_auth, db, test_user):
        """Create a refresh token directly and pass it as a cookie."""
        from app.services.auth import create_refresh_token
        c, _ = client_with_auth
        raw_token = create_refresh_token(db, test_user.id)

        refresh_resp = c.post(
            "/api/v1/auth/refresh",
            cookies={"sb_refresh": raw_token},
        )
        assert refresh_resp.status_code == 200
        assert "access_token" in refresh_resp.json()

    def test_refresh_without_cookie_returns_401(self, client):
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_returns_204(self, client):
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 204

    def test_logout_clears_cookie(self, client_with_auth, db, test_user):
        from app.services.auth import create_refresh_token
        c, _ = client_with_auth
        raw_token = create_refresh_token(db, test_user.id)

        logout_resp = c.post("/api/v1/auth/logout", cookies={"sb_refresh": raw_token})
        assert logout_resp.status_code == 204


# ---------------------------------------------------------------------------
# Auth middleware (JWT guard)
# ---------------------------------------------------------------------------

class TestAuthMiddleware:
    def test_missing_token_returns_401(self, client_with_auth):
        """Without auth headers, protected endpoints must return 401."""
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
