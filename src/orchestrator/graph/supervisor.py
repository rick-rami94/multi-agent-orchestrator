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


def _route(instruction: str) -> str:
    text = instruction.lower()
    for kind, kws in _KEYWORD_ROUTES.items():
        if any(k in text for k in kws):
            return kind
    return "analysis"


def decompose(state: GraphState) -> GraphState:
    """Break the task into ordered subtasks, one per specialist kind."""
    task = state["task"]
    with span("supervisor.decompose", task=task):
        llm = LLMClient()
        # The LLM proposes a plan; we keep a deterministic skeleton so the graph
        # is exercised even with the mock provider.
        llm.complete(
            system="You are a supervisor that decomposes tasks for specialist agents.",
            prompt=f"Decompose this task into subtasks: {task}",
        )
        plan: list[Subtask] = [
            {
                "id": "s1",
                "kind": _route(task),
                "instruction": task,
                "status": "pending",
                "result": "",
                "confidence": 0.0,
            }
        ]
    return {
        "plan": plan,
        "retries": state.get("retries", 0),
        "trace": [{"node": "supervisor", "event": "decompose", "subtasks": len(plan)}],
    }


def reduce(state: GraphState) -> GraphState:
    """Combine completed subtasks into a final answer."""
    with span("supervisor.reduce"):
        parts = [c["result"] for c in state.get("completed", []) if c["status"] == "done"]
        answer = "\n\n".join(parts) if parts else "(no specialist output)"
    return {
        "answer": answer,
        "trace": [{"node": "supervisor", "event": "reduce", "parts": len(parts)}],
    }
