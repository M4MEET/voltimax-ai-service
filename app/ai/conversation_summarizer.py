"""Conversation summarizer — compresses older messages for long chats.

When a conversation exceeds SUMMARIZE_THRESHOLD messages, older messages
are summarized into a compact paragraph. The summary is cached on the
session document in MongoDB and refreshed when enough new messages accumulate.

The summary is injected into the system prompt so the AI maintains full
conversational continuity without sending all messages to the context window.
"""
from __future__ import annotations

import logging

from langsmith import traceable

from app.ai.router import get_provider, get_default_provider

logger = logging.getLogger(__name__)

SUMMARIZE_THRESHOLD = 12   # start summarizing after this many messages
RECENT_WINDOW = 6          # keep this many recent messages verbatim
REFRESH_INTERVAL = 6       # re-summarize after this many new messages beyond cache

_SUMMARY_PROMPT = """\
Summarize this customer support conversation into a compact paragraph (max 100 words).
Preserve:
- What the customer asked about and wanted
- Key facts: order numbers, product names, ticket IDs, verification status
- What was resolved or what is still pending
- The customer's language (German, English, etc.)

This summary will be injected into the AI's context so it can continue the conversation naturally.
Write in third person ("The customer asked about...", "Order #12345 was verified...").
Do NOT include greetings or filler — only factual context the AI needs."""


@traceable(name="groot-conversation-summarizer")
async def summarize_if_needed(
    history: list[dict],
    session: dict,
    llm_provider: str | None = None,
) -> tuple[str, list[dict]]:
    """Return (summary, recent_messages) for the conversation.

    If history is short enough, returns ("", history) — no summarization.
    Otherwise returns a cached or freshly generated summary of older
    messages plus the most recent RECENT_WINDOW messages verbatim.
    """
    if len(history) <= SUMMARIZE_THRESHOLD:
        return "", history

    recent = history[-RECENT_WINDOW:]
    older = history[:-RECENT_WINDOW]

    # Check cached summary
    cached_summary = session.get("conversation_summary", "")
    summary_msg_count = session.get("summary_up_to", 0)

    new_msgs_since_summary = len(older) - summary_msg_count
    if cached_summary and new_msgs_since_summary < REFRESH_INTERVAL:
        return cached_summary, recent

    # Generate a fresh summary
    provider_name = llm_provider or get_default_provider()
    try:
        provider = get_provider(provider_name)

        conv_lines = []
        for msg in older:
            role = "Customer" if msg.get("role") == "user" else "Groot"
            content = (msg.get("content") or "")[:200]
            conv_lines.append(f"{role}: {content}")
        conversation_text = "\n".join(conv_lines)

        summary = await provider.generate(
            [{"role": "user", "content": f"{_SUMMARY_PROMPT}\n\nCONVERSATION:\n{conversation_text}"}],
            temperature=0,
            max_tokens=150,
        )
        summary = summary.strip()

        # Cache on session document
        try:
            from app.db.collections import sessions_collection
            from datetime import datetime

            await sessions_collection().update_one(
                {"id": session.get("id", "")},
                {"$set": {
                    "conversation_summary": summary,
                    "summary_up_to": len(older),
                    "updated_at": datetime.utcnow(),
                }},
            )
        except Exception as e:
            logger.warning(f"Failed to cache conversation summary: {e}")

        logger.info(f"Summarized {len(older)} msgs → {len(summary)} chars")
        return summary, recent

    except Exception as e:
        logger.warning(f"Summarization failed: {e}")
        return cached_summary or "", recent
