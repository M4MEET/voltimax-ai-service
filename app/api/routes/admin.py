from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import verify_dashboard_auth
from app.analytics.aggregator import AnalyticsAggregator
from app.config import get_config
from app.db.admin_config import get_admin_config, set_admin_config
from app.tasks.purge import purge_old_sessions

router = APIRouter(
    prefix="/api/admin",
    dependencies=[Depends(verify_dashboard_auth)],
)

aggregator = AnalyticsAggregator()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class LlmProviderEntry(BaseModel):
    api_key: str = ""
    default_model: str = ""
    base_url: str = ""
    enabled: bool = True


# ---------------------------------------------------------------------------
# LLM Config
# ---------------------------------------------------------------------------


@router.get("/config/llm")
async def get_llm_config() -> dict:
    """Return current LLM provider config, masking api_key values."""
    data: dict[str, Any] | None = await get_admin_config("llm_providers")
    if data is None:
        # Fall back to config.yaml
        cfg = get_config()
        data = {
            name: prov.model_dump()
            for name, prov in cfg.llm_providers.items()
        }
    # Mask api_key values
    masked = {}
    for provider, entry in data.items():
        entry_copy = dict(entry)
        if entry_copy.get("api_key"):
            entry_copy["api_key"] = "***"
        masked[provider] = entry_copy
    return masked


@router.put("/config/llm")
async def update_llm_config(body: dict[str, LlmProviderEntry]) -> dict:
    """Update LLM provider config. Keeps existing keys when api_key is '' or '***'."""
    # Load existing stored config (or fall back to yaml)
    existing: dict[str, Any] | None = await get_admin_config("llm_providers")
    if existing is None:
        cfg = get_config()
        existing = {
            name: prov.model_dump()
            for name, prov in cfg.llm_providers.items()
        }

    merged: dict[str, Any] = dict(existing)
    for provider, entry in body.items():
        prev = merged.get(provider, {})
        new_entry = entry.model_dump()
        # Keep existing key when placeholder is sent
        if new_entry["api_key"] in ("", "***"):
            new_entry["api_key"] = prev.get("api_key", "")
        merged[provider] = new_entry

    await set_admin_config("llm_providers", merged)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Topic Cards
# ---------------------------------------------------------------------------


@router.get("/topics")
async def get_topics() -> list:
    """Return current topic cards config."""
    data = await get_admin_config("topic_cards")
    if data is None:
        cfg = get_config()
        data = [c.model_dump() for c in cfg.topic_cards]
    return data


@router.put("/topics")
async def update_topics(body: list[dict]) -> dict:
    """Update topic cards. Builds routing map and saves both configs."""

    def collect_routing(cards: list[dict], routing: dict[str, str]) -> None:
        for card in cards:
            provider = card.get("llm_provider")
            if provider:
                routing[card.get("id", "")] = provider
            sub = card.get("sub_cards", [])
            if sub:
                collect_routing(sub, routing)

    routing: dict[str, str] = {}
    collect_routing(body, routing)

    await set_admin_config("topic_cards", body)
    await set_admin_config("topic_routing", routing)

    return {"ok": True, "routing": routing}


# ---------------------------------------------------------------------------
# Knowledge Base
# ---------------------------------------------------------------------------


@router.get("/knowledge/status")
async def knowledge_status() -> dict:
    """Return knowledge base status."""
    from app.knowledge.manager import KnowledgeManager  # lazy import

    km = KnowledgeManager()
    return await km.get_status()


@router.post("/knowledge/sync-cms")
async def knowledge_sync_cms() -> dict:
    """Trigger CMS sync into the knowledge base."""
    from app.knowledge.manager import KnowledgeManager  # lazy import

    km = KnowledgeManager()
    return await km.sync_cms()


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


@router.get("/performance")
async def performance(days: int = Query(7, ge=1, le=365)) -> dict:
    """Response time and LLM latency stats."""
    return await aggregator.get_performance(days)


# ---------------------------------------------------------------------------
# GDPR – delete customer data
# ---------------------------------------------------------------------------


@router.delete("/customers/{email}/data")
async def delete_customer_data(email: str) -> dict:
    """Delete all sessions, messages, and analytics events for an email."""
    from app.db.collections import (  # lazy import
        analytics_events_collection,
        messages_collection,
        sessions_collection,
    )

    cursor = sessions_collection().find({"customer_email": email}, {"id": 1, "_id": 0})
    session_docs = await cursor.to_list(10000)
    session_ids = [s["id"] for s in session_docs if "id" in s]

    if session_ids:
        await messages_collection().delete_many({"session_id": {"$in": session_ids}})
        await analytics_events_collection().delete_many({"session_id": {"$in": session_ids}})
        await sessions_collection().delete_many({"customer_email": email})

    return {"email": email, "deleted_sessions": len(session_ids)}


# ---------------------------------------------------------------------------
# Manual Purge
# ---------------------------------------------------------------------------


@router.post("/purge")
async def manual_purge() -> dict:
    """Manually trigger the old-session purge task."""
    count = await purge_old_sessions()
    return {"deleted": count}
