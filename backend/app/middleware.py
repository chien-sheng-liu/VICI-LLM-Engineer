from __future__ import annotations

import asyncio
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_concurrency: int):  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._sem = asyncio.Semaphore(max_concurrency)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:  # type: ignore[override]
        async with self._sem:
            return await call_next(request)

