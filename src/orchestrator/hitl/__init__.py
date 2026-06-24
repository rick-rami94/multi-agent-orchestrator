"""Human-in-the-loop: escalation triggers + review queue + audit chain."""

from .audit import AuditChain, verify_audit
from .auth import AuthError, Reviewer, authenticate
from .escalation import ApprovalLevel, escalate
from .queue import Resolution, ReviewItem, ReviewQueue
from .sensitivity import classify, is_sensitive

__all__ = [
    "ApprovalLevel",
    "escalate",
    "ReviewItem",
    "ReviewQueue",
    "Resolution",
    "AuditChain",
    "verify_audit",
    "AuthError",
    "Reviewer",
    "authenticate",
    "classify",
    "is_sensitive",
]
