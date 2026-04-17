from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import verify_dashboard_auth
from app.analytics.aggregator import AnalyticsAggregator

router = APIRouter(
    prefix="/api/analytics",
    dependencies=[Depends(verify_dashboard_auth)],
)

aggregator = AnalyticsAggregator()


@router.get("/overview")
async def overview(days: int = Query(7, ge=1, le=365)) -> dict:
    """Dashboard overview metrics for the last N days."""
    return await aggregator.get_overview(days)


@router.get("/topics")
async def topics(days: int = Query(7, ge=1, le=365)) -> list[dict]:
    """Topic usage breakdown for the last N days."""
    return await aggregator.get_topic_breakdown(days)


@router.get("/escalations")
async def escalations(days: int = Query(7, ge=1, le=365)) -> list[dict]:
    """Escalation reason breakdown for the last N days."""
    return await aggregator.get_escalation_breakdown(days)


@router.get("/costs")
async def costs(days: int = Query(30, ge=1, le=365)) -> dict:
    """LLM cost tracking per provider for the last N days."""
    return await aggregator.get_cost_tracking(days)


@router.get("/conversations")
async def conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    topic: str | None = Query(None),
) -> dict:
    """Paginated list of chat sessions."""
    return await aggregator.get_conversations(skip, limit, topic)


@router.get("/conversation/{session_id}")
async def conversation_detail(session_id: str) -> dict:
    """Full transcript for a single conversation."""
    return await aggregator.get_conversation_transcript(session_id)


@router.get("/feedback")
async def feedback(days: int = Query(7, ge=1, le=365)) -> dict:
    """👍/👎 feedback stats for the last N days."""
    return await aggregator.get_feedback_stats(days)


@router.get("/ratings")
async def ratings(days: int = Query(7, ge=1, le=365)) -> dict:
    """Star rating distribution and average for the last N days."""
    return await aggregator.get_rating_stats(days)


@router.get("/performance")
async def performance(days: int = Query(7, ge=1, le=365)) -> dict:
    """Response time, LLM latency, and avg chat duration for the last N days."""
    return await aggregator.get_performance(days)
