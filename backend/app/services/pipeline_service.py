# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Pipeline Service — Main orchestrator for FastAPI integration.
==============================================================
Coordinates the full 4-stage DSPy pipeline:
  Stage 1 → Stage 2 → Stage 3 → Stage 4

Manages:
  - SSE event emission for real-time frontend updates
  - Append-only PostgreSQL audit ledger writes [C5]
  - Idempotency guard via Redis [C7]
  - FAISS semantic dedup [J7]
  - DSPy module lifecycle
"""

import asyncio
import time
import uuid
from datetime import datetime
from typing import Optional, AsyncGenerator, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Claim, AnalysisRun, StageRecord, Verdict, Classification, Source
from app.db.session import AsyncSessionLocal
from app.services.cache import redis_client
from app.services.vector_store import faiss_store
from pipeline.stage1.orchestrator import Stage1Orchestrator, Stage1Result
from app.core.debuglog import log
from app.api.metrics import record_claim_submitted, record_claim_completed, record_claim_failed


class PipelineService:
    """
    Main pipeline orchestrator.

    Usage (from FastAPI route):
        service = PipelineService(db_session, sse_queue)
        await service.run_pipeline(claim_text, locale, run_id)
    """

    def __init__(
        self,
        db: AsyncSession,
        sse_queue: Optional[asyncio.Queue] = None,
        run_id: Optional[str] = None,
    ):
        self.db = db
        self.sse_queue = sse_queue
        self.run_id: Optional[uuid.UUID] = uuid.UUID(run_id) if run_id else None

    async def run_pipeline(
        self,
        claim_text: str,
        locale: str = "en",
        user_id: Optional[uuid.UUID] = None,
        context: str = "",
    ) -> str:
        """
        Run the full fact-checking pipeline.

        Returns:
            run_id (str) — UUID of the analysis run for SSE subscription.
        """
        self.run_id = self.run_id or uuid.uuid4()
        started_at = datetime.utcnow()
        record_claim_submitted()
        log(f"PIPELINE: start run_id={self.run_id} claim='{claim_text[:60]}...'")

        # Use a FRESH session — the request session is closed when the task runs
        async with AsyncSessionLocal() as db:
            await self._run_with_db(db, claim_text, locale, user_id, started_at, context)

        return str(self.run_id)

    async def _run_with_db(
        self,
        db: AsyncSession,
        claim_text: str,
        locale: str,
        user_id: Optional[uuid.UUID],
        started_at: datetime,
        context: str = "",
    ):
        """Run pipeline with a dedicated database session."""
        await self._emit("pipeline_start", {
            "run_id": str(self.run_id),
            "claim_text": claim_text,
            "locale": locale,
        })

        # --- Create Claim record (handle duplicates gracefully) ---
        log(f"PIPELINE: creating Claim DB record")
        claim_hash = redis_client.claim_hash(claim_text)
        
        # Check if this exact claim already exists in DB
        from sqlalchemy import select
        existing = (await db.execute(
            select(Claim).where(Claim.sha256_hash == claim_hash)
        )).scalar_one_or_none()
        
        if existing:
            log(f"PIPELINE: claim already exists id={existing.id}, reusing")
            claim = existing
        else:
            claim = Claim(
                user_id=user_id,
                claim_text=claim_text,
                context=context or None,
                locale=locale,
                sha256_hash=claim_hash,
            )
            db.add(claim)
            log(f"PIPELINE: flushing claim...")
            await db.flush()
            log(f"PIPELINE: claim flushed id={claim.id}")

        # --- Create AnalysisRun ---
        run = AnalysisRun(
            claim_id=claim.id,
            run_id=self.run_id,
            status="running",
            started_at=started_at,
        )
        db.add(run)
        log(f"PIPELINE: calling flush()...")
        
        try:
            await db.flush()  # Get IDs without committing
            log(f"PIPELINE: flush() OK")
            
            # --- Stage 1: Claim Processing ---
            s1_orchestrator = Stage1Orchestrator(sse_callback=self._emit)
            s1_result = await s1_orchestrator.process(
                claim_text, locale, db=db, run_id=run.run_id, context=context
            )
            log(f"PIPELINE: Stage 1 done, is_check_worthy={s1_result.is_check_worthy} label={s1_result.worthiness_label}")

            if not s1_result.is_check_worthy:
                # Early stop — not a check-worthy claim
                # Create UNVERIFIABLE verdict for audit trail
                db.add(Verdict(
                    run_id=run.run_id,
                    verdict="UNVERIFIABLE",
                    confidence=0.0,
                    explanation=f"Claim not check-worthy: {s1_result.stop_reason}",
                    distribution={"TRUE": 0.0, "MOSTLY_TRUE": 0.0, "HALF_TRUE": 0.0,
                                  "MOSTLY_FALSE": 0.0, "FALSE": 0.0, "PANTS_ON_FIRE": 0.0,
                                  "UNVERIFIABLE": 1.0},
                ))
                await self._finalize_run(run, "completed", started_at)
                await db.commit()
                log(f"PIPELINE: committed early-stop verdict, emitting verdict_complete")
                await self._emit("verdict_complete", {
                    "verdict": "UNVERIFIABLE",
                    "confidence": 0.0,
                    "explanation": f"Claim not check-worthy: {s1_result.stop_reason}",
                    "early_stop": True,
                })
                record_claim_completed()
                return str(self.run_id)

            # --- Stage 2: Blind Retrieval ---
            from pipeline.stage2.orchestrator import Stage2Orchestrator
            s2_orchestrator = Stage2Orchestrator(sse_callback=self._emit)
            s2_results = await s2_orchestrator.process(
                s1_result.atomic_claims, db=db, locale=locale, run_id=run.run_id
            )

            # Collect all evidence
            all_evidence = []
            for s2r in s2_results:
                all_evidence.extend(s2r.canonical_evidence)

            # --- Stage 3: Per-Source Classification ---
            from pipeline.stage3.orchestrator import Stage3Orchestrator
            s3_orchestrator = Stage3Orchestrator(sse_callback=self._emit)

            # Each atomic claim's evidence classifications are independent —
            # run them concurrently rather than sequentially.
            async def _classify_one_atomic(i: int, atomic_claim: str):
                claim_evidence = [
                    ev for ev in all_evidence
                    if getattr(ev, "query_used", "").startswith(atomic_claim[:20])
                ] if i == 0 else all_evidence
                return await s3_orchestrator.process(
                    atomic_claim, claim_evidence or all_evidence,
                    db=db, run_id=run.run_id, locale=locale,
                )

            s3_results = await asyncio.gather(*[
                _classify_one_atomic(i, ac)
                for i, ac in enumerate(s1_result.atomic_claims)
            ])
            s3_results = list(s3_results)  # gather returns tuple

            # --- Stage 4: Verdict Aggregation ---
            from pipeline.stage4.orchestrator import Stage4Orchestrator
            s4_orchestrator = Stage4Orchestrator(sse_callback=self._emit)

            # Per-atomic verdicts are also independent — run concurrently.
            async def _verdict_one_atomic(s3r):
                return await s4_orchestrator.process(
                    s3r.atomic_claim, s3r, db=db, run_id=run.run_id, locale=locale,
                )

            s4_results = list(await asyncio.gather(*[
                _verdict_one_atomic(s3r) for s3r in s3_results
            ]))

            # --- Create ONE aggregated Verdict per run [C5] ---
            agg = self._create_aggregate_verdict(db, run.run_id, s4_results, s1_result.atomic_claims)

            log(f"PIPELINE: all stages complete, finalizing run as completed")
            # Fix any placeholder run_ids that slipped through (safety net)
            await self._fix_stage_run_ids(db, run.run_id)
            await self._finalize_run(run, "completed", started_at)
            await db.commit()
            await self._emit("verdict_complete", agg)
            log(f"PIPELINE: committed, emitted verdict_complete")
            record_claim_completed()

        except Exception as e:
            import traceback
            log(f"PIPELINE ERROR: {e}")
            log(f"PIPELINE TRACEBACK: {traceback.format_exc()}")
            try:
                await self._finalize_run(run, "failed", started_at)
                await db.commit()
                log(f"PIPELINE: committed failure status")
            except Exception as e2:
                log(f"PIPELINE: could not commit failure: {e2}")
            record_claim_failed()
            await self._emit("pipeline_error", {
                "run_id": str(self.run_id),
                "error": str(e),
            })
            raise

        return str(self.run_id)

    async def _fix_stage_run_ids(self, db: AsyncSession, run_id: uuid.UUID):
        """Set correct run_id on ALL records created by orchestrators.
        
        This is a safety net — orchestrators should use the correct run_id,
        but if any records were created with placeholder 00000000...,
        this fixes them before commit.
        Uses no_autoflush to prevent premature flush of pending inserts.
        """
        from sqlalchemy import update
        placeholder = uuid.UUID("00000000-0000-0000-0000-000000000000")
        
        with db.no_autoflush:
            # Fix StageRecord
            result = await db.execute(
                update(StageRecord)
                .where(StageRecord.run_id == placeholder)
                .values(run_id=run_id)
            )
            if result.rowcount:
                log(f"PIPELINE: fixed {result.rowcount} StageRecord(s) with placeholder run_id")
            
            # Fix Classification
            result = await db.execute(
                update(Classification)
                .where(Classification.run_id == placeholder)
                .values(run_id=run_id)
            )
            if result.rowcount:
                log(f"PIPELINE: fixed {result.rowcount} Classification(s) with placeholder run_id")
            
            # Fix Source (if any use run_id)
            try:
                result = await db.execute(
                    update(Source)
                    .where(Source.run_id == placeholder)
                    .values(run_id=run_id)
                )
                if result.rowcount:
                    log(f"PIPELINE: fixed {result.rowcount} Source(s) with placeholder run_id")
            except Exception:
                pass  # Source might not have run_id FK
            
            # Fix Verdict
            result = await db.execute(
                update(Verdict)
                .where(Verdict.run_id == placeholder)
                .values(run_id=run_id)
            )
            if result.rowcount:
                log(f"PIPELINE: fixed {result.rowcount} Verdict(s) with placeholder run_id")

    def _create_aggregate_verdict(
        self, db: AsyncSession, run_id: uuid.UUID,
        s4_results: list, atomic_claims: list[str],
    ) -> dict:
        """Create ONE Verdict per analysis run, aggregating all atomic claims.

        If all atomics agree on the same verdict label, a single aggregate is
        computed (majority, averaged confidence, merged distribution).

        If atomics disagree, the verdict is "MIXED" and every atomic result is
        surfaced individually so the user can see the split rather than a
        meaningless compromise.
        """
        from collections import Counter

        if not s4_results:
            db.add(Verdict(
                run_id=run_id,
                verdict="UNVERIFIABLE",
                confidence=0.0,
                explanation="No atomic claims were processed — claim could not be verified.",
                distribution={"TRUE": 0.0, "MOSTLY_TRUE": 0.0, "HALF_TRUE": 0.0,
                              "MOSTLY_FALSE": 0.0, "FALSE": 0.0, "PANTS_ON_FIRE": 0.0,
                              "UNVERIFIABLE": 1.0},
            ))
            return {"verdict": "UNVERIFIABLE", "confidence": 0.0,
                    "explanation": "No atomic claims were processed.",
                    "atomic_verdicts": []}

        # --- Build per-atomic summaries ---
        atomic_verdicts = []
        unique_labels: set[str] = set()
        for i, r in enumerate(s4_results):
            label = r.verdict
            unique_labels.add(label)
            atomic_verdicts.append({
                "index": i,
                "claim": atomic_claims[i] if i < len(atomic_claims) else "",
                "verdict": label,
                "confidence": r.confidence,
                "explanation": r.explanation,
                "distribution": r.distribution,
            })

        # --- If atomics disagree, surface ALL results ---
        if len(unique_labels) > 1:
            labels_str = ", ".join(sorted(unique_labels))
            explanation = (
                f"Atomic claims disagree ({labels_str}).  "
                f"See individual results below:\n"
                + "\n".join(
                    f"  Sub-claim {a['index']+1}: {a['verdict']} ({a['confidence']:.0%})"
                    for a in atomic_verdicts
                )
            )
            db.add(Verdict(
                run_id=run_id,
                verdict="MIXED",
                confidence=0.0,
                explanation=explanation,
                distribution={"TRUE": 0.0, "MOSTLY_TRUE": 0.0, "HALF_TRUE": 0.0,
                              "MOSTLY_FALSE": 0.0, "FALSE": 0.0, "PANTS_ON_FIRE": 0.0,
                              "UNVERIFIABLE": 0.0},
            ))
            log(f"PIPELINE: atomics disagree → MIXED verdict ({labels_str})")
            return {
                "verdict": "MIXED",
                "confidence": 0.0,
                "explanation": explanation,
                "atomic_verdicts": atomic_verdicts,
            }

        # --- All atomics agree — compute a single aggregate ---
        verdict_counts = Counter(r.verdict for r in s4_results)
        majority_verdict = verdict_counts.most_common(1)[0][0]

        avg_confidence = sum(r.confidence for r in s4_results) / len(s4_results)

        merged_dist: dict[str, float] = {}
        all_labels = ["TRUE", "MOSTLY_TRUE", "HALF_TRUE", "MOSTLY_FALSE",
                      "FALSE", "PANTS_ON_FIRE", "UNVERIFIABLE"]
        for label in all_labels:
            merged_dist[label] = sum(
                r.distribution.get(label, 0.0) for r in s4_results
            ) / len(s4_results)

        if len(s4_results) == 1:
            explanation = s4_results[0].explanation
        else:
            parts = [f"Atomic claim {i+1}: {r.verdict} ({r.confidence:.0%})"
                     for i, r in enumerate(s4_results)]
            explanation = (
                f"Aggregated from {len(s4_results)} atomic claims:\n"
                + "\n".join(parts)
                + f"\n\nOverall verdict: {majority_verdict}"
            )

        human_review = None
        for r in s4_results:
            if r.human_review:
                human_review = r.human_review
                break

        db.add(Verdict(
            run_id=run_id,
            verdict=majority_verdict,
            confidence=avg_confidence,
            explanation=explanation,
            distribution=merged_dist,
            retry_of=None,
            human_review=human_review,
        ))
        log(f"PIPELINE: created aggregate Verdict: {majority_verdict} (from {len(s4_results)} atomic claims)")
        return {
            "verdict": majority_verdict,
            "confidence": avg_confidence,
            "explanation": explanation,
            "distribution": merged_dist,
            "atomic_verdicts": atomic_verdicts,
        }

    async def _finalize_run(
        self, run: AnalysisRun, status: str, started_at: datetime
    ):
        """Mark analysis run as completed or failed."""
        run.status = status
        run.completed_at = datetime.utcnow()

    async def _emit(self, event_type: str, data: Dict[str, Any]):
        """Emit SSE event to frontend subscribers via the queue."""
        event = {
            "event": event_type,  # SSE protocol uses "event" key
            "data": data,
            "id": str(self.run_id) if self.run_id else "unknown",
            "timestamp": datetime.utcnow().isoformat(),
        }
        if self.sse_queue:
            await self.sse_queue.put(event)
        # Also publish via Redis for distributed SSE
        try:
            await redis_client.publish_event(
                f"pipeline:{self.run_id}", event
            )
        except Exception:
            pass  # Redis failure is non-critical for SSE


# Convenience function for FastAPI background tasks
async def execute_pipeline(
    claim_text: str,
    locale: str,
    user_id: Optional[uuid.UUID],
    db: AsyncSession,
    sse_queue: asyncio.Queue,
) -> str:
    """Run the pipeline as a background task. Returns run_id."""
    service = PipelineService(db, sse_queue)
    run_id = await service.run_pipeline(claim_text, locale, user_id)
    await db.commit()
    return run_id
