from __future__ import annotations

from app.ai.router import get_provider
from app.config import get_config


async def compute_frustration_score(
    history: list[dict],
    user_message: str,
    ai_response: str,
    llm_provider: str = "openai",
) -> float:
    """Use an LLM to compute a frustration score (0.0-1.0) for the conversation."""
    config = get_config()
    if not config.escalation.ai_detection_enabled:
        return 0.0

    provider = get_provider(llm_provider)

    detection_prompt = """Analyze this customer support conversation and rate the user's frustration level.
Output ONLY a single float between 0.0 (calm) and 1.0 (very frustrated), nothing else.

Consider:
- Expressions of frustration, anger, or impatience
- Repeated unanswered questions
- Requests for human agent
- Short, terse, or rude messages
- User saying the AI isn't helping"""

    history_text = "\n".join([
        f"{msg['role']}: {msg['content']}" for msg in history[-6:]
    ])
    history_text += f"\nuser: {user_message}\nassistant: {ai_response}"

    messages = [{"role": "user", "content": history_text}]
    score_str = await provider.generate(
        messages, system_prompt=detection_prompt, temperature=0.1, max_tokens=10
    )

    try:
        return min(max(float(score_str.strip()), 0.0), 1.0)
    except ValueError:
        return 0.0


def should_escalate(
    frustration_score: float,
    history: list[dict],
) -> tuple[bool, str]:
    """Determine if escalation is needed. Returns (should_escalate, reason)."""
    config = get_config()

    if frustration_score >= config.escalation.frustration_threshold:
        return True, "ai_frustration_detected"

    # Count consecutive failed AI responses
    recent_fails = sum(
        1
        for msg in history[-6:]
        if msg.get("role") == "assistant"
        and any(
            phrase in msg.get("content", "").lower()
            for phrase in ["i don't have", "i'm not sure", "i cannot", "unable to"]
        )
    )
    if recent_fails >= config.escalation.max_failed_responses:
        return True, "max_failed_responses"

    return False, ""
