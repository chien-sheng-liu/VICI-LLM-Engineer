VICI LLM Gateway + Browser Agent
================================

Overview
--------

This repository delivers a small, production‑minded system combining:
- A FastAPI‑based LLM Gateway with an OpenAI‑compatible `/v1/chat/completions` endpoint
- A Playwright‑based research Agent that navigates to a URL, captures artifacts, and generates a report and slides
- A minimal React (TSX) frontend to trigger agent runs and show artifacts

Design emphasizes provider abstraction, structured JSON logs, strict safety boundaries, deterministic dry‑run, and verifiable artifacts. See `AGENTS.md` for the full spec.


Repository Layout (Refined)
---------------------------

- `backend/app` — FastAPI application
  - `main.py` — app factory, CORS, static mount for runs, middleware
  - `gateway.py` — `/health` and `/v1/chat/completions` routes
  - `agent_runner.py` — `/agent/run` and `/agent/status/{id}` (loads root agent.py)
  - `providers/` — provider abstraction + mock/openai/claude providers
  - `models.py` — Pydantic models for request/response
  - `config.py` — env‑driven configuration and safety caps
  - `logging_utils.py` — JSON logging
  - `middleware.py` — concurrency limiter
- `backend/tests` — pytest tests
- `agents/` — Modular agent package (new)
  - `news_agent.py` — per‑news micro summaries + event enrichment
  - `finance_agent.py` — sentiment, trader insights, overview, watchlist
  - `scoring.py` — confidence score combiner (LLM + heuristic)
- `agent.py` — Orchestrator/CLI: wires agents + artifacts
- `frontend` — React + TSX scaffold (Vite‑style)
- `runs` — Per‑run artifacts (served by backend at `/runs`)


Quickstart
----------

Prerequisites: Python 3.11+, pip; optional Node 18+ for frontend. All common flows are wrapped in the Makefile so you only need a few commands to stand everything up.

1. Install backend deps

       make install

2. Configure environment

       cp .env.example .env
       # Edit .env and set OPENAI_API_KEY=sk-...

