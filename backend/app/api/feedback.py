# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Feedback API Routes — Loop 3 Input
====================================
POST /api/v1/feedback  — Submit user feedback on a verdict

User feedback (ratings, tags, comments) feeds into DSPy
re-optimization (Loop 3) — human-labeled examples for
BootstrapFewShot / MIPROv2 compiler.
"""

import uuid as uuid_lib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models import Feedback

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit user feedback on a verdict.

    Request body:
        {
            "verdict_id": "uuid",
            "rating": 4,           // 1–5 stars
            "tags": ["accurate", "well_sourced"],
            "comment": "Good analysis but missed context X."
        }
    """
    verdict_id = payload.get("verdict_id")
    rating = payload.get("rating")
    tags = payload.get("tags", [])
    comment = payload.get("comment", "")

    if not verdict_id:
        raise HTTPException(status_code=422, detail="verdict_id is required")
    if not rating or not (1 <= rating <= 5):
        raise HTTPException(status_code=422, detail="rating must be 1–5")

    try:
        v_uuid = uuid_lib.UUID(verdict_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid verdict_id")

    feedback = Feedback(
        verdict_id=v_uuid,
        user_id=uuid_lib.UUID("00000000-0000-0000-0000-000000000001"),  # placeholder
        rating=rating,
        tags=tags if tags else None,
        comment=comment if comment else None,
    )
    db.add(feedback)
    await db.commit()

    return {
        "id": str(feedback.id),
        "verdict_id": verdict_id,
        "rating": rating,
        "status": "recorded",
        "note": "Feedback will be used for DSPy re-optimization (Loop 3).",
    }
