from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_config

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    global _client, _db
    config = get_config()
    _client = AsyncIOMotorClient(config.mongodb.uri)
    _db = _client[config.mongodb.database]
    await _ensure_indexes()


async def close_db() -> None:
    global _client, _db
    if _client:
        _client.close()
    _client = None
    _db = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not connected. Call connect_db() first.")
    return _db


async def _ensure_indexes() -> None:
    db = get_db()

    # Chat sessions collection
    sessions = db["chat_sessions"]
    await sessions.create_index("customer_email")
    await sessions.create_index("created_at")
    await sessions.create_index("topic_id")
    await sessions.create_index("status")

    # Chat messages collection
    messages = db["chat_messages"]
    await messages.create_index("session_id")
    await messages.create_index("created_at")

    # Knowledge base collection
    knowledge = db["knowledge_sources"]
    await knowledge.create_index("source_type")
    await knowledge.create_index("status")

    # Knowledge vectors collection (Atlas Vector Search index created separately)
    vectors = db["knowledge_vectors"]
    await vectors.create_index("source_id")
    await vectors.create_index("source_type")

    # Analytics events collection
    events = db["analytics_events"]
    await events.create_index("event_type")
    await events.create_index("created_at")
    await events.create_index([("event_type", 1), ("created_at", -1)])

    # Q&A pairs collection
    qa_pairs = db["qa_pairs"]
    await qa_pairs.create_index("question")

    # Admin config collection
    await db["admin_config"].create_index("type", unique=True)
