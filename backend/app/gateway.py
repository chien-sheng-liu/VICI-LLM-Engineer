from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .config import GatewayConfig, model_to_provider
from .logging_utils import log_event
from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    ErrorResponse,
    HealthResponse,
    Usage,
)
from .providers.base import Provider
from .providers.claude_cli import ClaudeProvider
from .providers.mock import MockProvider
from .providers.openai import OpenAIProvider


router = APIRouter()


def get_config() -> GatewayConfig:
    return GatewayConfig.from_env()


def get_provider(name: str) -> Provider:
    mapping = {
        "mock": MockProvider(),
        "openai": OpenAIProvider(),
        "claude": ClaudeProvider(),
    }
    if name not in mapping:
        raise KeyError(name)
    return mapping[name]


@router.get("/health", response_model=HealthResponse)
async def health(cfg: GatewayConfig = Depends(get_config)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=cfg.version,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


async def _run_with_retries(
    provider: Provider,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    timeout_s: float,
    max_retries: int,
    api_key: str | None,
) -> Tuple[str, Dict[str, int], Dict[str, Any], int]:
    attempt = 0
    last_err: Exception | None = None
    while attempt <= max_retries:
        try:
            result = await asyncio.wait_for(
                provider.generate(messages, temperature, max_tokens, api_key=api_key),
                timeout=timeout_s,
            )
            text, usage, meta = result
            return text, usage, meta, attempt
        except asyncio.TimeoutError as e:
            last_err = e
            break  # do not retry timeouts
        except Exception as e:  # transient error
            last_err = e
            if attempt >= max_retries:
                break
            await asyncio.sleep(0.2 * (2 ** attempt))
            attempt += 1
            continue
    assert last_err is not None
    raise last_err


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse, responses={
    408: {"model": ErrorResponse},
    400: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
})
async def chat_completions(
    req: ChatCompletionRequest,
    request: Request,
    cfg: GatewayConfig = Depends(get_config),
) -> ChatCompletionResponse:
    # Safety: model allowlist
    if req.model not in cfg.allowed_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "model_not_allowed", "model": req.model},
        )

    # Safety: request size limit (approximate by content length)
    total_chars = sum(len(m.content) for m in req.messages)
    if total_chars > cfg.max_input_chars:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "input_too_large", "limit": cfg.max_input_chars},
        )

    provider_name = model_to_provider(req.model)
    if provider_name not in cfg.allowed_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "provider_not_allowed", "provider": provider_name},
        )

    pv = get_provider(provider_name)

    started = time.perf_counter()
    request_id = str(uuid.uuid4())

    # Inject request marker for mock provider deterministic behavior
    msg_dicts = [m.model_dump() for m in req.messages]
    msg_dicts.append({"role": "system", "content": f"REQ:{request_id}"})

    # Optional API Key from client, prefer Authorization: Bearer <key>, fallback X-OPENAI-API-KEY
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    api_key: str | None = None
    if auth and auth.lower().startswith("bearer "):
        api_key = auth.split(" ", 1)[1].strip()
    elif request.headers.get("X-OPENAI-API-KEY"):
        api_key = request.headers.get("X-OPENAI-API-KEY")
    elif request.headers.get("X-ANTHROPIC-API-KEY"):
        api_key = request.headers.get("X-ANTHROPIC-API-KEY")
    # Fallback to server-side .env if no key provided by client
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")

    try:
        text, usage, meta, retries = await _run_with_retries(
            provider=pv,
            messages=msg_dicts,
            temperature=req.temperature or 0.2,
            max_tokens=req.max_tokens or 256,
            timeout_s=cfg.request_timeout_s,
            max_retries=cfg.max_retries,
            api_key=api_key,
        )
    except asyncio.TimeoutError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_event(
            request_id=request_id,
            route="/v1/chat/completions",
            provider=provider_name,
            model=req.model,
            latency_ms=latency_ms,
            retry_count=0,
            error="timeout",
        )
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=ErrorResponse(request_id=request_id, error="timeout").model_dump(),
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_event(
            request_id=request_id,
            route="/v1/chat/completions",
            provider=provider_name,
            model=req.model,
            latency_ms=latency_ms,
            retry_count=cfg.max_retries,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(request_id=request_id, error=str(e)).model_dump(),
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    log_event(
        request_id=request_id,
        route="/v1/chat/completions",
        provider=provider_name,
        model=req.model,
        latency_ms=latency_ms,
        retry_count=retries,
        error=None,
        api_key_present=bool(api_key),
    )

    created = int(time.time())
    choice = Choice(
        index=0,
        message=ChoiceMessage(role="assistant", content=text),
        finish_reason="stop",
    )
    usage_obj = Usage(
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
    )
    resp = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=created,
        model=req.model,
        choices=[choice],
        usage=usage_obj,
        request_id=request_id,
        provider=provider_name,
        latency_ms=latency_ms,
        retry_count=retries,
        meta=meta,
    )
    return resp


@router.get("/providers/status")
async def providers_status(cfg: GatewayConfig = Depends(get_config)) -> Dict[str, Any]:
    import shutil
    claude_cli = os.getenv("GATEWAY_CLAUDE_CLI_PATH", "claude")
    claude_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    cli_path = shutil.which(claude_cli) if os.path.sep not in claude_cli else claude_cli
    cli_exists = bool(cli_path) and (os.path.exists(cli_path))
    ready = ("claude" in cfg.allowed_providers) and ("claude-3-haiku" in cfg.allowed_models) and bool(claude_key) and cli_exists
    return {
        "allowed_providers": sorted(list(cfg.allowed_providers)),
        "allowed_models": sorted(list(cfg.allowed_models)),
        "providers": {
            "claude": {
                "enabled": "claude" in cfg.allowed_providers,
                "model_allowed": "claude-3-haiku" in cfg.allowed_models,
                "cli_path": claude_cli,
                "cli_exists": cli_exists,
                "api_key_present": bool(claude_key),
                "ready": ready,
            }
        },
    }
