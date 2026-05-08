from __future__ import annotations

import json

from langsmith import traceable

from app.ai.agents import get_agent_system_prefix
from app.ai.shop_context import SHOP_CONTEXT
from app.ai.prompt_hub import pull_system_prompt, render_prompt
from app.ai.graph.state import ChatState
from app.config import get_config


def _format_order(order: dict) -> str:
    if not order:
        return ""
    lines = [f"Order #{order.get('orderNumber', 'unknown')}"]
    status = order.get("statusLabel") or order.get("status") or order.get("stateName")
    if status:
        lines.append(f"  Status: {status}")
    date = order.get("orderDate") or order.get("orderDateTime")
    if date:
        lines.append(f"  Ordered: {str(date)[:10]}")
    total = order.get("totalAmount") or order.get("amountTotal")
    if total:
        currency = order.get("currency") or order.get("currencyIsoCode", "EUR")
        lines.append(f"  Total: {total} {currency}")
    # Payment status
    payment = order.get("paymentStatus")
    if payment:
        payment_labels = {
            "paid": "Paid", "open": "Payment pending", "cancelled": "Payment cancelled",
            "refunded": "Fully refunded", "refunded_partially": "Partially refunded",
            "paid_partially": "Partially paid", "failed": "Payment failed",
            "reminded": "Payment reminder sent", "authorized": "Payment authorized",
        }
        lines.append(f"  Payment: {payment_labels.get(payment, payment)}")

    # Deliveries with status
    for i, delivery in enumerate(order.get("deliveries", [])):
        prefix = f"  Delivery {i+1}:" if len(order.get("deliveries", [])) > 1 else "  Delivery:"
        delivery_status = delivery.get("deliveryStatus") or delivery.get("deliveryStateName")
        delivery_label = delivery.get("deliveryStatusLabel")

        status_info = {
            "open": "Not yet shipped — order is being prepared",
            "shipped": "Shipped — package is on its way",
            "shipped_partially": "Partially shipped — some items sent, rest pending",
            "returned": "Returned — full return received",
            "returned_partially": "Partially returned — some items returned",
            "cancelled": "Delivery cancelled",
        }

        if delivery_status:
            detail = status_info.get(delivery_status, delivery_label or delivery_status)
            lines.append(f"{prefix} {detail}")

        if delivery.get("shippingMethod"):
            lines.append(f"  Carrier: {delivery['shippingMethod']}")
        if delivery.get("shippingDate"):
            lines.append(f"  Ship date: {delivery['shippingDate']}")
        if delivery.get("trackingCodes"):
            codes = delivery["trackingCodes"]
            codes_str = ", ".join(codes) if isinstance(codes, list) else codes
            if codes_str:
                lines.append(f"  Tracking: {codes_str}")
    if order.get("lineItems"):
        lines.append("  Items:")
        for item in order["lineItems"][:5]:
            lines.append(f"    - {item.get('label', '?')} x{item.get('quantity', 1)}")
    return "\n".join(lines)


def _format_orders(orders: list) -> str:
    if not orders:
        return "No orders found."
    formatted = []
    for o in orders[:5]:
        formatted.append(_format_order(o))
    return "\n\n".join(formatted)


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    import re
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def _format_product(product: dict) -> str:
    if not product:
        return ""
    lines = [product.get("name", "Unknown product")]

    # Manufacturer: Store API nests it as object, plugin API returns flat string
    manufacturer = product.get("manufacturer")
    if isinstance(manufacturer, dict):
        manufacturer = manufacturer.get("name") or manufacturer.get("translated", {}).get("name")
    if manufacturer:
        lines.append(f"  Manufacturer: {manufacturer}")

    if product.get("productNumber"):
        lines.append(f"  Product #: {product['productNumber']}")

    # Price: Store API uses calculatedPrice.totalPrice (VAT included), plugin API uses flat price
    calculated = product.get("calculatedPrice")
    if calculated and isinstance(calculated, dict):
        lines.append(f"  Price: {calculated.get('totalPrice')} EUR (incl. VAT)")
    elif product.get("price") is not None:
        lines.append(f"  Price: {product['price']} EUR")

    stock = product.get("stock") or 0
    is_available = product.get("available", stock > 0)
    lines.append(f"  Availability: {'available' if is_available else 'out of stock'}")

    # Real delivery time based on stock + availability
    from app.ai.card_builder import get_real_delivery_label
    delivery_label = get_real_delivery_label(product)
    if delivery_label:
        lines.append(f"  Delivery time: {delivery_label}")

    # Essential properties (from Shopware property groups)
    props = product.get("properties", {})
    if props and isinstance(props, dict):
        for group_name, value in props.items():
            lines.append(f"  {group_name}: {value}")

    # Product link — construct from product ID
    product_id = product.get("id", "")
    if product_id:
        lines.append(f"  Link: https://voltimax.de/detail/{product_id}")

    if product.get("description"):
        desc = _strip_html(product["description"])[:300]
        if desc:
            lines.append(f"  Specs: {desc}")
    return "\n".join(lines)


