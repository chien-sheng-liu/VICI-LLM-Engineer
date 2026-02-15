from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.2
    max_tokens: Optional[int] = 256

    @validator("temperature")
    def _temp_range(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v < 0 or v > 2:
            raise ValueError("temperature out of range [0,2]")
        return v


class ChoiceMessage(BaseModel):
    role: str
    content: str


class Choice(BaseModel):
    index: int
    message: ChoiceMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage
    request_id: str = Field(..., description="Internal request ID for traceability")
    provider: str
    latency_ms: int
    retry_count: int
    meta: Dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    request_id: str
    error: str
    detail: Optional[Dict[str, Any]] = None

