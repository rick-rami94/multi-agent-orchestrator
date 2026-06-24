"""Short-term working memory in Redis, scoped to a single task.

Degrades to an in-process dict when Redis is unavailable.
"""
from __future__ import annotations

import json

from ..config import get_settings


class ShortTermMemory:
    def __init__(self, task_id: str, ttl_seconds: int = 3600) -> None:
        self.task_id = task_id
        self.ttl = ttl_seconds
        self._key = f"task:{task_id}:working"
        self._client = self._connect()
        self._local: dict[str, str] = {}

    def _connect(self):
        try:
            import redis

            client = redis.from_url(get_settings().redis_url, decode_responses=True)
            client.ping()
            return client
        except Exception:
            return None

    def set(self, field: str, value) -> None:
        payload = json.dumps(value)
        if self._client:
            self._client.hset(self._key, field, payload)
            self._client.expire(self._key, self.ttl)
        else:
            self._local[field] = payload

    def get(self, field: str):
        raw = self._client.hget(self._key, field) if self._client else self._local.get(field)
        return json.loads(raw) if raw else None

    def all(self) -> dict:
        if self._client:
            data = self._client.hgetall(self._key)
        else:
            data = self._local
        return {k: json.loads(v) for k, v in data.items()}

    def clear(self) -> None:
        if self._client:
            self._client.delete(self._key)
        else:
            self._local.clear()
