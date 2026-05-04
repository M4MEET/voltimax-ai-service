from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Stream tokens from the LLM."""
        ...

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate a complete response (non-streaming)."""
        ...

    def _to_langchain_messages(self, messages: list[dict], system_prompt: str | None = None):
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

        lc = []
        if system_prompt:
            lc.append(SystemMessage(content=system_prompt))
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                lc.append(HumanMessage(content=content))
            elif role == "assistant":
                lc.append(AIMessage(content=content))
            elif role == "system":
                lc.append(SystemMessage(content=content))
        return lc
