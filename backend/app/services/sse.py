# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
SSE (Server-Sent Events) Infrastructure
========================================
Manages per-run_id asyncio.Queue for streaming pipeline events
to frontend subscribers in real-time.

Each analysis run gets its own queue. SSE endpoint reads from
the queue and pushes events to the EventSource connection.
"""

import asyncio
from typing import Dict
from datetime import datetime


class SSEManager:
    """
    Manages SSE event queues per pipeline run.

    Flow:
      1. POST /claims creates run_id → SSEManager creates queue
      2. Pipeline emits events → pushed to queue
      3. GET /claims/{run_id}/stream → reads from queue, yields SSE
      4. On pipeline complete → queue closed, subscribers disconnected
    """

    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}

    def create_queue(self, run_id: str) -> asyncio.Queue:
        """Create a new SSE event queue for a pipeline run."""
        queue = asyncio.Queue(maxsize=100)
        self._queues[run_id] = queue
        return queue

    def get_queue(self, run_id: str) -> asyncio.Queue | None:
        """Get the SSE queue for a run, or None if not found."""
        return self._queues.get(run_id)

    def remove_queue(self, run_id: str):
        """Remove the queue when the pipeline completes."""
        self._queues.pop(run_id, None)

    async def push_event(self, run_id: str, event_type: str, data: dict):
        """Push a pipeline event to the SSE queue."""
        queue = self._queues.get(run_id)
        if queue is None:
            return

        event = {
            "event": event_type,
            "data": data,
            "id": run_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await queue.put(event)


# Singleton
sse_manager = SSEManager()


async def sse_event_generator(run_id: str):
    """
    Async generator that yields SSE-formatted events for a run.

    Usage (FastAPI StreamingResponse):
        return StreamingResponse(
            sse_event_generator(run_id),
            media_type="text/event-stream",
        )
    """
    queue = sse_manager.get_queue(run_id)
    if queue is None:
        # Run already completed or doesn't exist — send cached result
        yield f"event: pipeline_complete\ndata: {{\"run_id\": \"{run_id}\", \"status\": \"not_found\"}}\n\n"
        return

    yield f"event: connected\ndata: {{\"run_id\": \"{run_id}\"}}\n\n"

    while True:
        try:
            # Wait for next event with 30s heartbeat timeout
            event = await asyncio.wait_for(queue.get(), timeout=30.0)
            event_type = event["event"]
            data = event["data"]

            # Format as SSE
            import json
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

            # Close connection on terminal events
            if event_type in ("verdict_complete", "pipeline_error"):
                break

        except asyncio.TimeoutError:
            # Send heartbeat to keep connection alive
            yield f": heartbeat\n\n"
