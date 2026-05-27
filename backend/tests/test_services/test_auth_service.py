"""
Tests for app.services.auth

Covers:
  - Access token creation and decoding
  - Refresh token creation, rotation, and revocation
  - upsert_user (create + update paths)

No live network calls are made.
OAuth provider tests live in test_oauth_providers.py.
"""
import uuid

import pytest
from jose import JWTError

from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    revoke_refresh_token,
    rotate_refresh_token,
    upsert_user,
)
from app.services.oauth.base import OAuthUser


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

class TestCreateAccessToken:
    def test_returns_a_string(self):
        token = create_access_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 10

    def test_decode_recovers_user_id(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)
        assert decode_access_token(token) == user_id

    def test_different_users_produce_different_tokens(self):
        t1 = create_access_token(str(uuid.uuid4()))
        t2 = create_access_token(str(uuid.uuid4()))
        assert t1 != t2


class TestDecodeAccessToken:
    def test_invalid_token_raises_jwt_error(self):
        with pytest.raises(JWTError):
            decode_access_token("not.a.valid.token")

    def test_tampered_token_raises(self):
        token = create_access_token("user-abc")
        tampered = token[:-4] + "XXXX"
        with pytest.raises(JWTError):
            decode_access_token(tampered)


# ---------------------------------------------------------------------------
# Refresh token lifecycle
# ---------------------------------------------------------------------------

class TestRefreshTokenLifecycle:
    def test_create_and_rotate(self, db):
        user = _make_user(db)
        raw = create_refresh_token(db, user.id)
        assert isinstance(raw, str) and len(raw) > 20

        new_raw, returned_user_id = rotate_refresh_token(db, raw)
        assert new_raw != raw
        assert returned_user_id == user.id

    def test_rotate_used_token_raises(self, db):
        user = _make_user(db)
        raw = create_refresh_token(db, user.id)
        rotate_refresh_token(db, raw)

        with pytest.raises(ValueError, match="Invalid or expired"):
            rotate_refresh_token(db, raw)

    def test_revoke_prevents_rotation(self, db):
        user = _make_user(db)
        raw = create_refresh_token(db, user.id)
        revoke_refresh_token(db, raw)

        with pytest.raises(ValueError, match="Invalid or expired"):
            rotate_refresh_token(db, raw)

    def test_revoke_nonexistent_is_silent(self, db):
        revoke_refresh_token(db, "totally-fake-token")


# ---------------------------------------------------------------------------
# upsert_user
# ---------------------------------------------------------------------------

class TestUpsertUser:
    def test_creates_new_user(self, db):
        ou = _make_oauth_user()
        user = upsert_user(db, ou)
        assert user.oauth_provider == ou.provider
        assert user.oauth_provider_id == ou.provider_id
        assert user.email == ou.email
        assert user.display_name == ou.display_name
        assert user.picture_url == ou.picture_url
        assert user.id is not None

    def test_updates_existing_user(self, db):
        ou = _make_oauth_user()
        user1 = upsert_user(db, ou)

        updated = OAuthUser(
            provider=ou.provider,
            provider_id=ou.provider_id,
            email="new@example.com",
            display_name="Updated Name",
            picture_url="https://new-pic.example.com",
        )
        user2 = upsert_user(db, updated)

        assert user2.id == user1.id
        assert user2.email == "new@example.com"
        assert user2.display_name == "Updated Name"

    def test_different_provider_ids_create_different_users(self, db):
        u1 = upsert_user(db, _make_oauth_user(provider_id="pid-111", email="a@a.com"))
        u2 = upsert_user(db, _make_oauth_user(provider_id="pid-222", email="b@b.com"))
        assert u1.id != u2.id

    def test_same_provider_id_different_provider_creates_different_users(self, db):
        u1 = upsert_user(db, _make_oauth_user(provider="google", provider_id="shared-pid", email="g@example.com"))
        u2 = upsert_user(db, _make_oauth_user(provider="linkedin", provider_id="shared-pid", email="l@example.com"))
        assert u1.id != u2.id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db):
    from app.models.user import User
    user = User(
        oauth_provider="google",
        oauth_provider_id=f"google-refresh-test-{uuid.uuid4()}",
        email=f"refresh-{uuid.uuid4()}@example.com",
        display_name="Refresh Test",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_oauth_user(
    provider: str = "google",
    provider_id: str = "pid-test-001",
    email: str = "oauth@example.com",
) -> OAuthUser:
    return OAuthUser(
        provider=provider,
        provider_id=provider_id,
        email=email,
        display_name="OAuth User",
        picture_url="https://lh3.googleusercontent.com/photo",
    )
