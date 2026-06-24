"""Tamper-evident audit chain: valid chains verify, tampered chains are caught."""

from __future__ import annotations

import json

import pytest

import orchestrator.hitl.audit as audit
from orchestrator.hitl.audit import AuditChain


@pytest.fixture
def chain():
    c = AuditChain()
    c.clear()
    yield c
    c.clear()


def test_record_carries_all_required_fields(chain):
    rec = chain.append(task_id="t1", action="approve_action", decision="approve", approver="alice")
    for f in (
        "timestamp",
        "task_id",
        "action",
        "decision",
        "approver",
        "previous_hash",
        "record_hash",
    ):
        assert f in rec


def test_each_record_links_to_its_predecessor(chain):
    r1 = chain.append(task_id="t1", action="a", decision="approve", approver="x")
    r2 = chain.append(task_id="t2", action="a", decision="reject", approver="y")
    assert r1["previous_hash"] == audit.GENESIS_HASH
    assert r2["previous_hash"] == r1["record_hash"]


def test_valid_chain_verifies(chain):
    chain.append(task_id="t1", action="approve_action", decision="approve", approver="alice")
    chain.append(
        task_id="t2",
        action="take_over",
        decision="take_over",
        approver="bob",
        final_input="human answer",
    )
    intact, broken_at = chain.verify()
    assert intact is True
    assert broken_at is None


def test_tampered_record_is_detected(chain):
    chain.append(task_id="t1", action="approve_action", decision="approve", approver="alice")
    chain.append(task_id="t2", action="approve_action", decision="reject", approver="bob")
    assert chain.verify()[0] is True

    # Flip the first record's decision in the underlying store.
    rec = json.loads(audit._LOCAL[0])
    rec["decision"] = "take_over"
    audit._LOCAL[0] = json.dumps(rec)

    intact, broken_at = chain.verify()
    assert intact is False
    assert broken_at == 0


def test_deleting_a_record_breaks_the_chain(chain):
    chain.append(task_id="t1", action="a", decision="approve", approver="x")
    chain.append(task_id="t2", action="a", decision="approve", approver="y")
    chain.append(task_id="t3", action="a", decision="approve", approver="z")
    # Remove the middle record: the link from #1 -> #2 (now #3) no longer holds.
    del audit._LOCAL[1]
    intact, broken_at = chain.verify()
    assert intact is False
    assert broken_at == 1
