# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
Metrics API Routes — Prometheus Endpoint
==========================================
GET /api/v1/metrics  — Prometheus-compatible metrics

Exports pipeline metrics for Grafana dashboards:
  - claims_submitted_total
  - pipeline_duration_seconds (per stage)
  - classifications_total (per label)
  - cache_hit_ratio
  - sse_connections_active
  - llm_cost_usd_total
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


# In-memory metrics counters (replace with Prometheus client in Phase 8)
_metrics = {
    "claims_submitted_total": 0,
    "claims_completed_total": 0,
    "claims_failed_total": 0,
    "cache_hits_total": 0,
    "cache_misses_total": 0,
    "sse_connections_active": 0,
    "llm_cost_usd_total": 0.0,
}

# Per-stage latency histograms (approximate)
_stage_latencies: dict[str, list[float]] = {}
_classification_counts: dict[str, int] = {"SUPPORTS": 0, "REFUTES": 0, "UNRELATED": 0}


def record_claim_submitted():
    _metrics["claims_submitted_total"] += 1


def record_claim_completed():
    _metrics["claims_completed_total"] += 1


def record_claim_failed():
    _metrics["claims_failed_total"] += 1


def record_cache_hit():
    _metrics["cache_hits_total"] += 1


def record_cache_miss():
    _metrics["cache_misses_total"] += 1


def record_stage_latency(stage: str, ms: float):
    if stage not in _stage_latencies:
        _stage_latencies[stage] = []
    _stage_latencies[stage].append(ms)


def record_classification(label: str):
    if label in _classification_counts:
        _classification_counts[label] += 1


def record_llm_cost(cost: float):
    _metrics["llm_cost_usd_total"] += cost


@router.get("")
async def get_metrics():
    """Prometheus-compatible metrics endpoint."""
    lines = []

    # Counters
    lines.append(f"# HELP claims_submitted_total Total claims submitted")
    lines.append(f"# TYPE claims_submitted_total counter")
    lines.append(f"claims_submitted_total {_metrics['claims_submitted_total']}")

    lines.append(f"# HELP claims_completed_total Total claims completed")
    lines.append(f"# TYPE claims_completed_total counter")
    lines.append(f"claims_completed_total {_metrics['claims_completed_total']}")

    lines.append(f"# HELP claims_failed_total Total claims failed")
    lines.append(f"# TYPE claims_failed_total counter")
    lines.append(f"claims_failed_total {_metrics['claims_failed_total']}")

    # Cache
    total_cache = _metrics["cache_hits_total"] + _metrics["cache_misses_total"]
    hit_ratio = _metrics["cache_hits_total"] / max(total_cache, 1)
    lines.append(f"# HELP cache_hit_ratio Idempotency cache hit ratio")
    lines.append(f"# TYPE cache_hit_ratio gauge")
    lines.append(f"cache_hit_ratio {hit_ratio:.3f}")

    # SSE connections
    lines.append(f"# HELP sse_connections_active Active SSE connections")
    lines.append(f"# TYPE sse_connections_active gauge")
    lines.append(f"sse_connections_active {_metrics['sse_connections_active']}")

    # LLM cost
    lines.append(f"# HELP llm_cost_usd_total Total LLM API cost in USD")
    lines.append(f"# TYPE llm_cost_usd_total counter")
    lines.append(f"llm_cost_usd_total {_metrics['llm_cost_usd_total']:.4f}")

    # Classifications by label
    lines.append(f"# HELP classifications_total Total classifications by label")
    lines.append(f"# TYPE classifications_total counter")
    for label, count in _classification_counts.items():
        lines.append(f'classifications_total{{label="{label}"}} {count}')

    # Stage latencies (avg)
    for stage, latencies in _stage_latencies.items():
        if latencies:
            avg = sum(latencies) / len(latencies)
            lines.append(f"# HELP stage_latency_ms_avg Average latency per stage")
            lines.append(f"# TYPE stage_latency_ms_avg gauge")
            lines.append(f'stage_latency_ms_avg{{stage="{stage}"}} {avg:.2f}')

    return PlainTextResponse("\n".join(lines) + "\n")
