from __future__ import annotations

from app.ai.providers.base import BaseLLMProvider
from app.config import get_config

_providers: dict[str, BaseLLMProvider] = {}


def get_provider(name: str) -> BaseLLMProvider:
    """Get or create an LLM provider by name."""
    if name in _providers:
        return _providers[name]

    config = get_config()

    # If the named provider is not in config, fall back
    if name not in config.llm_providers:
        fallback = config.topic_routing.get("fallback", "openai")
        if fallback in _providers:
            return _providers[fallback]
        name = fallback

    if name == "openai":
        from app.ai.providers.openai_provider import OpenAIProvider
        provider: BaseLLMProvider = OpenAIProvider()
    elif name == "anthropic":
        from app.ai.providers.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider()
    elif name == "google":
        from app.ai.providers.google_provider import GoogleProvider
        provider = GoogleProvider()
    elif name == "mistral":
        from app.ai.providers.mistral_provider import MistralProvider
        provider = MistralProvider()
    elif name == "custom":
        from app.ai.providers.custom_provider import CustomProvider
        provider = CustomProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {name}")

    _providers[name] = provider
    return provider


def get_provider_for_topic(topic_id: str) -> BaseLLMProvider:
    """Get the LLM provider assigned to a topic card."""
    config = get_config()
    provider_name = config.topic_routing.get(
        topic_id, config.topic_routing.get("fallback", "openai")
    )
    return get_provider(provider_name)


async def get_live_llm_provider(topic_id: str | None) -> str:
    """
    Return the LLM provider name for a topic.
    Checks MongoDB-stored routing first, falls back to config.yaml.
    """
    config = get_config()
    try:
        from app.db.admin_config import get_admin_config
        routing = await get_admin_config("topic_routing")
    except Exception:
        routing = None
    if routing and topic_id and topic_id in routing:
        return routing[topic_id]
    if topic_id and topic_id in config.topic_routing:
        return config.topic_routing[topic_id]
    return config.topic_routing.get("fallback", "openai")


async def get_live_llm_config(provider_name: str) -> dict:
    """
    Return LLM provider config dict.
    Checks MongoDB-stored providers first, falls back to config.yaml.
    Returns {} if provider not found.
    """
    config = get_config()
    try:
        from app.db.admin_config import get_admin_config
        stored_providers = await get_admin_config("llm_providers")
    except Exception:
        stored_providers = None
    if stored_providers and provider_name in stored_providers:
        p = stored_providers[provider_name]
        if p.get("enabled", True) and p.get("api_key"):
            return p
    p = config.llm_providers.get(provider_name)
    if p:
        return {"api_key": p.api_key, "default_model": p.default_model, "base_url": p.base_url or ""}
    return {}
