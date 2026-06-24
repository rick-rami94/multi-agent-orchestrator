"""Human-in-the-loop: escalation triggers + review queue."""
from .auth import AuthError, Reviewer, authenticate
from .escalation import ApprovalLevel, escalate
from .queue import ReviewItem, ReviewQueue
from .sensitivity import classify, is_sensitive

__all__ = [
    "ApprovalLevel",
    "escalate",
    "ReviewItem",
    "ReviewQueue",
    "AuthError",
    "Reviewer",
    "authenticate",
    "classify",
    "is_sensitive",
]
