#!/usr/bin/env python3
"""Re-embed all knowledge base vectors with the configured embedding model.

Usage:
    cd voltimax-ai-service
    venv/bin/python scripts/reembed_knowledge.py          # re-embed all
    venv/bin/python scripts/reembed_knowledge.py --dry-run # preview only
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


async def main(dry_run: bool = False):
    from app.db.mongodb import connect_db
    from app.db.collections import knowledge_vectors_collection
    from app.knowledge.embedder import get_embeddings
    from app.config import get_config

    await connect_db()
    coll = knowledge_vectors_collection()
    config = get_config()

    model = config.knowledge_base.embedding_model
    provider = config.knowledge_base.embedding_provider
    print(f"Provider: {provider}  Model: {model}")

    docs = await coll.find({}, {"_id": 1, "content": 1}).to_list(length=10000)
    print(f"Documents: {len(docs)}")

    if dry_run:
        print("Dry run — no changes made.")
        return

    embeddings = get_embeddings()

    # Test one embedding to get dimensions
    test_vec = await embeddings.aembed_query("test")
    dims = len(test_vec)
    print(f"Embedding dimensions: {dims}")

    # Drop and recreate vector index
    try:
        await coll.drop_search_index("vector_index")
        print("Dropped old vector_index")
    except Exception:
        pass

    # Re-embed in batches
    batch_size = 50
    done = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        texts = [d["content"] for d in batch]
        vectors = await embeddings.aembed_documents(texts)

        for doc, vector in zip(batch, vectors):
            await coll.update_one({"_id": doc["_id"]}, {"$set": {"embedding": vector}})

        done += len(batch)
        print(f"  {done}/{len(docs)} ({done * 100 // len(docs)}%)")

    # Recreate vector index
    await coll.create_search_index({
        "definition": {
            "mappings": {
                "dynamic": True,
                "fields": {
                    "embedding": {
                        "type": "knnVector",
                        "dimensions": dims,
                        "similarity": "cosine",
                    }
                }
            }
        },
        "name": "vector_index",
    })
    print(f"\nDone! {done} docs re-embedded. Vector index created ({dims} dims, cosine).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-embed knowledge base vectors")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
