"""MongoDB logging handler — persists Python log records to the `logs` collection."""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone

_buffer: list[dict] = []
_MAX_BUFFER = 5


def logs_collection():
    from app.db.mongodb import get_db
    return get_db()["logs"]


class MongoLogHandler(logging.Handler):
    """Async-safe handler that buffers log records and flushes to MongoDB."""

    def emit(self, record: logging.LogRecord) -> None:
        doc = {
            "timestamp": datetime.now(timezone.utc),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }
        if record.exc_info and record.exc_info[1]:
            doc["traceback"] = traceback.format_exception(*record.exc_info)

        _buffer.append(doc)
        if len(_buffer) >= _MAX_BUFFER:
            self._flush_sync()

    @staticmethod
    def _flush_sync() -> None:
        """Best-effort flush — runs from sync context, schedules async insert."""
        import asyncio

        if not _buffer:
            return
        batch = _buffer.copy()
        _buffer.clear()

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_insert_batch(batch))
        except RuntimeError:
            pass  # no event loop — drop silently (startup/shutdown)


async def _insert_batch(docs: list[dict]) -> None:
    try:
        await logs_collection().insert_many(docs, ordered=False)
    except Exception:
        pass  # never break the app over logging


async def flush_logs() -> None:
    """Explicit flush — call on shutdown or periodically."""
    if _buffer:
        batch = _buffer.copy()
        _buffer.clear()
        await _insert_batch(batch)
