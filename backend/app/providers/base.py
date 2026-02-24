from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple, Optional


class Provider(ABC):
    """Every provider exposes the same async generate signature."""
    name: str

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        api_key: Optional[str] = None,
    ) -> Tuple[str, Dict[str, int], Dict[str, Any]]:
        """Generate text based on chat messages.

        Returns: (text, usage, meta)
        usage keys: prompt_tokens, completion_tokens, total_tokens
        meta: provider-specific metadata
        """
        raise NotImplementedError
