from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.collections import analytics_events_collection


async def track_event(
    event_type: str,
    session_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Record an analytics event to MongoDB."""
    doc: dict[str, Any] = {
        "event_type": event_type,
        "created_at": datetime.utcnow(),
    }
    if session_id:
        doc["session_id"] = session_id
    if data:
        doc.update(data)
    await analytics_events_collection().insert_one(doc)


async def track_token_usage(
    session_id: str,
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Track LLM token usage for cost analytics."""
    await track_event(
        "token_usage",
        session_id=session_id,
        data={
            "provider": provider,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )


async def track_response_time(
    session_id: str,
    response_time_ms: int,
    llm_latency_ms: int,
    provider: str,
) -> None:
    """Track end-to-end response time and LLM latency for a single message."""
    await track_event(
        "response_time",
        session_id=session_id,
        data={
            "response_time_ms": response_time_ms,
            "llm_latency_ms": llm_latency_ms,
            "provider": provider,
        },
    )


async def track_session_end(
    session_id: str,
    duration_seconds: int,
    message_count: int,
) -> None:
    """Track session duration when a chat ends."""
    await track_event(
        "session_end",
        session_id=session_id,
        data={
            "duration_seconds": duration_seconds,
            "message_count": message_count,
        },
    )
