from __future__ import annotations

import logging

from app.ai.graph.nodes.summarizer import summarize_conversation
from app.chat.manager import ChatManager
from app.config import get_config
from app.escalation.ticket.base import BaseTicketAdapter

logger = logging.getLogger(__name__)


class EscalationActions:
    def __init__(self):
        self.chat_manager = ChatManager()

    async def create_ticket(self, session_id: str) -> dict:
        """Summarize conversation, create ticket, send emails. Returns dict with ticket details."""
        session = await self.chat_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        history = await self.chat_manager.get_session_messages(session_id)
        from app.ai.router import get_default_provider
        llm_provider = session.get("llm_provider") or get_default_provider()
        topic = session.get("topic_id", "General")
        ticket_subject = session.get("ticket_subject") or f"Groot Escalation \u2014 {topic}"
        customer_email = session.get("customer_email", "")
        customer_name = session.get("customer_name", "")
        escalation_reason = session.get("escalation_reason", "customer_request")

        # 1. AI summarizes the conversation (with order data + session events for full context)
        summary = await summarize_conversation(
            session_id, history, llm_provider,
            order_data=session.get("cached_order_data"),
            session_events=session.get("events"),
        )

        # 2. Build full transcript
        transcript = "\n".join([
            f"{'Customer' if msg['role'] == 'user' else 'Groot (AI)'}: {msg['content']}"
            for msg in history
        ])

        # 3. Create the support ticket (Zendesk or n8n)
        adapter = self._get_adapter()
        ticket_id = await adapter.create_ticket(
            subject=ticket_subject,
            description=f"AI Summary:\n{summary}\n\n--- Full Transcript ---\n{transcript}",
            customer_email=customer_email,
            customer_name=customer_name,
            metadata={
                "session_id": session_id,
                "topic": topic,
                "escalation_reason": escalation_reason,
                "message_count": session.get("message_count", 0),
                "order_number": session.get("order_number", ""),
            },
        )

        # 4. Mark session as escalated
        await self.chat_manager.escalate_session(session_id, "ticket_created")

        # 5. Send emails (non-blocking — don't fail the ticket on email errors)
        try:
            from app.escalation.email_sender import (
                send_escalation_email_to_support,
                send_escalation_email_to_customer,
            )

            # Email to support team
            await send_escalation_email_to_support(
                customer_email=customer_email,
                customer_name=customer_name,
                session_id=session_id,
                ticket_id=ticket_id,
                topic=topic,
                escalation_reason=escalation_reason,
                summary=summary,
                transcript=transcript,
            )

            # Confirmation email to customer
            if customer_email:
                await send_escalation_email_to_customer(
                    customer_email=customer_email,
                    customer_name=customer_name,
                    session_id=session_id,
                    ticket_id=ticket_id,
                    topic=topic,
                    summary=summary,
                )
        except Exception as e:
            logger.error(f"Email notification failed (ticket still created): {e}")

        return {
            "ticket_id": ticket_id,
            "session_id": session_id,
            "topic": topic,
            "summary": summary,
        }

    def _get_adapter(self) -> BaseTicketAdapter:
        config = get_config()

        if config.escalation.n8n.enabled:
            from app.escalation.ticket.n8n_webhook import N8nWebhookAdapter
            return N8nWebhookAdapter()

        from app.escalation.ticket.zendesk_adapter import ZendeskAdapter
        return ZendeskAdapter()
