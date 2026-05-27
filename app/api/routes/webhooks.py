from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.config import get_config
from app.db.collections import conversions_collection

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


@router.post("/conversion")
async def track_conversion(request: Request) -> dict:
    """Track a purchase attributed to a Groot chat recommendation.

    Called from Shopware checkout finish page when groot_attribution cookie exists.
    No auth required — the data is non-sensitive (order number + total) and
    the attribution cookie validates the flow.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    order_number = payload.get("order_number", "")
    if not order_number:
        raise HTTPException(400, "order_number is required")

    doc = {
        "order_number": order_number,
        "order_total": payload.get("order_total", 0),
        "currency": payload.get("currency", "EUR"),
        "items_count": payload.get("items_count", 0),
        "groot_ref": payload.get("groot_ref", "chat"),
        "groot_session": payload.get("groot_session", ""),
        "groot_campaign": payload.get("groot_campaign", ""),
        "product_page": payload.get("product_page", ""),
        "created_at": datetime.now(timezone.utc),
    }

    # Deduplicate — don't record the same order twice
    existing = await conversions_collection().find_one({"order_number": order_number})
    if existing:
        return {"status": "already_tracked", "order_number": order_number}

    await conversions_collection().insert_one(doc)
    logger.info(f"Groot conversion tracked: order={order_number}, total={doc['order_total']}, session={doc['groot_session']}")
    return {"status": "tracked", "order_number": order_number}
