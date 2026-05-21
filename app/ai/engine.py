from __future__ import annotations

from typing import AsyncIterator

from langsmith import traceable

from app.ai.graph.chat_graph import get_chat_graph
from app.ai.graph.state import ChatState
from app.ai.router import get_provider


class AIEngine:
    """Main AI orchestrator. Processes messages through LangGraph and streams responses."""

    async def process_message(
        self,
        message: str,
        session: dict,
        history: list[dict],
        user_claims: dict,
        language: str = "auto",
        classification: dict | None = None,
        pre_fetched_shopware: dict | None = None,
    ) -> AsyncIterator[dict]:
        """Process a user message and yield response chunks.

        If *classification* is provided (from unified classifier), its fields
        are injected into ChatState so the intent_classifier node skips the LLM call.

        If *pre_fetched_shopware* is provided, data_fetcher skips its fetch
        and the AI knows a card is coming (writes a short intro instead of listing products).
        """

        from app.ai.router import get_default_provider
        llm_provider = session.get("llm_provider") or get_default_provider()

        # Summarize older messages for long conversations
        from app.ai.conversation_summarizer import summarize_if_needed
        conv_summary, recent_history = await summarize_if_needed(
            history, session, llm_provider,
        )

        state = ChatState(
            user_message=message,
            session=session,
            user_claims=user_claims,
            history=history,
            llm_provider=llm_provider,
            language=language,
            conversation_summary=conv_summary,
        )

        # Inject pre-classified results so intent_classifier node is a no-op
        if classification:
            state.pre_classified = True
            state.intent = classification.get("intent", "direct")
            state.search_query = classification.get("search_query", "")
            state.resolved_topic = classification.get("resolved_topic", "")
            state.data_type = classification.get("data_type", "")
            state.needs_shopware_data = classification.get("needs_shopware_data", False)
            state.should_escalate = classification.get("should_escalate", False)
            if state.should_escalate:
                state.escalation_reason = "user_request"
            if classification.get("card_context"):
                state.card_context = classification["card_context"]

        # Inject pre-fetched Shopware data so data_fetcher skips its fetch
        if pre_fetched_shopware:
            state.shopware_data = pre_fetched_shopware
            state.data_pre_fetched = True

        # Run through LangGraph — this classifies intent, fetches data, retrieves RAG context
        graph = get_chat_graph()
        result = await graph.ainvoke(state.model_dump())
        final_state = ChatState(**result)

        # Always yield the classified intent so connection handler can act on it
        yield {
            "type": "intent",
            "intent": final_state.intent,
        }

        # Auto-switch topic based on intent + accumulate topic tags
        if final_state.resolved_topic:
            yield {
                "type": "topic_switch",
                "topic_id": final_state.resolved_topic,
                "intent": final_state.intent,
            }

        # Escalation — do not stream, return escalation event
        if final_state.should_escalate:
            fallback_escalation = (
                "I understand this is a complex situation. "
                "Would you like to contact our support team?"
            )
            yield {
                "type": "escalation",
                "message": final_state.response or fallback_escalation,
                "reason": final_state.escalation_reason,
            }
            return

        # Q&A exact match — stream the pre-built answer directly, no second LLM call
        if final_state.qa_match:
            for word in final_state.qa_match.split(" "):
                yield {"type": "token", "content": word + " "}
            return

        # ── Semantic cache: check for cached response to similar query ──
        from app.ai.semantic_cache import get_semantic_cache
        _sem_cache = get_semantic_cache()
        _query_embedding = _sem_cache.get_embedding(message)
        if _query_embedding is None:
            from app.knowledge.embedder import get_embeddings
            _query_embedding = await get_embeddings().aembed_query(message)
            _sem_cache.put_embedding(message, _query_embedding)

        _cache_result = _sem_cache.lookup(_query_embedding, final_state.intent)
        _cache_entry = _sem_cache.get_entry_from_lookup(_cache_result)
        if _cache_entry:
            # Cache hit — stream the cached response directly, no LLM call
            yield {"type": "cache_hit", "cached_query": _cache_entry.query, "similarity": _cache_result["similarity_score"]}
            for word in _cache_entry.response.split(" "):
                yield {"type": "token", "content": word + " "}
            return

        # Stream the response that was built in response_generator using the provider
        # We re-stream using generate_stream so the browser sees token-by-token output.
        # The system prompt and messages are passed from the final state so context is preserved.
        provider = get_provider(llm_provider)

        # Use recent_history (trimmed by summarizer) instead of full history
        messages = []
        for msg in recent_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": message})

        lc_messages = provider._to_langchain_messages(messages, final_state.system_prompt)

        # Stream with LangSmith metadata for tracing
        # Include session events so they appear in LangSmith traces for debugging
        events_summary = []
        for ev in (session.get("events") or [])[-10:]:
            events_summary.append(f"{ev.get('ts','')} {ev.get('type','')}: {ev.get('detail','')}")

        active_topic = final_state.resolved_topic or session.get("topic_id", "general")
        chat_id = session.get("chat_id") or session.get("id", "")
        config = {
            "metadata": {
                "session_id": session.get("id", ""),
                "chat_id": chat_id,
                "topic_id": active_topic,
                "topic_tags": session.get("topic_tags", []),
                "customer_email": user_claims.get("email", ""),
                "intent": final_state.intent,
                "llm_provider": llm_provider,
                "order_number": session.get("order_number", ""),
                "session_events": events_summary,
            },
            "tags": ["groot-chat", f"session:{chat_id}", f"topic:{active_topic}"],
            "configurable": {"thread_id": chat_id},
        }

        run_id = None
        _full_response_for_cache = ""
        async for event in provider.model.astream_events(
            lc_messages, config=config, version="v2",
        ):
            kind = event.get("event", "")
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield {"type": "token", "content": chunk.content}
                    _full_response_for_cache += chunk.content
            elif kind == "on_chat_model_start":
                run_id = event.get("run_id")

        # Store in semantic cache for future similar queries
        if _full_response_for_cache and _query_embedding:
            _sem_cache.store(
                query=message,
                embedding=_query_embedding,
                rag_context=final_state.rag_context or "",
                response=_full_response_for_cache,
                intent=final_state.intent,
            )

        # Yield run_id so connection handler can store it with the message
        if run_id:
            yield {"type": "run_id", "run_id": run_id}

        # Yield product search results so connection handler can build a product card
        # Skip when pre-fetched — connection handler already has the data
        if not final_state.data_pre_fetched and final_state.shopware_data and final_state.shopware_data.get("search_results"):
            yield {
                "type": "product_results",
                "products": final_state.shopware_data["search_results"],
            }
