# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Observability Sidecar — LangSmith + Prometheus + Grafana
===========================================================
LangSmith: traces every DSPy LLM call (input/output/latency/cost)
Prometheus: system metrics for Grafana dashboards
Grafana: pre-built dashboard JSON for pipeline monitoring
"""

import os
import time
import functools
from typing import Optional
from datetime import datetime


# ============================================================
# LangSmith Tracing
# ============================================================

class LangSmithTracer:
    """
    Traces every LLM call in the DSPy pipeline.

    Requires LANGSMITH_API_KEY in environment.
    Automatically integrated with DSPy via environment variables:
      LANGCHAIN_TRACING_V2=true
      LANGCHAIN_PROJECT=piste
    """

    @staticmethod
    def configure():
        """Configure LangSmith environment variables for DSPy integration."""
        from app.core.config import settings

        if settings.LANGSMITH_API_KEY:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
            os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT

    @staticmethod
    def trace_call(func):
        """Decorator to trace individual pipeline function calls."""

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.monotonic() - start) * 1000
                LangSmithTracer._record(func.__name__, elapsed, "success")
                return result
            except Exception as e:
                elapsed = (time.monotonic() - start) * 1000
                LangSmithTracer._record(func.__name__, elapsed, f"error: {e}")
                raise

        return wrapper

    @staticmethod
    def _record(name: str, latency_ms: float, status: str):
        """Record a trace event (in production, send to LangSmith API)."""
        # DSPy + LangSmith integration handles this automatically
        # when LANGCHAIN_TRACING_V2 is set
        pass


langsmith_tracer = LangSmithTracer()


# ============================================================
# Grafana Dashboard JSON
# ============================================================

GRAFANA_DASHBOARD = {
    "title": "Piste — Pipeline Monitoring",
    "uid": "piste-pipeline",
    "panels": [
        {
            "title": "Claims Submitted",
            "type": "stat",
            "targets": [{"expr": "claims_submitted_total"}],
            "gridPos": {"x": 0, "y": 0, "w": 6, "h": 4},
        },
        {
            "title": "Claims Completed",
            "type": "stat",
            "targets": [{"expr": "claims_completed_total"}],
            "gridPos": {"x": 6, "y": 0, "w": 6, "h": 4},
        },
        {
            "title": "Cache Hit Ratio",
            "type": "gauge",
            "targets": [{"expr": "cache_hit_ratio"}],
            "gridPos": {"x": 12, "y": 0, "w": 6, "h": 4},
            "fieldConfig": {
                "defaults": {
                    "thresholds": {
                        "steps": [
                            {"value": 0, "color": "red"},
                            {"value": 0.3, "color": "yellow"},
                            {"value": 0.7, "color": "green"},
                        ]
                    }
                }
            },
        },
        {
            "title": "Active SSE Connections",
            "type": "stat",
            "targets": [{"expr": "sse_connections_active"}],
            "gridPos": {"x": 18, "y": 0, "w": 6, "h": 4},
        },
        {
            "title": "LLM Cost (USD)",
            "type": "stat",
            "targets": [{"expr": "llm_cost_usd_total"}],
            "gridPos": {"x": 0, "y": 4, "w": 6, "h": 4},
        },
        {
            "title": "Pipeline Duration (seconds)",
            "type": "timeseries",
            "targets": [{"expr": "pipeline_duration_seconds"}],
            "gridPos": {"x": 6, "y": 4, "w": 18, "h": 8},
        },
        {
            "title": "Classifications by Label",
            "type": "bargauge",
            "targets": [
                {"expr": 'classifications_total{label="SUPPORTS"}'},
                {"expr": 'classifications_total{label="REFUTES"}'},
                {"expr": 'classifications_total{label="UNRELATED"}'},
            ],
            "gridPos": {"x": 0, "y": 12, "w": 12, "h": 6},
        },
        {
            "title": "Stage Latencies (ms avg)",
            "type": "bargauge",
            "targets": [{"expr": "stage_latency_ms_avg"}],
            "gridPos": {"x": 12, "y": 12, "w": 12, "h": 6},
        },
        {
            "title": "Claims Failed",
            "type": "stat",
            "targets": [{"expr": "claims_failed_total"}],
            "gridPos": {"x": 0, "y": 18, "w": 6, "h": 4},
        },
    ],
    "refresh": "10s",
    "schemaVersion": 38,
    "tags": ["piste", "fact-checking", "pipeline"],
}
