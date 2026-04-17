from __future__ import annotations

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.api.middleware.jwt_auth import validate_jwt
from app.chat.manager import ChatManager
from app.chat.models import IncomingMessage, MessageRole, OutgoingMessage
from app.config import get_config

logger = logging.getLogger(__name__)


class ConnectionHandler:
    """Handles WebSocket and SSE connections for chat."""

    def __init__(self):
        self.chat_manager = ChatManager()
        self.active_connections: dict[str, WebSocket] = {}

    async def handle_websocket(self, websocket: WebSocket) -> None:
        import time as _time
        _session_start = _time.monotonic()

        await websocket.accept()
        session_id: str | None = None
        user_claims: dict | None = None
        language: str = "de"

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await self._send_ws(
                        websocket,
                        OutgoingMessage(type="error", message="Invalid message format"),
                    )
                    continue

                msg = IncomingMessage(**data)

                if msg.type == "auth":
                    try:
                        user_claims = validate_jwt(msg.token or "")
                    except Exception as e:
                        await self._send_ws(
                            websocket,
                            OutgoingMessage(type="error", message=f"Authentication failed: {e}"),
                        )
                        await websocket.close()
                        return

                    language = msg.language or "de"
                    session = await self.chat_manager.create_session(
                        customer_name=user_claims["name"],
                        customer_email=user_claims["email"],
                        order_number=user_claims.get("order_number"),
                        sales_channel_id=user_claims.get("sales_channel_id"),
                        language=language,
                    )
                    session_id = session.id
                    self.active_connections[session_id] = websocket

                    topics = self._get_visible_topics(user_claims)
                    await self._send_ws(
                        websocket,
                        OutgoingMessage(type="auth_success", session_id=session_id, topics=topics),
                    )

                elif msg.type == "set_language" and session_id:
                    language = msg.language or "de"
                    await self.chat_manager.set_language(session_id, language)

                elif msg.type == "select_topic" and session_id:
                    topic_id = msg.topic_id or "others"
                    llm_provider = self._get_provider_for_topic(topic_id)
                    await self.chat_manager.set_topic(session_id, topic_id, llm_provider)

                    greeting = self._get_topic_greeting(topic_id, language)
                    greeting_msg = await self.chat_manager.add_message(
                        session_id, MessageRole.ASSISTANT, greeting
                    )
                    await self._send_ws(
                        websocket,
                        OutgoingMessage(type="message", content=greeting, message_id=greeting_msg.id),
                    )

                elif msg.type == "message" and session_id and user_claims:
                    if not msg.content:
                        continue

                    # Store user message
                    await self.chat_manager.add_message(
                        session_id, MessageRole.USER, msg.content
                    )

                    # Send typing indicator
                    await self._send_ws(websocket, OutgoingMessage(type="typing"))

                    # Process with AI engine (lazy import to avoid circular deps at startup)
                    from app.ai.engine import AIEngine

                    engine = AIEngine()
                    session = await self.chat_manager.get_session(session_id)
                    history = await self.chat_manager.get_session_messages(session_id)

                    # Stream response
                    await self._send_ws(websocket, OutgoingMessage(type="stream_start"))

                    full_response = ""
                    token_count = 0
                    escalated = False

                    from app.analytics.collector import track_response_time as _track_rt
                    _t0 = _time.monotonic()
                    async for chunk in engine.process_message(
                        message=msg.content,
                        session=session or {},
                        history=history,
                        user_claims=user_claims,
                        language=language,
                    ):
                        if chunk.get("type") == "token":
                            await self._send_ws(
                                websocket,
                                OutgoingMessage(type="stream_chunk", content=chunk["content"]),
                            )
                            full_response += chunk["content"]
                            token_count += 1
                        elif chunk.get("type") == "escalation":
                            await self._send_ws(websocket, OutgoingMessage(type="stream_end"))
                            await self._send_ws(
                                websocket,
                                OutgoingMessage(
                                    type="escalation", message=chunk["message"]
                                ),
                            )
                            await self.chat_manager.escalate_session(
                                session_id, chunk.get("reason", "ai_detected")
                            )
                            full_response = chunk["message"]
                            escalated = True
                            break

                    _elapsed_ms = int((_time.monotonic() - _t0) * 1000)
                    _llm_ms = int(_elapsed_ms * 0.8)
                    _provider = session.get("llm_provider", "unknown") if session else "unknown"
                    try:
                        await _track_rt(session_id, _elapsed_ms, _llm_ms, _provider)
                    except Exception:
                        pass  # never block chat on analytics

                    if not escalated and full_response:
                        # Store before stream_end so the message_id can be sent with it
                        ai_msg = await self.chat_manager.add_message(
                            session_id,
                            MessageRole.ASSISTANT,
                            full_response,
                            metadata={"tokens_used": token_count},
                        )
                        await self._send_ws(
                            websocket,
                            OutgoingMessage(type="stream_end", message_id=ai_msg.id),
                        )
                    elif not escalated:
                        await self._send_ws(websocket, OutgoingMessage(type="stream_end"))

                elif msg.type == "not_helpful" and session_id:
                    await self.chat_manager.escalate_session(session_id, "user_not_helpful")
                    not_helpful_msg = (
                        "Es tut mir leid, dass ich nicht weiterhelfen konnte. "
                        "Möchten Sie mit unserem Support-Team sprechen?"
                        if language == "de" else
                        "I'm sorry I couldn't help. "
                        "Would you like to contact our support team?"
                    )
                    await self._send_ws(
                        websocket,
                        OutgoingMessage(type="escalation", message=not_helpful_msg),
                    )

                elif msg.type == "create_ticket" and session_id:
                    try:
                        from app.escalation.actions import EscalationActions

                        actions = EscalationActions()
                        ticket_id = await actions.create_ticket(session_id)
                        await self._send_ws(
                            websocket,
                            OutgoingMessage(type="ticket_created", ticket_id=ticket_id),
                        )
                    except Exception as e:
                        logger.exception(f"Ticket creation error: {e}")
                        await self._send_ws(
                            websocket,
                            OutgoingMessage(
                                type="error", message="Failed to create ticket. Please try again."
                            ),
                        )

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: session={session_id}")
        except Exception as e:
            logger.exception(f"WebSocket error: {e}")
            try:
                await self._send_ws(
                    websocket,
                    OutgoingMessage(type="error", message="An internal error occurred."),
                )
            except Exception:
                pass
        finally:
            from app.analytics.collector import track_session_end as _track_end
            _duration = int(_time.monotonic() - _session_start)
            _msg_count = self.chat_manager._sessions.get(session_id, {}).get("message_count", 0) if session_id else 0
            try:
                await _track_end(session_id or "unknown", _duration, _msg_count)
            except Exception:
                pass

            if session_id:
                self.active_connections.pop(session_id, None)
                await self.chat_manager.close_session(session_id)

    async def _send_ws(self, websocket: WebSocket, msg: OutgoingMessage) -> None:
        try:
            await websocket.send_text(msg.model_dump_json(exclude_none=True))
        except Exception:
            pass  # Connection may be closed

    def _get_visible_topics(self, user_claims: dict) -> list[dict]:
        """Filter topic cards based on customer context from JWT claims."""
        config = get_config()
        has_orders = user_claims.get("has_orders", False)
        is_b2b = user_claims.get("is_b2b", False)
        visible = []

        for card in config.topic_cards:
            if not self._is_visible(card.visibility, has_orders, is_b2b):
                continue

            card_data: dict = {
                "id": card.id,
                "title": card.title,
                "icon": card.icon,
                "description": card.description,
            }

            if card.sub_cards:
                card_data["sub_cards"] = [
                    {
                        "id": sc.id,
                        "title": sc.title,
                        "icon": sc.icon,
                        "description": sc.description,
                    }
                    for sc in card.sub_cards
                    if self._is_visible(sc.visibility, has_orders, is_b2b)
                ]

            visible.append(card_data)

        return visible

    def _is_visible(self, visibility: str, has_orders: bool, is_b2b: bool = False) -> bool:
        if visibility == "always":
            return True
        if visibility == "has_orders":
            return has_orders
        if visibility == "is_b2b":
            return is_b2b
        return True

    def _get_provider_for_topic(self, topic_id: str) -> str:
        config = get_config()
        return config.topic_routing.get(
            topic_id, config.topic_routing.get("fallback", "openai")
        )

    def _get_topic_greeting(self, topic_id: str, language: str = "de") -> str:
        greetings: dict[str, dict[str, str]] = {
            "order_status":         {"de": "Ich helfe Ihnen gerne bei der Sendungsverfolgung. Um welche Bestellnummer geht es?",
                                     "en": "I'd be happy to help with order tracking. Which order number are you looking for?"},
            "returns":              {"de": "Ich unterstütze Sie bei Rücksendungen und Erstattungen. Welche Bestellung möchten Sie zurückschicken?",
                                     "en": "I can help with returns and refunds. Which order would you like to return?"},
            "order_issue":          {"de": "Es tut mir leid, dass es ein Problem mit Ihrer Bestellung gibt. Bitte schildern Sie das Problem.",
                                     "en": "I'm sorry to hear there's an issue with your order. Please describe the problem."},
            "product_help":         {"de": "Ich helfe Ihnen gerne bei Produktfragen. Was möchten Sie wissen?",
                                     "en": "I'd be happy to help with product questions. What would you like to know?"},
            "stock":                {"de": "Ich prüfe die Verfügbarkeit für Sie. Nach welchem Produkt suchen Sie?",
                                     "en": "I'll check availability for you. Which product are you looking for?"},
            "compatibility":        {"de": "Ich helfe Ihnen das passende Produkt für Ihr Fahrzeug zu finden. Welches Fahrzeug haben Sie?",
                                     "en": "I'll help you find the right product for your vehicle. What vehicle do you have?"},
            "compatibility_check":  {"de": "Ich prüfe die Kompatibilität für Sie. Bitte geben Sie Ihr Fahrzeug an.",
                                     "en": "I'll check compatibility for you. Please enter your vehicle details."},
            "delivery_time":        {"de": "Ich informiere Sie gerne über Lieferzeiten. Was möchten Sie wissen?",
                                     "en": "I can provide information about delivery times. What would you like to know?"},
            "shipping_costs":       {"de": "Ich beantworte Ihre Fragen zu Versandkosten. Womit kann ich helfen?",
                                     "en": "I can answer your shipping cost questions. How can I help?"},
            "express_delivery":     {"de": "Ich helfe Ihnen mit Expresslieferoptionen. Was benötigen Sie?",
                                     "en": "I can help with express delivery options. What do you need?"},
            "installation":         {"de": "Ich unterstütze Sie beim Einbau. Um welches Produkt geht es?",
                                     "en": "I can help with installation. Which product are you installing?"},
            "tech_specs":           {"de": "Ich stelle Ihnen gerne technische Daten bereit. Welches Produkt interessiert Sie?",
                                     "en": "I can provide technical specifications. Which product are you interested in?"},
            "payment":              {"de": "Ich beantworte Ihre Fragen zu Zahlungsarten. Womit kann ich helfen?",
                                     "en": "I can answer your payment questions. How can I help?"},
            "address":              {"de": "Ich helfe Ihnen bei der Verwaltung Ihrer Adressen. Was möchten Sie tun?",
                                     "en": "I can help you manage your addresses. What would you like to do?"},
            "invoice":              {"de": "Ich helfe Ihnen mit Rechnungen und Belegen. Was benötigen Sie?",
                                     "en": "I can help with invoices and receipts. What do you need?"},
            "b2b_quotes":           {"de": "Ich helfe Ihnen bei B2B-Angeboten. Was benötigen Sie?",
                                     "en": "I can help with B2B quotes. What do you need?"},
            "b2b_employees":        {"de": "Ich helfe Ihnen bei der Verwaltung von Mitarbeiterkonten. Was möchten Sie tun?",
                                     "en": "I can help manage employee accounts. What would you like to do?"},
            "faq":                  {"de": "Ich beantworte gerne Ihre häufigen Fragen. Womit kann ich helfen?",
                                     "en": "I'd be happy to answer frequently asked questions. How can I help?"},
            "complaint":            {"de": "Es tut mir leid, dass Sie ein Anliegen haben. Bitte schildern Sie Ihre Situation.",
                                     "en": "I'm sorry to hear you have a concern. Please describe your situation."},
            "others":               {"de": "Wie kann ich Ihnen heute helfen?",
                                     "en": "How can I help you today?"},
        }
        lang = language if language in ("de", "en") else "de"
        fallback = {"de": "Wie kann ich Ihnen heute helfen?", "en": "How can I help you today?"}
        topic = greetings.get(topic_id, fallback)
        return topic.get(lang, topic.get("de", fallback["de"]))


# Singleton
_connection_handler: ConnectionHandler | None = None


def get_connection_handler() -> ConnectionHandler:
    global _connection_handler
    if _connection_handler is None:
        _connection_handler = ConnectionHandler()
    return _connection_handler
