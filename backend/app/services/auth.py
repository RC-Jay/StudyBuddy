import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import RefreshToken, User
from app.services.oauth.base import OAuthUser


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """Returns user_id or raises JWTError."""
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    user_id: str = payload.get("sub")
    if not user_id:
        raise JWTError("Missing subject")
    return user_id


def create_refresh_token(db: Session, user_id: uuid.UUID) -> str:
    raw = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    db.add(RefreshToken(user_id=user_id, token_hash=_hash_token(raw), expires_at=expires))
    db.commit()
    return raw


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[str, uuid.UUID]:
    """Validates the incoming refresh token, revokes it, issues a new one. Returns (new_raw_token, user_id)."""
    token_hash = _hash_token(raw_token)
    record = db.query(RefreshToken).filter_by(token_hash=token_hash, revoked_at=None).first()
    if not record:
        raise ValueError("Invalid or expired refresh token")
    if record.expires_at < datetime.now(timezone.utc):
        raise ValueError("Refresh token expired")

    record.revoked_at = datetime.now(timezone.utc)
    db.commit()

    new_raw = create_refresh_token(db, record.user_id)
    return new_raw, record.user_id


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    token_hash = _hash_token(raw_token)
    record = db.query(RefreshToken).filter_by(token_hash=token_hash, revoked_at=None).first()
    if record:
        record.revoked_at = datetime.now(timezone.utc)
        db.commit()


def upsert_user(db: Session, oauth_user: OAuthUser) -> User:
    """Create a new user or update an existing one matched by (oauth_provider, oauth_provider_id)."""
    user = db.query(User).filter_by(
        oauth_provider=oauth_user.provider,
        oauth_provider_id=oauth_user.provider_id,
    ).first()
    if user:
        user.email = oauth_user.email
        user.display_name = oauth_user.display_name
        user.picture_url = oauth_user.picture_url
        user.last_seen_at = datetime.now(timezone.utc)
    else:
        user = User(
            oauth_provider=oauth_user.provider,
            oauth_provider_id=oauth_user.provider_id,
            email=oauth_user.email,
            display_name=oauth_user.display_name,
            picture_url=oauth_user.picture_url,
        )
        db.add(user)
    db.commit()
    db.refresh(user)
    return user
