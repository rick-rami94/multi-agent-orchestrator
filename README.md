# Multi-Agent Orchestrator

A production-shaped reference implementation of a **supervisor → specialist → reviewer** agent
system with persistent memory, a security-first **human-in-the-loop (HITL)** approval layer, tool
use with rate limiting, and OpenTelemetry tracing.

Built on **LangGraph**, provider-agnostic across **OpenAI** and **Anthropic**, with **Postgres**,
**ChromaDB**, and **Redis + Celery** behind it — and a **Streamlit** console for human reviewers.

> **Runs with zero API keys.** Every external dependency (LLM providers, Redis, ChromaDB,
> LangGraph) degrades gracefully to a deterministic in-process fallback, so you can clone and run
> the entire graph end-to-end before configuring anything.

---

## What it does

A task enters the graph and flows through four roles:

1. **Supervisor** decomposes the task and routes it to the right specialist, then reduces the
   specialist outputs into a final answer.
2. **Specialists** (`research`, `analysis`, `writing`, `code`) do the work. Each one recalls
   relevant long-term memories, may call a registered tool, and reports its own confidence.
3. **Reviewer** scores the output and decides whether to accept it or escalate to a human.
4. **Escalation** packages the context and pushes it onto a review queue for an authenticated
   human to approve, reject, or take over.

```
                    ┌─────────────┐
   task ───────────▶│ Supervisor  │  decompose + route
                    └──────┬──────┘
            ┌──────────────┼──────────────┬───────────────┐
            ▼              ▼              ▼               ▼
        research       analysis        writing          code      (tool-using specialists)
            └──────────────┴──────────────┴───────────────┘
                                 ▼
                          ┌─────────────┐
                          │  Reviewer   │  quality / confidence / sensitivity gate
                          └──────┬──────┘
                       accept    │   escalate
                           ┌─────┴─────┐
                           ▼           ▼
                      ┌────────┐  ┌───────────┐
                      │ Reduce │◀─│ Escalate  │ → Redis review queue → Streamlit HITL console
                      └───┬────┘  └───────────┘
                          ▼
                    final answer  ──▶  persisted to long-term memory
```

## Design highlights

- **Stateful graph, not a prompt chain.** Roles are LangGraph nodes over a shared, typed
  `GraphState`. Parallel specialist outputs accumulate via `operator.add` reducers instead of
  clobbering each other.
- **Two-tier memory.**
  - *Short-term* working memory per task in **Redis** (TTL-scoped).
  - *Long-term* semantic memory in **ChromaDB** — the system remembers what worked and recalls it
    by similarity on future tasks.
- **Security-first human-in-the-loop.** Four graded approval levels — `NOTIFY`,
  `APPROVE_ACTION`, `APPROVE_PLAN`, `TAKE_OVER` — chosen by escalation reason. The **authoritative
  gate is an allow-list on side-effecting tools**: any tool that can write, pay, deploy, or
  communicate requires explicit human approval and is *default-deny*. Text-based sensitivity
  classification is treated only as defense-in-depth, never the primary control.
- **Attributable approvals.** Reviewer auth is **secure by default** (constant-time token compare,
  fails closed when enabled-but-unconfigured). Every resolution writes an append-only audit record
  of *who* decided *what*.
- **Safe tool use.** Tools are registered with a JSON schema and a token-bucket rate limit. The
  demo `calculator` evaluates arithmetic via an AST walker (no `eval`, exponentiation rejected to
  prevent resource exhaustion).
- **Observability.** Every node is wrapped in an OpenTelemetry span; set an OTLP endpoint to export,
  otherwise spans print to console — instrumentation never breaks the run.
- **Graceful degradation everywhere.** No LangGraph? An in-process executor mirrors the topology.
  No Redis/Chroma/keys? In-memory fallbacks keep the full pipeline working.

## Tech stack

