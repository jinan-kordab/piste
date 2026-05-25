# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Database Models — All 12 entities for the Piste platform.
===========================================================
APPEND-ONLY POLICY: stage_records, classifications, verdicts,
and replay_runs are never UPDATEd or DELETEd — only INSERTed.
This guarantees a complete, immutable forensic audit trail [C5].
"""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column, String, Text, Float, Boolean, Integer,
    DateTime, ForeignKey, Enum, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.db.base import Base


# ============================================================
# USERS
# ============================================================
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    auth0_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    claims = relationship("Claim", back_populates="user")
    discussions = relationship("DiscussionPost", back_populates="author")
    votes = relationship("DiscussionVote", back_populates="voter")
    feedbacks = relationship("Feedback", back_populates="user")

    __table_args__ = (
        Index("ix_users_auth0_id", "auth0_id"),
        Index("ix_users_email", "email"),
    )


# ============================================================
# CLAIMS
# ============================================================
class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="en")
    sha256_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="claims")
    analysis_runs = relationship("AnalysisRun", back_populates="claim")

    __table_args__ = (
        Index("ix_claims_sha256", "sha256_hash"),
        Index("ix_claims_created_at", "created_at"),
    )


# ============================================================
# ANALYSIS RUNS
# ============================================================
class AnalysisRun(Base):
    """Tracks a single end-to-end pipeline execution for a claim."""

    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id"), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, default=uuid.uuid4, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|completed|failed
    pipeline_version: Mapped[str] = mapped_column(String(20), default="0.1.0")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    claim = relationship("Claim", back_populates="analysis_runs")
    stage_records = relationship("StageRecord", back_populates="analysis_run", order_by="StageRecord.created_at")
    sources = relationship("Source", back_populates="analysis_run")
    classifications = relationship("Classification", back_populates="analysis_run")
    verdict = relationship("Verdict", back_populates="analysis_run", uselist=False, primaryjoin="AnalysisRun.run_id == foreign(Verdict.run_id)")
    replay_runs = relationship("ReplayRun", back_populates="original_run", foreign_keys="ReplayRun.original_run_id")

    __table_args__ = (
        Index("ix_analysis_runs_run_id", "run_id"),
        Index("ix_analysis_runs_status", "status"),
    )


# ============================================================
# STAGE RECORDS — APPEND-ONLY [C5]
# ============================================================
class StageRecord(Base):
    """
    Immutable record of every pipeline stage execution.
    APPEND-ONLY: never UPDATE or DELETE rows in this table.
    Each row captures the full input/output snapshot of one stage.
    """

    __tablename__ = "stage_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_runs.run_id"), nullable=False, index=True)
    stage_name: Mapped[str] = mapped_column(String(30), nullable=False)
    # stage_1a, stage_1b, stage_2a, stage_2b, stage_2c, stage_2d, stage_2e,
    # stage_3, stage_4a, stage_4b, stage_4c

    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    retry_attempt: Mapped[int] = mapped_column(Integer, default=0)  # Loop 1 retry count
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    analysis_run = relationship("AnalysisRun", back_populates="stage_records")

    __table_args__ = (
        Index("ix_stage_records_run_id_stage", "run_id", "stage_name"),
        Index("ix_stage_records_created_at", "created_at"),
    )


# ============================================================
# SOURCES
# ============================================================
class Source(Base):
    """Evidence source retrieved during Stage 2."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_runs.run_id"), nullable=False, index=True)

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credibility_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # CanonicalEvidence [C6] — normalized JSONB blob
    canonical_evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    analysis_run = relationship("AnalysisRun", back_populates="sources")
    classifications = relationship("Classification", back_populates="source")

    __table_args__ = (
        Index("ix_sources_run_id", "run_id"),
        Index("ix_sources_domain", "domain"),
    )


# ============================================================
# CLASSIFICATIONS — APPEND-ONLY [C5]
# ============================================================
class Classification(Base):
    """
    Per-source classification from Stage 3.
    APPEND-ONLY: each source gets one immutable classification row.
    """

    __tablename__ = "classifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_runs.run_id"), nullable=False, index=True)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=True)

    label: Mapped[str] = mapped_column(String(20), nullable=False)  # SUPPORTS | REFUTES | UNRELATED
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    votes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # If voting enabled: [label1, label2, label3]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    analysis_run = relationship("AnalysisRun", back_populates="classifications")
    source = relationship("Source", back_populates="classifications")

    __table_args__ = (
        Index("ix_classifications_run_id", "run_id"),
    )


