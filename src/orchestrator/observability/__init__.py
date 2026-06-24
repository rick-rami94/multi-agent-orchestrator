"""Observability: OpenTelemetry tracing for planning, tools, memory, escalation."""
from .tracing import setup_tracing, span

__all__ = ["setup_tracing", "span"]
