from __future__ import annotations

from langgraph.graph import StateGraph, END

from app.ai.graph.state import ChatState
from app.ai.graph.nodes.intent_classifier import classify_intent
from app.ai.graph.nodes.data_fetcher import fetch_shopware_data
from app.ai.graph.nodes.rag_retriever import retrieve_knowledge
from app.ai.graph.nodes.response_generator import generate_response
from app.ai.graph.nodes.escalation_detector import detect_escalation


def build_chat_graph():
    """Build the LangGraph conversation flow."""
    graph = StateGraph(ChatState)

    # Add nodes
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("fetch_data", fetch_shopware_data)
    graph.add_node("retrieve_knowledge", retrieve_knowledge)
    graph.add_node("generate_response", generate_response)
    graph.add_node("detect_escalation", detect_escalation)

    # Entry point
    graph.set_entry_point("classify_intent")

    # Conditional routing after intent classification
    def route_after_intent(state: ChatState) -> str:
        if state.should_escalate:
            return "generate_response"  # Go straight to escalation response
        if state.needs_shopware_data:
            return "fetch_data"
        return "retrieve_knowledge"

    graph.add_conditional_edges(
        "classify_intent",
        route_after_intent,
        {
            "fetch_data": "fetch_data",
            "retrieve_knowledge": "retrieve_knowledge",
            "generate_response": "generate_response",
        },
    )

    # After fetching data, also check knowledge base
    graph.add_edge("fetch_data", "retrieve_knowledge")

    # After knowledge retrieval, generate response
    graph.add_edge("retrieve_knowledge", "generate_response")

    # After generating response, check for escalation
    graph.add_edge("generate_response", "detect_escalation")

    # End
    graph.add_edge("detect_escalation", END)

    return graph.compile()


# Compiled graph singleton
_chat_graph = None


def get_chat_graph():
    global _chat_graph
    if _chat_graph is None:
        _chat_graph = build_chat_graph()
    return _chat_graph
