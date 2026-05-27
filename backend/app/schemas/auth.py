from pydantic import BaseModel


class OAuthLoginBody(BaseModel):
    credential: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
