# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Piste — FastAPI Application Entry Point
==========================================
API Gateway with SSE streaming, idempotency guard,
and DSPy 2.6 fact-checking pipeline.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings


def _run_alembic_upgrade() -> None:
    """Apply pending Alembic migrations (blocking; call via asyncio.to_thread)."""
    import os
    from alembic import command
    from alembic.config import Config

    ini_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "alembic.ini")
    # Fallback for container layout where alembic.ini lives at /app/alembic.ini
    if not os.path.exists(ini_path):
        ini_path = "/app/alembic.ini"
    cfg = Config(ini_path)
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Startup: init DB pool, Redis, DSPy
    import asyncio
    from app.db.session import engine
    from app.services.cache import redis_client
    from pipeline.compiler import configure_dspy
    from app.core.debuglog import log

    # Apply DB migrations before anything else touches the database.
    log("LIFESPAN: running Alembic migrations...")
    await asyncio.to_thread(_run_alembic_upgrade)
    log("LIFESPAN: migrations up to date")

    await redis_client.connect()
    log("LIFESPAN: Redis connected, configuring DSPy...")
    configure_dspy()
    log("LIFESPAN: DSPy configured, app ready")
    # FAISS initialization skipped — OpenMP hang in container environment
    yield
    # Shutdown
    await redis_client.disconnect()
    await engine.dispose()


app = FastAPI(
    title="Piste — Fact-Check Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting — token bucket per user/IP
from app.core.middleware import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ============================================================
# API Routes — Phase 6
# ============================================================
from app.api import claims, verdicts, audit, discussions, feedback, replay, metrics

app.include_router(claims.router)
app.include_router(verdicts.router)
app.include_router(audit.router)
app.include_router(discussions.router)
app.include_router(feedback.router)
app.include_router(replay.router)
app.include_router(metrics.router)
