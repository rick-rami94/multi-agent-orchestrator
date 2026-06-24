"""Shared state passed between graph nodes."""
from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

SpecialistKind = Literal["research", "analysis", "writing", "code"]


class Subtask(TypedDict):
    id: str
    kind: SpecialistKind
    instruction: str
    status: Literal["pending", "done", "rejected"]
    result: str
    confidence: float


class GraphState(TypedDict, total=False):
    """The object that flows through every LangGraph node.

    `operator.add` reducers let parallel specialist nodes append to shared
    lists without clobbering each other.
    """

    task_id: str
    task: str

    plan: list[Subtask]
    completed: Annotated[list[Subtask], operator.add]
    tools_used: Annotated[list[str], operator.add]

    retries: int
    quality: float
    confidence: float

    # Human-in-the-loop
    escalated: bool
    escalation_reason: str
    approval: str  # notify | approve_action | approve_plan | take_over

    # Final
    answer: str
    trace: Annotated[list[dict], operator.add]
