"""
Azure OpenAI wrappers for chat completion only.
Embeddings are handled by LangChain (see langchain_setup.py).
"""
from openai import AsyncAzureOpenAI

from app.config import settings

_chat_client = AsyncAzureOpenAI(
    api_key=settings.azure_openai_api_key,
    azure_endpoint=settings.azure_openai_endpoint,
    api_version=settings.azure_openai_api_version,
)


async def chat_completion(messages: list[dict], temperature: float = 0.3) -> str:
    response = await _chat_client.chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content


async def chat_completion_stream(messages: list[dict], temperature: float = 0.3):
    """Yields text chunks as they stream from the API."""
    stream = await _chat_client.chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta
