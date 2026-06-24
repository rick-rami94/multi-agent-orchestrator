"""Tool registry: every tool declares a name, schema, and rate limit."""

from .registry import REGISTRY, Tool, tool

__all__ = ["REGISTRY", "Tool", "tool"]
