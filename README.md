VICI LLM Gateway + Browser Agent
================================

Overview
--------

This repository delivers a small, production‑minded system combining:
- A FastAPI‑based LLM Gateway with an OpenAI‑compatible `/v1/chat/completions` endpoint
- A Playwright‑based research Agent that navigates to a URL, captures artifacts, and generates a report and slides
- A minimal React (TSX) frontend to trigger agent runs and show artifacts

Design emphasizes provider abstraction, structured JSON logs, strict safety boundaries, deterministic dry‑run, and verifiable artifacts. See `AGENTS.md` for the full spec.


Repository Layout
-----------------

- `backend/app` — FastAPI application
  - `main.py` — app factory, CORS, static mount for runs, middleware
  - `gateway.py` — `/health` and `/v1/chat/completions` routes
  - `agent_runner.py` — `/agent/run` and `/agent/status/{id}`
  - `providers/` — provider abstraction + mock/openai/claude providers
  - `models.py` — Pydantic models for request/response
  - `config.py` — env‑driven configuration and safety caps
  - `logging_utils.py` — JSON logging
  - `middleware.py` — concurrency limiter
- `backend/tests` — pytest tests
- `agent.py` — Agent CLI with dry‑run and artifact creation
- `frontend` — React + TSX scaffold (Vite‑style)
- `runs` — Per‑run artifacts (served by backend at `/runs`)


Quickstart
----------

Prerequisites: Python 3.11+, pip; optional Node 18+ for frontend.

1) Install Python deps

    make install

2) Run tests

    make test

3) Start gateway (localhost:8000)

    make run-gateway

4) Trigger an agent run (dry‑run from CLI)

    make run-agent-demo

5) Docker (backend + frontend)

    # Requires Docker Desktop (or a compatible daemon) running
    make up           # build and start both services
    make docker-logs  # tail logs for both
    make down         # stop and remove containers


Gateway API
-----------

- Health
  - GET `/health`
  - Response: `{ "status": "ok", "version": "…", "timestamp": "…" }`

- Chat Completions (OpenAI‑compatible minimal)
  - POST `/v1/chat/completions`
  - Body example:

        {"model":"mock-01","messages":[{"role":"user","content":"Summarize: hello"}],"max_tokens":64,"temperature":0.2}

  - Returns: `choices[0].message.content`, `usage`, internal `request_id`, provider, latency, retry_count


Agent Runner API
----------------

- Start Run
  - POST `/agent/run`
  - Body:

        {"ticker":"AAPL","source":"https://example.com","model":"mock-01","dry_run":true}

  - Returns: `{ "run_id": "…", "status": "running" }`

- Get Status
  - GET `/agent/status/{run_id}`
  - Returns: `status` (running/completed/error), `report_md_text`, `artifacts.slides_url`, `screenshots[]`
  - Artifacts served at `/runs/{run_id}/…`


Agent CLI
---------

Run the agent directly:

    python agent.py --ticker AAPL --source https://example.com --gateway http://localhost:8000 --model mock-01 --dry-run

Artifacts per run:
- `outputs/report.md` — includes Source URL, Evidence snippet, LLM summary, Timestamp
- `outputs/slides.pdf` — minimal single‑page PDF
- `outputs/checksums.txt` — sha256 hashes
- `run_logs/run.json` — ticker, source, steps, timings, artifact paths, request_ids, latency summary
- `run_logs/trace.zip`, `run_logs/screenshots/…`


Frontend
--------

Requires network to install Node packages.

    cd frontend
    npm install
    npm run dev

Docker Compose launches the frontend dev server on port 5173. Open http://localhost:5173.

Set Gateway URL in the left panel (default `http://localhost:8000`). Click Run to trigger a backend run and view report/slides/screenshots.

Troubleshooting
---------------

- Docker not running: start Docker Desktop and retry `make up`.
- Compose warning about `version`: removed; Compose v2 auto-detects features.
- Frontend container build: uses `npm install` (no lockfile). For reproducibility, you can add a lockfile and switch to `npm ci`.


Configuration
-------------

Environment variables (see `backend/app/config.py` for defaults):
- `GATEWAY_VERSION`
- `GATEWAY_REQUEST_TIMEOUT_S`
- `GATEWAY_MAX_RETRIES` (capped at 2)
- `GATEWAY_MAX_INPUT_CHARS`
- `GATEWAY_MAX_CONCURRENCY`
- `GATEWAY_ALLOWED_PROVIDERS`
- `GATEWAY_ALLOWED_MODELS`
- `AGENT_TIMEOUT_S`
- `AGENT_MODEL`


Observability & Safety
----------------------

- JSON logs include: `request_id`, `route`, `provider`, `model`, `latency_ms`, `retry_count`, `error`
- Safety boundaries: request size limit, per‑request timeout, concurrency limit, provider/model allowlists, retry limit ≤ 2


Makefile Targets
----------------

- `make install` — install Python requirements
- `make test` — run pytest
- `make run-gateway` — start the FastAPI app
- `make run-agent-demo` — run the agent in dry‑run mode
- `make run-frontend` — guidance on launching frontend (local npm commands)
- `make docker-up` / `make docker-down` — compose up/down


Notes
-----

- In restricted environments without Playwright, the agent runs in dry‑run or fallback mode and still produces valid artifacts.
- The OpenAI and Claude providers are simulated locally (no network calls); the `mock` provider is used for tests and deterministic behavior.
