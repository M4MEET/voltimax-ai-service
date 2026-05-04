from fastapi import APIRouter

from app.db.mongodb import get_db

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint. Server A admin panel calls this."""
    try:
        db = get_db()
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    from app.ai.semantic_cache import get_semantic_cache
    cache_stats = get_semantic_cache().stats()

    return {
        "status": "ok",
        "service": "voltimax-ai-service",
        "version": "1.0.0",
        "mongodb": db_status,
        "semantic_cache": cache_stats,
    }


@router.post("/cache/clear")
async def clear_cache():
    """Clear the semantic response cache. Use when policies or KB content changes."""
    from app.ai.semantic_cache import get_semantic_cache
    count = get_semantic_cache().clear()
    return {"cleared": count, "message": "Semantic cache cleared"}
