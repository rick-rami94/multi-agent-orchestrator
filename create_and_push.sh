#!/usr/bin/env bash
#
# Create the GitHub repo and push this scaffold.
#
# Prereqs:
#   - GitHub CLI installed and authenticated:  gh auth login
#   - Run this script from the project root (where this file lives).
#
# Usage:
#   ./create_and_push.sh [repo-name] [--private]
#
set -euo pipefail

REPO_NAME="${1:-multi-agent-orchestrator}"
VISIBILITY="public"
if [[ "${2:-}" == "--private" ]]; then
  VISIBILITY="private"
fi

DESC="Multi-agent orchestration with persistent memory and human-in-the-loop (LangGraph, OpenAI+Anthropic, Postgres/ChromaDB, Redis+Celery, Streamlit, Docker)."

cd "$(dirname "$0")"

# 1. Initialize git (idempotent)
if [[ ! -d .git ]]; then
  git init -b main
fi

git add -A
if git diff --cached --quiet; then
  echo "Nothing to commit."
else
  git commit -m "Scaffold multi-agent orchestrator (Phases 1-5)"
fi

# 2. Create the repo on GitHub and push.
#    gh reads the authenticated account; the repo is created under it.
if gh repo view "$REPO_NAME" >/dev/null 2>&1; then
  echo "Repo already exists; pushing to it."
  git remote get-url origin >/dev/null 2>&1 || \
    git remote add origin "$(gh repo view "$REPO_NAME" --json sshUrl -q .sshUrl)"
  git push -u origin main
else
  gh repo create "$REPO_NAME" \
    --"$VISIBILITY" \
    --source=. \
    --remote=origin \
    --description "$DESC" \
    --push
fi

echo
echo "✅ Done. View it:  gh repo view --web $REPO_NAME"
