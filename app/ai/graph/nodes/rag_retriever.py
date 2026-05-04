from __future__ import annotations

from langsmith import traceable

from app.ai.graph.state import ChatState


@traceable(name="groot-rag-retriever")
async def retrieve_knowledge(state: ChatState) -> ChatState:
    """Retrieve relevant context from the knowledge base.

    Q&A pairs are always checked — they're fast and provide exact answers.
    RAG retrieval runs for all intents so policy content (return address,
    shipping info, etc.) can supplement order/return data from Shopware.
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
    except Exception:
        pass  # Knowledge base may not be configured yet

    return state
