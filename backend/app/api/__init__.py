# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

# API routes package
#   claims.py      — POST /claims, GET /claims/{run_id}/stream (SSE)
#   verdicts.py    — GET /verdicts/{run_id} (polling fallback)
#   audit.py       — GET /audit/{run_id} (full forensic trail [C5])
#   discussions.py — POST /discussions/{verdict_id}/posts, POST /discussions/{post_id}/votes (UI3)
#   feedback.py    — POST /feedback (Loop 3 input)
#   replay.py      — GET /replay/{run_id} (Replay Engine [C5])
#   metrics.py     — GET /metrics (Prometheus endpoint)
