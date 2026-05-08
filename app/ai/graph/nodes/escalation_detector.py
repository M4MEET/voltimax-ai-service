from __future__ import annotations

from app.ai.graph.state import ChatState
from app.ai.prompt_hub import pull_system_prompt
from app.ai.router import get_provider
from app.config import get_config

_FALLBACK_DETECTION = """Analyze the conversation and rate the user's frustration level from 0.0 to 1.0.
Consider:
- Repeated questions about the same topic
- Expressions of frustration or anger
- Requests for human agent
- Questions the AI cannot answer
- Multiple failed attempts to get help

Respond with ONLY a number between 0.0 and 1.0, nothing else."""


async def detect_escalation(state: ChatState) -> ChatState:
    """Detect if the conversation should be escalated."""
    if state.should_escalate:
        return state  # Already marked for escalation

    config = get_config()
    if not config.escalation.ai_detection_enabled:
        return state

    provider = get_provider(state.llm_provider)

    detection_prompt = pull_system_prompt("groot-escalation-detector") or _FALLBACK_DETECTION

    # Include recent history for context
    history_text = "\n".join([
        f"{msg['role']}: {msg['content']}" for msg in state.history[-6:]
    ])
    history_text += f"\nuser: {state.user_message}\nassistant: {state.response}"

    messages = [{"role": "user", "content": history_text}]
    score_str = await provider.generate(
        messages, system_prompt=detection_prompt, temperature=0.1, max_tokens=10
    )

    try:
        score = float(score_str.strip())
        state.frustration_score = min(max(score, 0.0), 1.0)
    except ValueError:
        state.frustration_score = 0.0

    # If order is verified and we have data, be less trigger-happy
    effective_threshold = config.escalation.frustration_threshold
    if state.session.get("cached_order_data") or state.session.get("order_number"):
        effective_threshold = max(effective_threshold, 0.85)

    if state.frustration_score >= effective_threshold:
        state.should_escalate = True
        state.escalation_reason = "ai_frustration_detected"

    # Check failed response count from history (exclude verification prompts)
    recent_fails = sum(
        1
        for msg in state.history[-6:]
        if msg["role"] == "assistant"
        and any(
            phrase in msg["content"].lower()
            for phrase in [
                "i don't have", "i'm not sure", "i cannot", "unable to",
                "kann ich leider nicht", "habe ich leider nicht", "bin ich nicht sicher",
                "kann ich nicht", "leider nicht möglich", "nicht in der lage",
            ]
        )
        and "verify" not in msg["content"].lower()
        and "verification" not in msg["content"].lower()
    )
    if recent_fails >= config.escalation.max_failed_responses:
        state.should_escalate = True
        state.escalation_reason = "max_failed_responses"

    return state
