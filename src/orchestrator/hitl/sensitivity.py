"""Sensitivity classification for escalation (VA-02).

The previous gate was a raw substring blocklist (``"drop table" in text``),
trivially bypassed by spacing/case ("DROP  TABLE", "drop_table"). This module:

  1. Normalizes text (lowercase, collapse non-alphanumerics to single spaces)
     so spacing/punctuation tricks don't evade detection.
  2. Matches destructive/sensitive intent with word-boundary regexes over a
     broad verb+object set.

IMPORTANT: heuristic text matching is *defense in depth only* — a weak signal,
never the authoritative control. The authoritative gate is the allow-list on
side-effecting tools (see ``tools.registry``): any tool that can cause external
effects requires explicit human approval regardless of what this classifier
says. Treat a "not sensitive" result as "no extra signal", not "safe".
"""
from __future__ import annotations

import re

# Patterns operate on normalized text (see _normalize). Word boundaries prevent
# substring false positives while spacing normalization prevents evasion.
_PATTERNS: tuple[tuple[str, str], ...] = (
    ("destructive_db", r"\b(drop|truncate|delete)\b.*\b(table|database|schema|collection|index)\b"),
    ("destructive_fs", r"\brm\b.*\b(rf|r f|fr)\b|\b(delete|remove|wipe|erase|format)\b.*\b(file|files|directory|disk|volume|all)\b"),
    ("funds", r"\b(transfer|wire|send|withdraw|refund|charge)\b.*\b(funds|money|payment|dollars|usd|btc|eth|account)\b"),
    ("deploy", r"\b(deploy|release|rollback|ship|promote)\b.*\b(prod|production|live|main|master)\b"),
    ("comms", r"\b(send|publish|post|email|tweet|broadcast)\b.*\b(email|message|customers|users|public|everyone)\b"),
    ("access", r"\b(grant|revoke|escalate|disable|drop)\b.*\b(access|permission|permissions|role|admin|root|privilege)\b"),
    ("secrets", r"\b(reveal|print|dump|exfiltrate|leak|export)\b.*\b(secret|secrets|password|passwords|credential|credentials|api[_ ]?key|token)\b"),
    ("infra", r"\b(shutdown|terminate|destroy|delete|stop)\b.*\b(instance|server|cluster|node|pod|service|infra|infrastructure)\b"),
)

_COMPILED = tuple((label, re.compile(pat)) for label, pat in _PATTERNS)


def _normalize(text: str) -> str:
    """Lowercase and collapse any run of non-alphanumerics to one space."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def classify(text: str) -> tuple[bool, list[str]]:
    """Return (is_sensitive, matched_labels) for the given text."""
    norm = _normalize(text or "")
    matched = [label for label, rx in _COMPILED if rx.search(norm)]
    return (bool(matched), matched)


def is_sensitive(text: str) -> bool:
    return classify(text)[0]
