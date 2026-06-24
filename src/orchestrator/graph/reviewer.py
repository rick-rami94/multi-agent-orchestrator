"""Reviewer node: validates specialist output before returning to supervisor."""
from __future__ import annotations

from ..config import get_settings
from ..hitl.sensitivity import classify
from ..observability.tracing import span
from ..tools.registry import REGISTRY
from .state import GraphState


def review(state: GraphState) -> GraphState:
    """Score the latest completed work and decide retry / escalate / accept."""
    settings = get_settings()
    completed = state.get("completed", [])
    latest = completed[-1] if completed else None

    with span("reviewer.review"):
        if latest is None:
            quality, confidence = 0.0, 0.0
        else:
            # Toy heuristic quality signal; swap for an LLM judge in production.
            quality = min(1.0, 0.5 + len(latest["result"]) / 400)
            confidence = latest["confidence"]

        # Authoritative gate: any side-effecting tool that was used requires
        # human approval. Text classification is only a secondary signal.
        tools_used = state.get("tools_used", [])
        used_side_effecting = [t for t in tools_used if REGISTRY.requires_approval(t)]

        text_sensitive, sensitivity_labels = (
            classify(latest["result"]) if latest is not None else (False, [])
        )

        reason = ""
        escalate = False
        # Side-effecting tool use is the authoritative trigger and takes
        # precedence so it can never be masked by a passing quality score.
        if used_side_effecting:
            escalate, reason = True, "side_effecting_tool"
        elif confidence < settings.confidence_threshold:
            escalate, reason = True, "low_confidence"
        elif quality < settings.quality_threshold:
            escalate, reason = True, "low_quality"
        elif text_sensitive:
            escalate, reason = True, "sensitive_operation"
        elif state.get("retries", 0) >= settings.max_retries:
            escalate, reason = True, "repeated_failure"

    return {
        "quality": quality,
        "confidence": confidence,
        "escalated": escalate,
        "escalation_reason": reason,
        "trace": [
            {
                "node": "reviewer",
                "event": "review",
                "quality": round(quality, 3),
                "confidence": round(confidence, 3),
                "escalate": escalate,
                "reason": reason,
                "sensitivity": sensitivity_labels,
                "side_effecting_tools": used_side_effecting,
            }
        ],
    }
