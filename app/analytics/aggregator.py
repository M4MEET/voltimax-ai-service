from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.collections import (
    analytics_events_collection,
    conversions_collection,
    messages_collection,
    rag_gaps_collection,
    sessions_collection,
)


class AnalyticsAggregator:

    async def _window_metrics(self, start, end) -> dict:
        """Core counts for a [start, end) time window — used for current + previous period."""
        rng = {"$gte": start, "$lt": end}
        total = await sessions_collection().count_documents({"created_at": rng})
        escalated = await sessions_collection().count_documents(
            {"created_at": rng, "status": "escalated"}
        )
        tickets = await analytics_events_collection().count_documents(
            {"event_type": "escalation", "created_at": rng}
        )
        token_result = await sessions_collection().aggregate([
            {"$match": {"created_at": rng}},
            {"$group": {"_id": None, "total_tokens": {"$sum": "$total_tokens"}}},
        ]).to_list(1)
        tokens = token_result[0]["total_tokens"] if token_result else 0
        rt_result = await analytics_events_collection().aggregate([
            {"$match": {"event_type": "response_time", "created_at": rng}},
            {"$group": {"_id": None, "avg_ms": {"$avg": "$response_time_ms"}}},
        ]).to_list(1)
        avg_response_ms = round(rt_result[0]["avg_ms"], 0) if rt_result and rt_result[0].get("avg_ms") else 0
        return {
            "total": total,
            "escalated": escalated,
            "tickets": tickets,
            "tokens": tokens,
            "escalation_rate": (escalated / total * 100) if total > 0 else 0.0,
            "resolution_rate": ((total - escalated) / total * 100) if total > 0 else 0.0,
            "avg_response_ms": avg_response_ms,
        }

    @staticmethod
    def _pct_delta(current: float, previous: float) -> float | None:
        """Percentage change vs previous period. None when no baseline to compare."""
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    async def get_overview(self, days: int = 7) -> dict:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        prev_since = now - timedelta(days=days * 2)

        cur = await self._window_metrics(since, now)
        prev = await self._window_metrics(prev_since, since)

        total = cur["total"]
        active = await sessions_collection().count_documents({"status": "active"})
        escalated = cur["escalated"]
        tickets = cur["tickets"]
        tokens = cur["tokens"]
        escalation_rate = cur["escalation_rate"]
        resolution_rate = cur["resolution_rate"]

        # Period-over-period trend deltas (None = no prior baseline)
        trends = {
            "total_chats": self._pct_delta(total, prev["total"]),
            "escalation_rate": self._pct_delta(escalation_rate, prev["escalation_rate"]),
            "ai_resolution_rate": self._pct_delta(resolution_rate, prev["resolution_rate"]),
            "tickets_created": self._pct_delta(tickets, prev["tickets"]),
            "token_usage": self._pct_delta(tokens, prev["tokens"]),
            "avg_response_ms": self._pct_delta(cur["avg_response_ms"], prev["avg_response_ms"]),
        }

        # Close reason breakdown
        close_pipeline = [
            {"$match": {"created_at": {"$gte": since}, "close_reason": {"$ne": None}}},
            {"$group": {"_id": "$close_reason", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        close_reasons = {
            doc["_id"]: doc["count"]
            async for doc in sessions_collection().aggregate(close_pipeline)
        }

        # Semantic cache stats
        try:
            from app.ai.semantic_cache import get_semantic_cache
            cache_stats = get_semantic_cache().stats()
        except Exception:
            cache_stats = {}

        return {
            "total_chats": total,
            "active_now": active,
            "escalation_rate": round(escalation_rate, 1),
            "tickets_created": tickets,
            "token_usage": tokens,
            "ai_resolution_rate": round(resolution_rate, 1),
            "avg_response_ms": int(cur["avg_response_ms"]),
            "period_days": days,
            "close_reasons": close_reasons,
            "semantic_cache": cache_stats,
            "trends": trends,
        }

    async def get_rag_gaps(self, days: int = 30, limit: int = 50) -> dict:
        """Knowledge-base gaps — FAQ/policy questions Groot answered weakly or not at all.

        Groups identical questions so frequently-asked unanswered ones rank first.
        Each group is directly actionable: add a Q&A pair or KB content for it.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {
                "_id": {"$toLower": {"$trim": {"input": "$query"}}},
                "query": {"$first": "$query"},
                "count": {"$sum": 1},
                "min_score": {"$min": "$top_score"},
                "last_asked": {"$max": "$created_at"},
            }},
            {"$sort": {"count": -1, "last_asked": -1}},
            {"$limit": limit},
        ]
        groups = await rag_gaps_collection().aggregate(pipeline).to_list(limit)
        total = await rag_gaps_collection().count_documents({"created_at": {"$gte": since}})
        return {
            "total_gaps": total,
            "unique_questions": len(groups),
            "gaps": [
                {
                    "query": g.get("query", ""),
                    "count": g.get("count", 0),
                    "min_score": round(g.get("min_score") or 0.0, 3),
                    "last_asked": g.get("last_asked").isoformat() if g.get("last_asked") else "",
                }
                for g in groups
            ],
            "period_days": days,
        }

    async def get_topic_breakdown(self, days: int = 7) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
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
        since = datetime.now(timezone.utc) - timedelta(days=days)
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
        since = datetime.now(timezone.utc) - timedelta(days=days)
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
        self, skip: int = 0, limit: int = 20, topic: str | None = None, search: str | None = None,
        tag: str | None = None, status: str | None = None, has_ticket: bool | None = None,
    ) -> dict:
        query: dict = {}
        if topic:
            query["topic_id"] = topic
        if status:
            query["status"] = status
        if tag:
            query["topic_tags"] = tag
        if has_ticket is True:
            query["events.type"] = "ticket_created"
        if search:
            query["$or"] = [
                {"customer_name": {"$regex": search, "$options": "i"}},
                {"customer_email": {"$regex": search, "$options": "i"}},
                {"topic_id": {"$regex": search, "$options": "i"}},
                {"chat_id": {"$regex": search, "$options": "i"}},
            ]

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
        since = datetime.now(timezone.utc) - timedelta(days=days)
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
        since = datetime.now(timezone.utc) - timedelta(days=days)
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

        # Enrich session with events and topic_tags for the dashboard
        if session:
            if "events" not in session:
                session["events"] = []
            if "topic_tags" not in session:
                session["topic_tags"] = []

        return {"session": session, "messages": msgs}

    async def get_product_recommendations(self, days: int = 30) -> dict:
        """Product recommendation funnel: shown → clicked (via events on sessions)."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Sessions with product_card_shown events
        shown_pipeline = [
            {"$match": {"created_at": {"$gte": since}, "events.type": "product_card_shown"}},
            {"$project": {
                "chat_id": 1,
                "customer_name": 1,
                "customer_email": 1,
                "topic_id": 1,
                "events": {"$filter": {
                    "input": "$events",
                    "as": "evt",
                    "cond": {"$in": ["$$evt.type", [
                        "product_card_shown", "cheaper_alternative_shown",
                    ]]},
                }},
            }},
        ]
        sessions_with_products = await sessions_collection().aggregate(shown_pipeline).to_list(500)

        total_shown = 0
        total_alternatives = 0
        product_mentions: dict[str, int] = {}
        for s in sessions_with_products:
            for ev in s.get("events", []):
                if ev.get("type") == "product_card_shown":
                    total_shown += 1
                    # Extract product names from detail string
                    detail = ev.get("detail", "")
                    if ":" in detail:
                        products_part = detail.split(":", 1)[1].strip() if ":" in detail else ""
                        for name in products_part.split(","):
                            name = name.strip().rstrip(".")
                            if name:
                                product_mentions[name] = product_mentions.get(name, 0) + 1
                elif ev.get("type") == "cheaper_alternative_shown":
                    total_alternatives += 1

        # Top recommended products
        top_products = sorted(product_mentions.items(), key=lambda x: -x[1])[:15]

        # Sessions with tickets after product recommendation
        ticket_after_product = await sessions_collection().count_documents({
            "created_at": {"$gte": since},
            "$and": [
                {"events.type": "product_card_shown"},
                {"events.type": "ticket_created"},
            ],
        })

        # Conversion data from the conversions collection
        conversions = await conversions_collection().find(
            {"created_at": {"$gte": since}}, {"_id": 0}
        ).sort("created_at", -1).to_list(100)

        total_revenue = sum(c.get("order_total", 0) for c in conversions)

        return {
            "total_sessions_with_recommendations": len(sessions_with_products),
            "total_product_impressions": total_shown,
            "total_alternatives_shown": total_alternatives,
            "top_recommended_products": [
                {"name": name, "count": count} for name, count in top_products
            ],
            "sessions_with_ticket_after_recommendation": ticket_after_product,
            "total_conversions": len(conversions),
            "total_revenue": round(total_revenue, 2),
            "recent_conversions": [
                {
                    "order_number": c.get("order_number", ""),
                    "order_total": c.get("order_total", 0),
                    "currency": c.get("currency", "EUR"),
                    "groot_session": c.get("groot_session", ""),
                    "created_at": c.get("created_at", "").isoformat() if hasattr(c.get("created_at", ""), "isoformat") else str(c.get("created_at", "")),
                }
                for c in conversions[:20]
            ],
            "period_days": days,
        }

    def _fill_dates(self, data: list[dict], days: int, group: str) -> list[dict]:
        """Fill in missing dates with zero values so charts show continuous timelines."""
        if group == "monthly":
            return data  # Monthly doesn't need gap-filling

        lookup = {d["_id"]: d["value"] for d in data}
        now = datetime.now(timezone.utc)
        filled = []
        for i in range(days):
            date_str = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            filled.append({"_id": date_str, "value": lookup.get(date_str, 0)})
        return filled

    async def _query_metric(self, metric: str, since: datetime, date_group: dict, date_format: str) -> list[dict]:
        """Run the aggregation for a single metric."""
        if metric == "chats":
            pipeline = [
                {"$match": {"created_at": {"$gte": since}}},
                {"$group": {"_id": date_group, "value": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
            return await sessions_collection().aggregate(pipeline).to_list(400)

        elif metric == "escalations":
            pipeline = [
                {"$match": {"created_at": {"$gte": since}, "status": "escalated"}},
                {"$group": {"_id": date_group, "value": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
            return await sessions_collection().aggregate(pipeline).to_list(400)

        elif metric == "tickets":
            pipeline = [
                {"$match": {"event_type": "escalation", "created_at": {"$gte": since}}},
                {"$group": {"_id": {"$dateToString": {"format": date_format, "date": "$created_at"}}, "value": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
            return await analytics_events_collection().aggregate(pipeline).to_list(400)

        elif metric == "tokens":
            pipeline = [
                {"$match": {"created_at": {"$gte": since}}},
                {"$group": {"_id": date_group, "value": {"$sum": "$total_tokens"}}},
                {"$sort": {"_id": 1}},
            ]
            return await sessions_collection().aggregate(pipeline).to_list(400)

        elif metric == "resolution":
            pipeline = [
                {"$match": {"created_at": {"$gte": since}}},
                {"$group": {
                    "_id": date_group,
                    "total": {"$sum": 1},
                    "escalated": {"$sum": {"$cond": [{"$eq": ["$status", "escalated"]}, 1, 0]}},
                }},
                {"$sort": {"_id": 1}},
            ]
            raw = await sessions_collection().aggregate(pipeline).to_list(400)
            return [{"_id": r["_id"], "value": round(((r["total"] - r["escalated"]) / r["total"]) * 100, 1) if r["total"] > 0 else 0} for r in raw]

        elif metric == "response_time":
            pipeline = [
                {"$match": {"event_type": "response_time", "created_at": {"$gte": since}}},
                {"$group": {"_id": {"$dateToString": {"format": date_format, "date": "$created_at"}}, "value": {"$avg": "$data.duration_ms"}}},
                {"$sort": {"_id": 1}},
            ]
            raw = await analytics_events_collection().aggregate(pipeline).to_list(400)
            return [{"_id": d["_id"], "value": round(d["value"] or 0)} for d in raw]

        return []

    async def get_timeseries(self, metric: str, days: int = 30, group: str = "daily") -> dict:
        """Return time-series data points for a metric, with zero-filled gaps."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        if group == "monthly":
            date_format = "%Y-%m"
            date_group = {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}}
        else:
            date_format = "%Y-%m-%d"
            date_group = {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}

        data = await self._query_metric(metric, since, date_group, date_format)
        filled = self._fill_dates(data, days, group)

        return {
            "metric": metric,
            "group": group,
            "days": days,
            "data": [{"date": d["_id"], "value": d["value"]} for d in filled],
        }

    async def get_combined_timeseries(self, days: int = 30, group: str = "daily") -> dict:
        """Return all metrics in one call for the combined overview chart."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        if group == "monthly":
            date_format = "%Y-%m"
            date_group = {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}}
        else:
            date_format = "%Y-%m-%d"
            date_group = {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}

        metrics = ["chats", "escalations", "tickets", "tokens", "resolution", "response_time"]
        result = {}
        for m in metrics:
            raw = await self._query_metric(m, since, date_group, date_format)
            filled = self._fill_dates(raw, days, group)
            result[m] = [{"date": d["_id"], "value": d["value"]} for d in filled]

        return {"days": days, "group": group, "metrics": result}

    async def get_performance(self, days: int = 7) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)

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
