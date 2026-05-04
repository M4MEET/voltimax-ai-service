from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.chat.manager import ChatManager

router = APIRouter(prefix="/chat", tags=["session"])

_manager = ChatManager()


# ── Request bodies ─────────────────────────────────────────────────────────────

class SessionStartRequest(BaseModel):
    chat_id: str      # Server A's local session/chat ID
    topic_id: str
    session_id: str | None = None  # If provided (WebSocket session), link rather than create


class FeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    feedback: str     # 'up' | 'down'


class RatingRequest(BaseModel):
    session_id: str
    rating: int = Field(ge=1, le=5)


class EndRequest(BaseModel):
    session_id: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/session/start")
async def session_start(
    body: SessionStartRequest,
    user_claims: dict = Depends(get_current_user),
) -> dict:
    """Called when the user selects a topic.
    If the WebSocket session_id is provided, links it to the chat_id.
    Otherwise creates a new session (SSE-only fallback)."""
    if body.session_id:
        # WebSocket session already exists — just store the chat_id linkage
        await _manager.sessions_collection_update(body.session_id, body.chat_id)
        return {"ok": True, "session_id": body.session_id}

    # SSE-only fallback: create a fresh session
    session = await _manager.create_session(
        customer_name=user_claims.get("name", ""),
        customer_email=user_claims.get("email", ""),
        order_number=user_claims.get("order_number"),
        sales_channel_id=user_claims.get("sales_channel_id"),
        chat_id=body.chat_id,
        topic_id=body.topic_id,
    )
    return {"ok": True, "session_id": session.id}


@router.post("/feedback")
async def record_feedback(
    body: FeedbackRequest,
    user_claims: dict = Depends(get_current_user),
) -> dict:
    """Called when the user taps 👍 or 👎 on an AI message."""
    if body.feedback not in ("up", "down"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="feedback must be 'up' or 'down'",
        )
    await _manager.record_feedback(body.message_id, body.feedback)
    return {"ok": True}


@router.post("/rating")
async def record_rating(
    body: RatingRequest,
    user_claims: dict = Depends(get_current_user),
) -> dict:
    """Called when the user submits a star rating (1–5) at end of session."""
    await _manager.record_rating(body.session_id, body.rating)
    return {"ok": True}


@router.post("/end")
async def session_end(
    body: EndRequest,
    user_claims: dict = Depends(get_current_user),
) -> dict:
    """Called when the user closes the chat widget."""
    await _manager.close_session(body.session_id)
    return {"ok": True}


@router.get("/document/{document_id}/{deep_link_code}")
async def download_document(document_id: str, deep_link_code: str):
    """Proxy document download from Shopware Admin API.

    This avoids requiring the customer to be logged into the storefront.
    The deep_link_code acts as the auth — it's a unique secret per document.
    """
    from app.shopware.client import ShopwareClient

    client = ShopwareClient()
    token = await client.get_oauth_token()
    if not token:
        raise HTTPException(status_code=503, detail="Shopware unavailable")

    import httpx
    from app.config import get_config
    config = get_config()

    async with httpx.AsyncClient(verify=False, timeout=30) as http:
        # Try Admin API download
        resp = await http.get(
            f"{config.shopware.server_a_url}/api/_action/document/{document_id}/{deep_link_code}",
            headers={"Authorization": f"Bearer {token}"},
        )

        if resp.status_code == 200 and "application/json" not in resp.headers.get("content-type", ""):
            content_type = resp.headers.get("content-type", "application/pdf")
            filename = resp.headers.get("content-disposition", "")
            if "filename=" in filename:
                filename = filename.split("filename=")[-1].strip('"')
            else:
                filename = f"document-{document_id}.pdf"

            return StreamingResponse(
                iter([resp.content]),
                media_type=content_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        # If Admin API fails, redirect to storefront route (customer may need to login)
        storefront_url = f"{config.shopware.server_a_url}/account/order/document/{document_id}/{deep_link_code}"
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=storefront_url)
