# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Replay API Routes [C5]
=======================
GET /api/v1/replay/{run_id}  — Trigger replay of a historical claim

Reads the original claim from the append-only audit ledger,
re-runs it through the current pipeline, and returns both
run IDs for side-by-side comparison in the frontend.
"""

import uuid as uuid_lib
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import AnalysisRun, StageRecord, Verdict
from app.services.pipeline_service import PipelineService
from app.services.sse import sse_manager
from app.core.debuglog import log

router = APIRouter(prefix="/api/v1/replay", tags=["replay"])


@router.get("/{run_id}")
async def trigger_replay(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger replay of a historical claim through the current pipeline.

    Reads the original claim text from stage_1a input_snapshot,
    submits it as a new pipeline run, and returns both run IDs
    so the frontend can render a before/after comparison.
    """
    try:
        run_uuid = uuid_lib.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    # 1. Fetch original run
    run_result = await db.execute(
        select(AnalysisRun).where(AnalysisRun.run_id == run_uuid)
    )
    original_run = run_result.scalar()
    if not original_run:
        raise HTTPException(status_code=404, detail="Run not found")

    # 2. Extract original claim text from stage_1a input snapshot
    stages_result = await db.execute(
        select(StageRecord)
        .where(StageRecord.run_id == run_uuid)
        .order_by(StageRecord.created_at)
    )
    stages = stages_result.scalars().all()

    claim_text = ""
    context = ""
    locale = "en"
    for stage in stages:
        if stage.stage_name == "stage_1a":
            claim_text = stage.input_snapshot.get("claim_text", "")
            context = stage.input_snapshot.get("context", "") or ""
            locale = stage.input_snapshot.get("locale", "en")
            break

    if not claim_text:
        raise HTTPException(status_code=400, detail="Could not extract claim text from audit trail")

    # 3. Fetch original verdict
    verdict_result = await db.execute(
        select(Verdict).where(Verdict.run_id == run_uuid)
    )
    original_verdict = verdict_result.scalar()

    # 4. Create new pipeline run (replay)
    new_run_id = str(uuid_lib.uuid4())
    sse_queue = sse_manager.create_queue(new_run_id)
    service = PipelineService(db, sse_queue, run_id=new_run_id)

    log(f"REPLAY: replaying run {run_id} as new run {new_run_id} claim='{claim_text[:60]}...'")
    background_tasks.add_task(service.run_pipeline, claim_text, locale, None, context)

    return {
        "original": {
            "runId": str(run_uuid),
            "verdict": original_verdict.verdict if original_verdict else None,
            "confidence": original_verdict.confidence if original_verdict else None,
            "explanation": original_verdict.explanation if original_verdict else None,
            "distribution": original_verdict.distribution if original_verdict else None,
        },
        "replay": {
            "runId": new_run_id,
            "status": "running",
            "claimText": claim_text[:200],
        },
    }
