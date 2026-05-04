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
        """Search for relevant documents using vector similarity (MongoDB Atlas Vector Search)."""
        # Check embedding cache first
        from app.ai.semantic_cache import get_semantic_cache
        cache = get_semantic_cache()
        query_vector = cache.get_embedding(query)
        if query_vector is None:
            query_vector = await self.embeddings.aembed_query(query)
            cache.put_embedding(query, query_vector)
        collection = knowledge_vectors_collection()

        # MongoDB Atlas Vector Search pipeline
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

        try:
            results = []
            async for doc in collection.aggregate(pipeline):
                results.append(doc)
            return results
        except Exception:
            # Fallback: Atlas Vector Search index may not be configured yet
            return []

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
