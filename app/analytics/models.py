from __future__ import annotations

from pydantic import BaseModel


class OverviewMetrics(BaseModel):
    total_chats: int = 0
    active_now: int = 0
    escalation_rate: float = 0.0
    avg_response_time_ms: int = 0
    tickets_created: int = 0
    token_usage: int = 0
    ai_resolution_rate: float = 0.0
    avg_chat_duration_seconds: int = 0
    period_days: int = 7
