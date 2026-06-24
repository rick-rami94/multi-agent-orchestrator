"""Security posture: secure-by-default auth and default-deny tool approval."""

from __future__ import annotations

import pytest

from orchestrator.config import get_settings
from orchestrator.hitl.auth import AuthError, authenticate
from orchestrator.tools.registry import REGISTRY, Tool


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _configure(**overrides):
    settings = get_settings()
    for key, value in overrides.items():
        object.__setattr__(settings, key, value)
    return settings


# ── auth (VA-01) ────────────────────────────────────────────────────────────
def test_auth_enabled_but_no_users_fails_closed():
    _configure(review_auth_enabled=True, review_users="")
    with pytest.raises(AuthError):
        authenticate("alice", "whatever")


def test_invalid_token_is_rejected():
    _configure(review_auth_enabled=True, review_users="alice:s3cret")
    with pytest.raises(AuthError):
        authenticate("alice", "wrong-token")


def test_valid_token_authenticates():
    _configure(review_auth_enabled=True, review_users="alice:s3cret")
    assert authenticate("alice", "s3cret").name == "alice"


def test_unknown_user_is_rejected():
    _configure(review_auth_enabled=True, review_users="alice:s3cret")
    with pytest.raises(AuthError):
        authenticate("mallory", "s3cret")


# ── tool approval (VA-02, default-deny) ─────────────────────────────────────
def test_side_effecting_unapproved_tool_requires_approval():
    REGISTRY.register(Tool(name="send_email_test", fn=lambda **k: "sent", schema={}, side_effecting=True))
    assert REGISTRY.requires_approval("send_email_test") is True


def test_approved_side_effecting_tool_is_allowed():
    REGISTRY.register(
        Tool(
            name="deploy_test",
            fn=lambda **k: "ok",
            schema={},
            side_effecting=True,
            approved=True,
        )
    )
    assert REGISTRY.requires_approval("deploy_test") is False


def test_approved_non_side_effecting_tool_does_not_require_approval():
    # The built-in read-only tools are explicitly safe.
    assert REGISTRY.requires_approval("web_search") is False
    assert REGISTRY.requires_approval("calculator") is False


def test_unknown_tool_defaults_to_requiring_approval():
    assert REGISTRY.requires_approval("does-not-exist") is True
