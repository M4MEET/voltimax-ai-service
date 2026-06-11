from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
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

    try:
        return await KnowledgeManager().sync_cms()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"CMS sync failed: {exc}") from exc


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
    session_docs = await cursor.to_list(None)
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


@router.post("/prompts/refresh")
async def refresh_prompts() -> dict:
    """Invalidate the prompt cache so LangSmith changes take effect immediately."""
    from app.ai.prompt_hub import invalidate_cache
    invalidate_cache()
    return {"status": "ok", "message": "Prompt cache cleared. Next request will pull fresh from LangSmith."}


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@router.get("/agents")
async def get_agents() -> list:
    """List all agent configurations."""
    from app.ai.agents import AGENTS

    return [
        {"id": topic_id, **{k: v for k, v in agent.items()}}
        for topic_id, agent in AGENTS.items()
    ]


# ---------------------------------------------------------------------------
# Prompts (LangSmith)
# ---------------------------------------------------------------------------


@router.get("/prompts")
async def get_prompts() -> dict:
    """List all LangSmith prompts with cache status."""
    import os

    from app.ai.prompt_hub import _cache, _pull_raw

    # Known prompts with metadata
    known_prompts = {
        "groot-system-prompt": {"type": "mustache", "used_by": "Response Generator", "description": "Main AI persona, shop context, instructions", "active": True},
        "groot-unified-classifier": {"type": "mustache", "used_by": "Unified Classifier", "description": "Card action + intent + search query + complexity in one call", "active": True},
        "groot-intent-classifier": {"type": "plain", "used_by": "Intent Classifier (legacy)", "description": "Fallback intent classifier — only runs if unified classifier is bypassed", "active": False},
        "groot-escalation-detector": {"type": "plain", "used_by": "Escalation Detector", "description": "Rates customer frustration 0.0-1.0 for auto-escalation", "active": True},
        "groot-summarizer": {"type": "plain", "used_by": "Ticket Summarizer", "description": "Summarizes conversation for Zendesk ticket creation", "active": True},
        "groot-card-router": {"type": "mustache", "used_by": "Card Router (removed)", "description": "Legacy — replaced by unified classifier. Not loaded at runtime.", "active": False},
        "groot-pre-classifier": {"type": "mustache", "used_by": "Pre-classifier (removed)", "description": "Legacy — replaced by unified classifier. Not loaded at runtime.", "active": False},
        "groot-greeting": {"type": "mustache", "used_by": "Greeting Generator (removed)", "description": "Legacy — greeting is now inline in agents.py. Not loaded at runtime.", "active": False},
        "groot-correctness-evaluator": {"type": "mustache", "used_by": "LangSmith Evaluator", "description": "Online evaluator for response correctness scoring", "active": True},
    }

    endpoint = os.getenv("LANGCHAIN_ENDPOINT", "https://eu.api.smith.langchain.com")
    enabled = bool(os.getenv("LANGCHAIN_API_KEY"))

    # Try to fetch all prompts from LangSmith
    langsmith_names: list[str] = []
    if enabled:
        try:
            from langsmith import Client
            client = Client()
            result = client.list_prompts()
            prompt_list = getattr(result, 'repos', None) or []
            for prompt in prompt_list:
                name = getattr(prompt, 'repo_handle', None) or getattr(prompt, 'name', None)
                if name and name.startswith("groot-"):
                    langsmith_names.append(name)
        except Exception as e:
            logger.warning(f"Failed to list LangSmith prompts: {e}")

    # Merge: known prompts + any extra from LangSmith
    all_names = list(known_prompts.keys())
    for name in langsmith_names:
        if name not in all_names:
            all_names.append(name)

    prompts = []
    for name in all_names:
        meta = known_prompts.get(name, {"type": "unknown", "used_by": "—", "description": "Prompt from LangSmith", "active": True})
        cached_entry = _cache.get(name)
        cached_content = cached_entry[1] if cached_entry else None
        prompts.append({
            "name": name,
            "type": meta["type"],
            "used_by": meta["used_by"],
            "description": meta["description"],
            "active": meta["active"],
            "cached": cached_content is not None,
            "status": "cached" if cached_content else ("in LangSmith" if name in langsmith_names else "available"),
            "char_count": len(cached_content) if cached_content else 0,
            "preview": (cached_content[:500] + "...") if cached_content and len(cached_content) > 500 else (cached_content or ""),
            "in_langsmith": name in langsmith_names,
        })

    return {"prompts": prompts, "endpoint": endpoint, "enabled": enabled}


