"""Escalation: pause execution, package context, push to the review queue.

Approval levels:
  NOTIFY         — inform a human, keep going
  APPROVE_ACTION — block on approval of the next concrete action
  APPROVE_PLAN   — block on approval of the whole plan
  TAKE_OVER      — hand control to a human entirely
"""
from __future__ import annotations

from enum import Enum

from ..graph.state import GraphState
from ..observability.tracing import span
from .queue import ReviewItem, ReviewQueue


class ApprovalLevel(str, Enum):
    NOTIFY = "notify"
    APPROVE_ACTION = "approve_action"
    APPROVE_PLAN = "approve_plan"
    TAKE_OVER = "take_over"


# Which approval level each escalation reason demands.
_REASON_TO_LEVEL = {
    "low_confidence": ApprovalLevel.APPROVE_ACTION,
    "low_quality": ApprovalLevel.APPROVE_ACTION,
    "repeated_failure": ApprovalLevel.APPROVE_PLAN,
    "side_effecting_tool": ApprovalLevel.APPROVE_ACTION,
    "sensitive_operation": ApprovalLevel.TAKE_OVER,
}


def escalate(state: GraphState) -> GraphState:
    """Package the current context and enqueue it for human review."""
    reason = state.get("escalation_reason", "low_confidence")
    level = _REASON_TO_LEVEL.get(reason, ApprovalLevel.NOTIFY)

    with span("hitl.escalate", reason=reason, level=level.value):
        completed = state.get("completed", [])
        item = ReviewItem(
            task_id=state.get("task_id", "unknown"),
            task=state.get("task", ""),
            reason=reason,
            level=level.value,
            proposed_action=completed[-1]["result"] if completed else "",
            confidence=state.get("confidence", 0.0),
            quality=state.get("quality", 0.0),
            memories=[],
        )
        ReviewQueue().push(item)

    return {
        "escalated": True,
        "approval": level.value,
        "trace": [{"node": "hitl", "event": "escalate", "reason": reason, "level": level.value}],
    }
