"""
Abstract chat provider interface.

All LLM backends must implement this contract. Callers depend only on
BaseChatProvider — never on a concrete implementation.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class BaseChatProvider(ABC):
    """
    Strategy interface for chat LLM backends.

    complete()  — blocking call, returns the full response as a string.
    stream()    — returns an async generator that yields text chunks as they
                  arrive. Implement as an async generator function (async def
                  with yield statements).

    Call site:
        text = await provider.complete(messages)
        async for chunk in provider.stream(messages): ...
    """

    @abstractmethod
    async def complete(self, messages: list[dict], temperature: float = 0.3) -> str:
        """Send messages and return the full response as a string."""
        ...

    @abstractmethod
    def stream(
        self, messages: list[dict], temperature: float = 0.3
    ) -> AsyncGenerator[str, None]:
        """
        Send messages and return an async generator that yields text chunks.

        Concrete implementations should be async generator functions:

            async def stream(self, messages, temperature=0.3):
                async for chunk in llm_stream:
                    yield chunk
        """
        ...
