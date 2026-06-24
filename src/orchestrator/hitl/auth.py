"""Authentication for the human-in-the-loop review surface (VA-01).

Approvals must be *attributable* — every resolution records which reviewer made
it. Tokens are compared in constant time. The system is secure by default:
authentication is on unless explicitly disabled for a local demo, and an
enabled-but-unconfigured deployment fails closed (no reviewers => no access).
"""

from __future__ import annotations

import hmac
import time
from dataclasses import dataclass

from ..config import get_settings


@dataclass(frozen=True)
class Reviewer:
    name: str


def _parse_users(raw: str) -> dict[str, str]:
    users: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        name, _, token = pair.partition(":")
        name, token = name.strip(), token.strip()
        if name and token:
            users[name] = token
    return users


class AuthError(Exception):
    """Raised when authentication fails."""


def auth_enabled() -> bool:
    return get_settings().review_auth_enabled


def authenticate(name: str, token: str) -> Reviewer:
    """Return the Reviewer on success; raise AuthError otherwise.

    When auth is disabled (local demo only) any non-empty name is accepted and
    tagged so downstream audit records make the insecure mode obvious.
    """
    settings = get_settings()
    if not settings.review_auth_enabled:
        if not name.strip():
            raise AuthError("name required")
        return Reviewer(name=f"{name.strip()} (auth-disabled)")

    users = _parse_users(settings.review_users)
    if not users:
        # Enabled but unconfigured: fail closed rather than allow everyone.
        raise AuthError("review authentication is enabled but no REVIEW_USERS are configured")

    expected = users.get(name)
    # Always run a comparison to avoid leaking which names exist via timing.
    candidate = expected if expected is not None else ""
    ok = hmac.compare_digest(candidate, token) and expected is not None
    if not ok:
        raise AuthError("invalid credentials")
    return Reviewer(name=name)


def session_timeout_seconds() -> int:
    """Configured reviewer-session lifetime in seconds (0 = no expiry)."""
    return max(0, get_settings().review_session_timeout_minutes) * 60


def session_expired(authenticated_at: float, now: float | None = None) -> bool:
    """Whether a session started at `authenticated_at` (epoch seconds) has aged out.

    Absolute timeout from sign-in: a privileged approval surface should re-verify
    the human periodically rather than trust an indefinitely open tab. A configured
    timeout of 0 disables expiry (not recommended). `now` is injectable for tests.
    """
    ttl = session_timeout_seconds()
    if ttl <= 0:
        return False
    current = time.time() if now is None else now
    return (current - authenticated_at) >= ttl
