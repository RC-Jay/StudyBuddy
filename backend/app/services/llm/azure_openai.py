"""
Azure OpenAI implementation of BaseChatProvider.
Backed by AsyncAzureOpenAI (openai SDK) — GPT-4o-mini by default.
"""
from collections.abc import AsyncGenerator

from openai import AsyncAzureOpenAI

from app.config import settings
from app.services.llm.base import BaseChatProvider


class AzureOpenAIChatProvider(BaseChatProvider):
    """Chat provider backed by Azure OpenAI (configured via AZURE_OPENAI_* env vars)."""

    def __init__(self) -> None:
        self._client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )

    async def complete(self, messages: list[dict], temperature: float = 0.3) -> str:
        response = await self._client.chat.completions.create(
            model=settings.azure_openai_chat_deployment,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content

    async def stream(
        self, messages: list[dict], temperature: float = 0.3
    ) -> AsyncGenerator[str, None]:
        response = await self._client.chat.completions.create(
            model=settings.azure_openai_chat_deployment,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
