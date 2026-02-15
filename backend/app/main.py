from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv

from .config import GatewayConfig
from .gateway import router as gateway_router
from .logging_utils import configure_json_logging
from .middleware import ConcurrencyLimitMiddleware
from .agent_runner import router as agent_router, RunStore


def create_app() -> FastAPI:
    # Load environment variables from .env if present
    load_dotenv()
    configure_json_logging()

    cfg = GatewayConfig.from_env()
    app = FastAPI(title="VICI LLM Gateway", version=cfg.version)

    app.add_middleware(ConcurrencyLimitMiddleware, max_concurrency=cfg.max_concurrency)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(gateway_router)
    app.include_router(agent_router)

    # Run storage and static mount
    runs_dir = Path("runs").resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    app.state.run_store = RunStore(runs_dir)  # type: ignore[attr-defined]
    app.mount("/runs", StaticFiles(directory=str(runs_dir)), name="runs")

    # Static sample content for demos
    static_dir = Path(__file__).resolve().parents[1] / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()
