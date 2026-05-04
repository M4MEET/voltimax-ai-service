"""Semantic cache — avoids repeated LLM calls for semantically identical queries.

Two cache layers:
1. Embedding cache: query text → embedding vector (avoids OpenAI embedding calls)
2. Response cache: query embedding → (rag_context, llm_response) for cacheable intents

Cacheable: rag_query, direct (general knowledge, policy questions)
Not cacheable: product_query, order_query, return_query, customer_query, etc.

Similarity threshold: 0.92 cosine — high enough to avoid false positives,
low enough to catch paraphrases ("return policy" ≈ "Rückgaberecht").

TTL: 24 hours — policy changes are monthly, cache refreshes daily.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

from langsmith import traceable

logger = logging.getLogger(__name__)

# Cache configuration
SIMILARITY_THRESHOLD = 0.85
CACHE_TTL_SECONDS = 86400  # 24 hours
MAX_CACHE_SIZE = 500       # max cached entries (LRU eviction)

# Intents whose responses are safe to cache (no personal/order data)
CACHEABLE_INTENTS = {"rag_query", "direct"}


@dataclass
class CacheEntry:
    query: str
    embedding: list[float]
    rag_context: str
    response: str
    intent: str
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > CACHE_TTL_SECONDS


class SemanticCache:
    """In-memory semantic cache using cosine similarity on embeddings."""

    def __init__(self):
        self._embedding_cache: dict[str, list[float]] = {}  # text → vector
        self._response_cache: list[CacheEntry] = []

    # ── Layer 1: Embedding cache ──

    def get_embedding(self, text: str) -> list[float] | None:
        """Return cached embedding for exact text match."""
        return self._embedding_cache.get(text)

    def put_embedding(self, text: str, vector: list[float]) -> None:
        """Cache an embedding vector for a text string."""
        self._embedding_cache[text] = vector
        # Evict oldest if too large
        if len(self._embedding_cache) > MAX_CACHE_SIZE * 2:
            keys = list(self._embedding_cache.keys())
            for k in keys[:len(keys) // 2]:
                del self._embedding_cache[k]

    # ── Layer 2: Response cache ──

    @traceable(name="groot-semantic-cache-lookup")
    def lookup(self, query_embedding: list[float], intent: str) -> dict:
        """Find a cached response for a semantically similar query.

        Only checks cache for cacheable intents.
        Returns dict with hit/miss info + similarity score for LangSmith tracing.
        """
        result = {
            "cache_hit": False,
            "similarity_score": 0.0,
            "cached_query": None,
            "intent": intent,
            "cacheable": intent in CACHEABLE_INTENTS,
            "cache_size": len(self._response_cache),
        }

        if intent not in CACHEABLE_INTENTS:
            return result

        best_entry: CacheEntry | None = None
        best_score = 0.0

        alive = []
        for entry in self._response_cache:
            if entry.is_expired():
                continue
            alive.append(entry)

            score = _cosine_similarity(query_embedding, entry.embedding)
            if score > best_score:
                best_score = score
                if score >= SIMILARITY_THRESHOLD:
                    best_entry = entry

        # Clean expired entries
        self._response_cache = alive

        result["similarity_score"] = round(best_score, 4)
        result["threshold"] = SIMILARITY_THRESHOLD

        if best_entry:
            result["cache_hit"] = True
            result["cached_query"] = best_entry.query
            result["cached_response_len"] = len(best_entry.response)
            logger.info(
                f"Semantic cache HIT: score={best_score:.3f} "
                f"cached_q={best_entry.query[:50]!r}"
            )

        return result

    def get_entry_from_lookup(self, lookup_result: dict) -> CacheEntry | None:
        """Get the actual CacheEntry from a lookup result."""
        if not lookup_result.get("cache_hit") or not lookup_result.get("cached_query"):
            return None
        for entry in self._response_cache:
            if entry.query == lookup_result["cached_query"] and not entry.is_expired():
                return entry
        return None

    def store(
        self,
        query: str,
        embedding: list[float],
        rag_context: str,
        response: str,
        intent: str,
    ) -> None:
        """Store a response in the semantic cache."""
        if intent not in CACHEABLE_INTENTS:
            return

        # Don't cache empty or very short responses
        if not response or len(response) < 20:
            return

        # Check if already cached (avoid duplicates)
        for entry in self._response_cache:
            if not entry.is_expired():
                score = _cosine_similarity(embedding, entry.embedding)
                if score >= SIMILARITY_THRESHOLD:
                    # Update existing entry with fresh response
                    entry.response = response
                    entry.rag_context = rag_context
                    entry.created_at = time.time()
                    return

        self._response_cache.append(CacheEntry(
            query=query,
            embedding=embedding,
            rag_context=rag_context,
            response=response,
            intent=intent,
        ))

        # Evict oldest if too large
        if len(self._response_cache) > MAX_CACHE_SIZE:
            self._response_cache = self._response_cache[-MAX_CACHE_SIZE:]

        logger.info(f"Semantic cache STORE: q={query[:50]!r} (total: {len(self._response_cache)})")

    def clear(self) -> int:
        """Clear all cached entries. Returns count of cleared entries."""
        count = len(self._response_cache) + len(self._embedding_cache)
        self._response_cache.clear()
        self._embedding_cache.clear()
        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        alive = [e for e in self._response_cache if not e.is_expired()]
        return {
            "embedding_cache_size": len(self._embedding_cache),
            "response_cache_size": len(alive),
            "total_entries": len(self._response_cache),
            "expired": len(self._response_cache) - len(alive),
        }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Singleton ──
_cache: SemanticCache | None = None


def get_semantic_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache
