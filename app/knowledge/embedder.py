from __future__ import annotations

from langchain_core.embeddings import Embeddings

from app.config import get_config


def get_embeddings() -> Embeddings:
    """Get the configured embedding model."""
    config = get_config()
    kb = config.knowledge_base
    provider = kb.embedding_provider

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings
        provider_config = config.llm_providers.get("openai")
        api_key = provider_config.api_key if provider_config else ""
        return OpenAIEmbeddings(api_key=api_key, model=kb.embedding_model)

    if provider == "fake":
        from langchain_community.embeddings import FakeEmbeddings
        return FakeEmbeddings(size=1536)

    raise ValueError(f"Unsupported embedding provider: {provider}")
