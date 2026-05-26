"""
Chat provider package — abstracts the LLM backend behind a stable interface.

Usage (anywhere in the codebase):
    from app.services.llm import get_chat_provider

    provider = get_chat_provider()
    text = await provider.complete(messages)

    async for chunk in provider.stream(messages):
        ...

Adding a new provider:
    1. Subclass BaseChatProvider in a new module (e.g. llm/openai.py)
    2. Add an elif branch in get_chat_provider() below
    3. Set LLM_PROVIDER=<your_key> in .env
    No other files change.
"""
from functools import lru_cache

from app.services.llm.base import BaseChatProvider


@lru_cache(maxsize=1)
def get_chat_provider() -> BaseChatProvider:
    """
    Return the configured chat provider singleton.
    Reads LLM_PROVIDER from settings (default: azure_openai).
    Cached for the lifetime of the process — always the same instance.
    """
    from app.config import settings

    provider = settings.llm_provider.lower()

    if provider == "azure_openai":
        from app.services.llm.azure_openai import AzureOpenAIChatProvider
        return AzureOpenAIChatProvider()

    raise ValueError(
        f"Unknown LLM provider: '{provider}'. "
        f"Supported: azure_openai"
    )


__all__ = ["BaseChatProvider", "get_chat_provider"]
