from __future__ import annotations

from typing import Dict, Optional


def clamp(n: float, lo: int = 1, hi: int = 5) -> int:
    """Utility to bound scores to UI-friendly ranges."""
    return max(lo, min(hi, int(round(n))))


def heuristic_confidence(news: Dict[str, str]) -> int:
    """Lightweight heuristic: higher if has numbers, % or reputable source."""
    title = (news.get("title") or "").lower()
    source = (news.get("source") or "").lower()
    score = 2.0
    if any(ch.isdigit() for ch in title):
        score += 0.6
    if "%" in title or "eps" in title or "guidance" in title or "目標價" in title:
        score += 0.6
    # simple source weighting
    reputable = ["reuters", "bloomberg", "ft.com", "wsj", "cnbc", "moneydj", "udn", "cnyes", "yahoo"]
    if any(s in source for s in reputable):
        score += 0.4
    return clamp(score)


def combine_confidence(llm_conf: Optional[float], news: Dict[str, str]) -> int:
    """Blend heuristic + LLM-provided score for transparency."""
    base = heuristic_confidence(news)
    if llm_conf is None:
        return base
    # simple average with heuristic, then clamp
    return clamp((float(llm_conf) + base) / 2.0)
