from __future__ import annotations

import uuid
from datetime import datetime

from app.chat.models import ChatMessage, ChatSession, MessageRole, SessionStatus
from app.db.collections import (
    analytics_events_collection,
    consent_log_collection,
    messages_collection,
    sessions_collection,
)


class ChatManager:
    """Manages chat session lifecycle and message persistence."""

    async def create_session(
        self,
        customer_name: str,
        customer_email: str,
        order_number: str | None = None,
        sales_channel_id: str | None = None,
        chat_id: str | None = None,
        topic_id: str | None = None,
    ) -> ChatSession:
        session = ChatSession(
            id=str(uuid.uuid4()),
            customer_name=customer_name,
            customer_email=customer_email,
            order_number=order_number,
            sales_channel_id=sales_channel_id,
            topic_id=topic_id,
        )

        doc = session.model_dump()
        if chat_id:
            doc["chat_id"] = chat_id  # Server A's local session ID for cross-reference

        await sessions_collection().insert_one(doc)

        await analytics_events_collection().insert_one({
            "event_type": "session_started",
            "session_id": session.id,
            "chat_id": chat_id,
            "customer_email": customer_email,
            "topic_id": topic_id,
            "created_at": datetime.utcnow(),
        })

        # GDPR consent log — mirror of Shopware's consent_log table
        await consent_log_collection().insert_one({
            "session_id": session.id,
            "chat_id": chat_id,
            "customer_name": customer_name,
            "customer_email": customer_email or "",
            "consented_at": datetime.utcnow(),
        })

        return session

    async def set_topic(self, session_id: str, topic_id: str, llm_provider: str) -> None:
        await sessions_collection().update_one(
            {"id": session_id},
            {
                "$set": {
                    "topic_id": topic_id,
                    "llm_provider": llm_provider,
                    "updated_at": datetime.utcnow(),
                },
                "$addToSet": {"topic_tags": topic_id},
            },
        )

        await analytics_events_collection().insert_one({
            "event_type": "topic_selected",
            "session_id": session_id,
            "topic_id": topic_id,
            "llm_provider": llm_provider,
            "created_at": datetime.utcnow(),
        })

    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        metadata: dict | None = None,
        message_id: str | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            id=message_id or str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata or {},
        )

        await messages_collection().insert_one(message.model_dump())

        # Update session counters
        update: dict = {
            "$inc": {"message_count": 1},
            "$set": {"updated_at": datetime.utcnow()},
        }
        if metadata and "tokens_used" in metadata:
            update["$inc"]["total_tokens"] = metadata["tokens_used"]

        await sessions_collection().update_one({"id": session_id}, update)

        return message

    async def get_session_messages(self, session_id: str, limit: int = 500) -> list[dict]:
        cursor = (
            messages_collection()
            .find({"session_id": session_id}, {"_id": 0})
            .sort("created_at", 1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    async def get_session(self, session_id: str) -> dict | None:
        return await sessions_collection().find_one(
            {"id": session_id},
            {"_id": 0},
        )

    async def escalate_session(self, session_id: str, reason: str) -> None:
        await sessions_collection().update_one(
            {"id": session_id},
            {
                "$set": {
                    "status": SessionStatus.ESCALATED.value,
                    "escalation_reason": reason,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        await analytics_events_collection().insert_one({
            "event_type": "escalation",
            "session_id": session_id,
            "reason": reason,
            "created_at": datetime.utcnow(),
        })

    async def set_language(self, session_id: str, language: str) -> None:
        await sessions_collection().update_one(
            {"id": session_id},
            {"$set": {"language": language, "updated_at": datetime.utcnow()}},
        )

    async def sessions_collection_update(self, session_id: str, chat_id: str) -> None:
        """Link a WebSocket session to a Server A chat_id."""
        from datetime import datetime
        await sessions_collection().update_one(
            {"id": session_id},
            {"$set": {"chat_id": chat_id, "updated_at": datetime.utcnow()}},
        )

    async def record_feedback(self, message_id: str, feedback: str) -> None:
        await analytics_events_collection().insert_one({
            "event_type": "message_feedback",
            "message_id": message_id,
            "feedback": feedback,  # 'up' | 'down'
            "created_at": datetime.utcnow(),
        })

    async def record_rating(self, session_id: str, rating: int) -> None:
        await sessions_collection().update_one(
            {"id": session_id},
            {"$set": {"rating": rating, "updated_at": datetime.utcnow()}},
        )
        await analytics_events_collection().insert_one({
            "event_type": "session_rated",
            "session_id": session_id,
            "rating": rating,
            "created_at": datetime.utcnow(),
        })

    async def cache_order_data(self, session_id: str, order_data: dict) -> None:
        """Cache the full Shopware order data in the session for follow-up queries."""
        await sessions_collection().update_one(
            {"id": session_id},
            {"$set": {"cached_order_data": order_data, "updated_at": datetime.utcnow()}},
        )

    async def update_session_order(self, session_id: str, order_number: str) -> None:
        await sessions_collection().update_one(
            {"id": session_id},
            {"$set": {"order_number": order_number, "updated_at": datetime.utcnow()}},
        )

    async def update_session_email(self, session_id: str, email: str) -> None:
        """Update the customer email on the session."""
        await sessions_collection().update_one(
            {"id": session_id},
            {"$set": {"customer_email": email, "updated_at": datetime.utcnow()}},
        )

    async def update_session_field(self, session_id: str, field: str, value) -> None:
        """Update a single field on the session document."""
        await sessions_collection().update_one(
            {"id": session_id},
            {"$set": {field: value, "updated_at": datetime.utcnow()}},
        )

    async def add_session_event(self, session_id: str, event_type: str, detail: str = "") -> None:
        """Append a lightweight event to the session's event log.

        Events track non-message interactions (cards shown, verification attempts,
        button clicks) so the AI has full session context without polluting the
        message history that goes into ticket transcripts.
        """
        event = {
            "type": event_type,
            "detail": detail,
            "ts": datetime.utcnow().strftime("%H:%M"),
        }
        await sessions_collection().update_one(
            {"id": session_id},
            {
                "$push": {"events": event},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )

    async def close_session(self, session_id: str, close_reason: str = "completed") -> None:
        await sessions_collection().update_one(
            {"id": session_id},
            {
                "$set": {
                    "status": SessionStatus.CLOSED.value,
                    "close_reason": close_reason,
                    "closed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        session = await self.get_session(session_id)
        if session:
            await analytics_events_collection().insert_one({
                "event_type": "session_closed",
                "session_id": session_id,
                "close_reason": close_reason,
                "message_count": session.get("message_count", 0),
                "total_tokens": session.get("total_tokens", 0),
                "topic_id": session.get("topic_id"),
                "created_at": datetime.utcnow(),
            })
