from __future__ import annotations

import json

from app.ai.graph.state import ChatState
from app.ai.prompt_hub import pull_system_prompt
from app.ai.router import get_provider

_FALLBACK_CLASSIFIER = """You are an intent classifier for a customer support chat.

Classify the user's message and respond with ONLY a JSON object (no markdown, no explanation):
{
  "intent": "<category>",
  "search_query": "<short keyword search term>"
}

Intent categories:
- order_query: Questions about order status, tracking, shipping, delivery
- return_query: Questions about returns, refunds, exchanges
- product_query: Questions about products, stock, availability, pricing, recommendations
- product_doc_query: Requesting a document, PDF, datasheet, manual, or technical specs for a SPECIFIC product
- customer_query: Questions about account, addresses, payment methods
- b2b_query: Questions about B2B quotes, employee accounts
- rag_query: General questions that might be answered from the knowledge base (policies, FAQ)
- direct: Simple greetings, thanks, or messages that need a direct response
- escalation: User is frustrated, asking for human agent, or the query is too complex

For search_query:
- product_query: Extract a product catalogue search term — product name, type, or specs.
  IMPORTANT: If the user mentions a vehicle (car model, year), extract the BATTERY TYPE they need (e.g. "Autobatterie", "Starterbatterie AGM"), NOT the car model. Car models are not in the product catalogue.
- product_doc_query: Extract ONLY the product name/model — strip words like "manual", "pdf", "download", "datenblatt", "datasheet", "anleitung", "handbuch", "dokument", "technische daten"
- order_query: Extract the order number if present (e.g. "10234"), otherwise empty string
- All other intents: empty string

Examples:
Message: "Ich suche eine Autobatterie für mein Auto"
→ {"intent": "product_query", "search_query": "Autobatterie"}

Message: "Batterie für Audi A4 2006 2.0 TFSI"
→ {"intent": "product_query", "search_query": "Autobatterie Starterbatterie"}

Message: "What battery for BMW 3 series 2010 diesel?"
→ {"intent": "product_query", "search_query": "Autobatterie Starterbatterie"}

Message: "Was ist der Status meiner Bestellung 10234?"
→ {"intent": "order_query", "search_query": "10234"}

Message: "Hallo, wie kann ich euch kontaktieren?"
→ {"intent": "direct", "search_query": ""}

Message: "Ich brauche einen NOQON NBS60 Ladebooster"
→ {"intent": "product_query", "search_query": "NOQON NBS60 Ladebooster"}

Message: "Haben Sie Varta AGM Batterien auf Lager?"
→ {"intent": "product_query", "search_query": "Varta AGM"}

Message: "PDF für Varta A7"
→ {"intent": "product_doc_query", "search_query": "Varta A7"}

Message: "Datenblatt Varta Silver Dynamic"
→ {"intent": "product_doc_query", "search_query": "Varta Silver Dynamic"}

Message: "I want to download the manual for NOQON NBS60"
→ {"intent": "product_doc_query", "search_query": "NOQON NBS60"}

FOLLOW-UP AWARENESS:
You will receive recent conversation history. If the customer's current message is a follow-up to a previous request, maintain the same intent category.
Examples:
- Previous: "PDF for Varta A7" (product_doc_query) → Current: "what about ea770?" → STILL product_doc_query, search_query: "EA770"
- Previous: "where is my order 12345?" (order_query) → Current: "and when will it arrive?" → STILL order_query
- Previous: product discussion → Current: "i want the manual for this" → product_doc_query"""


async def classify_intent(state: ChatState) -> ChatState:
    """Classify the user's intent and extract a clean search query in one LLM call."""
    # If the unified classifier already ran, all fields are set — skip the LLM call
    if state.pre_classified:
        return state

    provider = get_provider(state.llm_provider)

    # Try LangSmith Prompt Hub first, fall back to hardcoded
    classification_prompt = pull_system_prompt("groot-intent-classifier") or _FALLBACK_CLASSIFIER

    # Include recent conversation history so the LLM understands follow-ups
    # e.g. "pdf for varta a7" → "what about ea770?" should stay as product_doc_query
    messages = []
    for msg in state.history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": state.user_message})

    raw = await provider.generate(
        messages, system_prompt=classification_prompt, temperature=0.1, max_tokens=80
    )

    intent = "direct"
    search_query = ""
    try:
        # Strip markdown code fences if present (some models wrap JSON in ```json ... ```)
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```", 2)[1]
            if clean.startswith("json"):
                clean = clean[4:]
            clean = clean.rstrip("`").strip()
        parsed = json.loads(clean)
        intent = parsed.get("intent", "direct").strip().lower()
        search_query = parsed.get("search_query", "").strip()
    except (json.JSONDecodeError, AttributeError):
        # Fallback: treat the whole response as intent label (old format)
        intent = raw.strip().lower()

    # Map intent to data needs
    data_map: dict[str, tuple[str, bool]] = {
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

    # Auto-resolve the best specialized topic for this intent
    topic_map: dict[str, str] = {
        "product_query": "product_help",
        "product_doc_query": "product_help",
        "order_query": "order_status",
        "return_query": "returns",
        "customer_query": "general",
        "b2b_query": "general",
        "rag_query": "",      # keep current topic
        "direct": "",         # keep current topic
        "escalation": "",     # keep current topic
    }
    resolved = topic_map.get(intent, "")

    state.intent = intent
    state.resolved_topic = resolved
    state.needs_shopware_data = needs_data
    state.data_type = data_type
    state.search_query = search_query

    if intent == "escalation":
        state.should_escalate = True
        state.escalation_reason = "user_request"

    return state