# ============================================================
# VERDICTS — APPEND-ONLY [C5]
# ============================================================
class Verdict(Base):
    """
    Final verdict from Stage 4.
    APPEND-ONLY: one immutable verdict per analysis run.
    Retries create NEW analysis_runs linked via retry_of.
    Human overrides create NEW verdicts with human_review populated.
    """

    __tablename__ = "verdicts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_runs.run_id"), unique=True, nullable=False)

    # 7-way PolitiFact-aligned verdict
    verdict: Mapped[str] = mapped_column(String(30), nullable=False)
    # TRUE | MOSTLY_TRUE | HALF_TRUE | MOSTLY_FALSE | FALSE | PANTS_ON_FIRE | UNVERIFIABLE

    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    # Verdict probability distribution over all 7 labels
    distribution: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Link to previous run if this is a retry (Loop 1)
    retry_of: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=True)

    # Human-in-the-loop override [C3]
    human_review: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # { reviewer_id, original_verdict, final_verdict, reason, reviewed_at }

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    analysis_run = relationship("AnalysisRun", back_populates="verdict", primaryjoin="foreign(Verdict.run_id) == AnalysisRun.run_id")
    discussion_posts = relationship("DiscussionPost", back_populates="verdict")
    feedbacks = relationship("Feedback", back_populates="verdict")

    __table_args__ = (
        Index("ix_verdicts_verdict", "verdict"),
        Index("ix_verdicts_created_at", "created_at"),
    )


# ============================================================
# DISCUSSION POSTS
# ============================================================
class DiscussionPost(Base):
    """Community discussion thread on a verdict (UI3 — Loop 3 input)."""

    __tablename__ = "discussion_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    verdict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("verdicts.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("discussion_posts.id"), nullable=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    verdict = relationship("Verdict", back_populates="discussion_posts")
    author = relationship("User", back_populates="discussions")
    parent = relationship("DiscussionPost", remote_side=[id], backref="replies")
    votes = relationship("DiscussionVote", back_populates="post")

    __table_args__ = (
        Index("ix_discussion_posts_verdict_id", "verdict_id"),
        Index("ix_discussion_posts_created_at", "created_at"),
    )


# ============================================================
# DISCUSSION VOTES
# ============================================================
class DiscussionVote(Base):
    """Up/down vote on a discussion post (UI3)."""

    __tablename__ = "discussion_votes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("discussion_posts.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    vote_type: Mapped[str] = mapped_column(String(10), nullable=False)  # UP | DOWN
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    post = relationship("DiscussionPost", back_populates="votes")
    voter = relationship("User", back_populates="votes")

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_discussion_votes_post_user"),
        Index("ix_discussion_votes_post_id", "post_id"),
    )


# ============================================================
# FEEDBACK
# ============================================================
class Feedback(Base):
    """User feedback on a verdict — Loop 3 input for DSPy re-optimization."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    verdict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("verdicts.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–5 stars
    tags: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)
    # e.g., ["inaccurate", "biased_source", "missing_context", "excellent"]

    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    verdict = relationship("Verdict", back_populates="feedbacks")
    user = relationship("User", back_populates="feedbacks")

    __table_args__ = (
        UniqueConstraint("verdict_id", "user_id", name="uq_feedback_verdict_user"),
        Index("ix_feedback_verdict_id", "verdict_id"),
    )


# ============================================================
# DOMAINS — Per-Domain Credibility [J1b]
# ============================================================
class Domain(Base):
    """
    Lin et al. (2023) per-domain credibility database.
    Scores each news domain on a continuous 0–1 scale.
    """

    __tablename__ = "domains"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    credibility_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_reliable: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # news_wire, public_broadcaster, newspaper, cable_news, digital_native,
    # hyperpartisan, conspiracy, fact_checker, satire, unknown

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_domains_domain_name", "domain_name"),
        Index("ix_domains_category", "category"),
    )


# ============================================================
# REPLAY RUNS — APPEND-ONLY [C5]
# ============================================================
class ReplayRun(Base):
    """
    Record of a replay execution.
    APPEND-ONLY: each replay is a new immutable row.
    """

    __tablename__ = "replay_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=False)
    new_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=True)

    pipeline_version: Mapped[str] = mapped_column(String(20), nullable=False)
    verdict_changed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Side-by-side comparison
    verdict_comparison: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # { original_verdict, new_verdict, stage_diffs: [{stage, old_output, new_output}] }

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    original_run = relationship("AnalysisRun", back_populates="replay_runs", foreign_keys=[original_run_id])

    __table_args__ = (
        Index("ix_replay_runs_original_run_id", "original_run_id"),
    )
