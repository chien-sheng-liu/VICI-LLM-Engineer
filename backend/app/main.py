from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - minimal env fallback
    def load_dotenv(*_args, **_kwargs):  # type: ignore
        return False

from .config import GatewayConfig
from .gateway import router as gateway_router
from .logging_utils import configure_json_logging
from .middleware import ConcurrencyLimitMiddleware
from .agent_runner import router as agent_router, RunStore

try:
    from safety import SafeguardConfig, SafeguardrailsAdapter
except ModuleNotFoundError:  # pragma: no cover - fallback when running from backend/ dir
    import sys
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from safety import SafeguardConfig, SafeguardrailsAdapter


def create_app() -> FastAPI:
    # Load environment variables from .env if present
    load_dotenv()
    configure_json_logging()

    cfg = GatewayConfig.from_env()
    app = FastAPI(title="VICI LLM Gateway", version=cfg.version)

    # Protect the gateway from overload.
    app.add_middleware(ConcurrencyLimitMiddleware, max_concurrency=cfg.max_concurrency)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers stay decoupled so gateway + agent lifecycle remain independent.
    app.include_router(gateway_router)
    app.include_router(agent_router)

    # Shared safety adapter (used by gateway + agent runner when invoking the agent orchestrator)
    safety_cfg = SafeguardConfig.from_env("GATEWAY_SAFEGUARD")
    app.state.safety_adapter = SafeguardrailsAdapter(safety_cfg)  # type: ignore[attr-defined]

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
