from __future__ import annotations

import json
import logging
import time as _time

from fastapi import WebSocket, WebSocketDisconnect

from app.api.middleware.jwt_auth import validate_jwt
from app.api.middleware.rate_limiter import AbuseError, get_rate_limiter
from app.chat.manager import ChatManager
from app.chat.models import IncomingMessage, MessageRole, OutgoingMessage
from app.analytics.collector import track_response_time as _track_rt
from app.analytics.collector import track_session_end as _track_end
from app.analytics.collector import track_token_usage as _track_tokens
from app.config import get_config
from app.ai.router import get_live_llm_provider
from app.db.collections import messages_collection

logger = logging.getLogger(__name__)


class ConnectionHandler:
    """Handles WebSocket and SSE connections for chat."""

    def __init__(self):
        self.chat_manager = ChatManager()
        self.active_connections: dict[str, WebSocket] = {}

    # Idle timeout settings
    IDLE_WARNING_SECONDS = 300   # 5 minutes — send warning
    IDLE_CLOSE_SECONDS = 420     # 7 minutes — close session

    async def handle_websocket(self, websocket: WebSocket) -> None:
        _session_start = _time.monotonic()

        await websocket.accept()
        session_id: str | None = None
        user_claims: dict | None = None
        _last_activity = _time.monotonic()
        _idle_warned = False
        _close_reason = "completed"

        try:
            while True:
                # Check idle timeout
                import asyncio as _timeout_aio
                try:
                    idle_check = self.IDLE_WARNING_SECONDS if not _idle_warned else (self.IDLE_CLOSE_SECONDS - self.IDLE_WARNING_SECONDS)
                    raw = await _timeout_aio.wait_for(websocket.receive_text(), timeout=idle_check)
                    _last_activity = _time.monotonic()
                    _idle_warned = False
                except _timeout_aio.TimeoutError:
                    if not _idle_warned:
                        # First timeout — send warning
                        _idle_warned = True
                        await self._send_ws(websocket, OutgoingMessage(
                            type="message",
                            content="Bist du noch da? Die Sitzung wird in 2 Minuten geschlossen, wenn keine Aktivit\u00e4t erfolgt.",
                        ))
                        continue
                    else:
                        # Second timeout — close session
                        await self._send_ws(websocket, OutgoingMessage(
                            type="message",
                            content="Die Sitzung wurde wegen Inaktivit\u00e4t geschlossen. Starte einen neuen Chat, wenn du weitere Hilfe brauchst!",
                        ))
                        # Tell widget to lock/close the chat UI
                        await self._send_ws(websocket, OutgoingMessage(
                            type="session_closed",
                            message="idle_timeout",
                        ))
                        if session_id:
                            await self.chat_manager.close_session(session_id, close_reason="idle_timeout")
                            await self.chat_manager.add_session_event(session_id, "session_closed", "idle timeout")
                        await websocket.close()
                        return
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

                    session = await self.chat_manager.create_session(
                        customer_name=user_claims.get("name", "Guest"),
                        customer_email=user_claims.get("email") or "",
                        order_number=user_claims.get("order_number"),
                        sales_channel_id=user_claims.get("sales_channel_id"),
                        topic_id="general",
                    )
                    session_id = session.id
                    self.active_connections[session_id] = websocket

                    # Auto-set general topic so messages work without select_topic
                    llm_provider = await self._get_provider_for_topic("general")
                    await self.chat_manager.set_topic(session_id, "general", llm_provider)

                    # Smart suggestions — only topics that map to cards/actions
                    suggestions = [
                        "Wo ist mein Paket?",
                        "Produktfrage",
                        "Retoure / Erstattung",
                        "Versandkosten",
                        "Rechnung anfordern",
                        "Ticket-Status pr\u00fcfen",
                    ]

                    await self._send_ws(
                        websocket,
                        OutgoingMessage(type="auth_success", session_id=session_id, suggestions=suggestions),
                    )

                elif msg.type == "select_topic" and session_id:
                    topic_id = msg.topic_id or "others"
                    llm_provider = await self._get_provider_for_topic(topic_id)
                    await self.chat_manager.set_topic(session_id, topic_id, llm_provider)

                    from app.ai.agents import get_agent_greeting, get_verification_tier
                    tier = get_verification_tier(topic_id)

                    if tier == 2:
                        # Tier 2: Show order lookup card directly
                        from app.ai.card_builder import build_order_lookup_card
                        await self._send_ws(websocket, OutgoingMessage(
                            type="info_card", info_card=build_order_lookup_card(),
                        ))
                    else:
                        # Tier 0/1: Generate AI greeting
                        greeting = await get_agent_greeting(topic_id, llm_provider, user_claims.get("name", ""))
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

                    # Intercept only the exact choice button responses for order verification
                    content_lower = (msg.content or "").strip().lower()
                    session_data = await self.chat_manager.get_session(session_id)
                    topic_id = session_data.get("topic_id", "") if session_data else ""

                    from app.ai.agents import get_verification_tier
                    tier = get_verification_tier(topic_id)

                    has_verified_order = bool((session_data or {}).get("order_number"))

                    # Handle "Check ticket status" button
                    if content_lower == "check ticket status":
                        from app.ai.card_builder import build_ticket_lookup_card
                        await self.chat_manager.add_message(session_id, MessageRole.USER, msg.content)
                        await self.chat_manager.add_session_event(session_id, "button_clicked", "Check ticket status")
                        await self._send_ws(websocket, OutgoingMessage(
                            type="info_card", info_card=build_ticket_lookup_card(),
                        ))
                        continue

                    # Handle "Mark as Urgent" button from ticket status card
                    if content_lower == "\U0001F6A8 mark as urgent":
                        await self.chat_manager.add_message(session_id, MessageRole.USER, msg.content)
                        # Check if already escalated in this session
                        session_events = (session_data or {}).get("events", [])
                        already_urgent = any(ev.get("type") == "ticket_urgent" for ev in session_events)
                        if already_urgent:
                            already_msg = "You've already escalated a ticket in this session."
                            ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, already_msg)
                            await self._send_ws(websocket, OutgoingMessage(type="message", content=already_msg, message_id=ai_msg.id))
                            continue

                        # Get the ticket ID from the last ticket_status event
                        last_ticket_id = ""
                        for ev in reversed(session_events):
                            if ev.get("type") == "ticket_status_shown":
                                # Extract ticket ID from detail like "Ticket #16985 — Open"
                                detail = ev.get("detail", "")
                                if "#" in detail:
                                    last_ticket_id = detail.split("#")[1].split(" ")[0].split("\u2014")[0].strip()
                                break

                        confirmation = {
                            "action": "mark_urgent",
                            "title": "Confirm Urgent Escalation",
                            "summary": f"This will change ticket #{last_ticket_id} priority to URGENT and notify our team for faster response.",
                            "fields": [
                                {"key": "ticket_id", "label": "Ticket", "value": f"#{last_ticket_id}", "editable": False, "type": "text"},
                                {"key": "urgency_reason", "label": "Reason for urgency (optional)", "value": "", "editable": True, "type": "textarea"},
                            ],
                        }
                        await self._send_ws(websocket, OutgoingMessage(type="confirmation_request", confirmation=confirmation))
                        continue

                    # Handle "Try again" from order verification failed card
                    if content_lower == "try again":
                        from app.ai.card_builder import build_order_lookup_card
                        await self.chat_manager.add_message(session_id, MessageRole.USER, msg.content)
                        await self.chat_manager.add_session_event(session_id, "button_clicked", "Try again — re-showing order lookup")
                        await self._send_ws(websocket, OutgoingMessage(
                            type="info_card", info_card=build_order_lookup_card(),
                        ))
                        continue

                    # Handle "Ich habe die Formulare ausgefüllt" chip from Batteriepfand download card
                    if content_lower in ("ich habe die formulare ausgefüllt", "ich habe die formulare ausgef\u00fcllt"):
                        from app.ai.card_builder import build_batteriepfand_upload_card
                        await self.chat_manager.add_message(session_id, MessageRole.USER, msg.content)
                        upload_card = build_batteriepfand_upload_card()
                        for field in upload_card.get("fields", []):
                            if field["key"] == "customer_name":
                                field["value"] = user_claims.get("name", "")
                            elif field["key"] == "customer_email":
                                field["value"] = user_claims.get("email", "")
                        intro = "Super! W\u00e4hle das Formular aus und lade die ausgef\u00fcllte PDF hoch:"
                        import asyncio as _aio
                        await self._send_ws(websocket, OutgoingMessage(type="typing"))
                        await _aio.sleep(0.8)
                        ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, intro)
                        await self._send_ws(websocket, OutgoingMessage(
                            type="ai_card", content=intro, message_id=ai_msg.id,
                            info_card=upload_card,
                        ))
                        await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))
                        continue

                    # Handle "Contact Support" from error card meta_actions
                    if content_lower == "contact support":
                        await self.chat_manager.add_message(session_id, MessageRole.USER, msg.content)
                        await self.chat_manager.add_session_event(session_id, "button_clicked", "Contact Support — showing ticket form")
                        intro = "Kein Problem! Bitte f\u00fclle das Formular aus und unser Team meldet sich bei dir:"
                        confirmation = {
                            "action": "create_ticket",
                            "title": "Contact Support",
                            "summary": "Unser Team k\u00fcmmert sich um dein Anliegen.",
                            "fields": [
                                {"key": "customer_name", "label": "Name", "value": user_claims.get("name", ""), "editable": True, "type": "text"},
                                {"key": "customer_email", "label": "Order Email", "value": user_claims.get("email", ""), "editable": True, "type": "text"},
                                {"key": "topic", "label": "Betreff", "value": topic_id or "General", "editable": True, "type": "text", "prefix": "Groot Escalation \u2014 "},
                                {"key": "issue_description", "label": "How can we help?", "value": "", "editable": True, "type": "textarea"},
                            ],
                        }
                        import asyncio as _aio
                        await self._send_ws(websocket, OutgoingMessage(type="typing"))
                        await _aio.sleep(0.8)
                        ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, intro)
                        await self._send_ws(websocket, OutgoingMessage(
                            type="ai_card", content=intro, message_id=ai_msg.id,
                            confirmation=confirmation,
                        ))
                        await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))
                        continue

                    # Handle order sub-topic chip clicks from suggestions
                    order_chip_map = {
                        "🚚 track shipment": "order_status",
                        "↩️ return / refund": "returns",
                        "⚠️ order problem": "order_issue",
                    }
                    if content_lower in order_chip_map:
                        new_topic = order_chip_map[content_lower]
                        llm_provider = await self._get_provider_for_topic(new_topic)
                        await self.chat_manager.set_topic(session_id, new_topic, llm_provider)
                        tier = 2
                        topic_id = new_topic
                        session_data = await self.chat_manager.get_session(session_id)
                        has_verified_order = False

                    # ── Unified classifier — one LLM call for card action + intent ──
                    verified_order = (session_data or {}).get("order_number")
                    cached_order = (session_data or {}).get("cached_order_data", {})

                    from app.ai.unified_classifier import classify_message
                    from app.ai.router import get_default_provider
                    session_provider = (session_data or {}).get("llm_provider") or get_default_provider()

                    # Get recent history for follow-up awareness
                    _recent_history = await self.chat_manager.get_session_messages(session_id)

                    classification = await classify_message(
                        message=msg.content,
                        has_verified_order=bool(verified_order),
                        order_number=verified_order or "",
                        topic=topic_id,
                        has_cached_data=bool(cached_order),
                        history=_recent_history,
                        llm_provider=session_provider,
                    )
                    card_action = classification["action"]
                    logger.info(f"Unified classifier: msg={msg.content[:50]!r} → action={card_action} intent={classification['intent']} complexity={classification.get('complexity','?')}")

                    # ── Smart model routing: Haiku for simple, Sonnet for complex ──
                    _use_complex_model = classification.get("complexity") == "complex"

                    # Layer 1: Heuristic overrides (free, instant)
                    if not _use_complex_model:
                        _msg_len = len(msg.content or "")
                        _session_events = (session_data or {}).get("events", [])
                        _topic_switches = sum(1 for e in _session_events if e.get("type") == "topic_auto_switched")
                        _had_thumbs_down = any(e.get("type") == "feedback_down" for e in _session_events)

                        if _msg_len > 150:
                            _use_complex_model = True
                        elif _topic_switches >= 3:
                            _use_complex_model = True
                        elif _had_thumbs_down:
                            _use_complex_model = True
                        elif classification.get("intent") == "escalation" and classification.get("complexity") == "complex":
                            _use_complex_model = True

                    if _use_complex_model:
                        session_provider = "anthropic-sonnet"
                        logger.info(f"Smart routing: upgraded to Sonnet (complexity={classification.get('complexity')}, msg_len={len(msg.content or '')})")

                        # For complex/frustrated messages, let the AI respond empathetically
                        # instead of showing a cold card form. The AI can offer to create a ticket.
                        if card_action in ("problem_ticket", "return_ticket", "escalation_ticket"):
                            logger.info(f"Smart routing: overriding card_action={card_action} → none (letting Sonnet respond)")
                            card_action = "none"

                    # Pre-purchase + escalation: show ticket form if customer explicitly asks
                    # Only let AI respond conversationally for vague/indirect escalation hints
                    if card_action == "escalation_ticket" and not has_verified_order:
                        _explicit_words = [
                            "support", "kontakt", "ticket", "erstell", "create",
                            "hilfe", "agent", "mitarbeiter", "mensch", "human",
                            "ja", "yes", "bitte", "please",
                        ]
                        _is_explicit = any(w in content_lower for w in _explicit_words)
                        if not _is_explicit:
                            logger.info("Pre-purchase escalation: letting AI respond with contact options")
                            card_action = "none"

                    # Invoice request — escalate to support for invoice generation
                    if content_lower.strip() in ("yes, request invoice", "ja, rechnung anfordern"):
                        await self.chat_manager.add_message(session_id, MessageRole.USER, msg.content)
                        intro = f"Ich erstelle ein Support-Ticket f\u00fcr die Rechnungsanforderung zu Bestellung **#{verified_order}**. Unser Team wird die Rechnung erstellen und dir zusenden."
                        confirmation = {
                            "action": "create_ticket",
                            "title": "Rechnung anfordern",
                            "summary": f"Rechnungsanforderung f\u00fcr Bestellung #{verified_order}.",
                            "fields": [
                                {"key": "customer_name", "label": "Name", "value": user_claims.get("name", ""), "editable": True, "type": "text"},
                                {"key": "customer_email", "label": "E-Mail", "value": user_claims.get("email") or "", "editable": True, "type": "text"},
                                {"key": "topic", "label": "Betreff", "value": f"Rechnung \u2014 Order #{verified_order}", "editable": True, "type": "text", "prefix": "Groot Escalation \u2014 "},
                                {"key": "issue_description", "label": "Anmerkung", "value": f"Bitte Rechnung f\u00fcr Bestellung #{verified_order} erstellen.", "editable": True, "type": "textarea"},
                            ],
                        }
                        import asyncio as _aio
                        await self._send_ws(websocket, OutgoingMessage(type="typing"))
                        await _aio.sleep(0.8)
                        ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, intro)
                        await self._send_ws(websocket, OutgoingMessage(
                            type="ai_card", content=intro, message_id=ai_msg.id,
                            confirmation=confirmation,
                        ))
                        await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))
                        continue

                    if card_action != "none":
                        await self.chat_manager.add_message(session_id, MessageRole.USER, msg.content)
                        await self.chat_manager.add_session_event(
                            session_id, "card_action",
                            f"{card_action} (order={'#' + verified_order if verified_order else 'none'})",
                        )

                        from app.ai.card_builder import (
                            build_tracking_card, build_payment_card, build_invoice_card,
                            build_order_lookup_card, build_no_order_card, build_warranty_card,
                            build_order_failed_card,
                        )

                        if card_action == "tracking" and verified_order:
                            await self._send_ai_card(websocket, session_id,
                                f"Hier ist der Lieferstatus f\u00fcr Bestellung **#{verified_order}**:",
                                build_tracking_card(cached_order, verified_order))
                            continue

                        elif card_action == "payment" and verified_order:
                            await self._send_ai_card(websocket, session_id,
                                f"Hier ist der Zahlungsstatus f\u00fcr Bestellung **#{verified_order}**:",
                                build_payment_card(cached_order, verified_order))
                            continue

                        elif card_action == "invoice" and verified_order:
                            try:
                                from app.shopware.client import ShopwareClient
                                client = ShopwareClient()
                                docs = await client.get_order_documents(verified_order)
                                if docs:
                                    await self._send_ai_card(websocket, session_id,
                                        f"Hier sind die Dokumente f\u00fcr Bestellung **#{verified_order}**:",
                                        build_invoice_card(verified_order, docs))
                                else:
                                    no_doc_msg = f"F\u00fcr Bestellung **#{verified_order}** sind noch keine Dokumente verf\u00fcgbar. Soll ich eine Rechnung f\u00fcr dich anfordern?"
                                    ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, no_doc_msg)
                                    await self._send_ws(websocket, OutgoingMessage(type="message", content=no_doc_msg, message_id=ai_msg.id))
                                    await self._send_ws(websocket, OutgoingMessage(type="choices", choices=["Ja, Rechnung anfordern", "Nein, danke"]))
                            except Exception as e:
                                logger.error(f"Invoice fetch failed: {e}")
                            continue

                        elif card_action == "warranty" and verified_order:
                            await self._send_ai_card(websocket, session_id,
                                f"Hier sind die Garantieinformationen f\u00fcr Bestellung **#{verified_order}**:",
                                build_warranty_card(cached_order, verified_order))
                            continue

                        elif card_action in ("return_ticket", "problem_ticket") and verified_order:
                            ticket_map = {
                                "return_ticket": ("Return Request", f"Groot Escalation — Return — Order #{verified_order}", "Reason for return",
                                                  f"Ich helfe dir gerne bei der Retoure f\u00fcr Bestellung **#{verified_order}**. Bitte f\u00fclle das Formular aus:"),
                                "problem_ticket": ("Report a Problem", f"Groot Escalation — Problem — Order #{verified_order}", "Describe the problem",
                                                   f"Es tut mir leid, dass es ein Problem gibt. Bitte beschreibe das Problem f\u00fcr Bestellung **#{verified_order}**:"),
                            }
                            title, subject, field_label, intro = ticket_map[card_action]
                            confirmation = {
                                "action": "create_ticket",
                                "title": title,
                                "summary": f"{title} for order #{verified_order}. Our team will follow up.",
                                "fields": [
                                    {"key": "customer_name", "label": "Name", "value": user_claims.get("name", ""), "editable": True, "type": "text"},
                                    {"key": "customer_email", "label": "Order Email", "value": user_claims.get("email", ""), "editable": True, "type": "text"},
                                    {"key": "topic", "label": "Betreff", "value": f"{title} \u2014 Order #{verified_order}", "editable": True, "type": "text", "prefix": "Groot Escalation \u2014 "},
                                    {"key": "issue_description", "label": field_label, "value": "", "editable": True, "type": "textarea"},
                                ],
                            }
                            import asyncio as _aio
                            await self._send_ws(websocket, OutgoingMessage(type="typing"))
                            await _aio.sleep(0.8)
                            ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, intro)
                            await self._send_ws(websocket, OutgoingMessage(
                                type="ai_card", content=intro, message_id=ai_msg.id,
                                confirmation=confirmation,
                            ))
                            await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))
                            continue

                        elif card_action == "escalation_ticket":
                            order_ref = f" \u2014 Order #{verified_order}" if verified_order else ""
                            intro = "Kein Problem! Ich erstelle ein Support-Ticket f\u00fcr dich. Bitte f\u00fclle kurz das Formular aus:"
                            confirmation = {
                                "action": "create_ticket",
                                "title": "Support kontaktieren",
                                "summary": "Unser Team k\u00fcmmert sich um dein Anliegen.",
                                "fields": [
                                    {"key": "customer_name", "label": "Name", "value": user_claims.get("name", ""), "editable": True, "type": "text"},
                                    {"key": "customer_email", "label": "Order Email", "value": user_claims.get("email", ""), "editable": True, "type": "text"},
                                    {"key": "topic", "label": "Betreff", "value": f"Support{order_ref}", "editable": True, "type": "text", "prefix": "Groot Escalation \u2014 "},
                                    {"key": "issue_description", "label": "Wie k\u00f6nnen wir helfen?", "value": "", "editable": True, "type": "textarea"},
                                ],
                            }
                            import asyncio as _aio
                            await self._send_ws(websocket, OutgoingMessage(type="typing"))
                            await _aio.sleep(0.8)
                            ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, intro)
                            await self._send_ws(websocket, OutgoingMessage(
                                type="ai_card", content=intro, message_id=ai_msg.id,
                                confirmation=confirmation,
                            ))
                            await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))
                            continue

                        elif card_action == "another_order":
                            await self.chat_manager.update_session_order(session_id, "")
                            await self._send_ai_card(websocket, session_id,
                                "Kein Problem! Gib die Daten der anderen Bestellung ein:",
                                build_order_lookup_card())
                            continue

                        elif card_action == "order_lookup":
                            if tier != 2:
                                llm_provider = await self._get_provider_for_topic("order_status")
                                await self.chat_manager.set_topic(session_id, "order_status", llm_provider)
                            await self._send_ai_card(websocket, session_id,
                                "Um dir zu helfen, brauche ich deine Bestelldaten. Bitte gib sie hier ein:",
                                build_order_lookup_card())
                            continue

                        elif card_action == "no_order":
                            llm_provider = await self._get_provider_for_topic("general")
                            await self.chat_manager.set_topic(session_id, "general", llm_provider)
                            await self._send_ai_card(websocket, session_id,
                                "Kein Problem! Ich kann dir auch ohne Bestellung weiterhelfen:",
                                build_no_order_card())
                            continue

                        elif card_action == "compatibility_check":
                            from app.ai.card_builder import build_compatibility_card
                            from app.shopware.client import ShopwareClient
                            client = ShopwareClient()
                            level1 = await client.compatibility_get_children()
                            await self._send_ai_card(websocket, session_id,
                                "Lass uns die passende Batterie f\u00fcr dein Fahrzeug finden! W\u00e4hle dein Fahrzeug aus:",
                                build_compatibility_card(level1))
                            await self.chat_manager.add_session_event(
                                session_id, "card_action", "compatibility_check — vehicle finder shown",
                            )
                            continue

                        elif card_action == "batteriepfand":
                            # Check if customer wants to upload (follow-up) or needs download first
                            _bp_upload_words = ["ausgef\u00fcllt", "hochladen", "upload", "fertig", "submit", "formulare fertig"]
                            _wants_upload = any(w in content_lower for w in _bp_upload_words)

                            if _wants_upload:
                                # Show upload form inside AI bubble
                                from app.ai.card_builder import build_batteriepfand_upload_card
                                upload_card = build_batteriepfand_upload_card()
                                # Pre-fill name/email
                                for field in upload_card.get("fields", []):
                                    if field["key"] == "customer_name":
                                        field["value"] = user_claims.get("name", "")
                                    elif field["key"] == "customer_email":
                                        field["value"] = user_claims.get("email", "")
                                intro = "Super! W\u00e4hle das Formular aus, das du einreichen m\u00f6chtest, und lade die ausgef\u00fcllte PDF hoch:"
                                import asyncio as _aio
                                await self._send_ws(websocket, OutgoingMessage(type="typing"))
                                await _aio.sleep(0.8)
                                ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, intro)
                                await self._send_ws(websocket, OutgoingMessage(
                                    type="ai_card", content=intro, message_id=ai_msg.id,
                                    info_card=upload_card,
                                ))
                                await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))
                            else:
                                # Show download card with both PDFs
                                from app.ai.card_builder import build_batteriepfand_download_card
                                intro = (
                                    "F\u00fcr den Batteriepfand ben\u00f6tigst du zwei ausgef\u00fcllte Formulare. "
                                    "Bitte lade sie herunter, f\u00fclle sie aus und komm dann zur\u00fcck \u2014 "
                                    "ich helfe dir beim Hochladen und Einreichen!"
                                )
                                _server_url = get_config().server.public_url
                                await self._send_ai_card(websocket, session_id, intro,
                                    build_batteriepfand_download_card(server_b_url=_server_url))
                            await self.chat_manager.add_session_event(
                                session_id, "batteriepfand",
                                "upload form shown" if _wants_upload else "download forms shown",
                            )
                            continue

                        elif card_action == "ticket_lookup":
                            from app.ai.card_builder import build_ticket_lookup_card
                            await self._send_ai_card(websocket, session_id,
                                "Gerne pr\u00fcfe ich den Status deines Tickets. Bitte gib deine Daten ein:",
                                build_ticket_lookup_card())
                            continue

                        elif card_action == "account_info":
                            account_msg = (
                                "F\u00fcr Kontoinformationen wie Adresse, Passwort oder Bestell\u00fcbersicht "
                                "kannst du dich direkt in deinem Kundenkonto einloggen:\n\n"
                                "\U0001F449 [**Zum Kundenkonto**](https://voltimax.de/account)\n\n"
                                "Dort kannst du:\n"
                                "- Deine Adresse und pers\u00f6nlichen Daten \u00e4ndern\n"
                                "- Dein Passwort zur\u00fccksetzen\n"
                                "- Deine Bestellungen einsehen\n"
                                "- Zahlungsmethoden verwalten\n\n"
                                "Falls du dein Passwort vergessen hast: "
                                "[**Passwort zur\u00fccksetzen**](https://voltimax.de/account/recover/password)"
                            )
                            import asyncio as _aio
                            await self._send_ws(websocket, OutgoingMessage(type="typing"))
                            await _aio.sleep(0.8)
                            ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, account_msg)
                            await self._send_ws(websocket, OutgoingMessage(
                                type="message", content=account_msg, message_id=ai_msg.id,
                            ))
                            await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))
                            await self.chat_manager.add_session_event(
                                session_id, "account_info_shown", "Directed to account login page",
                            )
                            continue

                    # card_action == "clarify" → let AI ask a follow-up question
                    if card_action == "clarify":
                        classification["intent"] = "direct"
                        classification["needs_shopware_data"] = False
                        classification["card_context"] = "ASK_CLARIFICATION"

                    # card_action == "none" or "clarify" \u2192 fall through to AI pipeline

                    rl = get_rate_limiter()

                    # Content validation (prompt injection, length)
                    try:
                        msg.content = rl.check_message_content(msg.content or "")
                    except AbuseError as e:
                        await self._send_ws(websocket, OutgoingMessage(type="error", message=str(e)))
                        continue

                    # Rapid-fire check
                    if not rl.check_rapid_fire(session_id):
                        await self._send_ws(
                            websocket,
                            OutgoingMessage(type="error", message="Slow down — too many messages in a short time."),
                        )
                        continue

                    # Store user message
                    await self.chat_manager.add_message(
                        session_id, MessageRole.USER, msg.content
                    )
                    await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="outgoing"))

                    # Send typing indicator
                    await self._send_ws(websocket, OutgoingMessage(type="typing"))

                    # ── Pre-fetch product data when classifier says products are needed ──
                    # This lets the AI know a card is coming so it writes a short intro
                    # instead of listing products in text. No discard+resend needed.
                    _pre_fetched_products = []
                    _pre_fetched_doc_card = None
                    _pre_fetched_shopware = None
                    _classified_intent = classification.get("intent", "")

                    logger.info(f"Pre-fetch check: intent={_classified_intent!r} needs_data={classification.get('needs_shopware_data')}")
                    if _classified_intent in ("product_query", "product_doc_query") and classification.get("needs_shopware_data"):
                        try:
                            from app.ai.graph.nodes.data_fetcher import search_products
                            _search_q = classification.get("search_query", "") or msg.content
                            logger.info(f"Pre-fetching products for: {_search_q!r}")
                            _pre_fetched_products, _total_product_count = await search_products(_search_q)
                            logger.info(f"Pre-fetch result: {len(_pre_fetched_products)} products (total in shop: {_total_product_count})")
                            if _pre_fetched_products:
                                _pre_fetched_shopware = {"search_results": _pre_fetched_products}

                                # Check cheaper alternatives for each displayed product
                                if _classified_intent == "product_query":
                                    try:
                                        from app.shopware.client import ShopwareClient
                                        _alt_client = ShopwareClient()
                                        _alternatives = {}
                                        for _p in _pre_fetched_products[:6]:
                                            _pid = _p.get("id")
                                            if _pid:
                                                _alt = await _alt_client.get_cheaper_alternative(_pid)
                                                if _alt:
                                                    _alternatives[_pid] = _alt
                                                    logger.info(f"Cheaper alt for {_p.get('name','?')[:30]}: {_alt.get('name','?')[:30]} ({_alt.get('savings',0)}% off)")
                                        if _alternatives:
                                            _pre_fetched_shopware["cheaper_alternatives"] = _alternatives
                                    except Exception as e:
                                        logger.warning(f"Cheaper alternative check failed: {e}")

                                # For document requests, also pre-fetch the actual documents
                                if _classified_intent == "product_doc_query":
                                    try:
                                        from app.shopware.client import ShopwareClient
                                        from app.ai.card_builder import build_document_card
                                        doc_client = ShopwareClient()
                                        msg_lower = msg.content.lower()
                                        msg_words = [w for w in msg_lower.split() if len(w) >= 2 and w not in (
                                            "pdf", "datenblatt", "datasheet", "download", "dokument", "für", "for", "von",
                                        )]
                                        best_product, best_score = None, -1
                                        for p in _pre_fetched_products:
                                            name_lower = (p.get("name") or "").lower()
                                            score = sum(1 for w in msg_words if w in name_lower)
                                            if score > best_score:
                                                best_score = score
                                                best_product = p
                                        if best_product and best_product.get("id"):
                                            pdocs = await doc_client.get_product_documents(best_product["id"])
                                            if pdocs:
                                                _pre_fetched_doc_card = build_document_card(
                                                    pdocs, "Produktdokumente", server_b_url=get_config().server.public_url,
                                                )
                                    except Exception:
                                        pass
                        except Exception as e:
                            logger.warning(f"Product pre-fetch failed: {e}")

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
                    _run_id = None
                    _product_results = []
                    _intent = ""

                    _t0 = _time.monotonic()
                    async for chunk in engine.process_message(
                        message=msg.content,
                        session=session or {},
                        history=history,
                        user_claims=user_claims,
                        classification=classification,
                        pre_fetched_shopware=_pre_fetched_shopware,
                    ):
                        if chunk.get("type") == "intent":
                            _intent = chunk.get("intent", "")
                        elif chunk.get("type") == "topic_switch":
                            # Auto-switch topic based on intent + accumulate tags
                            new_topic = chunk["topic_id"]
                            current_topic = (session or {}).get("topic_id", "general")
                            if new_topic != current_topic:
                                llm_provider = await self._get_provider_for_topic(new_topic)
                                await self.chat_manager.set_topic(session_id, new_topic, llm_provider)
                                await self.chat_manager.add_session_event(
                                    session_id, "topic_auto_switched",
                                    f"{current_topic} → {new_topic} (intent={chunk.get('intent', '')})",
                                )
                        elif chunk.get("type") == "token":
                            await self._send_ws(
                                websocket,
                                OutgoingMessage(type="stream_chunk", content=chunk["content"]),
                            )
                            full_response += chunk["content"]
                            token_count += 1
                        elif chunk.get("type") == "run_id":
                            _run_id = chunk.get("run_id")
                        elif chunk.get("type") == "product_results":
                            _product_results = chunk.get("products", [])
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

                            # Send confirmation instead of auto-creating
                            try:
                                session_data = await self.chat_manager.get_session(session_id)
                                confirmation = {
                                    "action": "create_ticket",
                                    "title": "Create Support Ticket",
                                    "summary": "Groot detected this needs human attention. Would you like to create a support ticket?",
                                    "fields": [
                                        {"key": "customer_name", "label": "Name", "value": user_claims.get("name", ""), "editable": True, "type": "text"},
                                        {"key": "customer_email", "label": "Order Email", "value": user_claims.get("email", ""), "editable": True, "type": "text"},
                                        {"key": "topic", "label": "Betreff", "value": session_data.get("topic_id", "General") if session_data else "General", "editable": True, "type": "text", "prefix": "Groot Escalation \u2014 "},
                                        {"key": "issue_description", "label": "Describe your issue", "value": "", "editable": True, "type": "textarea"},
                                    ],
                                }
                                await self._send_ws(
                                    websocket,
                                    OutgoingMessage(type="confirmation_request", confirmation=confirmation),
                                )
                            except Exception as e:
                                logger.error(f"Confirmation request failed: {e}")

                            full_response = chunk["message"]
                            escalated = True
                            break

                    _elapsed_ms = int((_time.monotonic() - _t0) * 1000)
                    # llm_latency_ms is estimated at 80% of total until providers expose actual LLM timing
                    _llm_ms = int(_elapsed_ms * 0.8)
                    _provider = session.get("llm_provider", "unknown") if session else "unknown"
                    try:
                        await _track_rt(session_id, _elapsed_ms, _llm_ms, _provider)
                    except Exception:
                        pass  # never block chat on analytics

                    if token_count > 0:
                        try:
                            await _track_tokens(session_id, _provider, token_count, token_count)
                        except Exception:
                            pass

                    if not escalated and full_response:
                        import asyncio as _aio

                        # ── Product/doc card: combine text + card in one ai_card bubble ──
                        if _pre_fetched_products:
                            # Discard buffered stream (widget only showed typing indicator)
                            await self._send_ws(websocket, OutgoingMessage(type="stream_end"))

                            card_to_send = None
                            if _pre_fetched_doc_card:
                                card_to_send = _pre_fetched_doc_card
                            else:
                                from app.ai.card_builder import build_product_card
                                from urllib.parse import quote_plus
                                import hashlib as _hl
                                _search_term = classification.get("search_query", "") or msg.content
                                _track_hash = _hl.sha256(f"{session_id}:{_time.monotonic()}".encode()).hexdigest()[:8]
                                _listing_url = f"https://voltimax.de/search?search={quote_plus(_search_term)}&groot_ref=search&groot_session={_track_hash}"
                                _cheaper_alts = (_pre_fetched_shopware or {}).get("cheaper_alternatives", {})
                                card_to_send = build_product_card(
                                    _pre_fetched_products, session_id,
                                    listing_url=_listing_url,
                                    total_in_shop=_total_product_count,
                                    cheaper_alternatives=_cheaper_alts,
                                )

                            # Send as ai_card: text + card in one bubble
                            await self._send_ai_card(websocket, session_id, full_response, card_to_send)
                            if card_to_send:
                                # Log products shown
                                _product_names = [p.get("name", "")[:40] for p in _pre_fetched_products[:6]]
                                await self.chat_manager.add_session_event(
                                    session_id, "product_card_shown",
                                    f"{len(_pre_fetched_products)} products: {', '.join(_product_names[:3])}",
                                )
                                # Log cheaper alternatives so AI remembers on follow-up
                                if _cheaper_alts:
                                    for _pid, _alt in _cheaper_alts.items():
                                        _orig_name = next((p.get("name", "")[:30] for p in _pre_fetched_products if p.get("id") == _pid), "?")
                                        _matched = ", ".join(_alt.get("matchedProperties", []))
                                        await self.chat_manager.add_session_event(
                                            session_id, "cheaper_alternative_shown",
                                            f"{_orig_name} → {_alt.get('name', '?')[:30]} "
                                            f"({_alt.get('savings', 0):.0f}% günstiger, matched: {_matched or 'key properties'})",
                                        )
                        else:
                            # Normal text response — no card
                            ai_msg = await self.chat_manager.add_message(
                                session_id,
                                MessageRole.ASSISTANT,
                                full_response,
                                metadata={"tokens_used": token_count, "run_id": _run_id},
                            )
                            await self._send_ws(
                                websocket,
                                OutgoingMessage(type="stream_end", message_id=ai_msg.id),
                            )
                            await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))

                        # ── Post-response cards with natural delay ──
                        import asyncio as _aio
                        response_lower = full_response.lower()
                        _card_shown = False

                        # If AI mentioned verification and order isn't verified
                        if not has_verified_order:
                            verify_keywords = ["verify", "verification", "verifizier", "bestellformular"]
                            if any(vk in response_lower for vk in verify_keywords):
                                await _aio.sleep(1.0)
                                await self._send_ws(websocket, OutgoingMessage(type="typing"))
                                await _aio.sleep(0.6)
                                from app.ai.card_builder import build_order_lookup_card
                                await self._send_ws(websocket, OutgoingMessage(
                                    type="info_card", info_card=build_order_lookup_card(),
                                ))
                                _card_shown = True

                        # If AI offered to create a ticket
                        if not _card_shown:
                            ticket_keywords = [
                                "support-ticket", "ticket erstellen", "anfrage an unser team",
                                "ticket f\u00fcr dich", "soll ich ein", "m\u00f6chtest du, dass ich",
                            ]
                            if any(tk in response_lower for tk in ticket_keywords):
                                await _aio.sleep(1.0)
                                await self._send_ws(websocket, OutgoingMessage(type="typing"))
                                await _aio.sleep(0.6)
                                confirmation = {
                                    "action": "create_ticket",
                                    "title": "Support-Ticket erstellen",
                                    "summary": "Unser Team k\u00fcmmert sich um dein Anliegen.",
                                    "fields": [
                                        {"key": "customer_name", "label": "Name", "value": user_claims.get("name", ""), "editable": True, "type": "text"},
                                        {"key": "customer_email", "label": "Order Email", "value": user_claims.get("email", ""), "editable": True, "type": "text"},
                                        {"key": "topic", "label": "Betreff", "value": (session or {}).get("topic_id", "General"), "editable": True, "type": "text", "prefix": "Groot Escalation \u2014 "},
                                        {"key": "issue_description", "label": "Beschreibung", "value": "", "editable": True, "type": "textarea"},
                                    ],
                                }
                                await self._send_ws(websocket, OutgoingMessage(type="confirmation_request", confirmation=confirmation))
                                _card_shown = True

                        # ── End-of-conversation detection: offer to close chat ──
                        if not _card_shown:
                            _msg_lower = (msg.content or "").strip().lower()
                            _closing_phrases = [
                                "danke", "dankeschön", "vielen dank", "thanks", "thank you",
                                "das war's", "das wars", "that's all", "thats all",
                                "nein danke", "no thanks", "nichts mehr", "nothing else",
                                "alles klar", "perfekt", "super danke", "ok danke",
                                "tschüss", "bye", "goodbye", "auf wiedersehen",
                                "nein", "no", "passt so", "alles gut",
                            ]
                            _is_closing = any(p in _msg_lower for p in _closing_phrases)
                            # Only show close card if conversation has enough messages (not first exchange)
                            _msg_count = (session or {}).get("message_count", 0)
                            if _is_closing and _msg_count >= 4:
                                await _aio.sleep(1.5)
                                await self._send_ws(websocket, OutgoingMessage(type="typing"))
                                await _aio.sleep(0.8)
                                from app.ai.card_builder import build_close_chat_card
                                await self._send_ws(websocket, OutgoingMessage(
                                    type="info_card", info_card=build_close_chat_card(),
                                ))
                                _card_shown = True

                        # ── Proactive suggestions based on conversation context ──
                        try:
                            from app.ai.suggestion_engine import get_smart_suggestions
                            _current_session = await self.chat_manager.get_session(session_id)
                            _smart_suggestions = get_smart_suggestions(
                                intent=_classified_intent,
                                has_verified_order=has_verified_order,
                                customer_phase="post-purchase" if has_verified_order else "pre-purchase",
                                topic_tags=(_current_session or {}).get("topic_tags", []),
                                session_events=(_current_session or {}).get("events", []),
                            )
                            if _smart_suggestions:
                                await self._send_ws(websocket, OutgoingMessage(
                                    type="suggestions", suggestions=_smart_suggestions,
                                ))
                        except Exception:
                            pass

                        # Run LangSmith auto-evaluators in background
                        if _run_id:
                            try:
                                from app.ai.langsmith_utils import run_auto_evaluators
                                import asyncio
                                asyncio.create_task(run_auto_evaluators(
                                    _run_id, msg.content, full_response
                                ))
                            except Exception:
                                pass


                    elif not escalated:
                        await self._send_ws(websocket, OutgoingMessage(type="stream_end"))
                        await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))

                elif msg.type == "not_helpful" and session_id:
                    await self.chat_manager.escalate_session(session_id, "user_not_helpful")
                    not_helpful_msg = (
                        "I'm sorry I couldn't help. "
                        "Would you like to contact our support team?"
                    )
                    await self._send_ws(
                        websocket,
                        OutgoingMessage(type="escalation", message=not_helpful_msg),
                    )

                elif msg.type == "create_ticket" and session_id:
                    # Send confirmation request — don't create immediately
                    session = await self.chat_manager.get_session(session_id)
                    confirmation = {
                        "action": "create_ticket",
                        "title": "Create Support Ticket",
                        "summary": "A support ticket will be created and sent to our team for review.",
                        "fields": [
                            {"key": "customer_name", "label": "Name", "value": user_claims.get("name", ""), "editable": True, "type": "text"},
                            {"key": "customer_email", "label": "Order Email", "value": user_claims.get("email", ""), "editable": True, "type": "text"},
                            {"key": "topic", "label": "Betreff", "value": session.get("topic_id", "General") if session else "General", "editable": True, "type": "text", "prefix": "Groot Escalation \u2014 "},
                            {"key": "issue_description", "label": "Issue Description", "value": "", "editable": True, "type": "textarea"},
                        ],
                    }
                    await self._send_ws(
                        websocket,
                        OutgoingMessage(type="confirmation_request", confirmation=confirmation),
                    )

                elif msg.type == "feedback" and session_id and msg.message_id:
                    if msg.feedback in ("up", "down"):
                        await self.chat_manager.record_feedback(msg.message_id, msg.feedback)

                        # Send to LangSmith if enabled
                        try:
                            from app.ai.langsmith_utils import send_feedback_to_langsmith
                            msg_doc = await messages_collection().find_one(
                                {"id": msg.message_id},
                                {"metadata": 1}
                            )
                            run_id = (msg_doc or {}).get("metadata", {}).get("run_id")
                            if run_id:
                                await send_feedback_to_langsmith(run_id, msg.feedback)
                        except Exception:
                            pass

                elif msg.type == "rating" and session_id and msg.rating is not None:
                    if 1 <= msg.rating <= 5:
                        await self.chat_manager.record_rating(session_id, msg.rating)

                        # Send to LangSmith linked to last AI message's run
                        try:
                            from app.ai.langsmith_utils import send_rating_to_langsmith
                            last_ai_msg = await messages_collection().find_one(
                                {"session_id": session_id, "role": "assistant"},
                                {"metadata": 1},
                                sort=[("created_at", -1)],
                            )
                            run_id = (last_ai_msg or {}).get("metadata", {}).get("run_id")
                            if run_id:
                                await send_rating_to_langsmith(run_id, msg.rating)
                        except Exception:
                            pass

                elif msg.type == "confirm_action" and session_id and msg.action:
                    if msg.action == "create_ticket":
                        try:
                            # Update session with form fields before creating ticket
                            fields = msg.fields or {}
                            form_email = fields.get("customer_email", "").strip()
                            form_name = fields.get("customer_name", "").strip()
                            form_description = fields.get("issue_description", "").strip()
                            form_topic = fields.get("topic", "").strip()
                            if form_email:
                                await self.chat_manager.update_session_email(session_id, form_email)
                            if form_name:
                                await self.chat_manager.update_session_field(session_id, "customer_name", form_name)
                            if form_topic:
                                await self.chat_manager.update_session_field(session_id, "ticket_subject", f"Groot Escalation \u2014 {form_topic}")
                            # Save the customer's description as a message so it appears in transcript
                            if form_description:
                                await self.chat_manager.add_message(
                                    session_id, MessageRole.USER, form_description
                                )

                            from app.escalation.actions import EscalationActions
                            actions = EscalationActions()
                            result = await actions.create_ticket(session_id)
                            await self.chat_manager.add_session_event(
                                session_id, "ticket_created",
                                f"Zendesk #{result['ticket_id']} — {result.get('topic', '')}",
                            )
                            # Send ticket confirmation card with copy button
                            from app.ai.card_builder import build_ticket_created_card
                            await self._send_ws(websocket, OutgoingMessage(
                                type="info_card",
                                info_card=build_ticket_created_card(
                                    ticket_id=result["ticket_id"],
                                    topic=result.get("topic", ""),
                                    summary=result.get("summary", ""),
                                ),
                            ))
                            ticket_msg = f"Support ticket **#{result['ticket_id']}** created. Our team will follow up shortly."
                            _uc_email = user_claims.get("email") or "" if user_claims else ""
                            if _uc_email:
                                ticket_msg += f" Confirmation sent to **{_uc_email}**."
                            ai_msg = await self.chat_manager.add_message(
                                session_id, MessageRole.ASSISTANT, ticket_msg
                            )
                            await self._send_ws(
                                websocket,
                                OutgoingMessage(type="message", content=ticket_msg, message_id=ai_msg.id),
                            )
                        except Exception as e:
                            logger.exception(f"Confirmed ticket creation failed: {e}")
                            await self._send_ws(
                                websocket,
                                OutgoingMessage(type="error", message="Failed to create ticket. Please try again."),
                            )
                    elif msg.action == "mark_urgent":
                        try:
                            fields = msg.fields or {}
                            ticket_id = fields.get("ticket_id", "").strip().lstrip("#")
                            reason = fields.get("urgency_reason", "").strip()

                            if not ticket_id:
                                await self._send_ws(websocket, OutgoingMessage(type="error", message="Missing ticket ID."))
                                continue

                            from app.escalation.ticket.zendesk_adapter import ZendeskAdapter
                            adapter = ZendeskAdapter()
                            success = await adapter.mark_urgent(ticket_id, reason)

                            if success:
                                await self.chat_manager.add_session_event(
                                    session_id, "ticket_urgent",
                                    f"Ticket #{ticket_id} escalated to urgent" + (f" — {reason[:50]}" if reason else ""),
                                )
                                # Send urgent confirmation card
                                from app.ai.card_builder import build_ticket_urgent_card
                                await self._send_ws(websocket, OutgoingMessage(
                                    type="info_card", info_card=build_ticket_urgent_card(ticket_id),
                                ))
                                urgent_msg = f"Ticket **#{ticket_id}** has been marked as **urgent**. Our team has been notified."
                                ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, urgent_msg)
                                await self._send_ws(websocket, OutgoingMessage(type="message", content=urgent_msg, message_id=ai_msg.id))

                                # Send urgent alert email (non-blocking)
                                try:
                                    from app.escalation.email_sender import send_urgent_alert_email
                                    # Fetch ticket subject for the email
                                    ticket_data = await adapter.get_ticket(ticket_id, user_claims.get("email", ""))
                                    ticket_subject = ticket_data.get("subject", "") if ticket_data else ""
                                    await send_urgent_alert_email(
                                        ticket_id=ticket_id,
                                        ticket_subject=ticket_subject,
                                        customer_email=user_claims.get("email", ""),
                                        customer_name=user_claims.get("name", ""),
                                        reason=reason,
                                    )
                                except Exception as e:
                                    logger.error(f"Urgent alert email failed: {e}")
                            else:
                                await self._send_ws(websocket, OutgoingMessage(type="error", message="Failed to update ticket priority. Please try again."))
                        except Exception as e:
                            logger.exception(f"Mark urgent failed: {e}")
                            await self._send_ws(websocket, OutgoingMessage(type="error", message="Failed to escalate ticket. Please try again."))

                elif msg.type == "cancel_action" and session_id:
                    cancel_msg = "No problem \u2014 the request has been cancelled."
                    ai_msg = await self.chat_manager.add_message(
                        session_id, MessageRole.ASSISTANT, cancel_msg
                    )
                    await self._send_ws(
                        websocket,
                        OutgoingMessage(type="message", content=cancel_msg, message_id=ai_msg.id),
                    )

                elif msg.type == "input_response" and session_id and msg.input_field:
                    if msg.input_field in ("order_number", "order_verify") and (msg.input_value or (msg.fields or {}).get("order_number")):
                        # Verify order — order number + postcode only (no email filter)
                        # Prefer explicit field over input_value (card forms may swap field order)
                        _fields = msg.fields or {}
                        order_number = (_fields.get("order_number") or msg.input_value or "").strip().lstrip("#")
                        postcode = _fields.get("postcode", "").strip()

                        if not postcode:
                            verify_msg = "Please enter your billing postcode for verification."
                            ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, verify_msg)
                            await self._send_ws(websocket, OutgoingMessage(
                                type="message", content=verify_msg, message_id=ai_msg.id,
                            ))
                            await self._send_ws(websocket, OutgoingMessage(
                                type="input_prompt",
                                input_prompt={
                                    "field": "order_verify",
                                    "label": "Look up your order",
                                    "fields": [
                                        {"name": "order_number", "label": "Order number", "placeholder": "#...", "type": "text", "value": order_number},
                                        {"name": "postcode", "label": "Billing postcode", "placeholder": "e.g. 10115", "type": "text"},
                                    ],
                                    "action": "verify_order",
                                },
                            ))
                            continue

                        try:
                            await self.chat_manager.add_session_event(
                                session_id, "verification_attempted",
                                f"Order #{order_number}, postcode={postcode}",
                            )
                            from app.shopware.client import ShopwareClient
                            client = ShopwareClient()
                            order_data = await client.get_order(order_number)

                            # Postcode verification: check billing address on the order
                            if order_data and not order_data.get("order_not_owned") and postcode:
                                try:
                                    # Check postcode against order's billing address
                                    order_obj = order_data.get("order", order_data)
                                    billing_addr = order_obj.get("billingAddress") or {}
                                    order_postcode = (billing_addr.get("zipcode") or billing_addr.get("postcode") or "").strip()

                                    # Fallback: check customer's saved addresses
                                    if not order_postcode:
                                        customer_email_for_addr = order_obj.get("customerEmail") or order_obj.get("email") or ""
                                        if customer_email_for_addr:
                                            addresses = await client.get_customer_addresses(customer_email_for_addr)
                                            if addresses and isinstance(addresses, list):
                                                for addr in addresses:
                                                    zc = (addr.get("zipcode") or addr.get("postcode") or "").strip()
                                                    if zc:
                                                        order_postcode = zc
                                                        break

                                    if order_postcode and postcode != order_postcode:
                                        order_data = {"order_not_owned": True}
                                except Exception:
                                    pass  # If postcode check fails, allow through

                            if order_data and not order_data.get("order_not_owned"):
                                # Order verified — store and cache
                                order = order_data.get("order", order_data)
                                status = order.get("statusLabel") or order.get("stateName") or "Unknown"
                                items_count = len(order.get("lineItems", []))
                                total = order.get("amountTotal") or order.get("totalAmount") or 0

                                await self.chat_manager.add_session_event(
                                    session_id, "verification_success",
                                    f"Order #{order_number} verified — {status}, {items_count} items, {total} EUR",
                                )
                                await self.chat_manager.update_session_order(session_id, order_number)
                                # Store the order's email for later use (ticket creation, etc.)
                                order_email = order.get("customerEmail") or order.get("email") or user_claims.get("email", "")
                                if order_email and order_email != user_claims.get("email", ""):
                                    await self.chat_manager.update_session_email(session_id, order_email)
                                await self.chat_manager.cache_order_data(session_id, order)

                                # Send acknowledgment + verified card
                                from app.ai.card_builder import build_order_verified_card
                                verify_msg = f"Danke! Deine Bestellung **#{order_number}** wurde verifiziert. Wie kann ich dir weiterhelfen?"
                                ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, verify_msg)
                                await self._send_ws(websocket, OutgoingMessage(
                                    type="ai_card", content=verify_msg, message_id=ai_msg.id,
                                    info_card=build_order_verified_card(order, order_number),
                                ))
                                await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))

                                # Update suggestions
                                session_data = await self.chat_manager.get_session(session_id)
                                topic_id = session_data.get("topic_id", "") if session_data else ""
                                if topic_id == "order_status":
                                    await self._send_ws(websocket, OutgoingMessage(
                                        type="suggestions",
                                        suggestions=["Where is my package?", "Tracking number", "Delivery date"],
                                    ))
                                elif topic_id == "returns":
                                    await self._send_ws(websocket, OutgoingMessage(
                                        type="suggestions",
                                        suggestions=["Start return", "Refund status", "Exchange item"],
                                    ))
                                elif topic_id == "order_issue":
                                    await self._send_ws(websocket, OutgoingMessage(
                                        type="suggestions",
                                        suggestions=["Wrong item", "Damaged item", "Missing item"],
                                    ))
                            else:
                                # Order not found or not owned — send error card
                                await self.chat_manager.add_session_event(
                                    session_id, "verification_failed",
                                    f"Order #{order_number} — not found or postcode mismatch",
                                )
                                from app.ai.card_builder import build_order_failed_card
                                await self._send_ws(websocket, OutgoingMessage(
                                    type="info_card",
                                    info_card=build_order_failed_card(order_number),
                                ))
                        except Exception as e:
                            logger.error(f"Order verification failed: {e}")
                            await self.chat_manager.add_session_event(
                                session_id, "verification_error", str(e)[:100],
                            )
                            # Fall through to chat — let the AI handle it conversationally
                            fallback_msg = "I had trouble looking up that order. Could you tell me more about your issue?"
                            ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, fallback_msg)
                            await self._send_ws(websocket, OutgoingMessage(
                                type="message", content=fallback_msg, message_id=ai_msg.id,
                            ))

                    elif msg.input_field == "ticket_verify":
                        # Ticket status lookup via Zendesk API
                        fields = msg.fields or {}
                        ticket_id = (fields.get("ticket_id") or msg.input_value or "").strip().lstrip("#")
                        email = fields.get("email", "").strip()

                        if not email:
                            err_msg = "Please enter your email to verify the ticket."
                            ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, err_msg)
                            await self._send_ws(websocket, OutgoingMessage(type="message", content=err_msg, message_id=ai_msg.id))
                            continue

                        try:
                            from app.escalation.ticket.zendesk_adapter import ZendeskAdapter
                            adapter = ZendeskAdapter()
                            ticket = await adapter.get_ticket(ticket_id, email)

                            if ticket:
                                await self.chat_manager.add_session_event(
                                    session_id, "ticket_status_shown",
                                    f"Ticket #{ticket['id']} \u2014 {ticket['status'].title()} (priority={ticket['priority']})",
                                )
                                from app.ai.card_builder import build_ticket_status_card
                                await self._send_ws(websocket, OutgoingMessage(
                                    type="info_card", info_card=build_ticket_status_card(ticket),
                                ))
                            else:
                                await self.chat_manager.add_session_event(
                                    session_id, "ticket_lookup_failed",
                                    f"Ticket #{ticket_id} — not found or email mismatch",
                                )
                                fail_msg = f"Ticket #{ticket_id} was not found or the email doesn't match. Please check your ticket number and email."
                                ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, fail_msg)
                                await self._send_ws(websocket, OutgoingMessage(type="message", content=fail_msg, message_id=ai_msg.id))
                                # Re-show lookup form
                                from app.ai.card_builder import build_ticket_lookup_card
                                await self._send_ws(websocket, OutgoingMessage(
                                    type="info_card", info_card=build_ticket_lookup_card(),
                                ))
                        except Exception as e:
                            logger.error(f"Ticket lookup failed: {e}")
                            err_msg = "I had trouble looking up that ticket. Please try again."
                            ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, err_msg)
                            await self._send_ws(websocket, OutgoingMessage(type="message", content=err_msg, message_id=ai_msg.id))

                    elif msg.input_field == "compatibility_check" and msg.input_value:
                        # Vehicle compatibility — final selection submitted
                        object_id = msg.input_value.strip()
                        fields = msg.fields or {}
                        vehicle_name = fields.get("vehicle_name", "dein Fahrzeug")
                        try:
                            from app.shopware.client import ShopwareClient
                            client = ShopwareClient()

                            # Fetch compatible products + listing URL
                            products = await client.compatibility_get_products(object_id)
                            result_url = await client.compatibility_get_result(object_id)

                            # Build public listing URL with tracking
                            listing_url = ""
                            if result_url:
                                if "shopware." in result_url:
                                    from urllib.parse import urlparse
                                    parsed = urlparse(result_url)
                                    listing_url = f"https://voltimax.de{parsed.path}"
                                else:
                                    listing_url = result_url
                                import hashlib as _hl
                                raw = f"{session_id}:{__import__('time').time()}"
                                track = _hl.sha256(raw.encode()).hexdigest()[:8]
                                listing_url += f"?groot_ref=compatibility&groot_session={track}"

                            if products:
                                # Show product card with compatible batteries
                                from app.ai.card_builder import build_product_card, get_real_delivery_label

                                # Build detailed product list for AI memory
                                product_lines = [f"**{len(products)} passende Batterie(n)** f\u00fcr **{vehicle_name}** gefunden:\n"]
                                for _p in products:
                                    _pname = _p.get("name", "?")[:60]
                                    _pprice = ""
                                    _calc = _p.get("calculatedPrice")
                                    if _calc and isinstance(_calc, dict):
                                        _pprice = f"\u20ac{_calc.get('totalPrice', 0):.2f}"
                                    elif _p.get("price") is not None:
                                        _pprice = f"\u20ac{_p['price']:.2f}"
                                    _pavail = "\u2705" if _p.get("available", (_p.get("stock") or 0) > 0) else "\u274c"
                                    _pdel = get_real_delivery_label(_p)
                                    _pid = _p.get("id", "")
                                    _purl = f"https://voltimax.de/detail/{_pid}" if _pid else ""
                                    product_lines.append(f"- [{_pname}]({_purl}) \u2014 {_pprice} {_pavail} \u2022 {_pdel}")

                                result_msg = "\n".join(product_lines)
                                ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, result_msg)
                                await self._send_ws(websocket, OutgoingMessage(type="message", content=product_lines[0], message_id=ai_msg.id))

                                product_card = build_product_card(products, session_id, from_compatibility=True, listing_url=listing_url)
                                if product_card:
                                    await self._send_ws(websocket, OutgoingMessage(
                                        type="info_card", info_card=product_card,
                                    ))

                                # Store full product details in session event
                                _product_names = [_p.get("name", "")[:50] for _p in products]
                                await self.chat_manager.add_session_event(
                                    session_id, "compatibility_result",
                                    f"Vehicle: {vehicle_name} \u2014 Products shown: {', '.join(_product_names)}",
                                )
                            else:
                                no_result_msg = f"Leider keine passenden Produkte f\u00fcr **{vehicle_name}** gefunden. Bitte versuche eine andere Kombination."
                                ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, no_result_msg)
                                await self._send_ws(websocket, OutgoingMessage(type="message", content=no_result_msg, message_id=ai_msg.id))
                        except Exception as e:
                            logger.error(f"Compatibility check failed: {e}")

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: session={session_id}")
            _close_reason = "disconnected"
        except Exception as e:
            logger.exception(f"WebSocket error: {e}")
            _close_reason = "error"
            try:
                await self._send_ws(
                    websocket,
                    OutgoingMessage(type="error", message="An internal error occurred."),
                )
            except Exception:
                pass
        finally:
            _duration = int(_time.monotonic() - _session_start)
            if session_id:
                _sess = await self.chat_manager.get_session(session_id)
                _msg_count = _sess.get("message_count", 0) if _sess else 0
                try:
                    await _track_end(session_id, _duration, _msg_count)
                except Exception:
                    pass
                self.active_connections.pop(session_id, None)
                # Only close if not already closed (idle timeout closes before reaching here)
                if _sess and _sess.get("status") != "closed":
                    await self.chat_manager.close_session(session_id, close_reason=_close_reason)

    async def _send_ws(self, websocket: WebSocket, msg: OutgoingMessage) -> None:
        try:
            await websocket.send_text(msg.model_dump_json(exclude_none=True))
        except Exception:
            pass  # Connection may be closed

    async def _send_ai_card(
        self, websocket: WebSocket, session_id: str, intro_text: str, card: dict | None,
    ) -> None:
        """Send a short AI message with an embedded card as one unified response.

        Also stores the full card content in the message text so the AI
        remembers what was shown in follow-up conversations.
        """
        import asyncio as _aio
        await self._send_ws(websocket, OutgoingMessage(type="typing"))
        await _aio.sleep(0.8)

        # Build full message text = intro + card details for AI memory
        full_text = intro_text
        if card:
            card_details = self._card_to_text(card)
            if card_details:
                full_text = intro_text + "\n\n" + card_details

        ai_msg = await self.chat_manager.add_message(session_id, MessageRole.ASSISTANT, full_text)
        await self._send_ws(websocket, OutgoingMessage(
            type="ai_card", content=intro_text, message_id=ai_msg.id, info_card=card,
        ))
        await self._send_ws(websocket, OutgoingMessage(type="play_sound", message="incoming"))

    @staticmethod
    def _card_to_text(card: dict) -> str:
        """Convert a card dict to readable text for AI conversation memory."""
        parts = []
        if card.get("title"):
            parts.append(f"[Card: {card['title']}]")
        if card.get("description"):
            parts.append(card["description"][:300])
        for row in card.get("rows", []):
            if row.get("label") and row.get("value"):
                parts.append(f"  {row['label']}: {row['value']}")
        for link in card.get("links", []):
            label = link.get("label", "")
            detail = link.get("detail", "")
            url = link.get("url", "")
            line = f"  - {label}"
            if detail:
                line += f" ({detail})"
            if url:
                line += f" → {url}"
            parts.append(line)
        for step in card.get("steps", []):
            if step.get("title"):
                parts.append(f"  {step['title']}: {step.get('text', '')[:100]}")
        for field in card.get("fields", []):
            if field.get("label") and field.get("value"):
                parts.append(f"  {field['label']}: {field['value']}")
        if card.get("actions"):
            parts.append(f"  Actions: {', '.join(card['actions'][:5])}")
        return "\n".join(parts) if parts else ""

    async def _get_visible_topics(self, user_claims: dict) -> list[dict]:
        """Filter topic cards based on customer context from JWT claims."""
        from app.db.admin_config import get_admin_config
        try:
            stored = await get_admin_config("topic_cards")
        except Exception:
            logger.warning("Failed to load topic_cards from MongoDB, using config fallback", exc_info=True)
            stored = None
        if stored is not None:
            # Filter stored cards by visibility
            has_orders = user_claims.get("has_orders", False)
            is_b2b = user_claims.get("is_b2b", False)
            visible = []
            for card in stored:
                if not self._is_visible(card.get("visibility", "always"), has_orders, is_b2b):
                    continue
                card_data = {
                    "id": card.get("id", ""),
                    "title": card.get("title", ""),
                    "icon": card.get("icon", ""),
                    "description": card.get("description", ""),
                }
                sub_cards = card.get("sub_cards", [])
                if sub_cards:
                    card_data["sub_cards"] = [
                        {
                            "id": sc.get("id", ""),
                            "title": sc.get("title", ""),
                            "icon": sc.get("icon", ""),
                            "description": sc.get("description", ""),
                        }
                        for sc in sub_cards
                        if self._is_visible(sc.get("visibility", "always"), has_orders, is_b2b)
                    ]
                visible.append(card_data)
            return visible

        # Fall back to config.yaml
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
                    {"id": sc.id, "title": sc.title, "icon": sc.icon, "description": sc.description}
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

    async def _get_provider_for_topic(self, topic_id: str) -> str:
        return await get_live_llm_provider(topic_id)


# Singleton
_connection_handler: ConnectionHandler | None = None


def get_connection_handler() -> ConnectionHandler:
    global _connection_handler
    if _connection_handler is None:
        _connection_handler = ConnectionHandler()
    return _connection_handler
