# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""Initial schema — all 12 tables for the Piste platform.

Revision ID: 001_initial
Create Date: 2026-05-23

This migration creates the complete append-only audit ledger schema:
  - users, claims, analysis_runs
  - stage_records (APPEND-ONLY), sources
  - classifications (APPEND-ONLY), verdicts (APPEND-ONLY)
  - discussion_posts, discussion_votes, feedback
  - domains, replay_runs (APPEND-ONLY)
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("auth0_id", sa.String(255), unique=True, nullable=True),
        sa.Column("locale", sa.String(10), default="en"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_auth0_id", "users", ["auth0_id"])
    op.create_index("ix_users_email", "users", ["email"])

    # --- claims ---
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("locale", sa.String(10), default="en"),
        sa.Column("sha256_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_claims_sha256", "claims", ["sha256_hash"])
    op.create_index("ix_claims_created_at", "claims", ["created_at"])

    # --- analysis_runs ---
    op.create_table(
        "analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), unique=True, nullable=False),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("pipeline_version", sa.String(20), default="0.1.0"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_analysis_runs_run_id", "analysis_runs", ["run_id"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])

    # --- stage_records (APPEND-ONLY) ---
    op.create_table(
        "stage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.run_id"), nullable=False),
        sa.Column("stage_name", sa.String(30), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("output_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("retry_attempt", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_stage_records_run_id_stage", "stage_records", ["run_id", "stage_name"])
    op.create_index("ix_stage_records_created_at", "stage_records", ["created_at"])

    # --- sources ---
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.run_id"), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("credibility_score", sa.Float(), nullable=True),
        sa.Column("canonical_evidence", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_sources_run_id", "sources", ["run_id"])
    op.create_index("ix_sources_domain", "sources", ["domain"])

    # --- classifications (APPEND-ONLY) ---
    op.create_table(
        "classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.run_id"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("votes", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_classifications_run_id", "classifications", ["run_id"])

    # --- verdicts (APPEND-ONLY) ---
    op.create_table(
        "verdicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.run_id"), unique=True, nullable=False),
        sa.Column("verdict", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("distribution", postgresql.JSONB(), nullable=False),
        sa.Column("retry_of", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("human_review", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_verdicts_verdict", "verdicts", ["verdict"])
    op.create_index("ix_verdicts_created_at", "verdicts", ["created_at"])

    # --- discussion_posts ---
    op.create_table(
        "discussion_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("verdict_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verdicts.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discussion_posts.id"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_discussion_posts_verdict_id", "discussion_posts", ["verdict_id"])
    op.create_index("ix_discussion_posts_created_at", "discussion_posts", ["created_at"])

    # --- discussion_votes ---
    op.create_table(
        "discussion_votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discussion_posts.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("vote_type", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_unique_constraint("uq_discussion_votes_post_user", "discussion_votes", ["post_id", "user_id"])
    op.create_index("ix_discussion_votes_post_id", "discussion_votes", ["post_id"])

    # --- feedback ---
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("verdict_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verdicts.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_unique_constraint("uq_feedback_verdict_user", "feedback", ["verdict_id", "user_id"])
    op.create_index("ix_feedback_verdict_id", "feedback", ["verdict_id"])

    # --- domains ---
    op.create_table(
        "domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain_name", sa.String(255), unique=True, nullable=False),
        sa.Column("credibility_score", sa.Float(), nullable=False),
        sa.Column("is_reliable", sa.Boolean(), default=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_domains_domain_name", "domains", ["domain_name"])
    op.create_index("ix_domains_category", "domains", ["category"])

    # --- replay_runs (APPEND-ONLY) ---
    op.create_table(
        "replay_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("original_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("new_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("pipeline_version", sa.String(20), nullable=False),
        sa.Column("verdict_changed", sa.Boolean(), default=False),
        sa.Column("verdict_comparison", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_replay_runs_original_run_id", "replay_runs", ["original_run_id"])


def downgrade() -> None:
    op.drop_table("replay_runs")
    op.drop_table("discussion_votes")
    op.drop_table("discussion_posts")
    op.drop_table("feedback")
    op.drop_table("verdicts")
    op.drop_table("classifications")
    op.drop_table("sources")
    op.drop_table("stage_records")
    op.drop_table("domains")
    op.drop_table("analysis_runs")
    op.drop_table("claims")
    op.drop_table("users")
