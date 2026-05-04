from __future__ import annotations

import csv
import io
from datetime import datetime

from app.db.collections import qa_pairs_collection
from app.knowledge.embedder import get_embeddings


async def add_qa_pair(question: str, answer: str) -> str:
    """Add a single Q&A pair to the database. Returns the inserted document ID."""
    embeddings = get_embeddings()
    question_embedding = await embeddings.aembed_query(question)

    result = await qa_pairs_collection().insert_one({
        "question": question,
        "answer": answer,
        "question_embedding": question_embedding,
        "created_at": datetime.utcnow(),
    })

    return str(result.inserted_id)


async def import_csv(content: str) -> int:
    """Import Q&A pairs from CSV content (columns: question, answer).
    Returns count of imported pairs."""
    reader = csv.DictReader(io.StringIO(content))
    count = 0

    for row in reader:
        question = row.get("question", "").strip()
        answer = row.get("answer", "").strip()
        if question and answer:
            await add_qa_pair(question, answer)
            count += 1

    return count


async def get_all_qa_pairs() -> list[dict]:
    """Get all Q&A pairs (without embeddings)."""
    cursor = qa_pairs_collection().find(
        {}, {"_id": 0, "question_embedding": 0}
    )
    return await cursor.to_list(length=10000)


async def delete_qa_pair(pair_id: str) -> bool:
    """Delete a Q&A pair by ObjectId. Returns True if deleted."""
    from bson import ObjectId

    result = await qa_pairs_collection().delete_one({"_id": ObjectId(pair_id)})
    return result.deleted_count > 0
