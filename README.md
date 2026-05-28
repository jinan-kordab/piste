# Piste — AI Fact-Checking Pipeline

> **Piste** (French for "trail") — every claim leaves a complete, replayable forensic audit trail.

A multilingual fact-checking platform that combines LLMs, blind web retrieval, and an append-only audit ledger. Built with DSPy, FastAPI, PostgreSQL, Redis, and vanilla JavaScript.

---

## Why Piste?

Most fact-checking tools search with the claim itself — baking in confirmation bias. **Piste is different:**

- 🕶️ **Blind by design** — the retrieval engine never sees the original claim. No confirmation bias. Period.
- 🔒 **Immutable audit trail** — every LLM call, every source, every vote is INSERT-only. Replay any verdict.
- 🇨🇦 **Built for Canada & Québec** — bilingual EN/FR pipeline pre-configured for federal + provincial political discourse.
- ⚙️ **Configurable** — currently tuned for political fact-checking, but the pipeline accepts any domain. Swap the search domains and criticality keywords, and you're checking science, health, or finance claims.

---

## Architecture

Designed and implemented by **Jinan Kordab**, 2026.

The pipeline runs in four stages, each leaving an immutable record:

```
Claim → Stage 1 (Check-Worthiness + Atomic Decomposition)
     → Stage 2 (Blind Web Retrieval — Tavily + Serper + Google CSE)
     → Stage 3 (Per-Source Classification — asyncio parallel)
     → Stage 4 (Verdict Aggregation — 7-way PolitiFact scale)
     → Append-Only Audit Ledger (PostgreSQL)
```

Key architectural properties:
- **Blind retrieval** — Stage 2 never sees the original claim. Prevents confirmation bias at the architecture level.
- **Immutable audit trail** — Every LLM call, every source, every classification is INSERT-only. Replay any historical run.
- **Multi-provider search** — Tavily (AI search) + Serper (Google proxy) aggregated concurrently with graceful fallback.
- **Bilingual** — Full EN/FR support across UI, pipeline stages, verdict labels, and LLM-generated explanations.

```mermaid
flowchart LR
    A[Claim] --> B[Stage 1<br/>Check-Worthiness]
    B --> C[Stage 2<br/>Blind Retrieval]
    C --> D[Stage 3<br/>Classification]
    D --> E[Stage 4<br/>Verdict]
    E --> F[(Audit Ledger)]
```

**[View full architecture →](FINAL.mermaid)**

---

## Screenshots

**Claim verdict — French (Québec political fact-checking):**

![FR Verdict](screenshot-fr-verdict.png)

**Replay & Audit — comparing pipeline versions:**

