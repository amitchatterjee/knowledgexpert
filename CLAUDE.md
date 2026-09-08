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

This project is a PoC, currently mid-migration between two architectures — see **Current status**
below before assuming any given module is still live.

## Current status: migration in progress

**Read [`.plans/001-2026-09-05-deepagents-modernization-plan-DRAFT.md`](.plans/001-2026-09-05-deepagents-modernization-plan-DRAFT.md)
first.** It is the authoritative description of the whole target architecture and why — including the
parts (MCP/AG-UI/session-picker/observability) that aren't in its own phase list. That plan covers
**phases 0-6 only** (retiring the legacy stack upfront as a clean-slate phase 0, then tooling and the
CLI-only generation graph); a second plan,
[`002-2026-09-07-deepagents-multitenant-frontends-plan-DRAFT.md`](.plans/002-2026-09-07-deepagents-multitenant-frontends-plan-DRAFT.md),
covers phases 8-10 (MCP, AG-UI+Okta+session-picker, observability) — genuinely new functionality, not
started, and deliberately gated on 001 being done *and validated on real generated rules*, not just
"phases finished." See 001's "Plan split" section for the reasoning. The summary below:

- **Legacy stack (currently what actually runs)**: `expert.py` (already deprecated in its own
  docstring), `raven.py` (a `langchain.agents.create_agent` ReAct-style agent with MCP tools and a
  vector retriever), and `wolfpack.py` (a `LangGraph` `StateGraph` of four `Raven` roles — `analyst`
  as spec-interpreter/router, `developer`, `tester`, and a stubbed-out `implementor` for config
  generation — writing files straight to disk via `write_files_tool`). Knowledge retrieval is
  vector-store based (OpenSearch/ChromaDB for the "know-it-all" expert content, per-collection stores
  for wolfpack's `rules_collection`/`app_docs_collection`/`framework_docs_collection`), with an
  earlier Neo4j graph-retrieval path. Front-ends: `wolfpack_cli.py`, `wolfpack_mcp.py` (FastMCP), and
  `copilot_api.py` (a hand-rolled FastAPI endpoint — not real AG-UI/CopilotKit protocol, same
  dead-end `carqna-agent` hit and later replaced; see that repo's `copilotkit_server.py` history).
  Tooling is pip + `requirements.txt` + a shared `~/ai-venv`, not `uv`.
- **Target architecture**: a DeepAgents supervisor/subagent graph modeled directly on
  [`carqna-agent`](../carqna-agent) — a filesystem-backed (not vector-indexed) knowledge base via
  DeepAgents' `BackendProtocol` (`FilesystemBackend` now, RustFS-compatible `S3Backend` later,
  following `carqna-agent/src/agent/s3_backend.py`'s pattern), a supervisor that interprets an
  app-specific specification template and routes to **code-generator**, **config-generator**, and
  **test-generator** subagents, and three front-ends (CLI, MCP, AG-UI/FastAPI) over one graph —
  `uv`-managed like `knowledgenet` and `carqna-agent`.
- Until the plan's phases land, treat `wolfpack.py` and its front-ends as the working reference
  implementation for *behavior* (what a request/response round-trip should accomplish), not as code
  to extend — new work happens on the DeepAgents rewrite.

## Repository layout (legacy, current)

- `src/knowledgexpert/` — package: `expert.py`, `raven.py`, `wolfpack.py`, `structures.py` (pydantic
  output schemas: `AnalystOutput`, `CodingOutput`, `TestingOutput`, `TestFileOutput`), vector/graph
  plumbing (`vector_backend.py`, `chunker.py`, `html_splitter.py`), `util.py`.
- `src/` (top-level scripts) — CLI/MCP/API entry points: `expert_cli.py`, `raven_cli.py`,
  `wolfpack_cli.py`, `wolfpack_mcp.py`, `copilot_api.py`, `vector_store.py`, `vector_query.py`,
  `graph_store.py`, `linux_exec_mcp.py`.
- `infrastructure/` — `docker/` (Compose services: OpenSearch w/ MCP plugin, a knowledgexpert base
  image, `linux-exec-mcp`), `conf/{expert,raven,wolfpack}/` (per-agent `config.json` +
  `agentic_prompt.txt`), `admin/opensearch/` (role/user/rolesmapping `ndjson` fixtures).
- `data/` — `opensearch/msrp/` (car-pricing bulk-load data), `linux-exec/insurance-docs/` (the
  filesystem-backed corpus the `carqna-agent` `insurance_expert` subagent already reads — likely
  reusable as-is for the new knowledge base).
- `benchmark/` — sample prompts (`raven/prompt-*.txt`) used as CLI/MCP smoke inputs.
- `.plans/` — see below; only the current dated plan is authoritative, retired plans are marked as such.

## Environment (legacy, current)

```bash
python3.14 -m venv ~/ai-venv
source ~/ai-venv/bin/activate   # or add to ~/.bashrc
pip install -r requirements.txt
```

Required env vars: `KNOWLEDGEXPERT_HOME`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`EMBEDDING_MODEL_DATA`, `EMBEDDING_MODEL_CODE`, `KNOWLEDGEXPERT_ENV` (`dev` → ChromaDB, `perf` →
OpenSearch). Full one-time setup (Docker infra, OpenSearch users/roles, vector/graph data loading) is
in `README.md` — don't re-derive it here, it's already fully scripted there.

## Running things today (legacy)

```bash
# Wolfpack CLI (interactive)
dotenv --file "${KNOWLEDGEXPERT_HOME}/env.${KNOWLEDGEXPERT_ENV}" run -- \
  python $KNOWLEDGEXPERT_HOME/src/wolfpack_cli.py

# Wolfpack MCP server
dotenv --file "${KNOWLEDGEXPERT_HOME}/env.${KNOWLEDGEXPERT_ENV}" run -- \
  fastmcp run "$KNOWLEDGEXPERT_HOME/src/wolfpack_mcp.py" --transport http --port 9901 --host 0.0.0.0

# Copilot API (hand-rolled, superseded design — see Current status above)
dotenv --file "${KNOWLEDGEXPERT_HOME}/env.${KNOWLEDGEXPERT_ENV}" run -- \
  uvicorn copilot_api:app --host 0.0.0.0 --port 9001 --app-dir "$KNOWLEDGEXPERT_HOME/src"
```

See `README.md` for the full command reference (vector/graph data loading, OpenSearch setup, Raven
CLI examples, checkpointer inspection).

## Editing conventions

- Keep changes surgical; don't reformat unrelated files.
- Don't change license headers.
- When adding to `.plans/`, follow `knowledgenet`'s convention: numbered, dated, status-suffixed
  filenames (`-DRAFT`/`-INPROG`/`-DONE`), updated in place as phases complete — see that repo's
  `.plans/` for the pattern this project now follows too.
