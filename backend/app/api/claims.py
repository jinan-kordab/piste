# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Claims API Routes
==================
POST   /api/v1/claims          — Submit a claim for fact-checking
GET    /api/v1/claims/{run_id}/stream — SSE stream of pipeline progress
"""

import asyncio
import uuid
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.sse import sse_manager, sse_event_generator
from app.services.cache import redis_client
from app.services.pipeline_service import PipelineService
from app.core.debuglog import log

router = APIRouter(prefix="/api/v1/claims", tags=["claims"])


@router.post("")
async def submit_claim(
    payload: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a claim for fact-checking.

    Request body:
        { "claim_text": "...", "locale": "en", "context": "..." }

    Returns:
        { "run_id": "uuid", "status": "accepted" }

    The pipeline runs asynchronously. Subscribe to SSE stream
    at GET /api/v1/claims/{run_id}/stream for real-time progress.
    """
    claim_text = payload.get("claim_text", "").strip()
    locale = payload.get("locale", "en")
    context = payload.get("context", "")

    log(f"CLAIMS API: received claim_text='{claim_text[:50]}...', locale={locale}")

    if not claim_text:
        raise HTTPException(status_code=422, detail="claim_text is required")
    if len(claim_text) > 10000:
        raise HTTPException(status_code=422, detail="claim_text too long (max 10,000 chars)")

    # Idempotency check [C7]
    duplicate = await redis_client.is_duplicate(claim_text)
    if duplicate and duplicate.get("cached"):
        return {
            "run_id": duplicate["verdict"].get("run_id"),
            "status": "cached",
            "verdict": duplicate["verdict"],
        }

    # Mark as processing
    await redis_client.mark_processing(claim_text)

    # Generate run_id and create SSE queue
    run_id = str(uuid.uuid4())
    sse_queue = sse_manager.create_queue(run_id)

    # Run pipeline as background task with the same run_id
    log(f"CLAIMS API: creating PipelineService for run_id={run_id}")
    service = PipelineService(db, sse_queue, run_id=run_id)
    log(f"CLAIMS API: adding background task, about to return")
    background_tasks.add_task(service.run_pipeline, claim_text, locale, None, context)
    log(f"CLAIMS API: returning accepted, run_id={run_id}")

    return {
        "run_id": run_id,
        "status": "accepted",
    }


@router.get("/{run_id}/stream")
async def stream_pipeline(run_id: str):
    """
    SSE endpoint — stream pipeline progress events.
    """
    log(f"SSE: stream requested for run_id={run_id}")
    return StreamingResponse(
        sse_event_generator(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
