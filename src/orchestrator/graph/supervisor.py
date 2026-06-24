"""Supervisor node: decomposes the task and reduces specialist outputs."""

from __future__ import annotations

from ..llm import LLMClient
from ..observability.tracing import span
from .state import GraphState, Subtask

_KEYWORD_ROUTES = {
    "research": ("research", "find", "investigate", "compare", "sources"),
    "code": ("code", "implement", "function", "bug", "refactor", "script"),
    "writing": ("write", "draft", "summarize", "report", "email", "pitch"),
    "analysis": ("analyze", "evaluate", "recommend", "assess", "trade-off"),
}


# Specialists run in this canonical pipeline order so a multi-subtask plan reads
# coherently (gather facts -> reason -> build -> write up).
_ORDER: tuple[str, ...] = ("research", "analysis", "code", "writing")


def _matched_kinds(task: str) -> list[str]:
    """Every specialist whose trigger keywords appear in the task, in pipeline order."""
    text = task.lower()
    return [k for k in _ORDER if any(kw in text for kw in _KEYWORD_ROUTES[k])]


def plan_subtasks(task: str) -> list[Subtask]:
    """Decompose a task into one subtask per relevant specialist.

    A task can legitimately need several specialists ("research X, analyze the
    options, and write a recommendation"), so we emit one subtask per matched
    kind rather than collapsing to a single route. When nothing matches we fall
    back to a single analysis subtask so the graph always has work to do.
    """
    kinds = _matched_kinds(task) or ["analysis"]
    return [
        {
            "id": f"s{i + 1}",
            "kind": kind,
            "instruction": task,
            "status": "pending",
            "result": "",
            "confidence": 0.0,
        }
        for i, kind in enumerate(kinds)
    ]


def decompose(state: GraphState) -> GraphState:
    """Break the task into ordered subtasks across the specialist pool."""
    task = state["task"]
    with span("supervisor.decompose", task=task):
        llm = LLMClient()
        # The LLM proposes a plan; we keep a deterministic skeleton so the graph
        # is exercised even with the mock provider.
        llm.complete(
            system="You are a supervisor that decomposes tasks for specialist agents.",
            prompt=f"Decompose this task into subtasks: {task}",
        )
        plan = plan_subtasks(task)
    return {
        "plan": plan,
        "retries": state.get("retries", 0),
        "trace": [
            {
                "node": "supervisor",
                "event": "decompose",
                "subtasks": len(plan),
                "kinds": [s["kind"] for s in plan],
            }
        ],
    }


def reduce(state: GraphState) -> GraphState:
    """Combine completed subtasks into a single, coherent final answer.

    Each specialist's output is kept as a labelled section so a multi-agent run
    aggregates into one readable answer instead of a flat concatenation.
    """
    with span("supervisor.reduce"):
        done = [c for c in state.get("completed", []) if c["status"] == "done"]
        if done:
            sections = [f"### {c['kind'].title()} specialist\n{c['result']}" for c in done]
            answer = "\n\n".join(sections)
        else:
            answer = "(no specialist output)"
        escalations = state.get("escalations", [])
    return {
        "answer": answer,
        # Authoritative final escalation signal: did *any* subtask need review?
        "escalated": bool(escalations),
        "escalation_reason": (
            escalations[-1]["reason"] if escalations else state.get("escalation_reason", "")
        ),
        "trace": [
            {
                "node": "supervisor",
                "event": "reduce",
                "parts": len(done),
                "escalations": len(escalations),
            }
        ],
    }
