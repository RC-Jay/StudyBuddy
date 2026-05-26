from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
    upsert_user,
)
from app.services.changepay import ChangepayError, changepay_client

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "sb_refresh"
COOKIE_MAX_AGE = settings.refresh_token_expire_days * 86400


class OtpRequestBody(BaseModel):
    phone: str


class OtpLoginBody(BaseModel):
    phone: str
    otp: str


class PasswordLoginBody(BaseModel):
    phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


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


def _issue_tokens(response: Response, db: Session, user) -> TokenResponse:
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(db, user.id)
    _set_refresh_cookie(response, refresh)
    return TokenResponse(
        access_token=access,
        user={"id": str(user.id), "phone": user.phone, "email": user.email, "display_name": user.display_name},
    )


@router.post("/otp/request")
async def request_otp(body: OtpRequestBody):
    try:
        result = await changepay_client.request_otp(body.phone)
        # In staging the OTP token is in the response — forward it to the client
        # In production this field is absent (OTP sent by SMS)
        return {"message": "OTP sent", "debug_token": result.get("token")}
    except ChangepayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/login/otp", response_model=TokenResponse)
async def login_otp(body: OtpLoginBody, response: Response, db: Session = Depends(get_db)):
    try:
        cp_user = await changepay_client.login_with_otp(body.phone, body.otp)
    except ChangepayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    user = upsert_user(db, cp_user)
    return _issue_tokens(response, db, user)


@router.post("/login/password", response_model=TokenResponse)
async def login_password(body: PasswordLoginBody, response: Response, db: Session = Depends(get_db)):
    try:
        cp_user = await changepay_client.login_with_password(body.phone, body.password)
    except ChangepayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    user = upsert_user(db, cp_user)
    return _issue_tokens(response, db, user)


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

    import uuid
    from app.models.user import User
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access = create_access_token(str(user.id))
    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(
        access_token=access,
        user={"id": str(user.id), "phone": user.phone, "email": user.email, "display_name": user.display_name},
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
