"""Human-in-the-loop decisions are meaningful and fully audited.

Covers all four decisions (approve / reject / edit / take_over), the required
reviewer text for edit/take_over, the workflow-influencing final result, and the
provenance captured in the tamper-evident audit record.
"""

from __future__ import annotations

import pytest

import orchestrator.hitl.queue as queue_mod
from orchestrator.hitl.audit import AuditChain
from orchestrator.hitl.queue import ReviewItem, ReviewQueue


@pytest.fixture
def queue():
    queue_mod._LOCAL.clear()
    AuditChain().clear()
    yield ReviewQueue()
    queue_mod._LOCAL.clear()
    AuditChain().clear()


def _item(task_id: str = "t1") -> ReviewItem:
    return ReviewItem(
        task_id=task_id,
        task="do the thing",
        reason="low_confidence",
        level="approve_action",
        proposed_action="proposed answer",
        confidence=0.4,
        quality=0.5,
    )


def test_approve_keeps_proposed_action(queue):
    queue.push(_item())
    res = queue.resolve(0, "approve", approver="alice")
    assert res.final_result == "proposed answer"
    assert res.decision == "approve"
    assert res.approver == "alice"


def test_reject_discards_the_result(queue):
    queue.push(_item())
    res = queue.resolve(0, "reject", approver="alice")
    assert res.final_result is None


def test_edit_substitutes_reviewer_text(queue):
    queue.push(_item())
    res = queue.resolve(0, "edit", approver="alice", note="corrected answer")
    assert res.final_result == "corrected answer"
    assert res.final_input == "corrected answer"


def test_take_over_makes_human_answer_final(queue):
    queue.push(_item())
    res = queue.resolve(0, "take_over", approver="alice", note="the human answer")
    assert res.final_result == "the human answer"


def test_edit_requires_reviewer_text(queue):
    queue.push(_item())
    with pytest.raises(ValueError):
        queue.resolve(0, "edit", approver="alice", note="   ")


def test_take_over_requires_reviewer_text(queue):
    queue.push(_item())
    with pytest.raises(ValueError):
        queue.resolve(0, "take_over", approver="alice")


def test_unknown_decision_is_rejected(queue):
    queue.push(_item())
    with pytest.raises(ValueError):
        queue.resolve(0, "frobnicate", approver="alice")


def test_resolve_requires_an_approver(queue):
    queue.push(_item())
    with pytest.raises(ValueError):
        queue.resolve(0, "approve", approver="")


def test_out_of_range_index_returns_none(queue):
    assert queue.resolve(5, "approve", approver="alice") is None


def test_audit_record_has_full_provenance(queue):
    queue.push(_item("task-42"))
    queue.resolve(0, "edit", approver="alice", note="revised text")

    log = queue.audit_log()
    assert len(log) == 1
    rec = log[0]
    for f in (
        "task_id",
        "action",
        "decision",
        "approver",
        "timestamp",
        "proposed_action",
        "final_input",
        "previous_hash",
        "record_hash",
    ):
        assert f in rec
    assert rec["task_id"] == "task-42"
    assert rec["decision"] == "edit"
    assert rec["approver"] == "alice"
    assert rec["proposed_action"] == "proposed answer"
    assert rec["final_input"] == "revised text"
    # The decision is committed to a verifiable chain.
    assert AuditChain().verify()[0] is True
