# DeepAgents Modernization Plan for knowledgexpert

Status: **DRAFT (2026-09-05)** — architecture agreed via discussion; implementation has **not**
started. Further design conversation is expected before this moves to `-INPROG`.

## Objective

Retire the LangChain-classic / vector-store generation of `knowledgexpert` (`expert.py`, `raven.py`,
`wolfpack.py`, and their OpenSearch/ChromaDB/Neo4j-backed retrieval) and rebuild the artifact-generation
tool on [DeepAgents](https://github.com/langchain-ai/deepagents), modeled directly on the sibling
`carqna-agent` project's architecture. Preserve `wolfpack`'s existing behavioral contract — a
spec-driven request that produces rule code, rule configuration, and/or test artifacts — while
replacing vector retrieval with a curated, filesystem-backed knowledge base and replacing ad hoc disk
writes with DeepAgents' backend abstraction.

## Background

`knowledgenet` is a generic, domain-agnostic RETE library. A real rules application built on it (e.g.
`knowledgenet-examples/autoins`) requires its own semantic layer: fact entity classes, loaders/parsers,
a `rule-config.json` convention, and a test framework with its own artifact formats. `knowledgexpert`
exists to help a developer produce those application-specific artifacts using AI agents, rather than
by hand.

The current implementation (`wolfpack.py`) already models the right shape — a spec-interpreting
`analyst` routing to `developer`/`tester`/`implementor` roles — but:
- Knowledge is vector-indexed (OpenSearch/ChromaDB), requiring an ingestion/embedding pipeline the
  user must run and re-run to keep current, rather than being directly curatable as files.
- `implementor` (config generation) is a stub — never implemented.
- File writes are a single hand-rolled `write_files_tool`, always hitting local disk — no notion of
  "no workspace" (MCP mode) or a remote/per-user workspace (a future web IDE).
- The AG-UI-shaped front-end (`copilot_api.py`) is a hand-rolled FastAPI endpoint that guesses at a
  REST/SSE shape — `carqna-agent` already hit this same dead end (`carqna_dapr.py`, since deleted) and
  replaced it with the real `ag-ui-langgraph` package; `knowledgexpert` should go straight to that.

`carqna-agent` has already solved the DeepAgents-supervisor, filesystem-backend (including an
S3-compatible/RustFS backend), and real-AG-UI-integration problems for a sibling use case (insurance
Q&A). This plan is largely "apply that same architecture to artifact generation instead of Q&A."

## Scope

### In scope

**Knowledge base** — DeepAgents virtual filesystems (`BackendProtocol`; local `FilesystemBackend` to
start, RustFS-compatible `S3Backend` later, per `carqna-agent/src/agent/s3_backend.py`), curated by
the tool's user (no ingestion pipeline). **A separate, fully self-contained virtual filesystem per
target application** — not one shared backend, not a runtime-combined shared+per-app pair. Each
application's backend holds its own copy of everything, including `knowledgenet-foundation/`.
Duplicating foundational content across applications is intentional and necessary, not just a
simplicity tradeoff: **different target applications may run on different `knowledgenet` versions with
different functional/programming interfaces**, so a single shared foundational copy would actually be
wrong for any application not pinned to the latest version — each app's foundational docs must match
the `knowledgenet` version that app actually uses. A subagent only ever talks to one backend, the
current app's; no composite/multi-backend mechanism needed. Six top-level directories per application:

- **`knowledgenet-foundation/`** — `knowledgenet` framework docs (`concepts.md`, `rule-service.md`,
  `rules-authoring.md`, generated API docs) **matching the specific `knowledgenet` version this
  application is built against**. Not assumed identical across applications.
- **`application-domain/`** — business/domain meaning (e.g. `autoins/docs/description.md`,
  `entity-relationships.md`).
- **`application-architecture/`** (renamed from `rules-engine-architecture/` — clearer alongside
  `knowledgenet-foundation/`, which already owns "rules engine") — the app's fact model/entities,
  loaders/helpers, and the **specification template** the supervisor interprets requests against.
  Resolved: the spec template is per-app knowledge, not a foundational baseline.
- **`configuration-guidelines/`** — `rule-config.json` conventions, split out from
  `application-architecture/` for the same reason as testing below.
- **`exemplars/`** — a deliberately curated set of reference rule implementations for the
  code-generator subagent to use as style/pattern guidance — distinct from "whatever rules currently
  exist in the app."
- **`testing-guidelines/`** — documentation of test artifact formats and workflow (e.g.
  `autoins/docs/testing.md`'s EDI format, `expected.csv` schema, the "write data → run → dump_result →
  promote to expected" workflow). Split out from `application-architecture/`: different lifecycle/owner
  than the app's code architecture, and maps directly to the test-generator subagent's dedicated
  grounding context.

**Workspace** — separate from the knowledge-base virtual filesystem entirely. Where generated
artifacts are actually written. Mode-dependent:
- **CLI** — a local directory the user points the tool at (they manage git themselves).
- **AG-UI** — a per-user, pre-provisioned network-filesystem path. Git lifecycle (clone/pull/push) is
  **out of scope** — assume the workspace already exists and is populated by something else.
- **MCP** — no workspace. Generated artifacts (code/config/test content + intended relative paths) are
  returned as structured tool output; the calling agentic tool (e.g. Claude Code) owns placement.

This means subagents should produce structured artifact output (as `wolfpack`'s `CodingOutput`/
`TestingOutput` already do), not write files directly from within their own tool loop — a single
mode-dependent step (workspace write, or MCP response passthrough) sits after generation.

**Graph** — a DeepAgents supervisor/subagent graph (mirrors `carqna-agent/src/agent/graph.py`),
replacing `wolfpack.py`:
- **Supervisor** — interprets an app-specific specification template (format varies per application;
  the supervisor must read/understand whatever template the target app defines) plus the free-form
  ask, classifies the request (code-generation / config-generation / test-generation — one or more),
  and delegates. Behavioral equivalent of `wolfpack`'s `analyst` + `request_router_node`.
- **code-generator** subagent — writes `@ruledef` rule code. Grounded in foundational + app-specific +
  exemplar knowledge layers.
- **config-generator** subagent — writes/edits `rule-config.json` entries. Must actually be built this
  time (`wolfpack`'s `implementor` never was). Routable directly for config-only asks (e.g. "change
  this rule's rank"), and always invoked alongside code-generation for a new rule, per the app's
  convention that new rules need matching config entries.
- **test-generator** subagent — writes the app's test artifacts (test-data, rule-config override,
  expected-results, test-module — four files in `autoins`'s convention). **Does not execute the
  app's test tool** (see "Test tool integration," out of scope below) — produces its best
  understanding of the expected-results artifact from the spec/rules alone, without running anything
  to verify or generate it.

(Resolved: a single supervisor + these 3 subagents is sufficient — config-generation stays its own
subagent rather than merging into code-generation, despite the two usually firing together.)

**Front-ends**, all over one graph, mirroring `carqna-agent`:
- **CLI** — replaces `wolfpack_cli.py`.
- **MCP server** — replaces `wolfpack_mcp.py` (FastMCP); no workspace, structured response only.
- **AG-UI/FastAPI** — replaces `copilot_api.py` with the real `ag-ui-langgraph` integration pattern
  `carqna-agent/src/agent/copilotkit_server.py` already validates. For a possible future web-based IDE.
- **Okta auth**, AG-UI mode only — mirrors the *code pattern* of
  `carqna-agent/src/agent/{auth,auth_middleware,auth_context}.py`, but **not its configuration**: we
  will not use `carqna-agent`'s Okta tenant/application. Okta tenant, application registration, and API
  must be fully configurable per deployment instance of `knowledgexpert` — different instances may run
  against different Okta tenants, different application registrations, different APIs entirely. No
  hardcoded or shared-with-carqna Okta config. CLI and MCP stay unauthenticated (CLI runs as the local
  user; MCP trusts the calling agentic tool).

**Prompts and configuration are externalized and application-configurable**, not just role-configurable.
`raven.py`'s existing mechanism (a `promptDir` + per-role `config.json`, see `wolfpack`'s
`analyst`/`developer`/`tester` configs) only varies content by *role*. The new supervisor/subagent
prompts and configs need an *application* dimension too, so a different target application (not just
`autoins`) can supply its own prompts/config without code changes — treated as another part of the
same user-curated, per-application knowledge layer described above, not hardcoded in the package.
Content is net-new either way: the mechanism (file-based prompts, file-based tool config) carries over
conceptually from `raven.py`/`carqna-agent`, but the actual prompt text and MCP tool configs are
specific to raven's current Q&A/vector-retrieval purpose and don't transfer — every prompt gets
rewritten for this tool's actual purpose (spec interpretation, rule/config/test generation) and for
the rules-engine domain.

**Tooling** — new `pyproject.toml` + `uv`-managed venv **inside the project** (`.venv` under
`knowledgexpert/`, per-project like `knowledgenet` and each `knowledgenet-examples` app), replacing
`requirements.txt` + the shared `~/ai-venv`, matching `knowledgenet` and `carqna-agent`.

**Retirement**, once the DeepAgents version reaches parity. Vector-store retirement specifically is
low priority and can be deferred — the legacy stack is fine to coexist for a while; earlier phases
aren't gated on cleaning it up:
- `expert.py`, `expert_cli.py`, `raven.py`, `raven_cli.py`, `wolfpack.py`, `wolfpack_cli.py`,
  `wolfpack_mcp.py`, `copilot_api.py`
- `vector_store.py`, `vector_query.py`, `graph_store.py`, `vector_backend.py`, `chunker.py`,
  `html_splitter.py`
- OpenSearch/ChromaDB/Neo4j infra: `infrastructure/conf/{expert,raven,wolfpack}/`,
  `infrastructure/docker/opensearch-mcp/`, `data/opensearch/`, `infrastructure/admin/opensearch/`
- `linux_exec_mcp.py` and `infrastructure/docker/linux-exec-mcp/` (the `ShellCommandExecutor` MCP
  service) — retired outright, not repurposed. Replaced by the DeepAgents virtual filesystem for the
  knowledge-base/workspace access it used to help provide indirectly; it is **not** replaced by an
  equivalent exec capability — see "Test tool integration," out of scope below.

### Explicitly out of scope

- Git lifecycle management (clone/pull/push) for AG-UI workspaces — assumed pre-provisioned.
- **Test tool integration** — actually running the target application's test tool (running the
  generated tests, inspecting output, generating/verifying `expected.csv`-equivalent results) is out
  of scope for now. Deliberately deferred rather than assumed to be pytest: the application's test
  framework may use a different tool entirely, so this needs its own design (likely a pluggable,
  per-application "how to run tests" concept) rather than hardcoding a pytest-exec tool now.
  `linux_exec_mcp.py` is retired, not repurposed for this — see Retirement above.
- Anything in the two now-retired plans (see `.plans/` — superseded, not part of this plan's scope):
  `plan-opensearch-chromadb-dual-backend-RETIRED.md`, `plan-replace-neo4j-with-arcadedb-RETIRED.md`.

## Open questions

None outstanding — everything raised during design discussion has been resolved above. The phase
order below answers "what happens when."

## Phases (tentative — sketch only, subject to change as implementation surfaces new information)

0. Tooling: `uv`-managed `pyproject.toml`, in-project `.venv`, drop `requirements.txt`/`~/ai-venv`.
1. Knowledge-base backend + content: both `FilesystemBackend` and RustFS-compatible `S3Backend` wired
   together in this single phase (not staged local-first) — `carqna-agent`'s `S3Backend` is already
   well-tested and reusable as-is, so there's no reason to defer it behind a separate later phase.
   Includes curating foundational/app-specific/exemplar/test-framework content for `autoins` as the
   reference application.
2. Supervisor + code-generator subagent (spec interpretation, classification, code generation, CLI
   front-end only) — smallest end-to-end slice, no config/test generation yet.
3. config-generator subagent.
4. test-generator subagent (artifact authoring only — no test-tool execution; see "Test tool
   integration," out of scope).
5. MCP front-end (structured output, no workspace).
6. AG-UI front-end + Okta auth (real `ag-ui-langgraph` integration, per-instance Okta config).
7. Retirement of legacy modules/infra listed above.
