# Security Notes

This document records the security posture of the scaffold and the hardening
required before any non-local deployment.

## Threat model (current scaffold)

This is a developer scaffold intended to run **locally**. Backing services
(Postgres, Redis, ChromaDB) are brought up via Docker Compose with default or
no credentials and are bound to `127.0.0.1` only. The LLM layer falls back to a
deterministic mock so the system runs with no secrets at all.

## Secure-coding decisions

- **No `eval`/`exec` on untrusted input.** The `calculator` tool evaluates
  arithmetic with a restricted AST walker (`tools/registry.py`), permitting only
  `+ - * / %` and unary minus. Exponentiation (`**`) is rejected to prevent
  resource-exhaustion (e.g. `9**9**9`).
- **No insecure deserialization.** All persistence uses `json` (never
  `pickle`): short-term memory, the review queue, and task records.
- **Tool rate limiting.** Every tool declares a token-bucket rate limit, applied
  on each call. *(Limitation: the bucket is in-process; see below.)*
- **Secrets via environment only.** API keys and DB credentials are read from
  the environment / `.env` (`config.py`). `.env` is git-ignored; only
  `.env.example` (no real secrets) is committed.
- **No secret logging.** The CLI logs the active provider name and task, never
  keys or credentials.
- **Container runs unprivileged.** The image creates and switches to a non-root
  `appuser` (`Dockerfile`).
- **Pinned CI actions.** GitHub Actions are pinned to major versions.
- **Bounded LLM calls.** Provider clients use an explicit timeout and a capped
  retry count (`llm.py`, configurable via `LLM_TIMEOUT_SECONDS` /
  `LLM_MAX_RETRIES`) so a hung or failing provider cannot stall a worker.
- **Input-size guard.** `run_task` rejects empty and over-length tasks
  (`MAX_TASK_CHARS`, default 8000) to limit cost/DoS amplification to paid APIs.
- **Collision-resistant memory IDs.** Long-term memory IDs use a SHA-256 digest
  of the document rather than the process-salted builtin `hash()`.
- **Authenticated, attributable approvals (VA-01).** The review UI requires
  sign-in (`hitl/auth.py`); tokens are compared with `hmac.compare_digest`.
  Secure by default — auth is on unless explicitly disabled for a local demo,
  and an enabled-but-unconfigured deployment fails closed. Every resolution
  records the authenticated approver to an append-only audit log
  (`ReviewQueue.audit_log`, partial VA-09).
- **Allow-list gate for side-effecting tools (VA-02).** Tools declare whether
  they are `side_effecting`; the reviewer escalates (default-deny) whenever a
  side-effecting, non-allow-listed tool is used — this is the authoritative
  control. Text-based sensitivity detection (`hitl/sensitivity.py`) is a
  secondary signal only, hardened against spacing/case/punctuation evasion via
  normalization + word-boundary regexes.

## Known limitations — harden before production

| Area | Limitation | Recommended hardening |
| ---- | ---------- | --------------------- |
| Credentials | Default Postgres creds (`orchestrator`/`orchestrator`) and Redis with no password in `.env.example` / compose. | Generate strong secrets; inject via a secrets manager; enable `requirepass` on Redis. |
| Transport | Redis/Chroma/Postgres connections are plaintext. | Enable TLS; place services on a private network. |
| Rate limiting | Token bucket is per-process, so limits are not enforced across multiple Celery workers. | Move to a shared limiter (e.g. Redis-backed). |
| Prompt injection | When real tools (web search, etc.) are added, tool output is concatenated into specialist prompts. | Sanitize/segment tool output; never let retrieved content carry instructions into privileged actions. |
| Tool execution | `web_search` is a stub. A real implementation makes outbound requests. | Validate/allow-list URLs to prevent SSRF; sandbox any code-execution tool. |
| Review auth store | Reviewer tokens are static strings in env (`REVIEW_USERS`). Adequate for small teams, not for scale. | Integrate SSO/OIDC; rotate tokens; per-action authorization. |
| Audit log | Approval audit log lives alongside the queue (Redis/in-process). | Ship to immutable/append-only storage (WORM, SIEM) for tamper-evidence. |

## Reporting

For a real deployment, report vulnerabilities privately to the maintainer
rather than opening a public issue.