![FR Replay](screenshot-fr-replay.png)

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Python 3.12+](https://www.python.org/downloads/) (for the frontend HTTP server)
- API keys (see [API Keys Required](#api-keys-required) below)

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/piste.git
cd piste
cp .env.example .env
```

Edit `.env` and add your API keys:
- `DEEPSEEK_API_KEY` — required (LLM)
- `TAVILY_API_KEY` or `SERPER_API_KEY` — at least one required (web search)

### 2. Start the backend

```bash
docker compose -f docker/docker-compose.yml up -d
```

This starts three containers:
- **PostgreSQL 16** — append-only audit ledger (port 5432)
- **Redis 7.2** — idempotency guard + verdict cache (port 6379)
- **FastAPI backend** — pipeline + API (port 8000)

The backend automatically runs `alembic upgrade head` on startup, so the
schema is provisioned on first boot. If you ever need to apply migrations
manually (e.g. after editing a revision), run:

```bash
docker compose -f docker/docker-compose.yml exec backend alembic upgrade head
```

Verify:
```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

### 3. Start the frontend

```bash
cd frontend
python -m http.server 3000
```

Open **http://localhost:3000** — the entire UI is a single `index.html` file. No build step, no npm, no node_modules.

### 4. Submit a claim

Type a claim in the textarea (English or French) and click **Fact-Check Claim**. The pipeline runs in ~40 seconds — watch the SSE progress bar as it moves through each stage.

---

## API Keys Required

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `DEEPSEEK_API_KEY` | https://platform.deepseek.com/api_keys | ✅ Required |
| `TAVILY_API_KEY` | https://app.tavily.com/home | ⚠️ One search provider required |
| `SERPER_API_KEY` | https://serper.dev/ | ⚠️ One search provider required |
| `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_ID` | https://console.cloud.google.com/apis/library/customsearch.googleapis.com | Optional fallback |

**Minimum setup**: DeepSeek + either Tavily or Serper. Without these, the pipeline cannot function.

---

## Project Structure

```text
piste/
├── README.md
├── LICENSE                    # MIT License
├── FINAL.mermaid              # Architecture diagram
├── .gitignore
├── .dockerignore
├── .env.example               # Template — copy to .env
├── docker/
│   ├── docker-compose.yml     # PostgreSQL + Redis + Backend + Frontend
│   ├── Dockerfile.backend
│   └── Dockerfile.frontend
├── frontend/
│   └── index.html             # Single-page vanilla JS UI
├── backend/
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/               # Database migrations
│   └── app/
│       ├── main.py            # FastAPI entry point
│       ├── api/               # REST endpoints (claims, verdicts, audit, replay, etc.)
│       ├── core/              # Config, middleware, debug logging
│       ├── db/                # SQLAlchemy models, session, base
│       ├── models/            # Pydantic schemas
│       └── services/          # Pipeline service, SSE, caching, observability
└── pipeline/
    ├── compiler.py            # DSPy configuration + compiler
    ├── replay_engine.py       # Replay historical claims
    ├── stage1/                # Check-worthiness + atomic decomposition
    ├── stage2/                # Blind web retrieval (multi-provider)
    ├── stage3/                # Per-source classification
    ├── stage4/                # Verdict aggregation + criticality gate
    ├── signatures/            # DSPy typed signatures
    ├── offline/               # VERIFAID offline dataset pipeline
    └── replay.py              # Replay utility
```

---

## How It Works

### Stage 1 — Claim Processing
- **1a: Check-Worthiness** — 3-vote LLM consensus classifies the claim as CFC (Check-worthy Factual Claim), UFC (Unimportant), or NFC (Non-Factual). Non-factual claims stop here.
- **1b: Atomic Decomposition** — Breaks compound claims into independent sub-claims. "Poilievre plans to abolish foreign aid and cut taxes" → two separate verifiable claims.

### Stage 2 — Blind Retrieval
- **2a: Search Decision** — LLM decides if web search is needed and generates neutral queries. The retriever NEVER sees the original claim.
- **2b: Web Search** — Queries run concurrently across Tavily, Serper, and Google CSE. Results are merged and deduplicated by URL. French claims get French-language sources.

### Stage 3 — Per-Source Classification
Each source is independently classified as SUPPORTS, REFUTES, or UNRELATED to the claim. Classifications run in parallel via `asyncio.gather`. This prevents cross-contamination — one source's rating doesn't influence another's.

### Stage 4 — Verdict Aggregation
- **4a: Criticality Gate** — High-stakes claims are flagged for human review.
- **4b: Verdict Aggregator** — Synthesizes all classifications into a 7-way PolitiFact-aligned verdict (True → Pants on Fire) with a probability distribution and natural-language explanation.

### Audit & Replay
Every pipeline run leaves an immutable forensic trail in PostgreSQL. Click **Audit Trail** to see every stage's input/output snapshots, every source retrieved, and every classification decision. Click **Replay** to re-run the claim through the current pipeline and see a side-by-side comparison.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM Framework** | DSPy 2.6 over LiteLLM |
| **Model** | DeepSeek (`deepseek-chat`) |
| **Backend** | FastAPI 0.115 + Uvicorn |
| **Database** | PostgreSQL 16 (append-only audit ledger) |
| **Cache** | Redis 7.2 (idempotency + verdict cache) |
| **Search** | Tavily + Serper + Google CSE (aggregated) |
| **Frontend** | Single-file vanilla JS, served by Python http.server |
| **Containerization** | Docker Compose (3 services) |

---

## License

MIT License. See [`LICENSE`](LICENSE).

Copyright (c) 2026 Jinan Kordab.

---

*Piste — every verdict leaves a trail.*
