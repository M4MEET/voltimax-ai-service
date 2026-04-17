from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.config import get_config
from app.db.collections import analytics_events_collection, messages_collection, sessions_collection

logger = logging.getLogger(__name__)


async def purge_old_sessions() -> int:
    """Delete sessions older than retention_days. Returns count deleted."""
    config = get_config()
    retention = config.analytics.retention_days
    if retention <= 0:
        return 0

    cutoff = datetime.utcnow() - timedelta(days=retention)
    cursor = sessions_collection().find({"created_at": {"$lt": cutoff}}, {"id": 1, "_id": 0})
    old_sessions = await cursor.to_list(10000)
    if not old_sessions:
        return 0

    session_ids = [s["id"] for s in old_sessions if "id" in s]
    await messages_collection().delete_many({"session_id": {"$in": session_ids}})
    await analytics_events_collection().delete_many({"session_id": {"$in": session_ids}})
    result = await sessions_collection().delete_many({"created_at": {"$lt": cutoff}})

    logger.info("Purged %d sessions older than %d days", result.deleted_count, retention)
    return result.deleted_count
