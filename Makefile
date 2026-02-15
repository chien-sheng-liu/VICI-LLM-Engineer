PY=python3
PIP=pip3

.PHONY: install test run-gateway run-agent-demo run-frontend docker-up docker-down fmt
 .PHONY: up down docker-logs

install:
	$(PIP) install -r requirements.txt

test:
	pytest -q

run-gateway:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend

run-agent-demo:
	$(PY) agent.py --ticker AAPL --source https://example.com --model mock-01 --dry-run

run-frontend:
	@echo "Frontend scaffolded. To run: 'npm install && npm run dev' in ./frontend (requires network)."

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

up: docker-up

down: docker-down

docker-logs:
	docker compose logs -f --tail=200
