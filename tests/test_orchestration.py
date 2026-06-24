"""Multi-agent orchestration: many subtasks, routed and aggregated.

Proves the supervisor decomposes into several specialist subtasks when the task
calls for it, the right specialists run, and the reducer merges every output
into one coherent answer — all on the deterministic mock provider.
"""

from __future__ import annotations

from orchestrator.graph import run_task
from orchestrator.graph.supervisor import plan_subtasks


def test_plan_creates_multiple_subtasks_across_specialists():
    plan = plan_subtasks("Research the options, analyze the trade-offs, and write a summary")
    kinds = [s["kind"] for s in plan]
    assert "research" in kinds
    assert "analysis" in kinds
    assert "writing" in kinds
    assert len(plan) >= 3
    # Subtask ids are unique so completion tracking is unambiguous.
    assert len({s["id"] for s in plan}) == len(plan)


def test_plan_orders_kinds_into_a_pipeline():
    plan = plan_subtasks("Write a report and research the sources first")
    kinds = [s["kind"] for s in plan]
    # Canonical pipeline order regardless of mention order.
    assert kinds.index("research") < kinds.index("writing")


def test_plan_defaults_to_single_analysis_when_unmatched():
    plan = plan_subtasks("zzz nonspecific request")
    assert [s["kind"] for s in plan] == ["analysis"]


def test_reducer_aggregates_multiple_specialist_outputs():
    result = run_task("Research vector DBs, analyze the trade-offs, and write a recommendation")
    assert len(result["completed"]) >= 3
    for sub in result["completed"]:
        assert sub["status"] == "done"
        # Every specialist's output appears as its own labelled section.
        assert f"### {sub['kind'].title()} specialist" in result["answer"]


def test_single_specialist_task_still_runs_end_to_end():
    result = run_task("Summarize the quarterly report")  # -> writing only
    assert [c["kind"] for c in result["completed"]] == ["writing"]
    assert result["answer"]
