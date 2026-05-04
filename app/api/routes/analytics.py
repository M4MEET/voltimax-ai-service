from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from app.api.deps import verify_dashboard_auth
from app.analytics.aggregator import AnalyticsAggregator
from app.db.collections import logs_collection

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
    search: str | None = Query(None),
) -> dict:
    """Paginated list of chat sessions."""
    return await aggregator.get_conversations(skip, limit, topic, search)


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


@router.get("/timeseries")
async def timeseries(
    metric: str = Query(..., description="chats|escalations|tickets|tokens|resolution|response_time"),
    days: int = Query(30, ge=1, le=365),
    group: str = Query("daily", description="daily|monthly"),
) -> dict:
    """Time-series data for a metric, grouped by day or month."""
    return await aggregator.get_timeseries(metric, days, group)


@router.get("/timeseries/combined")
async def timeseries_combined(
    days: int = Query(30, ge=1, le=365),
    group: str = Query("daily", description="daily|monthly"),
) -> dict:
    """All key metrics in one call for the combined overview chart."""
    return await aggregator.get_combined_timeseries(days, group)


@router.get("/logs")
async def logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    level: str | None = Query(None),
    search: str | None = Query(None),
    hours: int = Query(24, ge=1, le=720),
) -> dict:
    """Application logs from MongoDB."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    query: dict = {"timestamp": {"$gte": since}}
    if level:
        query["level"] = level.upper()
    if search:
        query["message"] = {"$regex": search, "$options": "i"}

    total = await logs_collection().count_documents(query)
    docs = await (
        logs_collection()
        .find(query, {"_id": 0})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    return {"total": total, "logs": docs}
