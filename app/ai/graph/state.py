from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatState(BaseModel):
    """State passed through the LangGraph nodes."""

    # User input
    user_message: str = ""
    session: dict[str, Any] = {}
    user_claims: dict[str, Any] = {}
    history: list[dict[str, Any]] = []

    # Intent classification
    intent: str = ""  # "order_query", "product_query", "rag_query", "direct", "escalation"
    resolved_topic: str = ""  # auto-detected best topic_id for this message
    needs_shopware_data: bool = False
    data_type: str = ""  # "order", "product", "customer", "return", "b2b"
    search_query: str = ""  # extracted keywords for Shopware search (shorter than raw message)

    # Fetched context
    shopware_data: dict[str, Any] | None = None
    data_pre_fetched: bool = False  # skip data_fetcher when True
    rag_context: str = ""
    qa_match: str | None = None

    # Conversation summary — compressed older messages for long chats
    conversation_summary: str = ""

    # Card context — what cards will be shown alongside this response
    card_context: str = ""

    # Response
    response: str = ""
    system_prompt: str = ""
    tokens_used: int = 0

    # Escalation
    should_escalate: bool = False
    escalation_reason: str = ""
    frustration_score: float = 0.0

    # Pre-classified by unified classifier (skip intent classifier LLM call)
    pre_classified: bool = False

    # Provider
    llm_provider: str = "openai"

    # Language for AI responses ("auto" = detect from customer's messages)
    language: str = "auto"
