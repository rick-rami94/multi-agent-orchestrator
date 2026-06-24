"""CLI smoke tests: the `orchestrator` entry point runs end-to-end on the mock."""

from __future__ import annotations

import json

from orchestrator.main import cli


def test_no_task_prints_help_and_returns_1(capsys):
    rc = cli([])
    assert rc == 1
    out = capsys.readouterr()
    assert "usage" in (out.out + out.err).lower()


def test_runs_task_in_text_mode(capsys):
    rc = cli(["Summarize the quarterly report"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== ANSWER ===" in out
    assert "=== REVIEW ===" in out


def test_json_mode_emits_valid_json(capsys):
    rc = cli(["Summarize the quarterly report", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload.get("answer")


def test_trace_flag_prints_trace(capsys):
    rc = cli(["Research vector DBs and write a summary", "--trace"])
    assert rc == 0
    assert "=== TRACE ===" in capsys.readouterr().out
