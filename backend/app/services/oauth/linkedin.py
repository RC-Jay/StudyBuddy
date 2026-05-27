import httpx

from app.config import settings
from app.services.oauth.base import BaseOAuthProvider, OAuthUser, ProviderNotConfiguredError


class LinkedInOAuthProvider(BaseOAuthProvider):
    @property
    def name(self) -> str:
        return "linkedin"

    async def get_user_info(self, credential: str) -> OAuthUser:
        """Exchange a LinkedIn authorization code for user info.

        Two-step flow:
          1. Exchange code → access token (LinkedIn token endpoint)
          2. Fetch user info via OpenID Connect userinfo endpoint
        """
        if not (settings.linkedin_client_id and settings.linkedin_client_secret and settings.linkedin_redirect_uri):
            raise ProviderNotConfiguredError("LinkedIn OAuth is not configured on this server")

        # Step 1: exchange authorization code for access token
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "authorization_code",
                    "code": credential,
                    "redirect_uri": settings.linkedin_redirect_uri,
                    "client_id": settings.linkedin_client_id,
                    "client_secret": settings.linkedin_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if token_resp.status_code != 200:
            raise ValueError("Failed to obtain LinkedIn access token")

        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise ValueError("LinkedIn token response missing access_token")

        # Step 2: fetch user profile via OpenID Connect userinfo endpoint
        async with httpx.AsyncClient() as client:
            profile_resp = await client.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if profile_resp.status_code != 200:
            raise ValueError("Failed to fetch LinkedIn profile")

        data = profile_resp.json()

        if not data.get("email_verified"):
            raise ValueError("LinkedIn account email is not verified")

        return OAuthUser(
            provider="linkedin",
            provider_id=data["sub"],
            email=data["email"],
            display_name=data.get("name") or data["email"].split("@")[0],
            picture_url=data.get("picture"),
        )