3. Run the FastAPI gateway (default http://localhost:8000)

       make run-gateway

4. Launch the React frontend (hot reload on :5173)

       make run-frontend

5. Trigger the full Yahoo TW agent demo (headless Playwright, arguments baked in). The Makefile ensures the gateway is reachable first.

       make run-agent-demo     # CLI flow (writes to runs/<timestamp>)
       make showcase           # Gateway + CLI end-to-end

6. Orchestrate everything via Docker Compose (backend + frontend containers)

       make docker-up          # build + start
       make docker-logs        # tail both services
       make docker-down        # stop/remove

7. Run the entire test suite

       make test               # executes pytest backend/tests

Manual API usage remains available (POST /agent/run then GET /agent/status/{id}), but the Makefile covers the common development loop.


Gateway API
-----------

- Health
  - GET `/health`
  - Response: `{ "status": "ok", "version": "…", "timestamp": "…" }`

- Chat Completions (OpenAI‑compatible minimal)
  - POST `/v1/chat/completions`
  - Body example:

        {"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"Summarize: hello"}],"max_tokens":64,"temperature":0.2}

  - Returns: `choices[0].message.content`, `usage`, internal `request_id`, provider, latency, retry_count


Agent Runner API
----------------

- Start Run
  - POST `/agent/run`
  - Body:

        {"ticker":"AAPL","source":"https://example.com","model":"gpt-3.5-turbo","dry_run":true}

  - Returns: `{ "run_id": "…", "status": "running" }`

- Get Status
  - GET `/agent/status/{run_id}`
  - Returns: `status` (running/completed/error), `report_md_text`, `artifacts.slides_url`, `screenshots[]`
  - Artifacts served at `/runs/{run_id}/…`


Agent CLI
---------

Run the agent directly:

    python agent.py --ticker 2330 --source https://tw.stock.yahoo.com/ --gateway http://localhost:8000 --model gpt-3.5-turbo --yahoo

Artifacts per run:
- `outputs/report.md` — includes Source URL, Evidence snippet, extracted table (if any), Event Extraction, Sentiment/Surprise, Summary, Timestamp
  - 內容為繁體中文，聚焦最新股票研究重點
- `outputs/slides.pdf` — structured sections (Events, Sentiment/Surprise, Risks note) for quick review
- `outputs/checksums.txt` — sha256 hashes
- `run_logs/run.json` — ticker, source, steps, timings, artifact paths, request_ids (per LLM call), latency summary
- `run_logs/trace.zip` — Playwright trace (or fallback)
- `run_logs/screenshots/…` — screenshots
- `run_logs/console.log` — console logs captured during browsing
- `run_logs/llm_calls.jsonl` — JSONL for each LLM call (category, request_id, latency, usage)


Frontend
--------

Requires network to install Node packages.

    cd frontend
    npm install
    npm run dev

Docker Compose launches the frontend dev server on port 5173. Open http://localhost:5173.

Set Gateway URL in the left panel (default `http://localhost:8000`).
- Model: `gpt-3.5-turbo` (OpenAI)
- 系統會自動開啟 Yahoo 奇摩股市並搜尋輸入的台股代號。
- API key 由後端 `.env` 提供，前端無需輸入。
Click Run to trigger a backend run and view the structured report、screenshots、and logs.

Housekeeping
------------

- Tracked artifacts and caches removed: `.idea/`, `.DS_Store`, `__pycache__/`, `backend/runs/`.
- `.gitignore` now ignores: `runs/`, `backend/runs/`, Python caches, Node `node_modules/`, Vite `dist/`, logs, PDFs/zips, editor folders, and `.env`.
- Keep `.env.example` in version control; copy to `.env` locally for configuration.
- Runtime outputs are always written under per-run directories inside `runs/` and are served at `/runs/{run_id}/...`.

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
 - `USE_YFINANCE` (optional, 1/true to enable yfinance for OHLC/Volume/basic financials)


Observability & Safety
----------------------

- JSON logs include: `request_id`, `route`, `provider`, `model`, `latency_ms`, `retry_count`, `error`
- Safety boundaries: request size limit, per‑request timeout, concurrency limit, provider/model allowlists, retry limit ≤ 2


Agents Architecture
-------------------

- Orchestrator (`agent.py`)
  - Coordinates browse/extract, invokes sub‑agents, generates artifacts, writes run.json.
  - Provides a unified `call_gw` wrapper used by all sub‑agents to call the gateway with consistent timeout/logs.

- **News Agent** (`agents/news_agent.py`)
  - Scrapes Yahoo TW + Google News (dry-run friendly) and persists a deterministic `news.json` for traceability.
  - Summarizes each article via the gateway with sentiment, event type, market note, and confidence; deduplicates/annotates the events list shown in the UI.

- **Finance Agent** (`agents/finance_agent.py`)
  - Owns every finance-facing LLM prompt: sentiment surprise, research bullets, trader insights, watchlist generation, KPI impact per news item, and the structured `fin_analysis` JSON.
  - Operates purely through the gateway; no data scraping, keeping responsibilities clear.

- **Trader Agent** (`agents/trader_agent.py`)
  - Pure-Python technical analysis: EMA/MACD/RSI/Bollinger, volatility, alerts. Feeds `trader_signals` and expert commentary that populate the Report tab’s flow section even when LLMs are offline.

- **Report Agent** (`agents/report_agent.py`)
  - Consumes the entire context (KPIs, finance/trader output, news bullets, watchlist) to craft a chief-research-level Markdown narrative plus a digest of catalysts/watch focus for the Analysis tab.

- **YFinance Agent** (`agents/yfinance_agent.py`)
  - Single entry point for Yahoo Finance data: snapshot KPIs, intraday stats, price series, and Chinese company-name extraction. Provides deterministic empty payloads when yfinance is unavailable to keep dry-run reproducible.

- **RAG Agent** (`agents/rag_agent.py`)
  - Lightweight retrieval over curated research notes. Supplies additional catalysts and playbook references to the Analysis tab so researchers have a knowledge base without leaving the app.

- Scoring (`agents/scoring.py`)
  - `combine_confidence` → 將 LLM confidence 與啟發式（含數字/百分比、來源可信度）合併為 1–5 分。

Experimentation & JD Alignment
------------------------------

- **Signal → Backtest → Deploy loop**: `tools/backtesting/backtest_runner.py` demonstrates offline evaluation of strategy variants (momentum vs mean reversion) using reproducible price series. Swap in real `runs/<id>/run_logs` for heavier experiments and stitch into A/B workflows.
- **AI Agents + Tooling**: The orchestrator wires News/Finance/Trader/Report/RAG/YFinance agents, covering RAG, tool invocation, and task planning to accelerate strategy research (matching the JD’s “Design and build AI agents”).
- **Prompt Engineering hooks**: All LLM calls share `_call_gateway`, so adjusting prompts or routing to MoE/LoRA endpoints happens centrally (environment-driven provider selection). ReportAgent composes multi-agent context into a single prompt, demonstrating prompt-engineering best practices.
- **Financial-text alignment**: NewsAgent + FinanceAgent specialize on financial text (news, KPIs, guidance). Swapping the gateway provider to a fine-tuned SFT/DPO model is a one-line config change, and the structured schema ensures sentiment/event comprehension.
- **MLOps**: Containerization (Dockerfiles + docker-compose), CI/CD (GitHub Actions for test/build/lint), and artifact/version logging (per-run `run.json`, checksums, llm_calls) satisfy model/version traceability.
- **Frontier research ready**: RAGAgent’s corpus is JSON-driven; append new notes or research digests to propagate new techniques instantly. README + AGENTS.md document the architecture so sharing/tech talks stay grounded.

Backtesting CLI
---------------

Run a quick offline test of tradable signals:

    python tools/backtesting/backtest_runner.py

Swap `--data` to point at your own price history. Integrate this script in automated experiments or hook into CI for regression-style monitoring.

Mockups & Documentation
-----------------------

- `docs/mockups/model_output.md` stores narrative/visual mockups for interviews and UI planning. Drop additional mock screens or YAML payloads here to keep the repo root tidy.
- `tools/backtesting/` centralizes experimentation utilities so top-level clutter stays minimal.

Data Sources
------------

- Optional Yahoo Finance via yfinance
  - `agents/data_sources.py: fetch_yfinance_data(ticker)` enriches KPIs (OHLC/Volume/Market Cap/PE/PB/Dividend Yield) and `finance_basic` (margins/growth/EBITDA/revenue).
  - Requires network and `yfinance` installed. Enable by setting `USE_YFINANCE=1` in `.env`.

Why is `agent.py` at repo root?
- The backend runner dynamically loads root `agent.py` as the assignment requires a standalone CLI entry. Sub‑agents live in `agents/` to keep the orchestrator thin and maintainable.

UI Mapping
-----------

- Report（財務/交易員頁）
  - 財務分析（量化視角）：thesis、drivers、risks、metrics_to_watch、positioning、timeframe、expected_move_pct、confidence。
  - KPI 卡與基本財務（價格/OHLC/量、市值、PE/PB、殖利率）。
  - 交易員指標（trend/momentum/volume/composite 等）與觀測清單。
  - 不顯示新聞清單、事件列表、或整體新聞情緒（這些移至 News）。

- News（新聞頁）
  - 新聞概覽：情緒分佈、來源類別、財務關鍵字、代表新聞。
  - 逐則新聞：標題連結、1–2 句摘要、情緒/類型/情緒分數/信心、KPI 影響徽章。
  - 不顯示 KPI/估值卡或交易員指標（避免與 Report 重疊）。

- Trader HUD（視覺節奏）
  1. Trade Verdict — 交易結論＋Confidence/Timeframe/Expected Move/Composite。
  2. Market Structure — KPI + Profitability Snapshot，快速判讀基本面。
  3. Playbook — Thesis/Drivers/Risks/Positioning/Watch Metrics。
  4. Flow & Technicals — Trend/Momentum/Volume/Volatility 與關鍵價位。
  5. Radar/Triggers — 觀測清單對應指標/檢核動作。


Makefile Targets
----------------

- `make install` — install Python requirements
- `make test` — run pytest
- `make run-gateway` — start the FastAPI app
- `make run-agent-demo` — run the Yahoo TW agent (台股代號 2330)
- `make run-frontend` — guidance on launching frontend (local npm commands)
- `make docker-up` / `make docker-down` — compose up/down


Notes
-----

- In restricted environments without Playwright, the agent runs in dry‑run or fallback mode and still produces valid artifacts.
- The OpenAI and Claude providers are simulated locally (no network calls); the `mock` provider is used for tests and deterministic behavior.
