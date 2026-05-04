"""Pull prompts from LangSmith Prompt Hub with caching + mustache rendering.

Prompts are cached for 5 minutes. Mustache variables are rendered at call time.
If LangSmith is unavailable, falls back to hardcoded prompts.
"""
from __future__ import annotations

import logging
import os
import time

import chevron

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 300  # 5 minutes


def _is_enabled() -> bool:
    return bool(os.getenv("LANGCHAIN_API_KEY"))


def _pull_raw(name: str) -> str | None:
    """Pull raw template text from LangSmith (cached)."""
    if not _is_enabled():
        return None

    now = time.time()
    if name in _cache:
        cached_time, cached_value = _cache[name]
        if now - cached_time < _CACHE_TTL:
            return cached_value

    try:
        from langsmith import Client
        client = Client()
        prompt = client.pull_prompt(name)

        content = None

        # Method 1: Extract raw template string from ChatPromptTemplate
        if hasattr(prompt, 'messages'):
            for msg_tmpl in prompt.messages:
                # Get the template string directly (no rendering)
                if hasattr(msg_tmpl, 'prompt') and hasattr(msg_tmpl.prompt, 'template'):
                    content = msg_tmpl.prompt.template
                    break  # Use the first message (system prompt)

        # Method 2: Try invoking with dummy variables
        if content is None:
            try:
                input_vars = getattr(prompt, 'input_variables', [])
                dummy = {v: "" for v in input_vars}
                msgs = prompt.invoke(dummy)
                for m in msgs.messages:
                    if type(m).__name__ == "SystemMessage":
                        content = m.content
                        break
                if content is None and msgs.messages:
                    content = msgs.messages[0].content
            except Exception as e:
                logger.debug(f"Invoke fallback failed for '{name}': {e}")

        if content is None:
            logger.warning(f"Could not extract template from prompt '{name}'")
            return None

        if isinstance(content, list):
            content = "\n".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in content
            )

        _cache[name] = (now, content)
        logger.info(f"Prompt '{name}' pulled from LangSmith ({len(content)} chars)")
        return content

    except Exception as e:
        logger.warning(f"Failed to pull prompt '{name}' from LangSmith: {e}. Using fallback.")
        return None


def pull_system_prompt(name: str = "groot-system-prompt", fallback: str = "") -> str | None:
    """Pull a prompt template (no mustache rendering). For backward compat."""
    return _pull_raw(name)


def render_prompt(name: str, variables: dict, fallback: str = "") -> str | None:
    """Pull a prompt from LangSmith and render mustache variables.

    Args:
        name: Prompt name in LangSmith Prompt Hub
        variables: Dict of variables to render in the mustache template
        fallback: Fallback text if LangSmith is unavailable

    Returns:
        Rendered prompt string, or None if LangSmith unavailable
    """
    template = _pull_raw(name)
    if template is None:
        return None

    try:
        rendered = chevron.render(template, variables)
        return rendered
    except Exception as e:
        logger.warning(f"Mustache render failed for '{name}': {e}. Returning raw template.")
        return template


def invalidate_cache(name: str | None = None) -> None:
    """Clear prompt cache. If name is None, clear all."""
    if name:
        _cache.pop(name, None)
    else:
        _cache.clear()
