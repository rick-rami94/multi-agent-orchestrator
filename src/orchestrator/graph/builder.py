"""Assemble the LangGraph: supervisor -> specialists -> reviewer -> (escalate|done).

Falls back to a plain in-process executor when LangGraph isn't installed, so the
demo and tests run anywhere.
"""

from __future__ import annotations

import logging
import uuid

from ..hitl.escalation import escalate as do_escalate
from ..memory.long_term import LongTermMemory
from ..memory.short_term import ShortTermMemory
from . import reviewer, specialists, supervisor
from .state import GraphState

logger = logging.getLogger(__name__)

_SPECIALIST_FN = {
    "research": specialists.research,
    "analysis": specialists.analysis,
    "writing": specialists.writing,
    "code": specialists.code,
}


def _next_specialist(state: GraphState) -> str:
    """Route to the next un-run subtask's specialist, or 'reduce' when done.

    Completion is tracked by id in the accumulated `completed` list, so the
    dispatch loop walks the whole plan one subtask at a time.
    """
    done_ids = {c["id"] for c in state.get("completed", [])}
    pending = [s for s in state.get("plan", []) if s["id"] not in done_ids]
    return pending[0]["kind"] if pending else "reduce"


def _after_review(state: GraphState) -> str:
    return "escalate" if state.get("escalated") else "dispatch"


def _dispatch(state: GraphState) -> GraphState:
    """Pass-through node; routing happens on its conditional edges."""
    return {}


def build_graph():
    """Build a compiled LangGraph StateGraph (when available).

    Topology: supervisor -> dispatch -> (specialist -> reviewer -> [escalate] ->
    dispatch)* -> reduce. The dispatch loop runs every planned subtask, so a
    multi-subtask plan exercises several specialists in one run.
    """
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(GraphState)
    g.add_node("supervisor", supervisor.decompose)
    g.add_node("dispatch", _dispatch)
    for kind, fn in _SPECIALIST_FN.items():
        g.add_node(kind, fn)
    g.add_node("reviewer", reviewer.review)
    g.add_node("escalate", do_escalate)
    g.add_node("reduce", supervisor.reduce)

    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", "dispatch")
    # Path map: each router return value -> destination node. Specialist kinds map
    # to their like-named nodes; "reduce" ends the dispatch loop.
    dispatch_routes = {kind: kind for kind in _SPECIALIST_FN}
    dispatch_routes["reduce"] = "reduce"
    g.add_conditional_edges("dispatch", _next_specialist, dispatch_routes)
    for kind in _SPECIALIST_FN:
        g.add_edge(kind, "reviewer")
    g.add_conditional_edges("reviewer", _after_review, {"escalate": "escalate", "dispatch": "dispatch"})
    g.add_edge("escalate", "dispatch")
    g.add_edge("reduce", END)
    return g.compile()


# List fields that LangGraph would accumulate via operator.add reducers; the
# fallback executor mirrors that so both paths produce identical state.
_ACCUMULATING = ("trace", "completed", "tools_used", "escalations")


def _merge(state: GraphState, update: GraphState) -> None:
    """Apply a node's output, accumulating list fields like LangGraph reducers."""
    for key, value in update.items():
        if key in _ACCUMULATING and isinstance(value, list):
            state[key] = state.get(key, []) + value
        else:
            state[key] = value


def _run_fallback(state: GraphState) -> GraphState:
    """Mirror the graph topology without LangGraph installed.

    Real exceptions raised by any node propagate out of here unchanged — only
    the *absence* of LangGraph routes execution to this executor (see run_task).
    """
    _merge(state, supervisor.decompose(state))
    # Bounded by plan size (+1 slack) purely as a runaway guard; the loop exits
    # naturally once every subtask id is in `completed`.
    for _ in range(len(state.get("plan", [])) + 1):
        kind = _next_specialist(state)
        if kind == "reduce":
            break
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

    state: GraphState = {"task_id": task_id, "task": task, "retries": 0, "completed": [], "trace": []}

    # Only fall back when LangGraph (an *optional* dependency) is unavailable.
    # Any other error — including real bugs inside graph execution — must surface
    # rather than be silently masked by the fallback executor.
    try:
        graph = build_graph()
    except ImportError as exc:
        logger.info("LangGraph unavailable (%s); using in-process fallback executor", exc)
        result = _run_fallback(state)
    else:
        result = graph.invoke(state)

    # Persist what worked into long-term semantic memory.
    LongTermMemory().remember(
        task=task,
        outcome=result.get("answer", ""),
        metadata={"task_id": task_id, "quality": result.get("quality", 0.0)},
    )
    return result
