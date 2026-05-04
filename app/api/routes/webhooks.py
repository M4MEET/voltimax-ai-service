from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks")


@router.post("/n8n")
async def n8n_webhook(request: Request) -> dict:
    """Receive incoming webhooks from n8n workflows.

    n8n can call this endpoint to:
    - Notify when a ticket has been created (with ticket_id)
    - Trigger knowledge base ingestion
    - Send alerts back to the system

    The payload is expected to contain at minimum a 'type' field.
    """
    config = get_config()

    # Verify request comes with valid API key
    api_key = request.headers.get("X-Voltimax-Api-Key", "")
    if api_key != config.shopware.api_key:
        raise HTTPException(401, "Invalid API key")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    event_type = payload.get("type", "unknown")
    logger.info(f"Received n8n webhook: type={event_type}")

    if event_type == "ticket_created":
        ticket_id = payload.get("ticket_id")
        session_id = payload.get("session_id")
        logger.info(f"Ticket created: ticket_id={ticket_id}, session_id={session_id}")
        return {"status": "acknowledged", "ticket_id": ticket_id}

    elif event_type == "ingestion_complete":
        source_id = payload.get("source_id")
        logger.info(f"Knowledge ingestion complete: source_id={source_id}")
        return {"status": "acknowledged", "source_id": source_id}

    elif event_type == "alert":
        message = payload.get("message", "")
        logger.warning(f"Alert from n8n: {message}")
        return {"status": "acknowledged"}

    else:
        logger.info(f"Unhandled webhook type: {event_type}")
        return {"status": "received", "type": event_type}
