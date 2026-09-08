# DeepAgents Multi-Tenant Front-Ends Plan for knowledgexpert

Status: **DRAFT (2026-09-07)** — not started. Gated on
[`001-2026-09-05-deepagents-modernization-plan-DRAFT.md`](001-2026-09-05-deepagents-modernization-plan-DRAFT.md)'s
phases 0-7 being **done and validated on real rules**, not just "phases finished."

## Objective

Add MCP and AG-UI front-ends (with Okta auth and a per-user session picker) plus OTel observability to
`knowledgexpert`. This is **new functionality the tool doesn't have today** — 001's phases 0-7 replace
`wolfpack`'s existing CLI-driven generation with a better architecture; this plan builds genuine
multi-tenant infrastructure (authentication, per-session Postgres state, distributed tracing) that has
no equivalent in the current legacy stack. `wolfpack_mcp.py` and `copilot_api.py` were retired outright
in 001's phase 7, not kept as a bridge — the MCP/AG-UI built here are fresh, not restorations.

## Why this is a separate plan, not phases 8-10 of 001

001's core, riskiest, least-precedented piece is the rule-spec-validator's sufficiency judgment and the
generation quality it gates — nothing in `carqna-agent` validates that pattern, unlike almost everything
else in 001 (checkpointer, auth, S3 backend, session picker), which is a verified copy of working carqna
code. Building Okta auth, per-session Postgres state, and OTel on top of an unproven core is a bet made
before there's evidence the core works. **Do not start this plan reflexively just because 001 reached
its last phase** — first confirm, on real `autoins` rules generated through the CLI, that a human is
actually happy with what phases 0-7 produce. If that validation surfaces problems with the
supervisor/validator/generator design, this plan's phases may need to change along with it, or wait
longer.

## Architecture

Fully specified in 001 — this plan does not repeat or fork it. In particular, see 001's:
- **"Workspace"** — `CompositeBackend` routing, per-session `root_dir` derivation, the
  git-worktree-per-session convention (human-managed, not the tool's job).
- **"Conversational memory / iterative feedback"** and its **"Session picker (AG-UI only)"**
  subsection — the SQLite-vs-Postgres checkpointer split, `user_registry`/`user_sessions` schema,
  `GET`/`POST /sessions` endpoints, composite `{user_id}:{session_id}` thread keys.
- **"MCP services — live application data"** — the generalized, optional-per-application MCP mechanism
  phase 8 (below) exposes over the MCP front-end itself (distinct from an application's own MCP tool
  configs, which already landed in 001's phase 1).
  **"Configuration approach"** — env-var pattern, `RULEGEN_ROOT`, Okta env vars.
- **"Observability"** — the OTel/`langsmith` mechanism, verified against `carqna-agent`'s
  `copilotkit_server.py` and `CLAUDE.md`, including the port-`4318`/`/v1/traces` and
  `FastAPIInstrumentor`-ordering gotchas.

If implementation surfaces a genuine architecture change (not just a phase-8-10-specific detail), update
it in 001, not by forking a duplicate description here — 001 stays the single source of truth for the
whole system's design regardless of which plan is currently executing.

## Phases

Numbered 8-10, continuing 001's sequence — there is no phase "1" here.

8. MCP front-end: `/workspace/` route swapped to `StateBackend`, structured response extraction,
   Postgres checkpointer wired in (see 001's "Conversational memory" — same instance/database AG-UI
   will use in phase 9).
   *Docs*: `README.md` MCP section (re)written — this front-end doesn't exist between 001's phase 7 and
   this phase landing.
9. AG-UI front-end + Okta auth (real `ag-ui-langgraph` integration, per-instance Okta config, Postgres
   checkpointer setup mirroring `copilotkit_server.py`'s `lifespan()` — explicit
   `await checkpointer.setup()` on startup), **plus the session picker**: `user_registry`/`user_sessions`
   tables and init scripts, `GET`/`POST /sessions` endpoints, composite `{user_id}:{session_id}` thread
   keys — ported from `carqna-agent`'s `sessions.py`/`user_tracking.py` near-verbatim (see 001's
   "Session picker"). Includes per-**session** (not just per-user) workspace `root_dir` derivation from
   the authenticated identity plus the picked session (see 001's "Workspace" — this is the critical
   piece to get right, not optional).
   *Docs*: `README.md` gains AG-UI/Okta/session-picker setup, including the human-managed
   worktree-per-session convention; `CLAUDE.md` updated to describe the now-complete architecture
   instead of "phases 8-10 not started."
10. Observability (see 001's "Observability") — deliberately last: OTel dependencies, the `jaeger`
    docker-compose service, env-var-only LangChain/LangGraph tracing (covers CLI and MCP retroactively,
    no code needed), and the AG-UI-only `FastAPIInstrumentor`/early-`langsmith.Client()` wiring
    (mirroring `copilotkit_server.py`'s exact ordering).
    *Docs*: `README.md`/dev-setup doc gain the OTel env vars and the `4318`/`/v1/traces` gotcha.
