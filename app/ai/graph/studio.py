"""LangGraph Studio entry point — exposes the chat graph for visual debugging."""
from app.ai.graph.chat_graph import build_chat_graph

# LangGraph Studio needs a compiled graph at module level
graph = build_chat_graph()
