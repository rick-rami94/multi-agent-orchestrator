"""CLI entry point: run a task through the orchestration graph."""

from __future__ import annotations

import argparse
import json
import sys

from .config import get_settings
from .graph import run_task
from .observability.tracing import setup_tracing


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a task through the multi-agent orchestrator.")
    parser.add_argument("task", nargs="?", help="The task to execute.")
    parser.add_argument("--trace", action="store_true", help="Print the full execution trace.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    if not args.task:
        parser.print_help()
        return 1

    setup_tracing()
    settings = get_settings()
    print(f"› provider={settings.active_provider}  task={args.task!r}", file=sys.stderr)

    result = run_task(args.task)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    print("\n=== ANSWER ===")
    print(result.get("answer", "(none)"))
    print("\n=== REVIEW ===")
    print(
        f"quality={result.get('quality')}  confidence={result.get('confidence')}  "
        f"escalated={result.get('escalated')}  reason={result.get('escalation_reason', '')}"
    )
    if args.trace:
        print("\n=== TRACE ===")
        for evt in result.get("trace", []):
            print(json.dumps(evt))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
