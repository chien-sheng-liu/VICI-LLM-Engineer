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

Prerequisites: Python 3.11+, pip; optional Node 18+ for frontend.

1) Install Python deps

    make install

2) Run tests

    make test

3) Configure environment

    cp .env.example .env
    # Edit .env and set OPENAI_API_KEY=sk-...

4) Start gateway (localhost:8000)

    make run-gateway

5) Trigger an agent run（官方 Yahoo 流程）

    - API flow (backend must be running):
      - Start backend as above, then:
        curl -X POST http://localhost:8000/agent/run \
          -H 'Content-Type: application/json' \
          -d '{"ticker":"2330","source":"https://tw.stock.yahoo.com/","model":"gpt-3.5-turbo","dry_run":true,"yahoo":true}'
      - Poll status: curl http://localhost:8000/agent/status/<run_id>
    - CLI flow:
        python agent.py --ticker 2330 --source https://tw.stock.yahoo.com/ --gateway http://localhost:8000 --model gpt-3.5-turbo --yahoo
    - One-command showcase:
        make showcase   # 先啟動 backend，再執行此指令即可跑完整流程

6) Docker (backend + frontend)

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

- News Agent (`agents/news_agent.py`)
  - `summarize_single_news` → 1–2 句摘要、情緒、分相（market_note）、事件類型、信心分數。
  - `enrich_or_build_events` → 以每則新聞摘要建立/強化事件清單，去重與摘要去重。
   - `collect_news` → 整合 Google News + Yahoo 個股新聞，寫入 run_logs/news.json。

- Finance Agent (`agents/finance_agent.py`)
  - `analyze_sentiment`、`overview_bullets`、`trader_insights`、`watchlist`。
   - `analyze_financials` → 以新聞摘要 + KPI 產出量化/財務結論（thesis、drivers、risks、positioning、metrics_to_watch、timeframe、expected_move_pct、confidence）。

- Trader Agent (`agents/trader_agent.py`)
  - 不透過 LLM，改以技術/量化指標（SMA/EMA/MACD/RSI/Bollinger）計算 `trader_signals` 與 `insights`，供 Report 分頁顯示 Flow Snapshot。

- Report Agent (`agents/report_agent.py`)
  - 結合 News/Finance/Trader/YFinance 資訊，透過 gateway 產生主管級 Markdown 分析，供 Analysis 分頁閱讀。
  - Digest 亦提供 catalysts/watch focus 等多 Agent 摘要，避免與 Report/News 重複。

- YFinance Agent (`agents/yfinance_agent.py`)
  - 單一入口存取 Yahoo Finance：snapshot（price/變動/估值/KPI）、intraday KPIs、價格序列、中文公司名稱清理。
  - 即使無法連網亦會以 deterministic 空資料回傳。

- Scoring (`agents/scoring.py`)
  - `combine_confidence` → 將 LLM confidence 與啟發式（含數字/百分比、來源可信度）合併為 1–5 分。

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
