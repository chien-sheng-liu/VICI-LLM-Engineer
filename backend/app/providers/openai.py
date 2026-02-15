from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .base import Provider


class OpenAIProvider(Provider):
    name = "openai"

    async def generate(
        self, messages: List[Dict[str, str]], temperature: float, max_tokens: int
    ) -> Tuple[str, Dict[str, int], Dict[str, Any]]:
        # Network access is restricted in this environment.
        # Implement a placeholder that mimics behavior.
        joined = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        text = f"[OPENAI SIM] {joined[:max_tokens]}"
        usage = {
            "prompt_tokens": max(1, len(joined) // 4),
            "completion_tokens": max(1, len(text) // 4),
            "total_tokens": max(2, (len(joined) + len(text)) // 4),
        }
        meta: Dict[str, Any] = {"provider": self.name, "model_family": "gpt"}
        return text, usage, meta