def _format_shopware_data(data: dict, intent: str) -> str:
    if not data:
        return ""

    parts = []

    if "order_not_owned" in data:
        parts.append(
            f"SECURITY: Order #{data['order_not_owned']} was requested but is NOT on this customer's account. "
            f"Tell the customer this order number cannot be found on their account. "
            f"Do NOT reveal any information about this order or who it belongs to."
        )

    if "order" in data and data["order"]:
        parts.append("SPECIFIC ORDER:\n" + _format_order(data["order"]))

    if "orders" in data and data["orders"]:
        orders = data["orders"]
        if isinstance(orders, list):
            parts.append(f"CUSTOMER ORDERS ({len(orders)} total):\n" + _format_orders(orders))

    if "return_status" in data and data["return_status"]:
        r = data["return_status"]
        parts.append(f"RETURN STATUS:\n{json.dumps(r, default=str)}")

    if "search_results" in data and data["search_results"]:
        results = data["search_results"]
        if isinstance(results, list) and results:
            formatted = [_format_product(p) for p in results[:4] if p]
            parts.append("MATCHING PRODUCTS:\n" + "\n\n".join(formatted))

    if "customer" in data and data["customer"]:
        c = data["customer"]
        customer_lines = []
        if c.get("firstName") or c.get("lastName"):
            customer_lines.append(f"Name: {c.get('firstName', '')} {c.get('lastName', '')}".strip())
        if c.get("email"):
            customer_lines.append(f"Email: {c['email']}")
        if c.get("customerNumber"):
            customer_lines.append(f"Customer #: {c['customerNumber']}")
        if customer_lines:
            parts.append("CUSTOMER ACCOUNT:\n" + "\n".join(customer_lines))

    if "addresses" in data and data["addresses"]:
        addrs = data["addresses"]
        if isinstance(addrs, list) and addrs:
            addr_lines = []
            for a in addrs[:3]:
                addr_lines.append(f"  - {a.get('street', '')} {a.get('zipcode', '')} {a.get('city', '')}".strip())
            parts.append("SAVED ADDRESSES:\n" + "\n".join(addr_lines))

    if "quotes" in data and data["quotes"]:
        parts.append(f"B2B QUOTES:\n{json.dumps(data['quotes'], default=str)[:500]}")

    if "cheaper_alternatives" in data and data["cheaper_alternatives"]:
        alt_lines = []
        for pid, alt in data["cheaper_alternatives"].items():
            alt_name = alt.get("name", "Unknown")
            alt_price = alt.get("price", 0)
            orig_price = alt.get("originalPrice", 0)
            savings = alt.get("savings", 0)
            matched = alt.get("matchedProperties", [])
            matched_str = ", ".join(matched) if matched else "key properties"
            alt_lines.append(
                f"  - {alt_name}: {alt_price:.2f} EUR (vs {orig_price:.2f} EUR — {savings}% günstiger)"
                f"\n    Matched on: {matched_str}"
            )
        parts.append(
            f"CHEAPER ALTERNATIVES shown in the product card:\n"
            + "\n".join(alt_lines) + "\n"
            "IMPORTANT: These alternatives were matched by our comparison system. The 'Matched on' line above "
            "shows EXACTLY which properties are identical between the products. The difference is only the brand "
            "and price — the alternative is a more affordable option.\n"
            "When a customer asks about the difference: mention the matched properties by name and say both "
            "products share those specs, the alternative is simply cheaper. NEVER invent differences "
            "or fabricate specs you don't have data for.\n"
            "Briefly mention that cheaper alternatives are shown as green cards in the product overview."
        )

    return "\n\n".join(parts) if parts else ""


