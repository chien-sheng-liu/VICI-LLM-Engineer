from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture()
def client():
    # Constrain timeouts and retries for tests
    os.environ.setdefault("GATEWAY_REQUEST_TIMEOUT_S", "0.5")
    os.environ.setdefault("GATEWAY_MAX_RETRIES", "2")
    os.environ.setdefault("GATEWAY_ALLOWED_MODELS", "mock-01,claude-3-haiku,gpt-3.5-turbo")
    app = create_app()
    return TestClient(app)


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


def test_chat_completions_schema_valid(client: TestClient):
    payload = {
        "model": "mock-01",
        "messages": [
            {"role": "user", "content": "Summarize: hello world"},
        ],
        "temperature": 0.1,
        "max_tokens": 64,
    }
    r = client.post("/v1/chat/completions", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "mock-01"
    assert isinstance(data["created"], int)
    assert "choices" in data and len(data["choices"]) == 1
    assert "usage" in data
    assert "request_id" in data and "provider" in data
    assert data["provider"] == "mock"


def test_retry_logic_works(client: TestClient):
    payload = {
        "model": "mock-01",
        "messages": [
            {"role": "user", "content": "FAIL_ONCE please"},
        ],
        "temperature": 0.1,
        "max_tokens": 64,
    }
    r = client.post("/v1/chat/completions", json=payload)
    assert r.status_code == 200
    data = r.json()
    # Should have retried at least once
    assert data["retry_count"] >= 1


def test_timeout_behavior(client: TestClient):
    payload = {
        "model": "mock-01",
        "messages": [
            {"role": "user", "content": "Please TIMEOUT"},
        ],
    }
    t0 = time.time()
    r = client.post("/v1/chat/completions", json=payload)
    elapsed = time.time() - t0
    assert r.status_code == 408
    data = r.json()
    assert "request_id" in data["detail"]
    # Should respect timeout window (not hang)
    assert elapsed < 3
