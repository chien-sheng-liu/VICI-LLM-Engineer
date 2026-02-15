from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from .logging_utils import log_event


class RunRequest(BaseModel):
    ticker: str
    source: str
    model: str = Field(default="mock-01")
    gateway: Optional[str] = Field(default=None)
    dry_run: bool = Field(default=True)


class RunResponse(BaseModel):
    run_id: str
    status: str


class RunStatusResponse(BaseModel):
    run_id: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    artifacts: Dict[str, Any] = {}
    report_md_text: Optional[str] = None
    screenshots: list[str] = []


router = APIRouter(prefix="/agent", tags=["agent"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_agent_module() -> Any:
    # Load agent.py from repo root without global path hacks
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    agent_path = repo_root / "agent.py"
    if not agent_path.exists():
        raise RuntimeError(f"agent.py not found at {agent_path}")
    spec = importlib.util.spec_from_file_location("agent_module", str(agent_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load agent module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


class RunStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.tasks: dict[str, asyncio.Task] = {}
        self.started: dict[str, str] = {}
        self.finished: dict[str, str] = {}

    def run_dir(self, run_id: str) -> Path:
        return self.base_dir / run_id


def get_store(request: Request) -> RunStore:
    return request.app.state.run_store  # type: ignore[attr-defined]


@router.post("/run", response_model=RunResponse)
async def start_run(req: RunRequest, request: Request, store: RunStore = Depends(get_store)) -> RunResponse:
    run_id = uuid.uuid4().hex
    run_dir = store.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    agent_module = _load_agent_module()
    AgentArgs = getattr(agent_module, "AgentArgs")
    run_fn = getattr(agent_module, "run")

    # Gateway default: infer from request host if not provided
    gateway = req.gateway
    if gateway is None:
        base_url = str(request.base_url).rstrip("/")
        gateway = base_url

    args_obj = AgentArgs(
        ticker=req.ticker,
        source=req.source,
        gateway=gateway,
        model=req.model,
        out_dir=run_dir,
        dry_run=req.dry_run,
        timeout_s=float(os.getenv("AGENT_TIMEOUT_S", "15")),
    )

    async def _runner():
        store.started[run_id] = _now_iso()
        log_event(event="agent_run_start", run_id=run_id, ticker=req.ticker, source=req.source, model=req.model)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, run_fn, args_obj)
        except Exception as e:
            # Persist error marker
            err_path = run_dir / "run_logs" / "error.txt"
            err_path.parent.mkdir(parents=True, exist_ok=True)
            err_path.write_text(str(e), encoding="utf-8")
            log_event(event="agent_run_error", run_id=run_id, error=str(e))
        finally:
            store.finished[run_id] = _now_iso()
            log_event(event="agent_run_end", run_id=run_id)

    task = asyncio.create_task(_runner())
    store.tasks[run_id] = task
    return RunResponse(run_id=run_id, status="running")


@router.get("/status/{run_id}", response_model=RunStatusResponse)
async def get_status(run_id: str, store: RunStore = Depends(get_store)) -> RunStatusResponse:
    run_dir = store.run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")

    run_json = run_dir / "run_logs" / "run.json"
    status_str = "running"
    artifacts: Dict[str, Any] = {}
    report_text: Optional[str] = None
    screenshots: list[str] = []

    if run_json.exists():
        data = json.loads(run_json.read_text("utf-8"))
        artifacts = data.get("artifacts", {})
        # Map to served URLs under /runs
        base = f"/runs/{run_id}"
        slides = artifacts.get("slides_pdf")
        report = artifacts.get("report_md")
        shot = artifacts.get("screenshot")
        artifacts = {
            "slides_url": f"{base}/outputs/slides.pdf" if slides else None,
            "report_url": f"{base}/outputs/report.md" if report else None,
            "checksums_url": f"{base}/outputs/checksums.txt",
        }
        if report and Path(report).exists():
            try:
                report_text = Path(report).read_text("utf-8")
            except Exception:
                report_text = None
        if shot and Path(shot).exists():
            # show first screenshot only for now
            screenshots = [f"{base}/run_logs/screenshots/{Path(shot).name}"]
        status_str = "completed"

    if (run_dir / "run_logs" / "error.txt").exists():
        status_str = "error"

    return RunStatusResponse(
        run_id=run_id,
        status=status_str,
        started_at=store.started.get(run_id),
        finished_at=store.finished.get(run_id),
        artifacts=artifacts,
        report_md_text=report_text,
        screenshots=screenshots,
    )

