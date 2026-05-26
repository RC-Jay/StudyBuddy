"""
Tests for app.services.auth

Covers:
  - Access token creation and decoding
  - Refresh token creation, rotation, and revocation
  - upsert_user (create + update paths)

No live network calls are made — the DB fixture from conftest is used for
refresh token tests, and JWT is handled locally with the test secret key.
"""
import uuid
from datetime import datetime, timedelta, timezone

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
from app.services.changepay import ChangepayUser


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
# Refresh token lifecycle (requires real DB)
# ---------------------------------------------------------------------------

class TestRefreshTokenLifecycle:
    def test_create_and_rotate(self, db):
        """Create a refresh token, then rotate it — should get a new token back."""
        user = _make_user(db)
        raw = create_refresh_token(db, user.id)
        assert isinstance(raw, str) and len(raw) > 20

        new_raw, returned_user_id = rotate_refresh_token(db, raw)
        assert new_raw != raw
        assert returned_user_id == user.id

    def test_rotate_used_token_raises(self, db):
        """Rotating an already-used token must raise ValueError."""
        user = _make_user(db)
        raw = create_refresh_token(db, user.id)
        rotate_refresh_token(db, raw)  # first rotation consumes the token

        with pytest.raises(ValueError, match="Invalid or expired"):
            rotate_refresh_token(db, raw)

    def test_revoke_prevents_rotation(self, db):
        user = _make_user(db)
        raw = create_refresh_token(db, user.id)
        revoke_refresh_token(db, raw)

        with pytest.raises(ValueError, match="Invalid or expired"):
            rotate_refresh_token(db, raw)

    def test_revoke_nonexistent_is_silent(self, db):
        """Revoking a token that doesn't exist should not raise."""
        revoke_refresh_token(db, "totally-fake-token")  # no exception


# ---------------------------------------------------------------------------
# upsert_user
# ---------------------------------------------------------------------------

class TestUpsertUser:
    def test_creates_new_user(self, db):
        cp_user = _make_cp_user()
        user = upsert_user(db, cp_user)
        assert user.phone == cp_user.phone
        assert user.email == cp_user.email
        assert user.display_name == cp_user.display_name
        assert user.changepay_profile_token == cp_user.customer_token

    def test_updates_existing_user(self, db):
        cp_user = _make_cp_user()
        user1 = upsert_user(db, cp_user)

        # Same user_id, updated email and display_name
        cp_updated = ChangepayUser(
            user_id=cp_user.user_id,
            phone=cp_user.phone,
            email="updated@example.com",
            display_name="Updated Name",
            customer_token="new-cp-token",
        )
        user2 = upsert_user(db, cp_updated)

        assert user2.id == user1.id
        assert user2.email == "updated@example.com"
        assert user2.display_name == "Updated Name"
        assert user2.changepay_profile_token == "new-cp-token"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db):
    """Insert a minimal User row and return it."""
    from app.models.user import User
    user = User(
        id=uuid.uuid4(),
        phone="7777777777",
        email="refresh@example.com",
        display_name="Refresh Test",
        changepay_profile_token="cp-refresh",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_cp_user() -> ChangepayUser:
    return ChangepayUser(
        user_id=str(uuid.uuid4()),
        phone="6666666666",
        email="cp@example.com",
        display_name="CP User",
        customer_token="cp-token-xyz",
    )
