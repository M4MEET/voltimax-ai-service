from __future__ import annotations

import logging

from langsmith import traceable

from app.ai.graph.state import ChatState

logger = logging.getLogger(__name__)

# Top-match score below which a knowledge question counts as a "gap".
# NOTE: production uses atlas-local $vectorSearch (cosine → ~0.5-1.0 range),
# so this threshold is tuned for that scale.
RAG_CONFIDENCE_THRESHOLD = 0.72


async def _log_rag_gap(state: ChatState, top_score: float, doc_count: int) -> None:
    """Record a knowledge-base gap so the team knows what content to add."""
    try:
        from datetime import datetime, timezone
        from app.db.collections import rag_gaps_collection

        session = state.session or {}
        await rag_gaps_collection().insert_one({
            "query": state.user_message,
            "intent": state.intent,
            "top_score": round(top_score, 4),
            "doc_count": doc_count,
            "session_id": session.get("id", ""),
            "chat_id": session.get("chat_id", ""),
            "created_at": datetime.now(timezone.utc),
        })
        logger.info(f"RAG gap logged: q={state.user_message[:60]!r} top_score={top_score:.3f} docs={doc_count}")
    except Exception:
        pass  # Gap logging must never break the chat


@traceable(name="groot-rag-retriever")
async def retrieve_knowledge(state: ChatState) -> ChatState:
    """Retrieve relevant context from the knowledge base.

    Q&A pairs are always checked — they're fast and provide exact answers.
    RAG retrieval runs for all intents so policy content (return address,
    shipping info, etc.) can supplement order/return data from Shopware.

    For knowledge questions (rag_query), an empty or low-confidence retrieval
    is logged as a "gap" — these are the questions Groot can't answer well,
    and directly tell the team what KB content or Q&A pairs to add.
    """
    try:
        from app.knowledge.vector_store import VectorStore

        store = VectorStore()

        # Q&A: exact/near-match check — always run, highest priority
        qa_match = await store.find_qa_match(state.user_message)
        if qa_match:
            state.qa_match = qa_match
            return state

        # RAG: fetch policy/procedural context for all intents.
        # Use more results for knowledge-heavy intents (rag_query, return_query)
        # to ensure important policy details aren't cut off by vector ranking.
        if state.intent in ("rag_query", "return_query", "direct"):
            top_k = 5
        else:
            top_k = 3
        docs = await store.search(state.user_message, top_k=top_k)
        if docs:
            state.rag_context = "\n\n".join([doc["content"] for doc in docs])

        # Track knowledge gaps for genuine FAQ/policy questions only.
        if state.intent == "rag_query":
            top_score = docs[0].get("score", 0.0) if docs else 0.0
            if not docs or top_score < RAG_CONFIDENCE_THRESHOLD:
                await _log_rag_gap(state, top_score, len(docs))
    except Exception:
        pass  # Knowledge base may not be configured yet

    return state
