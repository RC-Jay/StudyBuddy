"""
Compatibility shim — re-exports from app.services.llm.

Prefer importing directly from app.services.llm:
    from app.services.llm import get_chat_provider
    provider = get_chat_provider()
    result   = await provider.complete(messages)
"""
from app.services.llm import get_chat_provider


async def chat_completion(messages: list[dict], temperature: float = 0.3) -> str:
    return await get_chat_provider().complete(messages, temperature)


async def chat_completion_stream(messages: list[dict], temperature: float = 0.3):
    async for chunk in get_chat_provider().stream(messages, temperature):
        yield chunk
