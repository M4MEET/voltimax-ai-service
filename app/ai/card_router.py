"""Smart card router — single LLM call to decide what card (if any) to show.

Replaces all hardcoded keyword matching with one intelligent classifier.
Takes session context into account for accurate routing.
Prompt is pulled from LangSmith Prompt Hub (groot-card-router) with local fallback.
"""
from __future__ import annotations

import json
import logging

from app.ai.prompt_hub import render_prompt
from app.ai.router import get_provider, get_default_provider

logger = logging.getLogger(__name__)

_FALLBACK_ROUTER_PROMPT = """You are a routing classifier for a customer support chat system for Voltimax (batteries, solar, electronics shop).

Based on the customer's message and session context, decide what action to take. Respond with ONLY a JSON object.

SESSION CONTEXT:
- Has verified order: {{has_order}}
- Verified order number: {{order_number}}
- Current topic: {{topic}}
- Has cached order data: {{has_data}}

AVAILABLE ACTIONS:

If customer HAS a verified order ({{has_order}}):
  "tracking" — asking about delivery, shipment, package location, tracking number, where is my order
  "payment" — asking about payment status, refund, money, charged, paid, erstattung, zahlung
  "invoice" — asking about invoice, receipt, rechnung, beleg, document, proof of purchase
  "return_ticket" — wants to return item(s), send back, exchange, rücksendung
  "problem_ticket" — reporting a problem, damaged, wrong item, missing, complaint about order
  "warranty" — asking about warranty, guarantee, garantie on ordered items
  "another_order" — wants to look up a different/another order, switch order, andere bestellung

ALWAYS available (with or without verified order):
  "escalation_ticket" — wants human agent, contact support, speak to someone, support kontaktieren, Hilfe von einem Mitarbeiter, create ticket, open ticket
  "ticket_lookup" — wants to check status of an existing support ticket, mentions ticket number, asks about ticket update
  "compatibility_check" — wants to find a battery for their specific vehicle, mentions car model, vehicle compatibility, "which battery fits my car", "Batterie für BMW", "welche Batterie passt"

If customer does NOT have a verified order:
  "order_lookup" — talking about their specific order, needs verification first
  "no_order" — explicitly says they don't have an order, want pre-sales help
  "none" — not about a specific order, general question (products, shipping times, policies, greetings, etc.)

RULES:
- Use "none" for greetings, thanks, general product questions, policy questions — let the AI respond naturally
- Use "order_lookup" ONLY when the customer clearly wants info about THEIR specific placed order
- Use "escalation_ticket" when customer wants to contact support, create a ticket, or speak to a human — even WITHOUT a verified order
- Use "ticket_lookup" when asking about an existing SUPPORT TICKET (not order)
- Use "compatibility_check" when asking about vehicle/car battery compatibility
- Use "tracking"/"payment"/"invoice" ONLY when an order is verified (has_order=true)
- Use "return_ticket"/"problem_ticket"/"escalation_ticket" for actions that need a Zendesk ticket
- When unsure, prefer "none" — it's better to let the AI respond than show the wrong card

Respond with ONLY: {"action": "<action_name>"}

Customer message: "{{message}}\""""


async def route_message(
    message: str,
    has_verified_order: bool,
    order_number: str = "",
    topic: str = "general",
    has_cached_data: bool = False,
    llm_provider: str | None = None,
) -> str:
    """Classify a message and return the action to take.

    Returns one of: tracking, payment, invoice, return_ticket, problem_ticket,
    escalation_ticket, warranty, another_order, order_lookup, no_order, none
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

        # Try LangSmith first, fall back to local template
        prompt = render_prompt("groot-card-router", variables)
        if not prompt:
            import chevron
            prompt = chevron.render(_FALLBACK_ROUTER_PROMPT, variables)

        result = await provider.generate(
            [{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20,
        )

        # Parse JSON response
        clean = result.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
            clean = clean.strip()

        parsed = json.loads(clean)
        action = parsed.get("action", "none").strip().lower()

        # Validate action is known
        valid_actions = {
            "tracking", "payment", "invoice", "return_ticket", "problem_ticket",
            "escalation_ticket", "warranty", "another_order",
            "order_lookup", "ticket_lookup", "compatibility_check", "no_order", "none",
        }
        if action not in valid_actions:
            logger.warning(f"Card router returned unknown action: {action}")
            return "none"

        # Safety: don't return order-specific cards if no verified order
        # escalation_ticket is excluded — contacting support works without an order
        order_cards = {"tracking", "payment", "invoice", "return_ticket",
                       "problem_ticket", "warranty", "another_order"}
        if action in order_cards and not has_verified_order:
            return "order_lookup"

        return action

    except Exception as e:
        logger.warning(f"Card router failed: {e}. Defaulting to 'none'.")
        return "none"
