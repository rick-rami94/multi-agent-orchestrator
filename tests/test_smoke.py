"""Smoke tests: exercise the orchestrator end-to-end with zero external services.

These assert the core promises of the project — that the full graph runs on the
deterministic mock provider with no API keys, Redis, or ChromaDB, and that the
security-critical gates (default-deny tool approval, sensitivity classification,
fail-closed reviewer auth, the safe calculator) behave as designed.
"""

from __future__ import annotations

import pytest

from orchestrator.config import get_settings
from orchestrator.graph import run_task
from orchestrator.hitl.auth import AuthError, authenticate
from orchestrator.hitl.sensitivity import classify
from orchestrator.tools.registry import REGISTRY


def test_runs_on_mock_provider_without_keys():
    """The whole graph completes and the provider downgrades to mock."""
    assert get_settings().active_provider == "mock"

    result = run_task("Research the trade-offs of vector databases")

    assert isinstance(result, dict)
    assert result.get("answer")
    assert isinstance(result.get("quality"), float)
    assert isinstance(result.get("confidence"), float)
    # The supervisor + at least one specialist + reviewer all emit trace events.
    assert len(result.get("trace", [])) >= 3


def test_empty_task_is_rejected():
    with pytest.raises(ValueError):
        run_task("   ")


def test_task_over_max_length_is_rejected():
    limit = get_settings().max_task_chars
    with pytest.raises(ValueError):
        run_task("x" * (limit + 1))


def test_side_effecting_tools_default_deny():
    """Unknown tools, and unapproved side-effecting ones, require approval."""
    assert REGISTRY.requires_approval("does-not-exist") is True
    # Built-in demo tools are read-only and explicitly safe.
    assert REGISTRY.requires_approval("web_search") is False
    assert REGISTRY.requires_approval("calculator") is False


def test_sensitivity_classifier_resists_spacing_evasion():
    """The classifier normalizes text so spacing/case tricks don't slip through."""
    flagged, labels = classify("Please DROP   TABLE users;")
    assert flagged is True
    assert "destructive_db" in labels

    benign, _ = classify("Summarize the quarterly report for the team.")
    assert benign is False


def test_reviewer_auth_fails_closed_when_unconfigured():
    """Auth on but no REVIEW_USERS configured => nobody gets in."""
    get_settings.cache_clear()
    settings = get_settings()
    object.__setattr__(settings, "review_auth_enabled", True)
    object.__setattr__(settings, "review_users", "")
    try:
        with pytest.raises(AuthError):
            authenticate("alice", "whatever")
    finally:
        get_settings.cache_clear()


def test_calculator_rejects_exponentiation():
    """The safe arithmetic evaluator refuses ** (resource-exhaustion guard)."""
    assert REGISTRY.call("calculator", expression="2 + 3 * 4") == "14"
    with pytest.raises(ValueError):
        REGISTRY.call("calculator", expression="9 ** 9 ** 9")