def _get_intent_guidance(intent: str, topic_id: str) -> str:
    guidance = {
        "order_query": (
            "The customer is asking about an order. "
            "Use ONLY the order data in SHOP DATA. NEVER fabricate data. "
            "If no SHOP DATA, tell them to verify their order first. "
            "Explain the order status clearly based on the delivery status: "
            "- 'open' / Not shipped = order is being prepared/packed "
            "- 'shipped' = package sent, provide tracking link "
            "- 'shipped_partially' = some items shipped, rest is being prepared. Show which tracking is available "
            "- 'returned' = customer returned the order, refund is being processed "
            "- 'returned_partially' = some items returned "
            "- 'cancelled' = delivery was cancelled "
            "Also mention payment status if relevant (refunded, partially refunded, etc.). "
            "Format tracking codes as clickable links: "
            "DHL: [code](https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?lang=de&idc=code) "
            "DPD: [code](https://tracking.dpd.de/status/de_DE/parcel/code) "
            "UPS: [code](https://www.ups.com/track?tracknum=code) "
            "Keep it short and structured."
        ),
        "return_query": (
            "The customer wants to return or get a refund. "
            "Be empathetic and guide them through the return process step by step. "
            "Reference the specific order if available. "
            "Explain what information they need to provide."
        ),
        "product_query": (
            "Lead immediately with matching products from the SHOP DATA. "
            "For each product: name, price, one short sentence on why it suits the customer's need. Maximum 3-4 products. "
            "Only list products that exist in the SHOP DATA — never invent or guess products. "
            "You MAY use general automotive/technical knowledge (e.g. required battery capacity for an engine size) "
            "to explain why a specific product is a good match — but only recommend products that are actually in the SHOP DATA. "
            "If the customer asks about vehicle compatibility, use the battery specs from the product names (Ah, V) "
            "together with your knowledge of typical requirements for their engine type and size. "
            "After the list, ask at most ONE follow-up question if truly needed."
        ),
        "product_doc_query": (
            "The customer wants to download a document (datasheet, manual, PDF) for a specific product. "
            "Keep your response SHORT — just confirm which product document you found. "
            "Say something like: 'Hier ist das Datenblatt für [product]. Du kannst es unten herunterladen.' "
            "or 'Das Dokument für [product] findest du im Download-Bereich unten.' "
            "Do NOT list product specs or prices — the customer wants the document, not a product recommendation. "
            "A download card will appear automatically below your message — just point to it. "
            "If no document is available, say so and suggest checking the product page on voltimax.de."
        ),
        "customer_query": (
            "The customer is asking about their account. "
            "Use the customer data above to provide accurate, personalized information. "
            "Be careful with sensitive data — only confirm what the customer is asking about."
        ),
        "b2b_query": (
            "This is a B2B customer. "
            "Be professional and business-focused. "
            "Reference their quotes or account details if available."
        ),
        "rag_query": (
            "Answer using the KNOWLEDGE BASE context above in 2-3 sentences MAX. "
            "State the key facts directly — no bullet points, no numbered lists, no sections, "
            "unless the customer explicitly asks for details or a breakdown. "
            "Quote the KB accurately — do NOT oversimplify in a way that changes the meaning. "
            "For example, if the KB says 'Prüfung der Beschaffenheit ist zulässig', do NOT say 'unbenutzt'. "
            "Do NOT add filler like 'Kann ich dir noch helfen?' — the system handles follow-ups automatically. "
            "Do NOT add emojis to policy answers. "
            "If the knowledge base doesn't cover this topic, say so briefly."
        ),
        "direct": (
            "Respond naturally and helpfully in 1-2 sentences. "
            "Be warm and conversational. No filler questions at the end."
        ),
    }
    return guidance.get(intent, guidance.get(topic_id, "Be helpful, accurate, and concise."))


