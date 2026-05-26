from pydantic import BaseModel


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
