from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.collections import admin_config_collection


async def get_admin_config(config_type: str) -> Any | None:
    """Return stored data for the given config_type, or None if not set."""
    doc = await admin_config_collection().find_one(
        {"type": config_type}, {"_id": 0, "data": 1}
    )
    return doc["data"] if doc else None


async def set_admin_config(config_type: str, data: Any) -> None:
    """Upsert config data for the given config_type."""
    await admin_config_collection().update_one(
        {"type": config_type},
        {"$set": {"type": config_type, "data": data, "updated_at": datetime.utcnow()}},
        upsert=True,
    )
