"""Review queue backed by Redis lists. Degrades to an in-process list."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from ..config import get_settings

_QUEUE_KEY = "hitl:review_queue"
_AUDIT_KEY = "hitl:audit_log"
_LOCAL: list[str] = []
_AUDIT_LOCAL: list[str] = []


@dataclass
class ReviewItem:
    task_id: str
    task: str
    reason: str
    level: str
    proposed_action: str
    confidence: float
    quality: float
    memories: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(raw: str) -> "ReviewItem":
        return ReviewItem(**json.loads(raw))


class ReviewQueue:
    def __init__(self) -> None:
        self._client = self._connect()

    def _connect(self):
        try:
            import redis

            client = redis.from_url(get_settings().redis_url, decode_responses=True)
            client.ping()
            return client
        except Exception:
            return None

    def push(self, item: ReviewItem) -> None:
        if self._client:
            self._client.rpush(_QUEUE_KEY, item.to_json())
        else:
            _LOCAL.append(item.to_json())

    def pending(self) -> list[ReviewItem]:
        raws = self._client.lrange(_QUEUE_KEY, 0, -1) if self._client else list(_LOCAL)
        return [ReviewItem.from_json(r) for r in raws]

    def resolve(self, index: int, decision: str, approver: str) -> ReviewItem | None:
        """Pop an item once an authenticated human has decided.

        `approver` is the authenticated reviewer identity and is required so
        every resolution is attributable; an append-only audit record is
        written (VA-01 / VA-09).
        """
        if not approver:
            raise ValueError("approver identity is required to resolve a review item")
        raws = self._client.lrange(_QUEUE_KEY, 0, -1) if self._client else _LOCAL
        if index >= len(raws):
            return None
        raw = raws[index]
        if self._client:
            self._client.lrem(_QUEUE_KEY, 1, raw)
        else:
            _LOCAL.remove(raw)
        item = ReviewItem.from_json(raw)
        item.reason = f"{item.reason}|resolved:{decision}"

        record = json.dumps({
            "task_id": item.task_id,
            "reason": item.reason,
            "level": item.level,
            "decision": decision,
            "approver": approver,
        })
        if self._client:
            self._client.rpush(_AUDIT_KEY, record)
        else:
            _AUDIT_LOCAL.append(record)
        return item

    def audit_log(self) -> list[dict]:
        """Return the append-only record of who resolved what."""
        raws = self._client.lrange(_AUDIT_KEY, 0, -1) if self._client else list(_AUDIT_LOCAL)
        return [json.loads(r) for r in raws]
