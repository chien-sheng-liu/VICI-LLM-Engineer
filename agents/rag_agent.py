from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class RAGAgent:
    """Minimal retrieval helper over curated research notes."""

    def __init__(self, corpus_path: Path | None = None) -> None:
        base = corpus_path or Path(__file__).resolve().parent / "corpus" / "research_notes.json"
        self.documents: List[Dict[str, Any]] = []
        if base.exists():
            try:
                self.documents = json.loads(base.read_text(encoding="utf-8"))
            except Exception:
                self.documents = []

    def retrieve(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        if not self.documents:
            return []
        q = query.lower()
        scored: List[tuple[int, Dict[str, Any]]] = []
        for doc in self.documents:
            text = " ".join([
                str(doc.get("title", "")),
                " ".join(doc.get("tags", [])),
                str(doc.get("content", "")),
            ]).lower()
            score = sum(text.count(token) for token in q.split())
            if any(token in text for token in q.split()):
                scored.append((score, doc))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]


__all__ = ["RAGAgent"]
