"""Unified classifier — single LLM call replaces card router + intent classifier.

Returns card action, intent, search query, and resolved topic in one call.
Saves ~0.7s and ~500 tokens per message vs two separate calls.
"""
from __future__ import annotations

import json
import logging

from langsmith import traceable

from app.ai.prompt_hub import render_prompt
from app.ai.router import get_provider, get_default_provider

logger = logging.getLogger(__name__)

_FALLBACK_PROMPT = """You are a unified classifier for a customer support chat system for Voltimax (batteries, solar, electronics shop).

Based on the customer's message and session context, decide TWO things:
1. What card/action to show (if any)
2. What the customer's intent is (for AI response)

Respond with ONLY a JSON object.

SESSION CONTEXT:
- Has verified order: {{has_order}}
- Verified order number: {{order_number}}
- Current topic: {{topic}}
- Has cached order data: {{has_data}}

CARD ACTIONS:

If customer HAS a verified order ({{has_order}}):
  "tracking" — asking specifically about delivery, shipment, package location, tracking number, where is my package
  "payment" — asking about payment status, refund, money
  "invoice" — asking about invoice, receipt, rechnung
  "return_ticket" — wants to return item(s)
  "problem_ticket" — reporting a problem, damaged, wrong item
  "warranty" — asking about warranty, guarantee
  "another_order" — wants to look up a different order
  "none" — general questions about the order (order date, items, total, status summary) — the AI can answer from cached data without showing a card

ALWAYS available (with or without verified order):
  "escalation_ticket" — wants human agent, contact support, support kontaktieren, create ticket
  "ticket_lookup" — customer explicitly asks to CHECK the status of an existing support ticket (e.g. "what's the status of my ticket?", "any update on ticket 12345?"). Do NOT use when customer merely MENTIONS a ticket number as context for an order question (e.g. "this order was created because of ticket 18465" → this is about the order, use "none")
  "compatibility_check" — when customer mentions a specific vehicle (car make/model/year, motorcycle make/model) and wants a battery for it. Examples: "BMW 3er", "Audi A4 2020", "Golf 7", "Harley Davidson Breakout", "Honda CBR 600", "Ducati Monster", "Breakout 2018". Includes cars, motorcycles, trucks, boats. NEVER use for product name searches like "Varta H3" or "search for battery" — those are product_query with action "none". When in doubt if a name is a vehicle model, prefer compatibility_check over product_query.
  "batteriepfand" — asking about Batteriepfand, battery deposit return, Pfandrückgabe, Altbatterie zurückgeben, wants to submit Batteriepfand forms
  "account_info" — asking about their OWN account, profile, login, password reset, address management, personal data, Kundenkonto, "Mein Konto". Do NOT use for: "Kundendienst" (customer service), company contact info, store location, opening hours, checkout/ordering process questions ("wie bestelle ich?", "Endverbraucher oder Geschäftskunde?", "wie funktioniert die Bestellung?"), payment method questions before purchase — all these are general questions (action="none", intent=rag_query)

If customer does NOT have a verified order:
  "order_lookup" — talking about THEIR specific order, needs verification. Use when customer wants to check THEIR order status, track THEIR package, return THEIR specific item, get THEIR invoice. NOT for general policy questions (return policy, shipping costs, warranty info) — those are "none" with rag_query intent. ALSO use this when the customer HAS an order but says they CANNOT FIND or DON'T HAVE the order number or invoice ZIP (e.g. "Ich finde die Nummern nicht", "Ich habe keine Bestellnummer", "wo finde ich die Bestellnummer?") — the system will offer help/escalation. NEVER invent an alternative lookup method (by email, date, or product) — the ONLY ways to verify are order number + invoice ZIP, otherwise escalate to support.
  "no_order" — explicitly says they have NO order at all (e.g. "Ich habe keine Bestellung", "ich habe noch nichts bestellt"). Do NOT use this when they have an order but just can't find the number — that is "order_lookup".
  "clarify" — message is too vague or ambiguous to determine intent. Use this when you genuinely cannot tell what the customer wants. AI will ask a follow-up question to understand better.
  "none" — general question, let AI respond naturally

INTENT CATEGORIES:
  "order_query" — about order status, tracking, delivery
  "return_query" — customer wants to RETURN or EXCHANGE a specific item they ordered. Use ONLY when they clearly want to initiate a return on their order.
  NOTE: General questions about return POLICY, costs, deadlines, conditions (e.g. "how does return work?", "Rückgaberecht", "return policy") are "rag_query" NOT "return_query" — these are answerable from knowledge base without needing an order.
  "product_query" — about products, stock, availability, pricing
  "product_doc_query" — requesting document, PDF, datasheet, manual for a product
  "customer_query" — about account, addresses, payment methods
  "b2b_query" — about B2B quotes, employee accounts
  "rag_query" — general questions answerable from knowledge base
  "direct" — greetings, thanks, simple conversation
  "escalation" — frustrated, asking for human agent

SEARCH QUERY:
  IMPORTANT: The product catalogue is in GERMAN. Always output search_query in German, even if the customer writes in English.
  For product_query: extract product name/type in German (NOT car models). Example: "car battery" → "Autobatterie", "solar panel" → "Solarmodul"
  For product_doc_query: extract ONLY the product name in German (strip "pdf", "manual", "datenblatt")
  For order_query: extract order number if present
  All other intents: empty string

RULES:
  - Use action "none" for greetings, thanks, general questions
  - Use "escalation_ticket" ONLY when customer explicitly wants to talk to a human agent, create a support ticket, or says "support kontaktieren" — NOT for account questions or payment questions
  - Asking HOW to reach/contact support is informational, NOT escalation: "Wie erreiche ich den Kundendienst?", "Kontaktdaten", "Telefonnummer Support", "habt ihr eine Hotline?" → action "none" (the AI gives contact info). Only use "escalation_ticket" when they want to be connected NOW or open a ticket about a specific problem.
  - Use "order_lookup" when customer asks about payment status, tracking, invoice, refund, or any order-specific info WITHOUT a verified order — they must verify first
  - Use "tracking"/"payment"/"invoice" ONLY when has_order=true
  - Use "account_info" ONLY when customer asks about their OWN account: login, password, address changes, Kundenkonto, "Mein Konto". NEVER use for: Kundendienst, company location, contact info, opening hours, checkout process, ordering questions, payment method selection — those are general questions (action="none", intent=rag_query)
  - Use "batteriepfand" whenever the customer mentions Batteriepfand, Pfandrückgabe, battery deposit, or Altbatterie return — this is NEVER a product search, always the batteriepfand action
  - Use "clarify" ONLY when the message is genuinely ambiguous with no topic hint (e.g. just "hi", "help" with zero context). Do NOT clarify when the message contains a clear topic word like "Bestellstatus", "Produktsuche", "Retoure", "Rechnung", "Batteriepfand", "Ticket", "Konto" — these always have a clear action even if short
  - Messages with emoji prefixes (📦, 🔋, ↩️, etc.) are suggestion chip clicks — treat the text after the emoji as the intent, NEVER clarify these. Examples: "↩️ Retoure & Erstattung" → rag_query about return policy (action=none), "📦 Bestellstatus" → order_lookup
  - "ticket_lookup" ONLY when customer explicitly asks to CHECK ticket status. Mentioning a ticket number as context for an order question is NOT a ticket lookup — use "none" to let AI respond
  - If the SAME card type was already shown in recent conversation and customer asks a follow-up question about the data (e.g. "why is the date so late?" after seeing tracking card), use "none" — let AI explain instead of re-showing the same card
  - When unsure between two specific actions, prefer the more specific action over clarify
  - NEVER use "clarify" more than once in a row — if the previous message was already a clarification response, use "none" and let the AI respond with the best guess. Repeated clarify loops frustrate customers.
  - When the customer can't find or doesn't have their order number / invoice ZIP after an order-lookup card was shown, use "order_lookup" (NOT "clarify", NOT "none"). The system detects the repeat and offers a support ticket. NEVER promise to find the order by email, date, or product — that capability is not available to the chat.
  - When a customer mentions a vehicle/model name + "Batterie", always use "compatibility_check" — even for motorcycles, boats, or unusual model names

COMPLEXITY (pick one):
  "simple" — greetings, thanks, yes/no answers, single straightforward question
  "complex" — multiple questions in one message, frustrated/emotional tone, multi-step request (e.g. return + refund + complaint), ambiguous request needing interpretation, technical compatibility questions

FOLLOW-UP AWARENESS:
  You will receive recent conversation history. If the current message is a follow-up, maintain the same intent.
  Examples:
  - Previous: "PDF for Varta A7" → Current: "what about ea770?" → STILL product_doc_query
  - Previous: "where is my order?" → Current: "when will it arrive?" → STILL order_query

Respond with ONLY: {"action": "<action>", "intent": "<intent>", "search_query": "<query>", "complexity": "<simple|complex>"}

Customer message: "{{message}}\""""


