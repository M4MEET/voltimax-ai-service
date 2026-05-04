"""Fast pre-classification — determines if a message needs order verification
before the full LangGraph pipeline runs.

Uses a minimal LLM call (~200ms) instead of brittle keyword matching.
Results are used to intercept order-related messages and show the verify form.
Prompt is pulled from LangSmith Prompt Hub (groot-pre-classifier) with local fallback.
"""
from __future__ import annotations

import logging

from app.ai.prompt_hub import render_prompt
from app.ai.router import get_provider

logger = logging.getLogger(__name__)

_FALLBACK_PROMPT = """Classify this customer support message. Does the customer need access to a SPECIFIC existing order they placed? Respond with ONLY "order" or "other".

"order" = Any of these about THEIR order:
- Tracking, shipment status, where is my package, delivery update
- Return, exchange, refund, send back, Rücksendung, Erstattung
- Cancel order, modify order, change address on order, Stornierung
- Invoice, receipt, Rechnung, billing document, proof of purchase
- Order problem, wrong item, damaged, missing item, complaint about order
- Order status, order details, order history, order confirmation
- Warranty claim on ordered product
- Escalate, speak to someone about my order

"other" = General questions NOT about a specific order:
- Product questions, recommendations, stock availability
- General shipping/delivery times, shipping costs
- Payment methods, account settings
- Greetings, thanks, general chat
- Store policies, FAQ, general complaints not tied to an order

Message: "{{message}}"

Classification:"""


async def is_order_related(message: str, llm_provider: str = "anthropic") -> bool:
    """Quick LLM check: is this message about an existing order?

    Returns True if the message is order-related and needs verification.
    Fast: uses max_tokens=5, temperature=0 for deterministic single-word response.
    """
    try:
        provider = get_provider(llm_provider)
        variables = {"message": message}
        prompt_text = render_prompt("groot-pre-classifier", variables)
        if not prompt_text:
            import chevron
            prompt_text = chevron.render(_FALLBACK_PROMPT, variables)

        result = await provider.generate(
            [{"role": "user", "content": prompt_text}],
            temperature=0,
            max_tokens=5,
        )
        category = result.strip().lower().rstrip(".")
        return category == "order"
    except Exception as e:
        logger.warning(f"Pre-classification failed: {e}")
        return False
