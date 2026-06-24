"""Review queue backed by Redis lists. Degrades to an in-process list.

Resolving an item records a real, attributable decision and (for ``edit`` /
``take_over``) the human's revised text, then writes a tamper-evident audit
record via the hash chain in :mod:`orchestrator.hitl.audit`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from ..config import get_settings
from .audit import AuditChain

_QUEUE_KEY = "hitl:review_queue"
_LOCAL: list[str] = []

# The four decisions a reviewer can record.
VALID_DECISIONS = ("approve", "reject", "edit", "take_over")
# Decisions that require the human to supply replacement text.
_TEXT_REQUIRED = ("edit", "take_over")


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
    def from_json(raw: str) -> ReviewItem:
        return ReviewItem(**json.loads(raw))


@dataclass
class Resolution:
    """The recorded outcome of a human review decision.

    ``final_result`` is what the workflow should treat as the authoritative
    answer for the task:
      - approve    -> the agent's proposed action stands
      - reject     -> None (the proposed action is discarded)
      - edit       -> the reviewer's revised text
      - take_over  -> the reviewer's own answer becomes the result
    """

    task_id: str
    decision: str
    approver: str
    timestamp: str
    proposed_action: str
    final_input: str
    final_result: str | None


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

    def resolve(
        self,
        index: int,
        decision: str,
        approver: str,
        note: str | None = None,
    ) -> Resolution | None:
        """Apply an authenticated human's decision to a queued item.

        `approver` is the authenticated reviewer identity and is required so
        every resolution is attributable (VA-01). The decision and any human
        input are committed to the tamper-evident audit chain (VA-09).

        Returns the :class:`Resolution` (including the workflow's final result),
        or ``None`` if `index` is out of range.
        """
        if not approver:
            raise ValueError("approver identity is required to resolve a review item")
        if decision not in VALID_DECISIONS:
            raise ValueError(f"unknown decision: {decision!r} (expected one of {VALID_DECISIONS})")
        note = (note or "").strip()
        if decision in _TEXT_REQUIRED and not note:
            raise ValueError(f"decision {decision!r} requires reviewer-provided text")

        raws = self._client.lrange(_QUEUE_KEY, 0, -1) if self._client else _LOCAL
        if index >= len(raws):
            return None
        raw = raws[index]
        if self._client:
            self._client.lrem(_QUEUE_KEY, 1, raw)
        else:
            _LOCAL.remove(raw)
        item = ReviewItem.from_json(raw)

        # The decision determines what the workflow should adopt as final.
        if decision == "approve":
            final_result: str | None = item.proposed_action
        elif decision == "reject":
            final_result = None
        else:  # edit | take_over both substitute the reviewer's text
            final_result = note

        record = AuditChain().append(
            task_id=item.task_id,
            action=item.level,
            decision=decision,
            approver=approver,
            proposed_action=item.proposed_action,
            final_input=note,
        )
        return Resolution(
            task_id=item.task_id,
            decision=decision,
            approver=approver,
            timestamp=record["timestamp"],
            proposed_action=item.proposed_action,
            final_input=note,
            final_result=final_result,
        )

    def audit_log(self) -> list[dict]:
        """Return the tamper-evident, append-only record of who resolved what."""
        return AuditChain().records()
