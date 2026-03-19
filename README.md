LLM Gateway + Browser Automation Agent
==========================================

Overview
--------

Production‑style system combining:
- FastAPI LLM Gateway with OpenAI‑compatible `/v1/chat/completions`
- Playwright Browser Agent producing verifiable artifacts
- Minimal React (TSX) frontend for triggering runs and viewing results

Design principles: strict provider abstraction, JSON structured logs, safety boundaries, deterministic dry‑run, and traceable per‑run artifacts. The full, authoritative spec lives in `AGENTS.md`.


Repository Layout
-----------------

- `backend/app` — FastAPI app, routers, providers, middleware, models
  - `main.py` app factory, CORS, static mount for `/runs`
  - `gateway.py` `/health`, `/v1/chat/completions`
  - `agent_runner.py` `/agent/run`, `/agent/status/{id}` (invokes root `agent.py`)
  - `providers/` provider abstraction + `mock.py`, `openai.py`, `claude_cli.py`
  - `models.py`, `config.py`, `logging_utils.py`, `middleware.py`
- `backend/tests` — pytest for gateway and agent runner
- `agent.py` — standalone CLI orchestrator
- `agents/` — sub‑agents (`news_agent.py`, `finance_agent.py`, `trader_agent.py`, `yfinance_agent.py`)
- `safety/` — safeguard guard layer (prompt/response scanning, redaction)
- `frontend/` — React + TSX minimal UI
- `runs/` — per‑run directories served by backend
  - Each run creates `runs/<run_id>/outputs/` and `runs/<run_id>/run_logs/`


Quickstart
----------

Prerequisites: Python 3.11+, pip; optional Node 18+ for frontend.

1) Install dependencies

       make install

2) Configure environment

       cp .env.example .env
       # Set provider keys if needed; mock provider works without keys

3) Start backend gateway (http://localhost:8000)

       make run-gateway

4) Run the demo agent (headless, deterministic dry‑run)

       make run-agent-demo   # writes artifacts under runs/<run_id>/

5) Frontend (local dev)

       make run-frontend     # shows how to run Vite dev server
       # Or via Docker Compose (see below)

6) Tests

       make test             # pytest under backend/tests


Gateway
-------

- GET `/health`
  - Returns `{status, version, timestamp}`

- POST `/v1/chat/completions` (OpenAI‑compatible minimal)
  - Input: `{ model, messages[], temperature?, max_tokens? }`
  - Returns: `choices[0].message.content`, `usage`, `request_id`, `provider`, `retry_count`, `meta`, `created`
  - Enforces: request size limit, timeout, concurrency limit, provider/model allowlists, retry limit (≤2)
  - Logs JSON lines with: `request_id, route, provider, model, latency_ms, retry_count, error`

Provider Abstraction
--------------------

- Interface: `generate(messages, temperature, max_tokens) -> (text, usage, meta)`
- Implementations: `providers/mock.py`, `providers/openai.py`, `providers/claude_cli.py`
- Routes never call providers directly — they go through the abstraction and safety guard.

Safety Guard
------------

- `safety/` provides prompt/response scanning and redaction
- Config via `GATEWAY_SAFEGUARD_*` and `AGENT_SAFEGUARD_*` env vars
- Fail‑open redaction or fail‑closed blocking supported; audits optionally to JSONL
- Tests simulate cases via the mock provider (e.g., timeout, retry, secret leak)


Agent
-----

CLI
- `python agent.py --ticker AAPL --source https://example.com --gateway http://localhost:8000 --model mock-01 --dry-run`
- Yahoo TW mode: pass a ticker and open `https://tw.stock.yahoo.com/`, search, navigate to quote page

Workflow
1. Launch headless browser
2. Navigate to source (or Yahoo TW search flow)
3. Extract main content
4. Save screenshots
5. Save `trace.zip`
6. Call Gateway endpoint
7. Generate `report.md` and `slides.pdf`
8. Save structured `run.json`

Artifacts (per run)
- `runs/<run_id>/outputs/report.md` — includes Source URL, LLM summary, Timestamp（重點以財務/交易員觀點撰寫）
- `runs/<run_id>/outputs/slides.pdf`
- `runs/<run_id>/outputs/checksums.txt` — sha256 for all artifacts
- `runs/<run_id>/run_logs/run.json` — ticker, source, steps, timings, artifacts, model, latency summary, `safety_events`
- `runs/<run_id>/run_logs/trace.zip` — Playwright trace
- `runs/<run_id>/run_logs/screenshots/`
- `runs/<run_id>/run_logs/llm_calls.jsonl`, `console.log`

Determinism
- Dry‑run yields stable outputs without network; YFinance agent returns empty structures when offline


Frontend
--------

Layout and required components:
- Left panel: ticker, source URL, model selector, run button
- Right tabs: Report, News, Logs, History
- Components: `Layout.tsx`, `RunForm.tsx`, `RunStatus.tsx`, `ArtifactViewer.tsx` (Report view), `NewsViewer.tsx`, `LogViewer.tsx`

Content boundaries（重要）
- Report tab only renders: `sections.fin_analysis`, `sections.trader_signals`, `sections.kpis`, `sections.finance_basic`, `sections.watch_items`
- News tab only renders: `sections.news`, `sections.news_micro`（情緒/來源/關鍵字/逐則新聞）
- No duplication across tabs; enforced in components


Testing
-------

Gateway
- `/health` returns ok
- `/v1/chat/completions` schema valid
- Retry logic exercised (mock provider triggers a single failure)
- Timeout behavior returns 408
- Safety: prompt blocked, response sanitized (redacted)

Agent
- Dry‑run mode produces artifacts
- `report.md` and `run.json` created
- Sections integrity: `news`/`news_micro` for News; `fin_analysis`/`trader_signals` for Report

Run tests:

    make test


Docker & Makefile
-----------------

Make targets
- `make install`, `make test`
- `make run-gateway`, `make run-agent-demo`, `make run-frontend`
- `make docker-up`, `make docker-down`, `make docker-logs`

Compose services
- `backend` on `:8000`
- `frontend` on `:5173`


Configuration
-------------

See `backend/app/config.py` for defaults.
- `GATEWAY_VERSION`
- `GATEWAY_REQUEST_TIMEOUT_S`
- `GATEWAY_MAX_RETRIES` (capped at 2)
- `GATEWAY_MAX_INPUT_CHARS`
- `GATEWAY_MAX_CONCURRENCY`
- `GATEWAY_ALLOWED_PROVIDERS`
- `GATEWAY_ALLOWED_MODELS`
- `AGENT_TIMEOUT_S`
- `AGENT_MODEL`


Acceptance Checklist
--------------------

- [ ] Gateway endpoints implemented and pass tests
- [ ] Provider abstraction with mock/openai/claude
- [ ] JSON logs with required fields
- [ ] Safety boundaries enforced
- [ ] Agent CLI produces report.md, slides.pdf, run.json, screenshots, trace.zip
- [ ] Frontend triggers run, polls status, shows artifacts and logs
- [ ] Docker + Makefile targets work
- [ ] Report and News tabs have no duplicated content


Troubleshooting
---------------

- If Playwright is unavailable, run with `--dry-run` (demo target already does) — artifacts are still produced
- Mock provider requires no network keys; OpenAI/Claude need keys via `.env`
- Frontend dev server requires network for `npm install` on first run

