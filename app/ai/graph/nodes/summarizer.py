from __future__ import annotations

from app.ai.prompt_hub import pull_system_prompt
from app.ai.router import get_provider

_FALLBACK_SUMMARIZER = """Summarize this customer support conversation concisely.
Include:
- What the customer asked about
- What was resolved (if anything)
- Why escalation was needed
- Any important details (order numbers, product names, etc.)
- Reference verified order data if provided (order number, status, items, tracking)

Keep it under 200 words."""


async def summarize_conversation(
    session_id: str,
    history: list[dict],
    llm_provider: str,
    order_data: dict | None = None,
    session_events: list[dict] | None = None,
) -> str:
    """Summarize a conversation for ticket creation.

    Includes order context and session events so the summary is complete.
    """
    provider = get_provider(llm_provider)

    system_prompt = pull_system_prompt("groot-summarizer") or _FALLBACK_SUMMARIZER

    # Build context: chat history + order data + session events
    parts = []

    if order_data:
        order_lines = [f"Verified Order #{order_data.get('orderNumber', '?')}"]
        status = order_data.get("statusLabel") or order_data.get("status", "")
        if status:
            order_lines.append(f"  Status: {status}")
        payment = order_data.get("paymentStatus", "")
        if payment:
            order_lines.append(f"  Payment: {payment}")
        total = order_data.get("amountTotal") or order_data.get("totalAmount")
        if total:
            order_lines.append(f"  Total: {total} EUR")
        for delivery in order_data.get("deliveries", []):
            d_status = delivery.get("deliveryStatus", "")
            carrier = delivery.get("shippingMethod", "")
            codes = delivery.get("trackingCodes", [])
            if d_status:
                order_lines.append(f"  Delivery: {d_status} via {carrier}")
            if codes:
                order_lines.append(f"  Tracking: {', '.join(codes)}")
        for item in order_data.get("lineItems", [])[:5]:
            order_lines.append(f"  Item: {item.get('label', '?')} x{item.get('quantity', 1)}")
        parts.append("ORDER DATA:\n" + "\n".join(order_lines))

    if session_events:
        event_lines = []
        for ev in session_events[-10:]:
            event_lines.append(f"[{ev.get('ts', '')}] {ev.get('type', '')}: {ev.get('detail', '')}")
        parts.append("SESSION EVENTS:\n" + "\n".join(event_lines))

    history_text = "\n".join([
        f"{'Customer' if msg['role'] == 'user' else 'AI'}: {msg['content']}"
        for msg in history
    ])
    parts.append("CONVERSATION:\n" + history_text)

    messages = [{"role": "user", "content": "\n\n".join(parts)}]
    return await provider.generate(messages, system_prompt=system_prompt, max_tokens=300)
