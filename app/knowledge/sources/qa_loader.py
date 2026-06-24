from __future__ import annotations

import csv
import io
import re
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


async def upsert_qa_pair(question: str, answer: str) -> str:
    """Insert a Q&A pair, or update the answer if the question already exists.

    Matching is case-insensitive on the trimmed question, so re-importing an
    edited CSV updates answers in place instead of creating duplicates.
    Returns "added" or "updated". Updating skips re-embedding (question is
    unchanged) — saves an embedding API call.
    """
    question = question.strip()
    answer = answer.strip()
    coll = qa_pairs_collection()
    existing = await coll.find_one(
        {"question": {"$regex": f"^{re.escape(question)}$", "$options": "i"}}
    )
    if existing:
        await coll.update_one(
            {"_id": existing["_id"]},
            {"$set": {"answer": answer, "updated_at": datetime.utcnow()}},
        )
        return "updated"
    await add_qa_pair(question, answer)
    return "added"


async def import_csv(content: str) -> dict:
    """Import Q&A pairs from CSV content (columns: question, answer).

    Upserts by question so re-importing won't create duplicates.
    Returns {"added": int, "updated": int}.
    """
    reader = csv.DictReader(io.StringIO(content))
    added = 0
    updated = 0

    for row in reader:
        question = row.get("question", "").strip()
        answer = row.get("answer", "").strip()
        if question and answer:
            if await upsert_qa_pair(question, answer) == "added":
                added += 1
            else:
                updated += 1

    return {"added": added, "updated": updated}


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
