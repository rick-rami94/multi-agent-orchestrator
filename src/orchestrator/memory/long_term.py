"""Long-term semantic memory in ChromaDB.

Stores what worked and which tools were used, retrievable by semantic similarity.
Degrades to an in-process keyword store when ChromaDB is unavailable.
"""
from __future__ import annotations

import hashlib

from ..config import get_settings

_COLLECTION = "agent_memories"
# Module-level fallback store so memories survive within a process run.
_LOCAL: list[dict] = []


class LongTermMemory:
    def __init__(self) -> None:
        self._collection = self._connect()

    def _connect(self):
        try:
            import chromadb

            settings = get_settings()
            client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
            return client.get_or_create_collection(_COLLECTION)
        except Exception:
            return None

    def remember(self, task: str, outcome: str, metadata: dict | None = None) -> None:
        meta = {"task": task, **(metadata or {})}
        doc = f"TASK: {task}\nOUTCOME: {outcome}"
        if self._collection is not None:
            mid = f"mem-{hashlib.sha256(doc.encode('utf-8')).hexdigest()[:32]}"
            self._collection.add(ids=[mid], documents=[doc], metadatas=[meta])
        else:
            _LOCAL.append({"doc": doc, "meta": meta})

    def recall(self, query: str, k: int = 3) -> list[str]:
        if self._collection is not None:
            try:
                res = self._collection.query(query_texts=[query], n_results=k)
                return res.get("documents", [[]])[0]
            except Exception:
                return []
        # Keyword fallback ranking.
        terms = set(query.lower().split())
        scored = sorted(
            _LOCAL,
            key=lambda m: len(terms & set(m["doc"].lower().split())),
            reverse=True,
        )
        return [m["doc"] for m in scored[:k] if terms & set(m["doc"].lower().split())]
