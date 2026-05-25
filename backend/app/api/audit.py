# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Audit API Routes
=================
GET /api/v1/audit/{run_id}  — Full forensic audit trail [C5]

Returns every stage record, source, classification, and verdict
for a given pipeline run. Immutable — all records are append-only.
"""

import uuid as uuid_lib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import AnalysisRun, StageRecord, Source, Classification, Verdict

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/{run_id}")
async def get_audit_trail(run_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the full forensic audit trail for a pipeline run.

    Returns every immutable stage record, evidence source,
    per-source classification, and final verdict.
    """
    try:
        run_uuid = uuid_lib.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    # Analysis run
    run_result = await db.execute(
        select(AnalysisRun).where(AnalysisRun.run_id == run_uuid)
    )
    run = run_result.scalar()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Stage records (ordered by created_at)
    stages_result = await db.execute(
        select(StageRecord)
        .where(StageRecord.run_id == run_uuid)
        .order_by(StageRecord.created_at)
    )
    stages = stages_result.scalars().all()

    # Sources
    sources_result = await db.execute(
        select(Source).where(Source.run_id == run_uuid)
    )
    sources = sources_result.scalars().all()

    # Classifications
    class_result = await db.execute(
        select(Classification).where(Classification.run_id == run_uuid)
    )
    classifications = class_result.scalars().all()

    # Verdict
    verdict_result = await db.execute(
        select(Verdict).where(Verdict.run_id == run_uuid)
    )
    verdict = verdict_result.scalar()

    return {
        "runId": str(run.run_id),
        "status": run.status,
        "pipelineVersion": run.pipeline_version,
        "startedAt": run.started_at.isoformat() if run.started_at else None,
        "completedAt": run.completed_at.isoformat() if run.completed_at else None,

        "stages": [
            {
                "stageName": s.stage_name,
                "inputSnapshot": s.input_snapshot,
                "outputSnapshot": s.output_snapshot,
                "modelUsed": s.model_used,
                "latencyMs": s.latency_ms,
                "costUsd": s.cost_usd,
                "retryAttempt": s.retry_attempt,
                "createdAt": s.created_at.isoformat(),
            }
            for s in stages
        ],

        "sources": [
            {
                "url": s.url,
                "domain": s.domain,
                "title": s.title,
                "credibilityScore": s.credibility_score,
                "canonicalEvidence": s.canonical_evidence,
            }
            for s in sources
        ],

        "classifications": [
            {
                "label": c.label,
                "confidence": c.confidence,
                "rationale": c.rationale,
                "modelUsed": c.model_used,
            }
            for c in classifications
        ],

        "verdict": {
            "verdict": verdict.verdict,
            "confidence": verdict.confidence,
            "explanation": verdict.explanation,
            "distribution": verdict.distribution,
            "retryOf": str(verdict.retry_of) if verdict and verdict.retry_of else None,
            "humanReview": verdict.human_review if verdict else None,
        } if verdict else None,
    }
