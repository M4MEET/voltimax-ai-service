from __future__ import annotations

import os
import uuid
from datetime import datetime

from app.config import get_config
from app.db.collections import knowledge_sources_collection
from app.knowledge.chunker import chunk_text
from app.knowledge.sources.cms_loader import load_cms_content
from app.knowledge.sources.file_loader import load_file
from app.knowledge.sources.url_loader import crawl_url
from app.knowledge.vector_store import VectorStore


class KnowledgeManager:
    """Orchestrates knowledge base operations."""

    def __init__(self):
        self.vector_store = VectorStore()

    async def index_file(self, file_path: str, original_name: str) -> dict:
        """Index a file into the knowledge base."""
        source_id = str(uuid.uuid4())
        text = load_file(file_path)
        chunks = chunk_text(text)

        await self.vector_store.add_documents(
            chunks,
            source_id,
            "file",
            metadata={"filename": original_name},
        )

        record: dict = {
            "id": source_id,
            "source_type": "file",
            "name": original_name,
            "chunk_count": len(chunks),
            "status": "indexed",
            "created_at": datetime.utcnow(),
        }
        await knowledge_sources_collection().insert_one(record)

        return {k: v for k, v in record.items() if k != "_id"}

    async def sync_cms(self, sales_channel_id: str | None = None) -> dict:
        """Sync CMS content from Server A."""
        content = await load_cms_content(sales_channel_id)

        total_chunks = 0
        for item in content:
            source_id = f"cms_{item['type']}_{item['id']}"
            await self.vector_store.delete_by_source(source_id)

            chunks = chunk_text(item["text"])
            await self.vector_store.add_documents(
                chunks,
                source_id,
                "cms",
                metadata={"title": item["title"], "cms_type": item["type"]},
            )
            total_chunks += len(chunks)

        # Also sync PDF documents from Shopware media library
        doc_chunks = await self._sync_media_documents()
        total_chunks += doc_chunks

        return {
            "sources_synced": len(content),
            "total_chunks": total_chunks,
            "documents_synced": doc_chunks,
            "synced_at": datetime.utcnow().isoformat(),
        }

    async def _sync_media_documents(self) -> int:
        """Fetch relevant PDF documents from Shopware media and embed their text content."""
        import tempfile
        from app.shopware.client import ShopwareClient
        from app.knowledge.sources.file_loader import load_pdf

        client = ShopwareClient()
        # Fetch documents matching service/policy keywords + datasheets
        # Use separate searches per keyword to avoid missing documents
        all_docs = {}
        keyword_groups = [
            (["pfand"], 20),
            (["formular"], 20),
            (["widerruf"], 10),
            (["retoure", "rueckgabe"], 10),
            (["agb"], 10),
            (["Datenblatt"], 200),  # large — many product datasheets
            (["datenblatt"], 200),
            (["Data-Sheet"], 50),
            (["datasheet"], 50),
            (["anleitung"], 30),
        ]
        for keywords, limit in keyword_groups:
            batch = await client.get_media_documents(keywords=keywords, limit=limit)
            for d in batch:
                all_docs[d["id"]] = d
        docs = list(all_docs.values())

        if not docs:
            return 0

        total_chunks = 0
        for doc in docs:
            source_id = f"media_pdf_{doc['id']}"
            await self.vector_store.delete_by_source(source_id)

            # Download the PDF
            content = await client.download_media_content(doc["url"])
            if not content:
                continue

            # Extract text from PDF
            try:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                text = load_pdf(tmp_path)
                os.unlink(tmp_path)
            except Exception:
                continue

            if not text or len(text.strip()) < 20:
                continue

            chunks = chunk_text(text)
            await self.vector_store.add_documents(
                chunks,
                source_id,
                "document",
                metadata={
                    "title": doc["title"],
                    "fileName": doc["fileName"],
                    "download_url": doc["url"],
                },
            )
            total_chunks += len(chunks)

        return total_chunks

    async def index_url(self, url: str) -> dict:
        """Crawl and index a URL."""
        config = get_config()
        source_id = str(uuid.uuid4())
        url_cfg = config.knowledge_base.sources.get("urls", {})

        pages = await crawl_url(
            url,
            max_depth=url_cfg.get("max_crawl_depth", 2),
            max_pages=url_cfg.get("max_pages_per_url", 100),
        )

        total_chunks = 0
        for page in pages:
            chunks = chunk_text(page["text"])
            await self.vector_store.add_documents(
                chunks,
                source_id,
                "url",
                metadata={"url": page["url"], "title": page["title"]},
            )
            total_chunks += len(chunks)

        record: dict = {
            "id": source_id,
            "source_type": "url",
            "name": url,
            "page_count": len(pages),
            "chunk_count": total_chunks,
            "status": "indexed",
            "created_at": datetime.utcnow(),
        }
        await knowledge_sources_collection().insert_one(record)

        return {k: v for k, v in record.items() if k != "_id"}

    async def delete_source(self, source_id: str) -> bool:
        """Delete a knowledge source and all its vectors."""
        await self.vector_store.delete_by_source(source_id)
        result = await knowledge_sources_collection().delete_one({"id": source_id})
        return result.deleted_count > 0

    async def get_status(self) -> dict:
        """Get knowledge base status summary."""
        from app.db.collections import knowledge_vectors_collection, qa_pairs_collection

        sources = await knowledge_sources_collection().find(
            {}, {"_id": 0}
        ).to_list(length=1000)
        vector_count = await knowledge_vectors_collection().count_documents({})
        qa_count = await qa_pairs_collection().count_documents({})

        return {
            "sources": sources,
            "total_vectors": vector_count,
            "total_qa_pairs": qa_count,
        }
