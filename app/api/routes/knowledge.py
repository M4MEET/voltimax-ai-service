from __future__ import annotations

import csv
import io
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.deps import verify_dashboard_auth
from app.config import get_config
from app.knowledge.manager import KnowledgeManager
from app.knowledge.sources.qa_loader import (
    add_qa_pair,
    delete_qa_pair,
    get_all_qa_pairs,
    import_csv,
)

router = APIRouter(
    prefix="/api/knowledge",
    dependencies=[Depends(verify_dashboard_auth)],
)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """Upload a file to the knowledge base (PDF, TXT, MD, DOCX)."""
    config = get_config()
    sources = config.knowledge_base.sources
    allowed = sources.get("files", {}).get("allowed_types", ["pdf", "txt", "md", "docx"])
    max_mb = sources.get("files", {}).get("max_file_size_mb", 50)
    max_size = max_mb * 1024 * 1024

    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed:
        raise HTTPException(400, f"File type .{ext} not allowed. Allowed: {allowed}")

    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(400, f"File too large. Maximum size: {max_mb}MB")

    upload_dir = sources.get("files", {}).get("upload_dir", "./knowledge_files")
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = f"{uuid.uuid4()}_{filename}"
    file_path = os.path.join(upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    manager = KnowledgeManager()
    result = await manager.index_file(file_path, filename)
    return result


@router.post("/sync-cms")
async def sync_cms(sales_channel_id: str | None = None) -> dict:
    """Trigger CMS sync from Server A into the knowledge base."""
    manager = KnowledgeManager()
    return await manager.sync_cms(sales_channel_id)


@router.post("/add-url")
async def add_url(url: str = Form(...)) -> dict:
    """Crawl a URL and add its content to the knowledge base."""
    manager = KnowledgeManager()
    return await manager.index_url(url)


@router.post("/add-qa")
async def add_qa(question: str = Form(...), answer: str = Form(...)) -> dict:
    """Add a single Q&A pair to the knowledge base."""
    pair_id = await add_qa_pair(question, answer)
    return {"id": pair_id, "question": question, "answer": answer}


@router.post("/import-qa-csv")
async def import_qa_csv(file: UploadFile = File(...)) -> dict:
    """Import Q&A pairs from a CSV file (columns: question, answer).

    Decodes with utf-8-sig so a leading BOM (added by Excel or our own
    export for umlaut rendering) is stripped and doesn't corrupt the
    first column header.
    """
    raw = await file.read()
    content = raw.decode("utf-8-sig")
    count = await import_csv(content)
    return {"imported": count}


@router.get("/qa-pairs")
async def list_qa_pairs() -> list[dict]:
    """List all Q&A pairs."""
    return await get_all_qa_pairs()


@router.get("/export-qa-csv")
async def export_qa_csv() -> Response:
    """Download all Q&A pairs as a CSV (columns: question, answer)."""
    pairs = await get_all_qa_pairs()
    buf = io.StringIO()
    buf.write("﻿")  # UTF-8 BOM so Excel renders umlauts correctly
    writer = csv.writer(buf)
    writer.writerow(["question", "answer"])
    for p in pairs:
        writer.writerow([p.get("question", ""), p.get("answer", "")])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=qa_pairs.csv"},
    )


@router.delete("/qa/{pair_id}")
async def remove_qa_pair(pair_id: str) -> dict:
    """Delete a Q&A pair by ID."""
    deleted = await delete_qa_pair(pair_id)
    if not deleted:
        raise HTTPException(404, "Q&A pair not found")
    return {"deleted": True}


@router.get("/status")
async def knowledge_status() -> dict:
    """Get knowledge base indexing status."""
    manager = KnowledgeManager()
    return await manager.get_status()


@router.delete("/{source_id}")
async def delete_source(source_id: str) -> dict:
    """Delete a knowledge source and all its vectors."""
    manager = KnowledgeManager()
    deleted = await manager.delete_source(source_id)
    if not deleted:
        raise HTTPException(404, "Source not found")
    return {"deleted": True}
