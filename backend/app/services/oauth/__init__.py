from app.services.oauth.base import BaseOAuthProvider, OAuthUser, ProviderNotConfiguredError
from app.services.oauth.google import GoogleOAuthProvider
from app.services.oauth.linkedin import LinkedInOAuthProvider

_REGISTRY: dict[str, BaseOAuthProvider] = {
    "google": GoogleOAuthProvider(),
    "linkedin": LinkedInOAuthProvider(),
}


def get_oauth_provider(name: str) -> BaseOAuthProvider:
    """Return the provider registered under *name*.

    Raises:
        KeyError: provider name is not in the registry (→ HTTP 404)
    """
    provider = _REGISTRY.get(name.lower())
    if not provider:
        supported = list(_REGISTRY.keys())
        raise KeyError(f"Unknown OAuth provider: '{name}'. Supported: {supported}")
    return provider


def register_oauth_provider(provider: BaseOAuthProvider) -> None:
    """Register or override a provider instance. Used in tests."""
    _REGISTRY[provider.name] = provider


__all__ = [
    "BaseOAuthProvider",
    "OAuthUser",
    "ProviderNotConfiguredError",
    "get_oauth_provider",
    "register_oauth_provider",
]