| Layer            | Technology                                        |
| ---------------- | ------------------------------------------------- |
| Orchestration    | LangGraph, LangChain Core                         |
| LLM providers    | OpenAI, Anthropic (mock fallback)                 |
| Working memory   | Redis                                             |
| Semantic memory  | ChromaDB                                          |
| Async work       | Celery + Redis                                    |
| Persistence      | PostgreSQL                                        |
| Human review UI  | Streamlit                                         |
| Observability    | OpenTelemetry (OTLP)                              |
| Config           | Pydantic Settings                                 |

## Quick start

Requires Python 3.10+.

```bash
# Install
make install            # pip install -e .   (or: pip install -r requirements.txt)

# Run a task through the graph — no API keys needed (uses the mock provider)
python -m orchestrator.main "Research the trade-offs of vector databases" --trace

# JSON output
python -m orchestrator.main "Summarize this quarter's risk posture" --json
```

Bring up the backing services and the human-review console:

```bash
make up        # docker compose up -d postgres redis chromadb
make ui        # streamlit run ui/review_app.py
make worker    # celery -A orchestrator.worker.celery_app worker
```

## Configuration

All settings load from environment variables or a local `.env` (see `src/orchestrator/config.py`).
Sensible defaults mean nothing is required to start.

| Variable                     | Default     | Purpose                                            |
| ---------------------------- | ----------- | -------------------------------------------------- |
| `DEFAULT_LLM_PROVIDER`       | `mock`      | `openai` \| `anthropic` \| `mock`                  |
| `OPENAI_API_KEY`             | —           | Enables the OpenAI provider                        |
| `ANTHROPIC_API_KEY`          | —           | Enables the Anthropic provider                     |
| `CONFIDENCE_THRESHOLD`       | `0.6`       | Below this, escalate to a human                    |
| `QUALITY_THRESHOLD`          | `0.6`       | Below this, escalate to a human                    |
| `REVIEW_AUTH_ENABLED`        | `true`      | Require authenticated reviewers (secure by default)|
| `REVIEW_USERS`               | —           | `name:token` pairs, e.g. `alice:s3cret,bob:hunter2`|
| `REDIS_URL`                  | `redis://localhost:6379/0` | Working memory + review queue       |
| `OTEL_EXPORTER_OTLP_ENDPOINT`| —           | Export traces (else console exporter)              |

> The provider auto-downgrades to `mock` whenever the matching API key is absent, so a misconfigured
> key can never silently bill you — it just falls back.

## Project layout

```
src/orchestrator/
├── main.py              # CLI entry point
├── config.py            # Pydantic settings + provider resolution
├── llm.py               # Provider-agnostic LLM client (OpenAI/Anthropic/mock)
├── graph/
│   ├── builder.py       # Assembles the LangGraph (+ in-process fallback)
│   ├── state.py         # Typed shared GraphState with reducers
│   ├── supervisor.py    # Decompose + reduce nodes
│   ├── specialists.py   # research / analysis / writing / code
│   └── reviewer.py      # Quality / confidence / sensitivity gate
├── hitl/
│   ├── escalation.py    # Graded approval levels
│   ├── sensitivity.py   # Defense-in-depth text classification
│   ├── queue.py         # Redis-backed review queue + audit log
│   └── auth.py          # Constant-time, fail-closed reviewer auth
├── memory/
│   ├── short_term.py    # Redis working memory (TTL-scoped)
│   └── long_term.py     # ChromaDB semantic memory
├── tools/registry.py    # Rate-limited, schema'd, allow-listed tools
├── observability/tracing.py  # OpenTelemetry spans
└── worker/celery_app.py # Async task queue
ui/review_app.py         # Streamlit human-review console
```

## Security

Security was a first-class concern, not an afterthought. See **[SECURITY.md](SECURITY.md)** and the
**[VULNERABILITY_ASSESSMENT.md](VULNERABILITY_ASSESSMENT.md)** for the threat model and the specific
findings (VA-01…) that shaped the auth, allow-list, and sensitivity-classification design.

## License

See repository for license details.
