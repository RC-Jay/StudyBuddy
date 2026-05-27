from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OAuthUser:
    provider: str        # "google" | "linkedin"
    provider_id: str     # provider's unique user ID (the "sub" claim)
    email: str
    display_name: str
    picture_url: str | None


class ProviderNotConfiguredError(ValueError):
    """Raised when required settings for an OAuth provider are absent."""


class BaseOAuthProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Registry key for this provider, e.g. 'google' or 'linkedin'."""
        ...

    @abstractmethod
    async def get_user_info(self, credential: str) -> OAuthUser:
        """Verify the credential and return a normalised OAuthUser.

        The credential is provider-specific:
          - Google:   ID token from the GoogleLogin component
          - LinkedIn: authorization code from the OAuth redirect

        Raises:
            ProviderNotConfiguredError: required settings are absent (→ HTTP 500)
            ValueError: credential is invalid, expired, or rejected (→ HTTP 401)
        """
        ...
