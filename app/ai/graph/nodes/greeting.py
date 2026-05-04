from __future__ import annotations

from app.ai.graph.state import ChatState
from app.ai.prompt_hub import render_prompt
from app.ai.router import get_provider

_FALLBACK_GREETING = """You are Groot, a friendly customer support assistant for Voltimax (voltimax.de).
Generate a brief, warm greeting (1-2 sentences) for a customer named {{name}} who wants help with '{{topic}}'.
Be welcoming and invite them to ask their question.
Respond in the same language the customer's topic suggests. If unclear, use German."""


async def generate_greeting(state: ChatState) -> ChatState:
    """Generate a personalized greeting for the user."""
    provider = get_provider(state.llm_provider)

    name = state.user_claims.get("name", "")
    topic_id = state.session.get("topic_id", "")

    variables = {"name": name or "the customer", "topic": topic_id or "general questions"}
    greeting_prompt = render_prompt("groot-greeting", variables)
    if not greeting_prompt:
        import chevron
        greeting_prompt = chevron.render(_FALLBACK_GREETING, variables)

    messages = [{"role": "user", "content": "Hello"}]
    greeting = await provider.generate(
        messages, system_prompt=greeting_prompt, temperature=0.8, max_tokens=60
    )
    state.response = greeting
    return state
