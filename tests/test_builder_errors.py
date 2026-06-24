"""Exception handling: real bugs surface; only missing LangGraph falls back.

The old builder wrapped graph execution in a bare ``except Exception`` and
silently dropped to the fallback executor, hiding real runtime errors. These
tests pin the corrected contract.
"""

from __future__ import annotations

import pytest

from orchestrator.graph import builder


def test_real_node_error_is_not_swallowed(monkeypatch):
    """An exception raised inside a node must propagate, not be masked."""

    def boom(state):
        raise RuntimeError("specialist exploded")

    monkeypatch.setitem(builder._SPECIALIST_FN, "analysis", boom)
    with pytest.raises(RuntimeError, match="specialist exploded"):
        builder.run_task("Analyze the options")  # routes to the analysis specialist


def test_missing_langgraph_falls_back(monkeypatch):
    """ImportError (optional dep absent) is the *only* trigger for the fallback."""

    def missing():
        raise ImportError("No module named 'langgraph'")

    monkeypatch.setattr(builder, "build_graph", missing)
    result = builder.run_task("Summarize the report")
    assert result["answer"]  # fallback executor produced a real result


def test_non_import_error_from_build_propagates(monkeypatch):
    """A real misconfiguration during graph build must not be swallowed."""

    def broken():
        raise ValueError("graph misconfigured")

    monkeypatch.setattr(builder, "build_graph", broken)
    with pytest.raises(ValueError, match="graph misconfigured"):
        builder.run_task("Summarize the report")
