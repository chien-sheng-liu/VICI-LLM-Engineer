PY ?= python3
PIP ?= pip3
PORT ?= 8000

.PHONY: install test run-gateway run-agent-demo run-frontend docker-up docker-down fmt doctor-claude
.PHONY: up down docker-logs

install:
	$(PIP) install -r requirements.txt

test:
	pytest -q

run-gateway:
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --app-dir backend

run-agent-demo:
	$(PY) agent.py --ticker 2330 --source https://tw.stock.yahoo.com/ --model gpt-3.5-turbo --dry-run --yahoo

showcase:
	$(PY) scripts/run_showcase.py --gateway http://localhost:8000 --ticker 2330 --source https://tw.stock.yahoo.com/ --model gpt-3.5-turbo --dry-run --yahoo

run-frontend:
	@echo "Frontend scaffolded. To run: 'npm install && npm run dev' in ./frontend (requires network)."

doctor-claude:
	@echo "Checking Claude CLI configuration..." && \
	if [ -z "$$ANTHROPIC_API_KEY" ]; then echo "[WARN] ANTHROPIC_API_KEY not set"; else echo "[OK] ANTHROPIC_API_KEY present"; fi; \
	CLI_PATH=$${GATEWAY_CLAUDE_CLI_PATH:-./scripts/claude_cli.sh}; \
	if [ -x "$$CLI_PATH" ]; then echo "[OK] CLI executable at $$CLI_PATH"; else echo "[WARN] CLI not executable at $$CLI_PATH"; fi; \
	echo "Try: echo 'hello' | $$CLI_PATH -m $${GATEWAY_CLAUDE_MODEL:-claude-3-haiku} -t 0.2 -M 64"

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

up: docker-up

down: docker-down

docker-logs:
	docker compose logs -f --tail=200
