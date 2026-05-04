from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import load_config
from app.db.mongodb import close_db, connect_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    config = load_config()
    logging.basicConfig(
        level=logging.DEBUG if config.server.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Load .env file for local development
    import os
    from dotenv import load_dotenv
    load_dotenv()

    # Enable LangSmith tracing — env vars from .env are authoritative
    if os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY"):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGCHAIN_PROJECT", "VoltimaxChat-Groot")
        # Don't override LANGCHAIN_ENDPOINT — .env already sets it to EU
        project = os.getenv("LANGCHAIN_PROJECT", "VoltimaxChat-Groot")
        endpoint = os.getenv("LANGCHAIN_ENDPOINT", "?")
        logger.info(f"LangSmith tracing enabled (project: {project}, endpoint: {endpoint})")
    else:
        logger.info("LangSmith tracing disabled (no API key set)")

    logger.info("Starting VoltimaxChat AI Service...")
    await connect_db()
    logger.info("MongoDB connected.")

    # Attach MongoDB log handler (persists WARNING+ to the logs collection)
    from app.logging_handler import MongoLogHandler
    mongo_handler = MongoLogHandler()
    mongo_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(mongo_handler)

    from app.tasks.purge import purge_old_sessions
    from app.logging_handler import flush_logs as _flush_logs

    async def _periodic_log_flush():
        while True:
            await asyncio.sleep(10)
            try:
                await _flush_logs()
            except Exception:
                pass

    _log_flush_task = asyncio.create_task(_periodic_log_flush())

    async def _daily_purge():
        while True:
            await asyncio.sleep(86400)
            try:
                n = await purge_old_sessions()
                logger.info("Daily purge: removed %d old sessions", n)
            except Exception as e:
                logger.error("Daily purge failed: %s", e)

    _purge_task = asyncio.create_task(_daily_purge())
    try:
        n = await purge_old_sessions()
        logger.info("Startup purge: removed %d old sessions", n)
    except Exception as e:
        logger.warning("Startup purge failed: %s", e)

    yield

    # --- Shutdown ---
    _log_flush_task.cancel()
    _purge_task.cancel()
    logger.info("Shutting down VoltimaxChat AI Service...")
    from app.logging_handler import flush_logs
    await flush_logs()
    await close_db()


def create_app() -> FastAPI:
    config = load_config()

    app = FastAPI(
        title="VoltimaxChat AI Service",
        description=(
            "AI services platform for the VoltimaxChat widget. "
            "Handles real-time chat via WebSocket/SSE, LLM routing, "
            "knowledge base RAG, and escalation."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — allow configured origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and register all routers
    from app.api.routes import analytics, chat, health, knowledge, session, webhooks

    app.include_router(health.router, tags=["health"])
    app.include_router(chat.router, tags=["chat"])
    app.include_router(session.router)
    app.include_router(knowledge.router, tags=["knowledge"])
    app.include_router(analytics.router, tags=["analytics"])
    app.include_router(webhooks.router, tags=["webhooks"])

    from app.api.routes import admin
    app.include_router(admin.router, tags=["admin"])

    # Serve React dashboard build
    import os
    dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard-build")
    if os.path.isdir(dashboard_dir):
        app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

    # Serve static forms (Batteriepfand PDFs, etc.)
    static_forms_dir = os.path.join(os.path.dirname(__file__), "..", "static", "forms")
    if os.path.isdir(static_forms_dir):
        app.mount("/static/forms", StaticFiles(directory=static_forms_dir), name="static-forms")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        "app.main:app",
        host=cfg.server.host,
        port=cfg.server.port,
        reload=cfg.server.debug,
    )
