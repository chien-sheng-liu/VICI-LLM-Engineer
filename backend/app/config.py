from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Set


@dataclass(frozen=True)
class GatewayConfig:
    version: str
    request_timeout_s: float
    max_retries: int
    max_input_chars: int
    max_concurrency: int
    allowed_providers: Set[str]
    allowed_models: Set[str]

    @staticmethod
    def from_env() -> "GatewayConfig":
        version = os.getenv("GATEWAY_VERSION", "0.1.0")
        request_timeout_s = float(os.getenv("GATEWAY_REQUEST_TIMEOUT_S", "15"))
        max_retries = int(os.getenv("GATEWAY_MAX_RETRIES", "2"))
        if max_retries > 2:
            # Enforce safety bound
            max_retries = 2
        max_input_chars = int(os.getenv("GATEWAY_MAX_INPUT_CHARS", "4000"))
        max_concurrency = int(os.getenv("GATEWAY_MAX_CONCURRENCY", "10"))

        allowed_providers = set(
            filter(
                None,
                [s.strip() for s in os.getenv("GATEWAY_ALLOWED_PROVIDERS", "mock,openai,claude").split(",")],
            )
        )
        allowed_models = set(
            filter(
                None,
                [
                    s.strip()
                    for s in os.getenv(
                        "GATEWAY_ALLOWED_MODELS",
                        "mock-01,gpt-3.5-turbo,claude-3-haiku",
                    ).split(",")
                ],
            )
        )

        return GatewayConfig(
            version=version,
            request_timeout_s=request_timeout_s,
            max_retries=max_retries,
            max_input_chars=max_input_chars,
            max_concurrency=max_concurrency,
            allowed_providers=allowed_providers,
            allowed_models=allowed_models,
        )


def model_to_provider(model: str) -> str:
    """Map model name to provider id; keep simple rules to avoid coupling.

    - mock-*  -> mock
    - claude* -> claude
    - gpt*    -> openai
    Otherwise default to 'mock'.
    """
    m = model.lower()
    if m.startswith("mock"):
        return "mock"
    if m.startswith("claude"):
        return "claude"
    if m.startswith("gpt") or m.startswith("o"):
        return "openai"
    return "mock"
