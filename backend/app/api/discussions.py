# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Discussions API Routes — UI3 Community Discussion
===================================================
POST /api/v1/discussions/{verdict_id}/posts   — Create discussion post
POST /api/v1/discussions/{post_id}/votes      — Vote on a post
GET  /api/v1/discussions/{verdict_id}         — Get discussion thread

Community discussion is Loop 3 input — user feedback on verdicts
feeds into DSPy re-optimization.
"""

import uuid as uuid_lib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.db.models import Verdict, DiscussionPost, DiscussionVote

router = APIRouter(prefix="/api/v1/discussions", tags=["discussions"])


@router.get("/{verdict_id}")
async def get_discussion(verdict_id: str, db: AsyncSession = Depends(get_db)):
    """Get threaded discussion for a verdict."""
    try:
        v_uuid = uuid_lib.UUID(verdict_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid verdict_id")

    # Get all posts for this verdict
    result = await db.execute(
        select(DiscussionPost)
        .where(DiscussionPost.verdict_id == v_uuid)
        .order_by(DiscussionPost.created_at)
    )
    posts = result.scalars().all()

    # Get vote counts per post
    post_ids = [p.id for p in posts]
    vote_counts = {}
    if post_ids:
        for pid in post_ids:
            up_result = await db.execute(
                select(func.count()).where(
                    DiscussionVote.post_id == pid,
                    DiscussionVote.vote_type == "UP",
                )
            )
            down_result = await db.execute(
                select(func.count()).where(
                    DiscussionVote.post_id == pid,
                    DiscussionVote.vote_type == "DOWN",
                )
            )
            vote_counts[str(pid)] = {
                "up": up_result.scalar() or 0,
                "down": down_result.scalar() or 0,
            }

    return {
        "verdict_id": verdict_id,
        "posts": [
            {
                "id": str(p.id),
                "parent_id": str(p.parent_id) if p.parent_id else None,
                "content": p.content,
                "created_at": p.created_at.isoformat(),
                "votes": vote_counts.get(str(p.id), {"up": 0, "down": 0}),
            }
            for p in posts
        ],
    }


@router.post("/{verdict_id}/posts")
async def create_post(
    verdict_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Create a discussion post on a verdict."""
    try:
        v_uuid = uuid_lib.UUID(verdict_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid verdict_id")

    content = payload.get("content", "").strip()
    parent_id = payload.get("parent_id")

    if not content:
        raise HTTPException(status_code=422, detail="content is required")

    post = DiscussionPost(
        verdict_id=v_uuid,
        user_id=uuid_lib.UUID("00000000-0000-0000-0000-000000000001"),  # placeholder
        parent_id=uuid_lib.UUID(parent_id) if parent_id else None,
        content=content,
    )
    db.add(post)
    await db.commit()

    return {
        "id": str(post.id),
        "verdict_id": verdict_id,
        "content": content,
        "created_at": post.created_at.isoformat(),
    }


@router.post("/{post_id}/votes")
async def vote_post(
    post_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Vote UP or DOWN on a discussion post."""
    try:
        p_uuid = uuid_lib.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post_id")

    vote_type = payload.get("vote_type", "UP").upper()
    if vote_type not in ("UP", "DOWN"):
        raise HTTPException(status_code=422, detail="vote_type must be UP or DOWN")

    # Upsert: one vote per user per post
    user_id = uuid_lib.UUID("00000000-0000-0000-0000-000000000001")  # placeholder

    existing = await db.execute(
        select(DiscussionVote).where(
            DiscussionVote.post_id == p_uuid,
            DiscussionVote.user_id == user_id,
        )
    )
    vote = existing.scalar()

    if vote:
        vote.vote_type = vote_type
    else:
        vote = DiscussionVote(
            post_id=p_uuid,
            user_id=user_id,
            vote_type=vote_type,
        )
        db.add(vote)

    await db.commit()
    return {"post_id": post_id, "vote_type": vote_type, "status": "recorded"}
