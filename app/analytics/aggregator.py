from __future__ import annotations

from datetime import datetime, timedelta

from app.db.collections import (
    analytics_events_collection,
    messages_collection,
    sessions_collection,
)


class AnalyticsAggregator:

    async def get_overview(self, days: int = 7) -> dict:
        since = datetime.utcnow() - timedelta(days=days)

        total = await sessions_collection().count_documents(
            {"created_at": {"$gte": since}}
        )
        active = await sessions_collection().count_documents({"status": "active"})
        escalated = await sessions_collection().count_documents(
            {"created_at": {"$gte": since}, "status": "escalated"}
        )
        tickets = await analytics_events_collection().count_documents(
            {"event_type": "escalation", "created_at": {"$gte": since}}
        )

        # Token usage aggregation
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {"_id": None, "total_tokens": {"$sum": "$total_tokens"}}},
        ]
        token_result = await sessions_collection().aggregate(pipeline).to_list(1)
        tokens = token_result[0]["total_tokens"] if token_result else 0

        escalation_rate = (escalated / total * 100) if total > 0 else 0.0
        resolution_rate = ((total - escalated) / total * 100) if total > 0 else 0.0

        return {
            "total_chats": total,
            "active_now": active,
            "escalation_rate": round(escalation_rate, 1),
            "tickets_created": tickets,
            "token_usage": tokens,
            "ai_resolution_rate": round(resolution_rate, 1),
            "period_days": days,
        }

    async def get_topic_breakdown(self, days: int = 7) -> list[dict]:
        since = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {
                "$match": {
                    "created_at": {"$gte": since},
                    "topic_id": {"$ne": None},
                }
            },
            {
                "$group": {
                    "_id": "$topic_id",
                    "count": {"$sum": 1},
                    "escalated": {
                        "$sum": {"$cond": [{"$eq": ["$status", "escalated"]}, 1, 0]}
                    },
                    "avg_messages": {"$avg": "$message_count"},
                }
            },
            {"$sort": {"count": -1}},
        ]
        return await sessions_collection().aggregate(pipeline).to_list(100)

    async def get_escalation_breakdown(self, days: int = 7) -> list[dict]:
        since = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {
                "$match": {
                    "event_type": "escalation",
                    "created_at": {"$gte": since},
                }
            },
            {"$group": {"_id": "$reason", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        return await analytics_events_collection().aggregate(pipeline).to_list(100)

    async def get_cost_tracking(self, days: int = 30) -> dict:
        since = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": "$llm_provider",
                    "total_tokens": {"$sum": "$total_tokens"},
                    "session_count": {"$sum": 1},
                }
            },
        ]
        providers = await sessions_collection().aggregate(pipeline).to_list(100)

        # Rough cost estimates per 1K tokens (USD)
        cost_per_1k = {
            "openai": 0.01,
            "anthropic": 0.015,
            "google": 0.007,
            "mistral": 0.004,
            "custom": 0.0,
        }

        result = []
        for p in providers:
            provider_name = p["_id"] or "unknown"
            rate = cost_per_1k.get(provider_name, 0.01)
            result.append({
                "provider": provider_name,
                "total_tokens": p["total_tokens"],
                "session_count": p["session_count"],
                "estimated_cost": round((p["total_tokens"] / 1000) * rate, 2),
            })

        return {"providers": result, "period_days": days}

    async def get_conversations(
        self, skip: int = 0, limit: int = 20, topic: str | None = None
    ) -> dict:
        query: dict = {}
        if topic:
            query["topic_id"] = topic

        total = await sessions_collection().count_documents(query)
        sessions = await (
            sessions_collection()
            .find(query, {"_id": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
            .to_list(limit)
        )

        return {"total": total, "sessions": sessions}

    async def get_feedback_stats(self, days: int = 7) -> dict:
        since = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {"$match": {"event_type": "message_feedback", "created_at": {"$gte": since}}},
            {"$group": {"_id": "$feedback", "count": {"$sum": 1}}},
        ]
        result = await analytics_events_collection().aggregate(pipeline).to_list(10)
        stats = {r["_id"]: r["count"] for r in result}
        total = sum(stats.values())
        return {
            "up": stats.get("up", 0),
            "down": stats.get("down", 0),
            "total": total,
            "satisfaction_rate": round(stats.get("up", 0) / total * 100, 1) if total > 0 else 0.0,
            "period_days": days,
        }

    async def get_rating_stats(self, days: int = 7) -> dict:
        since = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {"$match": {"event_type": "session_rated", "created_at": {"$gte": since}}},
            {"$group": {
                "_id": None,
                "avg_rating": {"$avg": "$rating"},
                "total": {"$sum": 1},
                "ratings": {"$push": "$rating"},
            }},
        ]
        result = await analytics_events_collection().aggregate(pipeline).to_list(1)
        if not result:
            return {"avg_rating": 0.0, "total": 0, "distribution": {}, "period_days": days}
        r = result[0]
        dist: dict[str, int] = {}
        for v in r.get("ratings", []):
            dist[str(v)] = dist.get(str(v), 0) + 1
        return {
            "avg_rating": round(r.get("avg_rating", 0) or 0, 2),
            "total": r.get("total", 0),
            "distribution": dist,
            "period_days": days,
        }

    async def get_conversation_transcript(self, session_id: str) -> dict:
        session = await sessions_collection().find_one(
            {"id": session_id}, {"_id": 0}
        )
        msgs = await (
            messages_collection()
            .find({"session_id": session_id}, {"_id": 0})
            .sort("created_at", 1)
            .to_list(1000)
        )

        return {"session": session, "messages": msgs}

    async def get_performance(self, days: int = 7) -> dict:
        since = datetime.utcnow() - timedelta(days=days)

        # Avg response time and LLM latency by provider
        rt_pipeline = [
            {"$match": {"event_type": "response_time", "created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": "$provider",
                    "avg_response_ms": {"$avg": "$response_time_ms"},
                    "avg_llm_ms": {"$avg": "$llm_latency_ms"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"count": -1}},
        ]
        try:
            perf_by_provider = await analytics_events_collection().aggregate(rt_pipeline).to_list(20)
        except Exception:
            perf_by_provider = []

        # Avg chat duration
        dur_pipeline = [
            {"$match": {"event_type": "session_end", "created_at": {"$gte": since}}},
            {"$group": {"_id": None, "avg_duration_s": {"$avg": "$duration_seconds"}}},
        ]
        dur_result = await analytics_events_collection().aggregate(dur_pipeline).to_list(1)
        avg_duration = dur_result[0]["avg_duration_s"] if dur_result else 0

        # Overall averages
        all_rt_pipeline = [
            {"$match": {"event_type": "response_time", "created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": None,
                    "avg_response_ms": {"$avg": "$response_time_ms"},
                    "avg_llm_ms": {"$avg": "$llm_latency_ms"},
                }
            },
        ]
        all_rt = await analytics_events_collection().aggregate(all_rt_pipeline).to_list(1)
        overall = all_rt[0] if all_rt else {}

        return {
            "avg_response_ms": round(overall.get("avg_response_ms") or 0, 1),
            "avg_llm_ms": round(overall.get("avg_llm_ms") or 0, 1),
            "avg_chat_duration_s": round(avg_duration or 0, 1),
            "by_provider": [
                {
                    "provider": p.get("_id") or "unknown",
                    "avg_response_ms": round(p.get("avg_response_ms") or 0, 1),
                    "avg_llm_ms": round(p.get("avg_llm_ms") or 0, 1),
                    "message_count": p.get("count", 0),
                }
                for p in perf_by_provider
            ],
            "period_days": days,
        }
