from __future__ import annotations

from typing import AsyncIterator

from langchain_openai import ChatOpenAI

from app.ai.providers.base import BaseLLMProvider
from app.config import get_config


class CustomProvider(BaseLLMProvider):
    """Custom LLM provider using an OpenAI-compatible API (e.g. Ollama, vLLM, LM Studio)."""

    def __init__(self):
        config = get_config()
        provider_config = config.llm_providers.get("custom")
        if not provider_config:
            raise ValueError("Custom provider not configured")

        if not provider_config.base_url:
            raise ValueError("Custom provider requires base_url to be set")

        self.model = ChatOpenAI(
            api_key=provider_config.api_key or "ollama",
            model=provider_config.default_model,
            base_url=provider_config.base_url,
        )

    async def generate_stream(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        lc_messages = self._to_langchain_messages(messages, system_prompt)
        async for chunk in self.model.astream(
            lc_messages, temperature=temperature, max_tokens=max_tokens
        ):
            if chunk.content:
                yield chunk.content

    async def generate(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        lc_messages = self._to_langchain_messages(messages, system_prompt)
        result = await self.model.ainvoke(
            lc_messages, temperature=temperature, max_tokens=max_tokens
        )
        return result.content
