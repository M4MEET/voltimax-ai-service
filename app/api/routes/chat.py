from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, File, Form, Query, UploadFile, WebSocket
from sse_starlette.sse import EventSourceResponse

from app.api.middleware.jwt_auth import validate_jwt
from app.chat.connection import get_connection_handler

router = APIRouter()


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time chat.

    Message protocol (browser -> server):
        {"type": "auth", "token": "<jwt>"}
        {"type": "select_topic", "topic_id": "<id>"}
        {"type": "message", "content": "<text>"}
        {"type": "not_helpful"}
        {"type": "create_ticket"}

    Message protocol (server -> browser):
        {"type": "auth_success", "topics": [...]}
        {"type": "stream_start"}
        {"type": "stream_chunk", "content": "<partial>"}
        {"type": "stream_end"}
        {"type": "typing"}
        {"type": "message", "content": "<full text>"}
        {"type": "escalation", "message": "<text>"}
        {"type": "ticket_created", "ticket_id": "<id>"}
        {"type": "error", "message": "<text>"}
    """
    handler = get_connection_handler()
    await handler.handle_websocket(websocket)


@router.get("/sse/chat")
async def sse_chat(token: str = Query(...)) -> EventSourceResponse:
    """SSE fallback endpoint for environments that don't support WebSocket.

    The client connects with ?token=<jwt> and receives server-sent events.
    Messages are sent back via POST /api/chat/send (see below).
    On connect, the auth_success event is fired with the topic list.
    """
    user_claims = validate_jwt(token)

    handler = get_connection_handler()
    topics = await handler._get_visible_topics(user_claims)

    async def event_generator():
        # Send auth success with topics — no session created here; WebSocket creates it
        yield {
            "event": "message",
            "data": json.dumps({
                "type": "auth_success",
                "topics": topics,
            }),
        }

        # Keep connection alive with periodic pings
        while True:
            await asyncio.sleep(30)
            yield {"event": "ping", "data": ""}

    return EventSourceResponse(event_generator())


@router.post("/api/chat/send")
async def sse_send_message(
    session_id: str,
    content: str,
    token: str,
) -> dict:
    """REST endpoint for SSE clients to send messages.

    The response is streamed via SSE on the /sse/chat connection.
    Returns the full AI response for clients that can't use WebSocket.
    """
    user_claims = validate_jwt(token)

    handler = get_connection_handler()
    chat_manager = handler.chat_manager

    from app.chat.models import MessageRole
    from app.ai.engine import AIEngine

    # Store user message
    await chat_manager.add_message(session_id, MessageRole.USER, content)

    session = await chat_manager.get_session(session_id)
    history = await chat_manager.get_session_messages(session_id)

    if not session:
        return {"error": "Session not found"}

    engine = AIEngine()
    full_response = ""
    should_escalate = False
    escalation_message = ""

    async for chunk in engine.process_message(
        message=content,
        session=session,
        history=history,
        user_claims=user_claims,
    ):
        if chunk.get("type") == "token":
            full_response += chunk["content"]
        elif chunk.get("type") == "escalation":
            should_escalate = True
            escalation_message = chunk["message"]
            await chat_manager.escalate_session(session_id, chunk.get("reason", "ai_detected"))
            break

    if should_escalate:
        return {"type": "escalation", "message": escalation_message}

    await chat_manager.add_message(session_id, MessageRole.ASSISTANT, full_response)
    return {"type": "message", "content": full_response}


# ── Compatibility filter API (proxies Shopware OncoCompatibilityFilter) ────


@router.get("/api/compatibility/children")
async def compatibility_children(parent_id: str | None = Query(None)):
    """Get child options for a compatibility level. No parent_id = root."""
    from app.shopware.client import ShopwareClient
    client = ShopwareClient()
    children = await client.compatibility_get_children(parent_id)
    return {"children": children}


@router.get("/api/compatibility/result")
async def compatibility_result(object_id: str = Query(...)):
    """Get the product page URL for a selected compatibility object."""
    from app.shopware.client import ShopwareClient
    client = ShopwareClient()
    url = await client.compatibility_get_result(object_id)
    # Replace internal Docker URL with public shop URL
    if url and "shopware." in url:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        url = f"https://voltimax.de{parsed.path}"
    return {"url": url}


@router.get("/api/media/download")
async def media_download(url: str = Query(...)):
    """Proxy download for Shopware media files (bypasses internal Docker SSL)."""
    from fastapi.responses import StreamingResponse
    from app.shopware.client import ShopwareClient
    client = ShopwareClient()
    content = await client.download_media_content(url)
    if not content:
        from fastapi import HTTPException
        raise HTTPException(404, "File not found")
    # Guess content type from URL
    filename = url.rsplit("/", 1)[-1] if "/" in url else "document.pdf"
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/media/search")
async def media_search(query: str = Query(...)):
    """Search Shopware media for documents matching a query."""
    from app.shopware.client import ShopwareClient
    client = ShopwareClient()
    keywords = [w.lower() for w in query.split() if len(w) >= 3]
    docs = await client.get_media_documents(keywords=keywords, limit=10)
    return {"documents": docs}


@router.post("/api/chat/batteriepfand-upload")
async def batteriepfand_upload(
    file: UploadFile = File(...),
    form_type: str = Form(""),
    customer_name: str = Form(""),
    customer_email: str = Form(""),
    session_id: str = Form(""),
    additional_info: str = Form(""),
):
    """Upload a Batteriepfand PDF to Zendesk and create a ticket.

    form_type: 'entsorgungsnachweis' or 'ruecksendung'
    """
    import logging
    logger = logging.getLogger(__name__)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"error": f"'{file.filename}' ist keine PDF-Datei", "success": False}

    type_labels = {
        "entsorgungsnachweis": "Entsorgungsnachweis",
        "ruecksendung": "R\u00fccksendung Altbatterie",
    }
    type_label = type_labels.get(form_type, form_type or "Batteriepfand")

    try:
        from app.escalation.ticket.zendesk_adapter import ZendeskAdapter
        adapter = ZendeskAdapter()

        content = await file.read()
        token = await adapter.upload_attachment(file.filename, content, "application/pdf")
        if not token:
            return {"error": "Upload fehlgeschlagen", "success": False}

        description = (
            f"Batteriepfand-Anfrage von {customer_name} ({customer_email}).\n\n"
            f"Formular: {type_label}\n"
            f"Datei: {file.filename}\n"
        )
        if additional_info:
            description += f"\nZus\u00e4tzliche Informationen:\n{additional_info}\n"
        description += f"\nSession: {session_id}"

        ticket_id = await adapter.create_ticket_with_attachments(
            subject=f"Groot Escalation \u2014 Batteriepfand ({type_label})",
            description=description,
            customer_email=customer_email,
            customer_name=customer_name,
            attachment_tokens=[token],
            tags=["voltimax-chat", "ai-escalation", "batteriepfand", form_type],
        )

        if session_id:
            try:
                from app.chat.manager import ChatManager
                from app.chat.models import MessageRole
                mgr = ChatManager()
                # Log session event
                await mgr.add_session_event(
                    session_id, "batteriepfand_submitted",
                    f"Zendesk #{ticket_id} \u2014 {type_label}",
                )
                # Add confirmation message to chat transcript so it's visible in dashboard
                confirm_msg = (
                    f"\u2705 Dein Batteriepfand-Formular ({type_label}) wurde erfolgreich eingereicht!\n\n"
                    f"**Zendesk Ticket #{ticket_id}** wurde erstellt. "
                    f"Unser Team wird deine Anfrage pr\u00fcfen und sich bei dir melden."
                )
                await mgr.add_message(session_id, MessageRole.ASSISTANT, confirm_msg)
                # Also log ticket_created event so it shows in dashboard badges
                await mgr.add_session_event(
                    session_id, "ticket_created",
                    f"Batteriepfand #{ticket_id} \u2014 {type_label}",
                )
            except Exception:
                pass

        logger.info(f"Batteriepfand ticket created: #{ticket_id} ({type_label}) for {customer_email}")
        return {"success": True, "ticket_id": ticket_id}

    except Exception as e:
        logger.error(f"Batteriepfand upload failed: {e}")
        return {"error": str(e), "success": False}
