from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple

from .base import Provider


_seen_fail_once: set[str] = set()


class MockProvider(Provider):
    name = "mock"

    async def generate(
        self, messages: List[Dict[str, str]], temperature: float, max_tokens: int
    ) -> Tuple[str, Dict[str, int], Dict[str, Any]]:
        prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])

        # Simulate a timeout if requested
        if "TIMEOUT" in prompt:
            await asyncio.sleep(10_000)  # effectively ensures timeout by caller

        # Simulate a transient error once per request id token embedded in prompt
        # Token format: REQ:<uuid>
        req_marker = None
        for m in messages:
            if "REQ:" in m.get("content", ""):
                req_marker = m["content"].split("REQ:")[-1].split()[0]
                break
        if "FAIL_ONCE" in prompt and req_marker:
            key = f"{req_marker}"
            if key not in _seen_fail_once:
                _seen_fail_once.add(key)
                raise RuntimeError("simulated transient error")

        content = (
            "[MOCK] Echo summary: "
            + (prompt[: max_tokens] if max_tokens else prompt)  # naive truncation
        )
        usage = {
            "prompt_tokens": max(1, len(prompt) // 4),
            "completion_tokens": max(1, len(content) // 4),
            "total_tokens": max(2, (len(prompt) + len(content)) // 4),
        }
        meta: Dict[str, Any] = {"provider": self.name}
        return content, usage, meta