@traceable(name="groot-unified-classifier")
async def classify_message(
    message: str,
    has_verified_order: bool,
    order_number: str = "",
    topic: str = "general",
    has_cached_data: bool = False,
    history: list[dict] | None = None,
    llm_provider: str | None = None,
    chat_id: str = "",
) -> dict:
    """Classify a message in one LLM call.

    Returns dict with: action, intent, search_query, resolved_topic, data_type, needs_shopware_data
    """
    provider_name = llm_provider or get_default_provider()

    try:
        provider = get_provider(provider_name)
        variables = {
            "has_order": str(has_verified_order).lower(),
            "order_number": order_number or "none",
            "topic": topic,
            "has_data": str(has_cached_data).lower(),
            "message": message,
        }

        prompt = render_prompt("groot-unified-classifier", variables)
        if not prompt:
            import chevron
            prompt = chevron.render(_FALLBACK_PROMPT, variables)

        # Include conversation history for follow-up awareness
        messages = []
        if history:
            for msg in history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})

        result = await provider.generate(
            messages,
            temperature=0,
            max_tokens=80,
        )

        # Parse JSON
        clean = result.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
            clean = clean.strip()

        parsed = json.loads(clean)
        action = parsed.get("action", "none").strip().lower()
        intent = parsed.get("intent", "direct").strip().lower()
        search_query = parsed.get("search_query", "").strip()
        complexity = parsed.get("complexity", "simple").strip().lower()

    except Exception as e:
        logger.warning(f"Unified classifier failed: {e}. Defaulting to none/direct.")
        action = "none"
        intent = "direct"
        search_query = ""
        complexity = "simple"

    # Validate action
    valid_actions = {
        "tracking", "payment", "invoice", "return_ticket", "problem_ticket",
        "escalation_ticket", "warranty", "another_order",
        "order_lookup", "ticket_lookup", "compatibility_check", "batteriepfand",
        "account_info", "clarify", "no_order", "none",
    }
    if action not in valid_actions:
        action = "none"

    # Safety: order-specific cards need verified order
    order_cards = {"tracking", "payment", "invoice", "return_ticket",
                   "problem_ticket", "warranty", "another_order"}
    if action in order_cards and not has_verified_order:
        action = "order_lookup"

    # The classifier should distinguish return POLICY questions (→ rag_query, action=none)
    # from specific return REQUESTS (→ return_query, action=order_lookup).
    # No hardcoded keyword overrides — trust the classifier.

    # Safety: customer_query about account should use account_info, not escalation
    if intent == "customer_query" and action in ("escalation_ticket", "none"):
        action = "account_info"

    # Map intent to data needs
    data_map = {
        "order_query": ("order", True),
        "return_query": ("return", True),
        "product_query": ("product", True),
        "product_doc_query": ("product", True),
        "customer_query": ("customer", True),
        "b2b_query": ("b2b", True),
        "rag_query": ("", False),
        "direct": ("", False),
        "escalation": ("", False),
    }
    data_type, needs_data = data_map.get(intent, ("", False))

    # account_info is handled directly in connection.py — no Shopware/RAG data needed
    if action == "account_info":
        data_type = ""
        needs_data = False

    # Auto-resolve topic
    topic_map = {
        "product_query": "product_help",
        "product_doc_query": "product_help",
        "order_query": "order_status",
        "return_query": "returns",
        "customer_query": "account",
        "escalation": "complaint",
        "rag_query": "faq",
        "b2b_query": "general",
    }
    resolved_topic = topic_map.get(intent, "")

    # Action-based topic override (only if intent didn't already set a specific topic)
    if action == "account_info":
        resolved_topic = "account"
    elif action == "batteriepfand":
        resolved_topic = "batteriepfand"
    elif action == "compatibility_check":
        resolved_topic = "compatibility"
    elif action == "ticket_lookup":
        resolved_topic = "general"
    elif action in ("tracking", "payment", "invoice", "order_lookup"):
        # Don't override if intent already mapped to a more specific topic
        if resolved_topic not in ("returns", "complaint"):
            resolved_topic = "order_status"
    elif action in ("problem_ticket", "return_ticket"):
        if intent == "return_query":
            resolved_topic = "returns"
        else:
            resolved_topic = "order_issue"

    # Validate complexity
    if complexity not in ("simple", "complex"):
        complexity = "simple"

    logger.info(f"Classifier: msg={message[:50]!r} → action={action} intent={intent} q={search_query!r} complexity={complexity}")

    return {
        "action": action,
        "intent": intent,
        "search_query": search_query,
        "resolved_topic": resolved_topic,
        "data_type": data_type,
        "needs_shopware_data": needs_data,
        "should_escalate": intent == "escalation" and complexity == "complex",
        "complexity": complexity,
    }
