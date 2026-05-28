from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import OAuthLoginBody, TokenResponse
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
    upsert_user,
)
from app.services.oauth import get_oauth_provider
from app.services.oauth.base import ProviderNotConfiguredError

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "sb_refresh"
COOKIE_MAX_AGE = settings.refresh_token_expire_days * 86400


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )


def _issue_tokens(response: Response, db: Session, user: User) -> TokenResponse:
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(db, user.id)
    _set_refresh_cookie(response, refresh)
    return TokenResponse(
        access_token=access,
        user={
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "picture_url": user.picture_url,
        },
    )


# Static routes are registered before /{provider} so they are never captured by it.

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    db: Session = Depends(get_db),
    refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
):
    if not refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")
    try:
        new_refresh, user_id = rotate_refresh_token(db, refresh)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access = create_access_token(str(user.id))
    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(
        access_token=access,
        user={
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "picture_url": user.picture_url,
        },
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: Session = Depends(get_db),
    refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
):
    if refresh:
        revoke_refresh_token(db, refresh)
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")


@router.post("/{provider}", response_model=TokenResponse)
async def login_with_oauth(
    provider: str,
    body: OAuthLoginBody,
    response: Response,
    db: Session = Depends(get_db),
):
    """Exchange a provider credential for a StudyBuddy access token + refresh cookie.

    The ``provider`` path segment selects the OAuth strategy (e.g. ``google``,
    ``linkedin``).  The ``credential`` field in the body is provider-specific:
    an ID token for Google, an authorization code for LinkedIn.
    """
    try:
        oauth_provider = get_oauth_provider(provider)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    try:
        oauth_user = await oauth_provider.get_user_info(body.credential)
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    user = upsert_user(db, oauth_user)
    return _issue_tokens(response, db, user)
