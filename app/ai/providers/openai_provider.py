from __future__ import annotations

from typing import AsyncIterator

from langchain_openai import ChatOpenAI

from app.ai.providers.base import BaseLLMProvider
from app.config import get_config


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        config = get_config()
        provider_config = config.llm_providers.get("openai")
        if not provider_config:
            raise ValueError("OpenAI provider not configured")

        self.model = ChatOpenAI(
            api_key=provider_config.api_key,
            model=provider_config.default_model,
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
