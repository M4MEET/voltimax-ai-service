from __future__ import annotations

import math
from datetime import datetime

from app.db.collections import knowledge_vectors_collection, qa_pairs_collection
from app.knowledge.embedder import get_embeddings


class VectorStore:
    """MongoDB-based vector store for the knowledge base."""

    def __init__(self):
        self.embeddings = get_embeddings()

    async def add_documents(
        self,
        chunks: list[str],
        source_id: str,
        source_type: str,
        metadata: dict | None = None,
    ) -> None:
        """Embed and store document chunks."""
        if not chunks:
            return

        vectors = await self.embeddings.aembed_documents(chunks)
        collection = knowledge_vectors_collection()

        docs = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            docs.append({
                "source_id": source_id,
                "source_type": source_type,
                "content": chunk,
                "embedding": vector,
                "chunk_index": i,
                "metadata": metadata or {},
                "created_at": datetime.utcnow(),
            })

        if docs:
            await collection.insert_many(docs)

    async def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Search for relevant documents using vector similarity."""
        from app.ai.semantic_cache import get_semantic_cache
        cache = get_semantic_cache()
        query_vector = cache.get_embedding(query)
        if query_vector is None:
            query_vector = await self.embeddings.aembed_query(query)
            cache.put_embedding(query, query_vector)
        collection = knowledge_vectors_collection()

        # Try MongoDB Atlas $vectorSearch first (atlas-local only)
        try:
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "embedding",
                        "queryVector": query_vector,
                        "numCandidates": top_k * 10,
                        "limit": top_k,
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "content": 1,
                        "source_type": 1,
                        "metadata": 1,
                        "score": {"$meta": "vectorSearchScore"},
                    }
                },
            ]
            results = []
            async for doc in collection.aggregate(pipeline):
                results.append(doc)
            if results:
                return results
        except Exception:
            pass

        # Fallback: Python-side cosine similarity (works with any MongoDB)
        return await self._python_vector_search(collection, query_vector, top_k)

    async def _python_vector_search(
        self, collection, query_vector: list[float], top_k: int
    ) -> list[dict]:
        """Fallback vector search using Python cosine similarity."""
        cursor = collection.find(
            {"embedding": {"$exists": True}},
            {"content": 1, "source_type": 1, "metadata": 1, "embedding": 1, "_id": 0},
        )
        docs = await cursor.to_list(length=5000)

        scored = []
        for doc in docs:
            score = self._cosine_similarity(query_vector, doc["embedding"])
            scored.append({
                "content": doc.get("content", ""),
                "source_type": doc.get("source_type", ""),
                "metadata": doc.get("metadata", {}),
                "score": score,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    async def find_qa_match(self, question: str, threshold: float = 0.85) -> str | None:
        """Find a matching Q&A pair using embedding similarity."""
        collection = qa_pairs_collection()
        cursor = collection.find({})
        qa_list = await cursor.to_list(length=1000)

        if not qa_list:
            return None

        from app.ai.semantic_cache import get_semantic_cache
        cache = get_semantic_cache()
        query_vector = cache.get_embedding(question)
        if query_vector is None:
            query_vector = await self.embeddings.aembed_query(question)
            cache.put_embedding(question, query_vector)
        best_match: str | None = None
        best_score = 0.0

        for qa in qa_list:
            if "question_embedding" in qa:
                score = self._cosine_similarity(query_vector, qa["question_embedding"])
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = qa["answer"]

        return best_match

    async def delete_by_source(self, source_id: str) -> None:
        """Delete all vectors for a given source."""
        await knowledge_vectors_collection().delete_many({"source_id": source_id})

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
