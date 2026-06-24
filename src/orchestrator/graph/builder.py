"""Assemble the LangGraph: supervisor -> specialists -> reviewer -> (escalate|done).

Falls back to a plain in-process executor when LangGraph isn't installed, so the
demo and tests run anywhere.
"""
from __future__ import annotations

import uuid

from ..hitl.escalation import escalate as do_escalate
from ..memory.long_term import LongTermMemory
from ..memory.short_term import ShortTermMemory
from . import reviewer, specialists, supervisor
from .state import GraphState

_SPECIALIST_FN = {
    "research": specialists.research,
    "analysis": specialists.analysis,
    "writing": specialists.writing,
    "code": specialists.code,
}


def _route_to_specialist(state: GraphState) -> str:
    plan = state.get("plan", [])
    pending = next((s for s in plan if s["status"] == "pending"), None)
    return pending["kind"] if pending else "analysis"


def _after_review(state: GraphState) -> str:
    if state.get("escalated"):
        return "escalate"
    return "reduce"


def build_graph():
    """Build a compiled LangGraph StateGraph (when available)."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(GraphState)
    g.add_node("supervisor", supervisor.decompose)
    for kind, fn in _SPECIALIST_FN.items():
        g.add_node(kind, fn)
    g.add_node("reviewer", reviewer.review)
    g.add_node("escalate", do_escalate)
    g.add_node("reduce", supervisor.reduce)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", _route_to_specialist, dict.fromkeys(_SPECIALIST_FN))
    for kind in _SPECIALIST_FN:
        g.add_edge(kind, "reviewer")
    g.add_conditional_edges("reviewer", _after_review, {"escalate": "escalate", "reduce": "reduce"})
    g.add_edge("escalate", "reduce")
    g.add_edge("reduce", END)
    return g.compile()


_ACCUMULATING = ("trace", "completed")


def _merge(state: GraphState, update: GraphState) -> None:
    """Apply a node's output, accumulating list fields like LangGraph reducers."""
    for key, value in update.items():
        if key in _ACCUMULATING and isinstance(value, list):
            state[key] = state.get(key, []) + value
        else:
            state[key] = value


def _run_fallback(state: GraphState) -> GraphState:
    """Mirror the graph topology without LangGraph installed."""
    _merge(state, supervisor.decompose(state))
    kind = _route_to_specialist(state)
    _merge(state, _SPECIALIST_FN[kind](state))
    _merge(state, reviewer.review(state))
    if state.get("escalated"):
        _merge(state, do_escalate(state))
    _merge(state, supervisor.reduce(state))
    return state


def run_task(task: str) -> GraphState:
    """Entry point: run one task through the orchestration graph."""
    from ..config import get_settings

    task = (task or "").strip()
    if not task:
        raise ValueError("task must not be empty")
    limit = get_settings().max_task_chars
    if len(task) > limit:
        raise ValueError(f"task exceeds maximum length of {limit} characters")

    task_id = uuid.uuid4().hex[:12]
    short = ShortTermMemory(task_id)
    short.set("task", task)

    state: GraphState = {"task_id": task_id, "task": task, "retries": 0,
                         "completed": [], "trace": []}
    try:
        graph = build_graph()
        result = graph.invoke(state)
    except Exception:  # pragma: no cover - LangGraph optional at runtime
        result = _run_fallback(state)

    # Persist what worked into long-term semantic memory.
    LongTermMemory().remember(
        task=task,
        outcome=result.get("answer", ""),
        metadata={"task_id": task_id, "quality": result.get("quality", 0.0)},
    )
    return result
