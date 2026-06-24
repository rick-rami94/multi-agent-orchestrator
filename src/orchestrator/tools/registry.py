"""A registry of tools available to specialists.

Each tool carries a name, JSON schema, and a simple token-bucket rate limit.
Register with the @tool decorator; specialists look tools up by name.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    rate_per_min: int
    allowance: float = field(init=False)
    last: float = field(default=0.0)

    def __post_init__(self) -> None:
        self.allowance = float(self.rate_per_min)

    def take(self, now: float) -> bool:
        if self.last == 0.0:
            self.last = now
        self.allowance += (now - self.last) * (self.rate_per_min / 60.0)
        self.last = now
        self.allowance = min(self.allowance, float(self.rate_per_min))
        if self.allowance < 1.0:
            return False
        self.allowance -= 1.0
        return True


@dataclass
class Tool:
    name: str
    fn: Callable[..., str]
    schema: dict
    rate_per_min: int = 60
    # Tools that can cause external effects (writes, payments, deploys, comms)
    # must be human-approved unless explicitly allow-listed (VA-02).
    side_effecting: bool = False
    approved: bool = False
    _bucket: _Bucket = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._bucket = _Bucket(self.rate_per_min)

    def __call__(self, **kwargs) -> str:
        now = time.monotonic()
        if not self._bucket.take(now):
            raise RuntimeError(f"rate limit exceeded for tool '{self.name}'")
        return self.fn(**kwargs)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, t: Tool) -> None:
        self._tools[t.name] = t

    def call(self, name: str, **kwargs) -> str:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name](**kwargs)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def requires_approval(self, name: str) -> bool:
        """True if using this tool must be gated by human approval.

        Default-deny: an unknown tool, or a side-effecting tool that has not
        been explicitly allow-listed, requires approval.
        """
        t = self._tools.get(name)
        if t is None:
            return True
        return t.side_effecting and not t.approved

    def schemas(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "schema": t.schema,
                "rate_per_min": t.rate_per_min,
                "side_effecting": t.side_effecting,
                "approved": t.approved,
            }
            for t in self._tools.values()
        ]


REGISTRY = ToolRegistry()


def tool(
    name: str, schema: dict, rate_per_min: int = 60, side_effecting: bool = False, approved: bool = False
):
    """Decorator to register a function as a rate-limited tool."""

    def deco(fn: Callable[..., str]) -> Callable[..., str]:
        REGISTRY.register(
            Tool(
                name=name,
                fn=fn,
                schema=schema,
                rate_per_min=rate_per_min,
                side_effecting=side_effecting,
                approved=approved,
            )
        )
        return fn

    return deco


# ── built-in demo tools ──────────────────────────────────────────
@tool(
    name="web_search",
    schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    rate_per_min=30,
)
def web_search(query: str) -> str:
    """Stub web search — replace with a real provider (Tavily, SerpAPI, etc.)."""
    return f"[web_search results for: {query}]"


@tool(
    name="calculator",
    schema={"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
    rate_per_min=120,
)
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression safely.

    Uses an AST walker rather than ``eval``: only +, -, *, /, %, and unary
    minus are permitted. Exponentiation (``**``) is deliberately rejected to
    avoid resource-exhaustion (e.g. ``9**9**9``).
    """
    return str(_safe_arith(expression))


def _safe_arith(expression: str):
    import ast

    _BIN = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.Mod: lambda a, b: a % b,
    }

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = _eval(node.operand)
            return +v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return _BIN[type(node.op)](_eval(node.left), _eval(node.right))
        raise ValueError("unsupported expression")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("invalid expression") from exc
    return _eval(tree)
