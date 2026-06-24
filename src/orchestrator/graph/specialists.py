"""Specialist nodes: research, analysis, writing, code.

Each specialist is tool-using: it pulls relevant long-term memories, may call a
registered tool, and produces a result with a self-reported confidence.
"""

from __future__ import annotations

from ..llm import LLMClient
from ..memory.long_term import LongTermMemory
from ..observability.tracing import span
from ..tools.registry import REGISTRY
from .state import GraphState, Subtask

_SYSTEM = {
    "research": "You are a research specialist. Gather and cite relevant facts.",
    "analysis": "You are an analysis specialist. Evaluate options and recommend.",
    "writing": "You are a writing specialist. Produce clear, structured prose.",
    "code": "You are a coding specialist. Write correct, tested code.",
}


def _run_specialist(state: GraphState, kind: str) -> GraphState:
    plan = state.get("plan", [])
    # A subtask is "pending" until its id shows up in the accumulated `completed`
    # list. Tracking completion by id (rather than mutating plan status) keeps the
    # node pure and lets several subtasks of the same kind run in sequence.
    done_ids = {c["id"] for c in state.get("completed", [])}
    subtask = next((s for s in plan if s["kind"] == kind and s["id"] not in done_ids), None)
    if subtask is None:
        return {}

    with span(f"specialist.{kind}", subtask=subtask["id"]):
        memories = LongTermMemory().recall(subtask["instruction"], k=3)
        memo_hint = f" (recalled {len(memories)} memories)" if memories else ""

        # Specialists may use registered tools; demo invokes a safe one if present.
        tool_note = ""
        tools_used: list[str] = []
        if kind == "research" and "web_search" in REGISTRY:
            tool_note = REGISTRY.call("web_search", query=subtask["instruction"])
            tools_used.append("web_search")

        llm = LLMClient()
        out = llm.complete(
            system=_SYSTEM[kind],
            prompt=f"{subtask['instruction']}\n{tool_note}".strip(),
        )
        done: Subtask = {
            **subtask,
            "status": "done",
            "result": f"{out.text}{memo_hint}",
            "confidence": 0.75,
        }
    return {
        "completed": [done],
        "confidence": done["confidence"],
        "tools_used": tools_used,
        "trace": [
            {
                "node": f"specialist.{kind}",
                "event": "complete",
                "provider": out.provider,
                "tools_used": tools_used,
            }
        ],
    }


def research(state: GraphState) -> GraphState:
    return _run_specialist(state, "research")


def analysis(state: GraphState) -> GraphState:
    return _run_specialist(state, "analysis")


def writing(state: GraphState) -> GraphState:
    return _run_specialist(state, "writing")


def code(state: GraphState) -> GraphState:
    return _run_specialist(state, "code")
