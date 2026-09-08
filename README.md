# Knowledgexpert README
A companion project for Knowledgenet that helps developers build rules-based application using AI

The examples in this README assume a fully trusted developer environment. For a production environment, the same concepts need to be ported into a secure deployment model, with proper secret handling, access controls, and automation.

## Initial setup

### Create a virtual environment
`knowledgexpert` is `uv`-managed, with an in-project virtual environment (`.venv` under the repo root),
following `knowledgenet`'s per-project convention. From the repo root:

```bash
uv venv
uv sync
```

This creates `.venv/` and installs the project's dependencies (see `pyproject.toml`) into it. No
`~/.bashrc` activation line is needed — use `uv run <command>` to run things inside the venv, or
`source .venv/bin/activate` for an interactive shell.

See [`docs/readme-development.md`](docs/readme-development.md) for dev tooling (lint, type-check,
tests) and other contributor-facing setup.

## Current status

Nothing beyond `uv`/`pyproject.toml` setup runs yet. This project is mid-rewrite onto a new
architecture — see
[`.plans/001-2026-09-05-deepagents-modernization-plan-INPROG.md`](.plans/001-2026-09-05-deepagents-modernization-plan-INPROG.md)
for the current status and what's next, and `CLAUDE.md` for a shorter summary.

Everything previously documented here (environment variables, Docker infra for ChromaDB/Neo4j/Ollama,
OpenSearch user/role/MCP-tool setup, vector/graph data loading, and the `raven_cli`/`wolfpack_cli`/
`wolfpack_mcp`/`copilot_api` commands) described the legacy stack, which was retired in phase 0 of that
plan. None of the code or infra it referenced exists in the working tree anymore — see `git log` if you
need to recover any of it. Each new front-end's setup and usage instructions land here again as that
phase of the plan is implemented, per the plan's own "Documentation" section — not before, and not left
stale in the meantime.