@traceable(name="groot-response-generator")
async def generate_response(state: ChatState) -> ChatState:
    """Build the system prompt with full context — engine streams the final response."""
    config = get_config()

    if state.should_escalate:
        state.response = (
            "I understand this is frustrating. "
            "Would you like to contact our support team directly?"
        )
        return state

    if state.qa_match:
        state.response = state.qa_match
        return state

    # Customer identity
    customer_name = state.user_claims.get("name", "")
    customer_email = state.user_claims.get("email", "")
    has_orders = state.user_claims.get("has_orders", False)
    is_b2b = state.user_claims.get("is_b2b", False)
    # Use auto-resolved topic if available, otherwise fall back to session topic
    topic_id = state.resolved_topic or state.session.get("topic_id", "") or "general"

    # Prepare variables for mustache rendering
    order_email = state.session.get("order_email") or ""
    is_order_topic = topic_id in ("order_status", "returns", "order_issue")
    shop_data_str = ""
    if state.shopware_data:
        shop_data_str = _format_shopware_data(state.shopware_data, state.intent)

    guidance = _get_intent_guidance(state.intent, topic_id)

    # ── Determine customer phase: pre-purchase vs post-purchase ──
    has_verified_order = bool(state.session.get("order_number"))
    post_purchase_intents = {"order_query", "return_query"}
    post_purchase_topics = {"order_status", "returns", "order_issue"}

    if has_verified_order or state.intent in post_purchase_intents or topic_id in post_purchase_topics:
        customer_phase = "post-purchase"
        phase_guidance = (
            "CUSTOMER PHASE: POST-PURCHASE — This customer has an existing order. "
            "Be solution-oriented: help resolve issues, offer ticket creation, track shipments. "
            "Proactively offer to create support tickets when the issue needs human follow-up."
        )
    else:
        customer_phase = "pre-purchase"
        phase_guidance = (
            "CUSTOMER PHASE: PRE-PURCHASE — This customer is browsing, researching, or asking general questions. "
            "They have NOT placed an order yet. Be informative and helpful — guide them toward a purchase decision. "
            "Answer policy questions (shipping, returns) factually and briefly — they are evaluating before buying. "
            "Do NOT proactively push support tickets or order-related actions. "
            "BUT if the customer wants more details or personal help, gently offer options: "
            "'Falls du weitere Fragen hast, kannst du uns auch per E-Mail (info@voltimax.de), Telefon (089 54196384) erreichen — oder ich erstelle ein Support-Ticket für dich.' "
            "If they explicitly ask for support or a ticket, create it immediately."
        )

    # When a card is shown, override verbose guidance with short intro instructions
    if state.card_context and state.intent in ("product_query", "product_doc_query"):
        guidance = (
            "A PRODUCT CARD is shown below your message with full details (names, prices, specs, links). "
            "Do NOT list products in your text — the card already has everything. "
            "Write 1-2 sentences MAX: briefly introduce what you found and point to the card. "
            "Example: 'Hier sind passende Varta Batterien — schau dir die Optionen in der Übersicht an!'"
        )

    # Format session events into a brief activity log for the AI
    events = state.session.get("events") or []
    session_activity = ""
    if events:
        lines = []
        for ev in events[-10:]:  # last 10 events max
            lines.append(f"[{ev.get('ts', '')}] {ev.get('type', '')}: {ev.get('detail', '')}")
        session_activity = "\n".join(lines)

    mustache_vars = {
        "agent_prefix": get_agent_system_prefix(topic_id),
        "is_first_message": len(state.history) == 0,
        "customer_name": customer_name,
        "customer_email": order_email or customer_email,
        "order_email": order_email if order_email and order_email != customer_email else "",
        "topic_id": topic_id,
        "is_order_topic": is_order_topic,
        "customer_phase": phase_guidance,
        "shop_data": shop_data_str,
        "rag_context": state.rag_context or "",
        "instructions": guidance,
        "conversation_summary": state.conversation_summary,
        "session_activity": session_activity,
        "card_context": state.card_context,
        "is_clarification": state.card_context == "ASK_CLARIFICATION",
    }

    # Try LangSmith Prompt Hub with mustache rendering
    rendered = render_prompt("groot-system-prompt", mustache_vars)

    if rendered:
        state.system_prompt = rendered
    else:
        # Fallback: build hardcoded prompt
        parts = [
            "You are Groot, a specialised AI customer support assistant for Voltimax (voltimax.de). "
            "When customers ask your name, say 'I'm Groot'.",
            get_agent_system_prefix(topic_id),
            "LANGUAGE: Respond in the SAME language the customer writes in.",
            "Keep responses under 150 words. Be direct.",
            "CONFIRMATION RULE: For irreversible actions, summarize and ask to confirm.",
            "ORDER SECURITY: Never fabricate order data. If no SHOP DATA below, direct to verification form.",
            SHOP_CONTEXT,
        ]

        if customer_name:
            parts.append(f"CUSTOMER: {customer_name} ({order_email or customer_email})")
        parts.append(phase_guidance)
        if topic_id:
            parts.append(f"TOPIC: {topic_id}")
        if shop_data_str:
            parts.append(f"SHOP DATA:\n{shop_data_str}")
        if state.rag_context:
            parts.append(f"KNOWLEDGE BASE:\n{state.rag_context}")
        if state.conversation_summary:
            parts.append(f"CONVERSATION SUMMARY (earlier messages compressed — use this context to maintain continuity):\n{state.conversation_summary}")
        if session_activity:
            parts.append(f"SESSION ACTIVITY (what happened so far in this session — cards shown, verifications, actions):\n{session_activity}")
        if state.card_context == "ASK_CLARIFICATION":
            parts.append(
                "CLARIFICATION NEEDED: The customer's message is vague or ambiguous. "
                "Ask a friendly, specific follow-up question to understand what they need. "
                "Offer 2-3 concrete options they can pick from. "
                "Example: 'Meinst du...? Ich kann dir bei folgenden Themen helfen: ...' "
                "Keep it short — 1-2 sentences max."
            )
        elif state.card_context:
            parts.append(f"CARDS SHOWN WITH THIS RESPONSE (the customer can see these interactive cards below your message — reference them, don't repeat their data):\n{state.card_context}")
        parts.append(f"INSTRUCTIONS: {guidance}")

        state.system_prompt = "\n\n".join(parts)

    return state