# ---------------------------------------------------------------------------
# Active WebSocket connections
# ---------------------------------------------------------------------------


@router.get("/active-connections")
async def get_active_connections() -> dict:
    """Return the current number of active WebSocket connections and their session IDs."""
    from app.chat.connection import get_connection_handler

    handler = get_connection_handler()
    active_ids = list(handler.active_connections.keys())
    return {"active": len(active_ids), "session_ids": active_ids}


# ---------------------------------------------------------------------------
# Zendesk Tickets (created by Groot)
# ---------------------------------------------------------------------------


@router.get("/tickets")
async def get_recent_tickets(limit: int = Query(20, ge=1, le=100)) -> dict:
    """Return recent sessions where a Zendesk ticket was created."""
    from app.db.collections import sessions_collection

    cursor = (
        sessions_collection()
        .find(
            {"escalation_reason": "ticket_created"},
            {
                "_id": 0,
                "id": 1,
                "customer_name": 1,
                "customer_email": 1,
                "topic_id": 1,
                "order_number": 1,
                "created_at": 1,
                "events": 1,
            },
        )
        .sort("created_at", -1)
        .limit(limit)
    )
    sessions = await cursor.to_list(length=limit)

    tickets = []
    for s in sessions:
        ticket_id = ""
        for ev in s.get("events") or []:
            if ev.get("type") == "ticket_created":
                detail = ev.get("detail", "")
                if "#" in detail:
                    ticket_id = detail.split("#")[1].split(" ")[0].split("\u2014")[0].strip()
                break
        tickets.append(
            {
                "session_id": s.get("id", ""),
                "customer_name": s.get("customer_name", ""),
                "customer_email": s.get("customer_email", ""),
                "topic_id": s.get("topic_id", ""),
                "order_number": s.get("order_number", ""),
                "ticket_id": ticket_id,
                "created_at": str(s.get("created_at", "")),
            }
        )

    return {"tickets": tickets, "total": len(tickets)}


# ---------------------------------------------------------------------------
# Test Agent
# ---------------------------------------------------------------------------


class TestAgentRequest(BaseModel):
    agent_id: str
    message: str


@router.post("/test-agent")
async def test_agent(body: TestAgentRequest) -> dict:
    """Send a sample message to an agent and return the response."""
    from app.ai.agents import get_agent_system_prefix
    from app.ai.router import get_default_provider, get_provider

    prefix = get_agent_system_prefix(body.agent_id)
    provider = get_provider(get_default_provider())
    response = await provider.generate(
        [{"role": "user", "content": body.message}],
        system_prompt=prefix,
        temperature=0.7,
        max_tokens=200,
    )
    return {"agent_id": body.agent_id, "response": response}


# ---------------------------------------------------------------------------
# Re-embed knowledge vectors
# ---------------------------------------------------------------------------


@router.post("/reembed")
async def trigger_reembed() -> dict:
    """Re-embed all knowledge vectors using the current embedding model."""
    from app.config import get_config as _get_config
    from app.db.collections import knowledge_vectors_collection
    from app.knowledge.embedder import get_embeddings

    coll = knowledge_vectors_collection()
    embeddings = get_embeddings()
    config = _get_config()

    docs = await coll.find({}, {"_id": 1, "content": 1}).to_list(length=10000)
    if not docs:
        return {"status": "no_documents", "count": 0}

    # Re-embed in batches
    batch_size = 50
    done = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        texts = [d["content"] for d in batch]
        vectors = await embeddings.aembed_documents(texts)
        for doc, vector in zip(batch, vectors):
            await coll.update_one({"_id": doc["_id"]}, {"$set": {"embedding": vector}})
        done += len(batch)

    return {
        "status": "completed",
        "count": done,
        "model": config.knowledge_base.embedding_model,
    }
