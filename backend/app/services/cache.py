# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Redis Cache Service [C7]
=========================
Idempotency guard, verdict cache, rate limiting, and SSE pub/sub.
Uses Redis 7.2 (Upstash-compatible API).
"""

import hashlib
import json
from typing import Optional
from datetime import timedelta

import redis.asyncio as aioredis
from app.core.config import settings


class RedisCache:
    """Async Redis client for idempotency, verdict cache, and rate limiting."""

    def __init__(self):
        self.client: Optional[aioredis.Redis] = None

    async def connect(self):
        """Initialize Redis connection pool."""
        self.client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await self.client.ping()
        print(f"Redis connected: {settings.REDIS_URL}")

    async def disconnect(self):
        """Gracefully close Redis connection."""
        if self.client:
            await self.client.close()

    # --- Idempotency Guard [C7] ---

    @staticmethod
    def claim_hash(claim_text: str) -> str:
        """SHA-256 hash of normalized claim text."""
        normalized = " ".join(claim_text.lower().strip().split())
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def is_duplicate(self, claim_text: str) -> Optional[dict]:
        """Check if claim was already processed. Returns cached verdict or None."""
        h = self.claim_hash(claim_text)
        # Check processing lock
        lock = await self.client.get(f"idempotency:{h}")
        if lock == "processing":
            return {"status": "processing", "cached": False}
        # Check verdict cache
        cached = await self.client.get(f"claim:{h}")
        if cached:
            return {"status": "complete", "cached": True, "verdict": json.loads(cached)}
        return None

    async def mark_processing(self, claim_text: str):
        """Set idempotency lock — claim is being processed."""
        h = self.claim_hash(claim_text)
        await self.client.set(
            f"idempotency:{h}",
            "processing",
            ex=settings.IDEMPOTENCY_LOCK_TTL_SECONDS,
        )

    async def cache_verdict(self, claim_text: str, verdict_data: dict):
        """Cache the final verdict for future idempotency checks."""
        h = self.claim_hash(claim_text)
        await self.client.set(
            f"claim:{h}",
            json.dumps(verdict_data),
            ex=settings.VERDICT_CACHE_TTL_SECONDS,
        )
        # Clear the processing lock
        await self.client.delete(f"idempotency:{h}")

    # --- Rate Limiting (token bucket) ---

    async def check_rate_limit(self, user_id: str) -> bool:
        """Returns True if request is allowed, False if rate limited."""
        key = f"rate:{user_id}"
        current = await self.client.get(key)
        if current is None:
            await self.client.set(key, 1, ex=60)  # 1-minute window
            return True
        count = int(current)
        if count >= settings.RATE_LIMIT_PER_USER:
            return False
        await self.client.incr(key)
        return True

    # --- SSE Pub/Sub ---

    async def publish_event(self, channel: str, event_data: dict):
        """Publish a pipeline event for SSE subscribers."""
        await self.client.publish(channel, json.dumps(event_data))


# Singleton
redis_client = RedisCache()
