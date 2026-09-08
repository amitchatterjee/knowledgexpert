# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`knowledgexpert` is a companion project to [`knowledgenet`](../knowledgenet) (sibling repo, a RETE
rules engine). Where `knowledgenet` is a generic, domain-agnostic library, a real rules application
built on it (e.g. [`knowledgenet-examples/autoins`](../knowledgenet-examples/autoins)) needs a
semantic layer on top: fact entities, loaders/parsers, a rule-config convention, and a test framework.
`knowledgexpert` is an AI-agent tool that helps produce those artifacts — rule code, rule
configuration, and test artifacts — for a target application, grounded in that application's own
semantic layer plus `knowledgenet`'s foundational docs and a curated set of exemplar rules.

This project is a PoC, mid-rewrite onto a new architecture — see **Current status** below before
assuming any given module exists.

## Current status: legacy stack retired, new architecture not yet built

**Read [`.plans/001-2026-09-05-deepagents-modernization-plan-INPROG.md`](.plans/001-2026-09-05-deepagents-modernization-plan-INPROG.md)
first.** It is the authoritative description of the whole target architecture and why — including the
parts (MCP/AG-UI/session-picker/observability) that aren't in its own phase list. That plan covers
**phases 0-6 only** (retiring the legacy stack upfront as a clean-slate phase 0, then tooling and the
CLI-only generation graph); a second plan,
[`002-2026-09-07-deepagents-multitenant-frontends-plan-DRAFT.md`](.plans/002-2026-09-07-deepagents-multitenant-frontends-plan-DRAFT.md),
covers phases 8-10 (MCP, AG-UI+Okta+session-picker, observability) — genuinely new functionality, not
started, and deliberately gated on 001 being done *and validated on real generated rules*, not just
"phases finished." See 001's "Plan split" section for the reasoning. The summary below:

- **Legacy stack — retired 2026-09-08 (phase 0 of plan 001)**: `expert.py`, `raven.py` (a
  `langchain.agents.create_agent` ReAct-style agent with MCP tools and a vector retriever), and
  `wolfpack.py` (a `LangGraph` `StateGraph` of four `Raven` roles — `analyst` as spec-interpreter/
  router, `developer`, `tester`, and a stubbed-out `implementor` for config generation — writing files
  straight to disk via `write_files_tool`) are all deleted, along with their vector-store-based
  knowledge retrieval (OpenSearch/ChromaDB collections, an earlier Neo4j graph-retrieval path), their
  front-ends (`wolfpack_cli.py`, `wolfpack_mcp.py`, `copilot_api.py`), and pip/`requirements.txt`/
  `~/ai-venv` tooling. None of this exists in the working tree anymore — recover any of it via
  `git log`/`git show` if ever needed, not by assuming it's still here. See plan 001's "Retirement"
  section for the full list and reasoning (deferring retirement past parity was considered and
  rejected — this is a branch nothing else consumes, so there was nothing real to preserve by keeping
  it around).
- **Target architecture**: a DeepAgents supervisor/subagent graph modeled directly on
  [`carqna-agent`](../carqna-agent) — a filesystem-backed (not vector-indexed) knowledge base via
  DeepAgents' `BackendProtocol` (`FilesystemBackend` now, RustFS-compatible `S3Backend` later,
  following `carqna-agent/src/agent/s3_backend.py`'s pattern), a supervisor that interprets an
  app-specific specification template and routes to **code-generator**, **config-generator**, and
  **test-generator** subagents, and three front-ends (CLI, MCP, AG-UI/FastAPI) over one graph —
  `uv`-managed like `knowledgenet` and `carqna-agent`, in-project `.venv` (diverging from
  `carqna-agent`'s external one, per `knowledgenet`'s convention). Nothing here is built yet except
  phase 0's tooling — `src/knowledgexpert/` is currently just an empty package.

## Repository layout (current)

- `src/knowledgexpert/` — package, currently just an empty `__init__.py`. Phase 1+ of plan 001 fills
  this in with the DeepAgents graph/agent code directly (flat, not nested under an `agent/`
  subpackage — that was tried and deliberately reverted, since it only existed to mirror
  `carqna-agent`'s own LangGraph-project-template naming convention, which this project doesn't need).
- `infrastructure/` — `docker/docker-compose.yml` now has just the `opensearch` service (ChromaDB,
  Neo4j, Ollama, `linux-exec-mcp`, and the `knowledgexpert-base` build image were all retired in phase
  0); `conf/mcp/opensearch/` (MCP tool registration for OpenSearch — **not retired**, relocates to
  `knowledgenet-examples/autoins-rulegen/` in phase 1 per plan 001's "Repository layout"); `conf/
  log-config.yaml` (generic, untouched); `admin/opensearch/` (role/user/rolesmapping `ndjson`
  fixtures).
- `data/` — `opensearch/msrp/` (car-pricing bulk-load data), `linux-exec/insurance-docs/` (the
  filesystem-backed corpus the `carqna-agent` `insurance_expert` subagent already reads — candidate
  reuse for the new knowledge base, not yet decided).
- `benchmark/` — legacy `raven`/`bookworm` sample prompts. Not yet retired (phase 0 didn't touch it)
  and not part of the new architecture — don't treat it as current, but don't assume it's gone either.
- `.plans/` — `001-...-INPROG.md` (phases 0-6, current work) and `002-...-DRAFT.md` (phases 8-10,
  gated on 001 being validated on real rules, not started) — see `001`'s "Plan split" section. Older
  retired plans are marked `-RETIRED`.
- `docs/readme-development.md` — contributor setup/lint/type-check/test commands; this file
  summarizes only what's needed for day-to-day edits.

## Environment (current)

`uv`-managed, in-project `.venv`: `uv venv && uv sync --group dev`. See
`docs/readme-development.md` for the full contributor workflow (lint, type-check, tests).

No env vars are required yet — phase 1+ introduces the new config surface (`RULEGEN_ROOT`,
`ANTHROPIC_API_KEY`, etc., per plan 001's "Configuration approach"); nothing reads any env var today.

## Running things today

**Nothing runs yet.** Phase 0 (legacy retirement + `uv` tooling) is done; phases 1-6 — the knowledge
base, the supervisor/rule-spec-validator, and the code/config/test-generator subagents — haven't
landed, so there's no CLI (or anything else) to invoke until phase 3 lands the first generator. See
plan 001's phase list for what's next.

## Editing conventions

- Keep changes surgical; don't reformat unrelated files.
- Don't change license headers.
- When adding to `.plans/`, follow `knowledgenet`'s convention: numbered, dated, status-suffixed
  filenames (`-DRAFT`/`-INPROG`/`-DONE`), updated in place as phases complete — see that repo's
  `.plans/` for the pattern this project now follows too.
