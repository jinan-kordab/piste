# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Verdicts API Routes
====================
GET /api/v1/verdicts/{run_id}  — Get final verdict (polling fallback)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import Verdict, AnalysisRun

router = APIRouter(prefix="/api/v1/verdicts", tags=["verdicts"])


@router.get("/{run_id}")
async def get_verdict(run_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the final verdict for a pipeline run.

    This is the polling fallback if SSE stream is not used.
    Returns the complete verdict with explanation and distribution.
    """
    import uuid as uuid_lib

    try:
        run_uuid = uuid_lib.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    result = await db.execute(
        select(Verdict).where(Verdict.run_id == run_uuid)
    )
    verdict = result.scalar()

    if not verdict:
        # Check if run exists but hasn't completed yet
        run_result = await db.execute(
            select(AnalysisRun).where(AnalysisRun.run_id == run_uuid)
        )
        run = run_result.scalar()
        if run:
            return {
                "run_id": run_id,
                "status": run.status,
                "verdict": None,
            }
        raise HTTPException(status_code=404, detail="Verdict not found")

    return {
        "run_id": str(verdict.run_id),
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
        "explanation": verdict.explanation,
        "distribution": verdict.distribution,
        "retry_of": str(verdict.retry_of) if verdict.retry_of else None,
        "human_review": verdict.human_review,
        "created_at": verdict.created_at.isoformat(),
    }
