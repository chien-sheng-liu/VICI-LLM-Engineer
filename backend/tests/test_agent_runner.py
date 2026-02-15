from __future__ import annotations

import time
from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_agent_runner_dry_run_flow():
    app = create_app()
    client = TestClient(app)

    # Start a run
    r = client.post(
        "/agent/run",
        json={
            "ticker": "AAPL",
            "source": "https://example.com",
            "model": "mock-01",
            "dry_run": True,
        },
    )
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    # Poll status until completed
    status = None
    report_url = None
    for _ in range(20):
        s = client.get(f"/agent/status/{run_id}")
        assert s.status_code == 200
        data = s.json()
        status = data["status"]
        if status in ("completed", "error"):
            report_url = data.get("artifacts", {}).get("report_url")
            assert data.get("report_md_text") is not None
            break
        time.sleep(0.1)

    assert status == "completed"
    assert report_url, "report_url should be available when completed"

    # Fetch the static report
    rr = client.get(report_url)
    assert rr.status_code == 200
    assert rr.text.startswith("# Research Report")

