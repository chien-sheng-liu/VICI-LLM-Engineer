from __future__ import annotations

from pathlib import Path

from agent import AgentArgs, run


def test_agent_dry_run_creates_outputs(tmp_path: Path):
    args = AgentArgs(
        ticker="AAPL",
        source="https://example.com",
        gateway=None,
        model="mock-01",
        out_dir=tmp_path,
        dry_run=True,
        timeout_s=2.0,
    )
    result = run(args)
    # outputs
    report = tmp_path / "outputs" / "report.md"
    run_json = tmp_path / "run_logs" / "run.json"
    assert report.exists(), "report.md should be created"
    assert run_json.exists(), "run.json should be created"
    # basic schema
    assert result["ticker"] == "AAPL"
    assert "artifacts" in result and "report_md" in result["artifacts"]

