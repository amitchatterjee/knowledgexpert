# For Developers

This page is meant for contributors to this project. It covers `uv` setup and day-to-day dev commands
— for the project's current status and architecture, see
[`../.plans/001-2026-09-05-deepagents-modernization-plan-INPROG.md`](../.plans/001-2026-09-05-deepagents-modernization-plan-INPROG.md)
and `../CLAUDE.md`, not this file.

> **Note:** for all commands below, `cd` to the project home directory first.

## One-time setup

This project needs Python 3.13 or higher (per `pyproject.toml`'s `requires-python`).

### Install uv

```bash
# Standalone installer (no Python dependency; supports `uv self update`)
curl -LsSf https://astral.sh/uv/install.sh | sh
```
or:
```bash
# Via pip, if you'd rather not run the installer script
pip install --user uv
```

### Create the virtual environment

`.venv` lives in-project (this repo's root), unlike `carqna-agent`'s external `~/carqna.venv` —
`knowledgexpert` follows `knowledgenet`'s per-project convention instead:

```bash
uv venv
uv sync --group dev
```

`uv sync --group dev` installs the base runtime dependencies plus dev tools (`mypy`, `ruff`, `pytest`,
etc. — see `pyproject.toml`'s `[dependency-groups]`) into `.venv`, and creates/updates `uv.lock`. Use
plain `uv sync` instead if you only want the runtime dependencies.

Run commands via `uv run <cmd>` (no activation needed), or `source .venv/bin/activate` for an
interactive shell and run bare commands as usual.

## Linting

```bash
uv run ruff check .
```
Configuration lives in `pyproject.toml`'s `[tool.ruff]` section.

## Type checking

```bash
uv run mypy src/knowledgexpert
```

## Running tests

```bash
uv run pytest
```

There are no tests yet — `src/knowledgexpert/` is still an empty package as of phase 0 of the
modernization plan (legacy retirement + tooling only). Tests land alongside real code in later phases.
Note the plan's own "Testing approach" section: the *agent's* generated artifacts are verified via
golden fixtures and structural checks, never execution — that's a different concern from this project's
own dev-time test suite (this section), which covers `knowledgexpert`'s own code, not artifacts it
generates.

## Not yet applicable

Unlike `knowledgenet`, this isn't a published PyPI package (no build/publish workflow), doesn't use
Sphinx for API docs, and doesn't use git flow — these sections are intentionally omitted rather than
copied from `knowledgenet`'s equivalent doc. Add them here if and when they actually become relevant,
not preemptively.
