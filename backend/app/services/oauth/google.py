import httpx

from app.config import settings
from app.services.oauth.base import BaseOAuthProvider, OAuthUser


class GoogleOAuthProvider(BaseOAuthProvider):
    @property
    def name(self) -> str:
        return "google"

    async def get_user_info(self, credential: str) -> OAuthUser:
        """Verify a Google ID token via Google's tokeninfo endpoint."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": credential},
            )

        if resp.status_code != 200:
            raise ValueError("Invalid Google ID token")

        data = resp.json()

        if data.get("aud") != settings.google_client_id:
            raise ValueError("Token audience does not match this application")

        if not data.get("email_verified"):
            raise ValueError("Google account email is not verified")

        return OAuthUser(
            provider="google",
            provider_id=data["sub"],
            email=data["email"],
            display_name=data.get("name") or data["email"].split("@")[0],
            picture_url=data.get("picture"),
        )
