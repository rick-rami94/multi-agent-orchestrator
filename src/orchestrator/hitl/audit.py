"""Tamper-evident audit log backed by a SHA-256 hash chain (VA-09).

Every resolution of a review item is appended as a record that links to its
predecessor: ``record_hash = sha256(content + previous_hash)``. Because each
hash commits to the one before it, any modification, reordering, or deletion of
a past record invalidates every hash after it — and ``verify()`` detects it.

Storage degrades from Redis to an in-process list, mirroring the review queue,
so the audit trail works with zero external services in demo/test mode.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from ..config import get_settings

_AUDIT_KEY = "hitl:audit_chain"
# Module-level fallback store so the chain survives within a process run.
_LOCAL: list[str] = []

GENESIS_HASH = "0" * 64

# Fields covered by record_hash, in a fixed order. previous_hash is included so
# the hash commits to the link, not just the payload.
_CONTENT_FIELDS = (
    "timestamp",
    "task_id",
    "action",
    "decision",
    "approver",
    "proposed_action",
    "final_input",
    "previous_hash",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_content(content: dict) -> str:
    """Deterministic hash over the canonical content fields."""
    payload = json.dumps(
        {k: content.get(k, "") for k in _CONTENT_FIELDS},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditChain:
    """Append-only, hash-chained audit log."""

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

    def _raws(self) -> list[str]:
        if self._client:
            return self._client.lrange(_AUDIT_KEY, 0, -1)
        return list(_LOCAL)

    def records(self) -> list[dict]:
        return [json.loads(r) for r in self._raws()]

    def append(
        self,
        *,
        task_id: str,
        action: str,
        decision: str,
        approver: str,
        proposed_action: str = "",
        final_input: str = "",
        timestamp: str | None = None,
    ) -> dict:
        """Append a tamper-evident record and return it (including its hashes)."""
        records = self.records()
        previous_hash = records[-1]["record_hash"] if records else GENESIS_HASH
        content = {
            "timestamp": timestamp or _utc_now(),
            "task_id": task_id,
            "action": action,
            "decision": decision,
            "approver": approver,
            "proposed_action": proposed_action,
            "final_input": final_input,
            "previous_hash": previous_hash,
        }
        record = {**content, "record_hash": _hash_content(content)}
        raw = json.dumps(record)
        if self._client:
            self._client.rpush(_AUDIT_KEY, raw)
        else:
            _LOCAL.append(raw)
        return record

    def verify(self) -> tuple[bool, int | None]:
        """Validate the whole chain.

        Returns ``(True, None)`` when intact, or ``(False, i)`` pointing at the
        index of the first record that fails its link or content hash.
        """
        prev = GENESIS_HASH
        for i, rec in enumerate(self.records()):
            if rec.get("previous_hash") != prev:
                return (False, i)
            content = {k: rec.get(k, "") for k in _CONTENT_FIELDS}
            if _hash_content(content) != rec.get("record_hash"):
                return (False, i)
            prev = rec["record_hash"]
        return (True, None)

    def clear(self) -> None:
        """Drop all records (intended for tests / fresh demo runs)."""
        if self._client:
            self._client.delete(_AUDIT_KEY)
        else:
            _LOCAL.clear()


def verify_audit() -> bool:
    """Convenience: True iff the current audit chain is intact."""
    return AuditChain().verify()[0]
