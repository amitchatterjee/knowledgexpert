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

**Workspace** — separate from the knowledge-base content entirely, but **the same live backend
mechanism**, unified via `deepagents.backends.composite.CompositeBackend` (confirmed present in the
installed `deepagents` package, `~/carqna.venv`). A subagent that needs workspace access is given one
`CompositeBackend` routing by path prefix — e.g. `{"/knowledge/": <app's knowledge backend>,
"/workspace/": <workspace backend>}` — giving it the **full standard DeepAgents tool set** (`ls`,
`read`, `write`, `edit`, `glob`, `grep`) live, in its own tool loop, across both trees at once. No
custom tool-building, no orchestration-level pre-fetch hack. `FilesystemPermission` (already used by
`carqna-agent`'s `insurance_expert`) matches by path pattern independent of backend, so `/knowledge/**`
stays read-only (deny write/edit/delete) while `/workspace/**` is read-write, within that same backend.

**These two routes vary along completely different axes, and are never conflated**: `/knowledge/` is
scoped **per application** — one shared, self-contained backend per target app (e.g. `autoins`'s
six-directory VFS), the same physical location for every user working on that application, per the
per-application knowledge-base decision above. `/workspace/` is scoped **per user** — never shared,
never duplicated with knowledge-base content, physically separate storage. A session for one user
working on `autoins` mounts that user's own workspace `root_dir` at `/workspace/` alongside `autoins`'s
one shared knowledge backend at `/knowledge/`; a different user working on the same application mounts
the identical `/knowledge/` backend with their own, separate `/workspace/`. The per-user isolation
work below only concerns `/workspace/` — the knowledge base's isolation (by application, not by user)
was already resolved separately and needs no further protection here.

This directly gives revising/config-editing subagents real exploration — `grep`/`glob`/`ls` over the
actual current workspace (sibling rules, cross-references, anything not already known from conversation
state or documented convention) — not just a single pre-fetched file's content. It also resolves the
earlier "does DeepAgents support two backends per subagent" question: yes, via `CompositeBackend`, no
further verification needed.

**What's mounted at `/workspace/` is the only thing that varies by mode** — the subagent's tool calls
are identical either way:
- **CLI** — `FilesystemBackend` rooted at a local directory the user points the tool at (they manage
  git themselves). Writes/edits land on disk immediately.
- **AG-UI** — `FilesystemBackend`/`S3Backend` rooted at a per-user, pre-provisioned network-filesystem
  path. Git lifecycle (clone/pull/push) is **out of scope** — assume the workspace already exists.
  **Multi-user isolation, resolved**: `FilesystemBackend(root_dir=..., virtual_mode=True)` (the
  default) treats every agent-facing path as virtual and anchored to `root_dir` — `..`/`~` traversal is
  blocked, virtual "absolute" paths are remapped under `root_dir` rather than escaping it, and every
  resolved path is verified to stay within `root_dir` before any I/O — enforced in `_resolve_path()`
  itself, not something a prompt or a confused agent can talk its way around. So the isolation is
  entirely a function of **backend construction**: each authenticated user's session must get its own
  freshly-built `FilesystemBackend` with `root_dir` set to *that specific user's own workspace leaf
  directory*, derived server-side from the Okta-authenticated identity (`auth_context`, mirroring
  `carqna-agent`) — **never** from anything client-supplied. **The mistake to avoid**: rooting the
  backend at a *shared parent* directory (e.g. `/mnt/nfs/workspaces/`) and trusting the agent to "stay
  in its own subdirectory" — `virtual_mode`'s guardrails only block escaping `root_dir`, not what's
  reachable *inside* it, and every other user's directory would be legitimately inside a shared root.
  **Caveat to carry forward, not paper over**: `FilesystemBackend`'s own docstring lists "web servers or
  HTTP APIs" (i.e. AG-UI) as an *inappropriate* use case, since path-based guardrails aren't real
  sandboxing/process isolation, and recommends `StateBackend`/`StoreBackend`/`SandboxBackend` instead.
  Those don't fit here (AG-UI's workspace is deliberately real and persistent, not ephemeral), so this
  is a deliberate accepted tradeoff — mitigate with HITL middleware on sensitive operations (as
  DeepAgents' own docs recommend), and treat `SandboxBackend` (real process/container isolation) as the
  escalation path if this ever becomes a concrete concern, not something to build now.
- **MCP** — `deepagents.backends.state.StateBackend` (confirmed present: stores files ephemerally in
  LangGraph state, not on disk). The subagent writes/edits exactly as it would against a real
  filesystem; nothing is persisted anywhere. After the run, the orchestration step reads back whatever
  landed in that ephemeral state and serializes it into the MCP response for the calling agentic tool
  (e.g. Claude Code) to place — replacing wolfpack's old `write_files_tool`/`skipWriter` flag with a
  backend swap instead of an `if` branch in the write path.

**`rule-config.json` still needs `edit`, not `write`**, regardless of backend: it's a file shared across
every rule in a ruleset, so config-generator must read the current content and apply a targeted change
(DeepAgents' standard `edit` operation) rather than overwriting the whole file — this is genuinely new
capability `wolfpack` never built (`implementor` was a stub, and `write_files_tool`'s signature has no
config parameter at all). New rule code and new test-artifact files, by contrast, are fine as plain
`write` (nothing pre-existing to clobber).

**Revision context**: the path of the file being revised is still recorded in conversation state from
the turn that originally generated it (via the Postgres checkpointer — see "Conversational memory"
below), so the revising subagent knows where to start — but now it can also `grep`/`glob`/`ls` beyond
that single file through its live workspace-mounted backend if the fix needs broader context. This
also removes the earlier gap around feedback referencing a file the session didn't itself
generate/track: the subagent can find it via `glob`/`grep` instead of requiring a tracked path.

**Graph** — a DeepAgents supervisor/subagent graph (mirrors `carqna-agent/src/agent/graph.py`),
replacing `wolfpack.py`:
- **Supervisor** — interprets an app-specific specification template (format varies per application;
  the supervisor must read/understand whatever template the target app defines) plus the free-form
  ask, classifies the request (code-generation / config-generation / test-generation — one or more —
  **or feedback on previously generated artifacts**, see "Conversational memory" below), and
  delegates. Behavioral equivalent of `wolfpack`'s `analyst` + `request_router_node`.
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

**Conversational memory / iterative feedback** — new functionality, not present in `wolfpack` today
(its `SqliteSaver` checkpointer is wired up but the graph doesn't use conversation history to inform
revision — every request is generated fresh). Flow: a human runs the generated code/tests themselves
(test execution is explicitly out of scope for the agent — see "Test tool integration" below) and
reports back issues or requested changes in the same conversation. The supervisor must recognize this
as feedback on prior output — not a new unrelated request — and route it to whichever subagent(s)
produced the artifact being corrected (a code bug → code-generator revises the rule it wrote; a bad
test fixture → test-generator revises it; a config value → config-generator), with enough context from
the prior turn(s) for that subagent to make a targeted revision rather than regenerating from scratch.
- **Prompts**: each of the three subagents' prompts needs explicit generate-fresh-vs-revise-existing
  guidance — on a revision, read the current workspace file first (see the workspace read-access
  question above), understand what's there, make the targeted change, and preserve everything the
  feedback didn't ask to change, rather than regenerating the whole artifact from scratch.
- **Technology**: the same Postgres-backed checkpointer pattern `carqna-agent` uses
  (`AsyncPostgresSaver`, explicit `await checkpointer.setup()` on startup, a fixed `thread_id` per
  session/CLI run — see `carqna-agent/src/agent/graph.py`'s `_get_checkpointer_conn_string()` and
  `src/agent/carqna_cli.py`). Same pattern as the Okta decision above: reuse the *mechanism*, not
  `carqna-agent`'s actual Postgres instance/database — `knowledgexpert` gets its own
  database/connection string, configurable per deployment instance.
- Applies across all three front-ends: CLI (replacing `wolfpack_cli.py`'s SQLite checkpointer),
  MCP (`wolfpack_mcp.py`'s `QueryRequest.session_id` already threads a session id through — this
  becomes load-bearing instead of decorative), and AG-UI (multi-turn is inherent to that protocol).

**Front-ends**, all over one graph, mirroring `carqna-agent`:
- **CLI** — replaces `wolfpack_cli.py`.
- **MCP server** — replaces `wolfpack_mcp.py` (FastMCP); no persistent workspace — `/workspace/` is a
  `StateBackend` (see "Workspace" above), read back into a structured response, nothing written to disk.
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

**Documentation** — both new authoring and refactoring of what exists, not an end-of-project
afterthought. Each phase below updates the docs it touches as part of that phase, not deferred to a
final documentation pass:
- **New**: a knowledge-base curation guide — how to set up a new target application's virtual
  filesystem across the six directories (what goes where, with `autoins` as the worked example), how
  to author a specification template, and conventions for the per-application prompts/config described
  above. Analogous to `knowledgenet`'s `docs/concepts.md`/`rules-authoring.md` and
  `knowledgenet-examples/autoins`'s `docs/description.md`/`testing.md`.
- **New**: a `docs/readme-development.md`-equivalent for `knowledgexpert` itself (dev setup, running
  tests, running the CLI/MCP/AG-UI front-ends), matching the pattern `knowledgenet` and `carqna-agent`
  already use, once the `uv` tooling phase lands.
- **Refactor**: `README.md` is currently written entirely around the legacy stack (pip setup, Docker
  OpenSearch/Neo4j infra, vector/graph data loading, `raven_cli`/`wolfpack_cli`/`wolfpack_mcp`
  commands) — rewritten in step with each phase as the legacy stack it documents is replaced, not left
  stale until final retirement.
- **Refactor**: `CLAUDE.md` (added this session, describing the current legacy-stack/migration-in-progress
  state) updated as each phase changes what's actually true — it should never describe code that no
  longer exists or omit code that now does.

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

None outstanding — everything raised during design discussion has been resolved above.

## Phases (tentative — sketch only, subject to change as implementation surfaces new information)

0. Tooling: `uv`-managed `pyproject.toml`, in-project `.venv`, drop `requirements.txt`/`~/ai-venv`.
   *Docs*: new `docs/readme-development.md`-equivalent for the `uv` workflow.
1. Knowledge-base backend + content: both `FilesystemBackend` and RustFS-compatible `S3Backend` wired
   together in this single phase (not staged local-first) — `carqna-agent`'s `S3Backend` is already
   well-tested and reusable as-is, so there's no reason to defer it behind a separate later phase.
   Includes curating foundational/app-specific/exemplar/test-framework content for `autoins` as the
   reference application.
   *Docs*: new knowledge-base curation guide (the six directories, worked `autoins` example).
2. Supervisor + code-generator subagent (spec interpretation, classification, code generation, CLI
   front-end only) — smallest end-to-end slice, no config/test generation yet. First use of the
   `CompositeBackend`-mounted workspace (`write` for new rule code files).
   *Docs*: new spec-template authoring guide; `README.md` CLI section rewritten to the new command.
3. config-generator subagent — first consumer of the workspace's `edit` (and `read`) capability, since
   `rule-config.json` must be merged into, not overwritten.
   *Docs*: knowledge-base curation guide gains `configuration-guidelines/` conventions.
4. test-generator subagent (artifact authoring only — no test-tool execution; see "Test tool
   integration," out of scope).
   *Docs*: knowledge-base curation guide gains `testing-guidelines/` conventions.
5. Conversational memory / iterative feedback: Postgres-backed checkpointer (own database, per-instance
   configurable — see above), supervisor logic to recognize and route feedback on prior artifacts to
   the subagent that produced them, revised prompts covering generate-fresh vs. revise-existing. The
   `CompositeBackend`-based live workspace access (see "Workspace" above) already exists from phases
   2-4 — this phase is about the supervisor's routing/state logic, not new backend plumbing.
   CLI front-end only at this point.
   *Docs*: `README.md`/CLI docs gain the feedback/revision workflow (how to report an issue in the
   same session so the right subagent picks it up).
6. MCP front-end: `/workspace/` route swapped to `StateBackend`, structured response extraction.
   *Docs*: `README.md` MCP section rewritten to the new server.
7. AG-UI front-end + Okta auth (real `ag-ui-langgraph` integration, per-instance Okta config),
   including per-user workspace `root_dir` derivation from the authenticated identity (see multi-user
   isolation notes under "Workspace" above — this is the critical piece to get right, not optional).
   *Docs*: `README.md` gains AG-UI/Okta setup; `CLAUDE.md` updated to describe the now-complete new
   architecture instead of "migration in progress."
8. Retirement of legacy modules/infra listed above.
   *Docs*: `README.md` stripped of every legacy-stack section (pip setup, Docker OpenSearch/Neo4j
   infra, vector/graph data loading, `raven_cli`/`wolfpack_cli`/`wolfpack_mcp`/`copilot_api` commands)
   in the same phase the code they describe is deleted, not left dangling.
