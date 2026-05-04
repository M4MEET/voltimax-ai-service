"""Context-aware suggestion engine — generates follow-up suggestions after each AI response.

Uses intent, customer phase, session history, and conversation state to suggest
relevant next questions. No LLM call needed — purely deterministic.
"""
from __future__ import annotations


def get_smart_suggestions(
    intent: str,
    has_verified_order: bool,
    customer_phase: str,
    topic_tags: list[str] | None = None,
    session_events: list[dict] | None = None,
) -> list[str]:
    """Return 3-4 context-aware follow-up suggestions.

    Args:
        intent: Current message intent from classifier
        has_verified_order: Whether the customer has a verified order
        customer_phase: "pre-purchase" or "post-purchase"
        topic_tags: Topics already discussed in this session
        session_events: Session events (cards shown, verifications, etc.)
    """
    tags = set(topic_tags or [])
    events = session_events or []
    event_types = {e.get("type", "") for e in events}

    suggestions: list[str] = []

    # ── Post-purchase: order-focused suggestions ──
    if has_verified_order:
        if intent == "order_query":
            suggestions = _after_order_query(event_types)
        elif intent == "return_query":
            suggestions = _after_return_query(event_types)
        elif intent in ("product_query", "product_doc_query"):
            suggestions = _after_product_query_with_order()
        elif intent == "rag_query":
            suggestions = _after_rag_with_order(tags)
        else:
            suggestions = _default_post_purchase(tags)

    # ── Pre-purchase: browsing/research suggestions ──
    else:
        if intent in ("product_query", "product_doc_query"):
            suggestions = _after_product_query_browsing(tags)
        elif intent == "rag_query":
            suggestions = _after_rag_browsing(tags)
        elif intent == "direct":
            suggestions = _default_pre_purchase(tags)
        elif intent == "escalation":
            suggestions = ["Support kontaktieren", "Frage zum Produkt"]
        else:
            suggestions = _default_pre_purchase(tags)

    # Deduplicate and cap at 4
    seen = set()
    unique = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique[:4]


# ── Post-purchase suggestion sets ──

def _after_order_query(event_types: set) -> list[str]:
    base = []
    if "product_card_shown" not in event_types:
        base.append("Rechnung anfordern")
    base.extend(["Lieferstatus prüfen", "Retoure starten"])
    if "ticket_created" not in event_types:
        base.append("Support kontaktieren")
    return base


def _after_return_query(event_types: set) -> list[str]:
    return [
        "Wie ist der Rücksendeablauf?",
        "Erstattung prüfen",
        "Support kontaktieren",
        "Andere Bestellung prüfen",
    ]


def _after_product_query_with_order() -> list[str]:
    return [
        "Versandkosten & Lieferzeit",
        "Fahrzeug-Kompatibilitätscheck",
        "Bestellstatus prüfen",
        "Wie ist das Rückgaberecht?",
    ]


def _default_post_purchase(tags: set) -> list[str]:
    suggestions = ["Lieferstatus prüfen"]
    if "returns" not in tags:
        suggestions.append("Retoure / Erstattung")
    suggestions.append("Rechnung anfordern")
    suggestions.append("Support kontaktieren")
    return suggestions


# ── Pre-purchase suggestion sets ──

def _after_product_query_browsing(tags: set) -> list[str]:
    suggestions = []
    suggestions.append("Versandkosten & Lieferzeit")
    suggestions.append("Fahrzeug-Kompatibilitätscheck")
    if "returns" not in tags:
        suggestions.append("Wie ist das Rückgaberecht?")
    suggestions.append("Anderes Produkt suchen")
    return suggestions


def _after_rag_browsing(tags: set) -> list[str]:
    suggestions = []
    if "product_help" not in tags:
        suggestions.append("Produktsuche")
    suggestions.append("Versandkosten & Lieferzeit")
    if "returns" not in tags:
        suggestions.append("Wie ist das Rückgaberecht?")
    suggestions.append("Noch eine Frage")
    return suggestions


def _default_pre_purchase(tags: set) -> list[str]:
    suggestions = []
    if "product_help" not in tags:
        suggestions.append("Produktsuche")
    suggestions.append("Versandkosten & Lieferzeit")
    suggestions.append("Wie ist das Rückgaberecht?")
    suggestions.append("Fahrzeug-Kompatibilitätscheck")
    return suggestions
