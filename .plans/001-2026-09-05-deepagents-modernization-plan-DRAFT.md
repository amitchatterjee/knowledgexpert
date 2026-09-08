# DeepAgents Modernization Plan for knowledgexpert

Status: **DRAFT (2026-09-05)** — architecture agreed via discussion; implementation has **not**
started. Further design conversation is expected before this moves to `-INPROG`.

## Objective

Retire the LangChain-classic / vector-store generation of `knowledgexpert` (`expert.py`, `raven.py`,
`wolfpack.py`, and their ChromaDB/Neo4j-backed retrieval, plus OpenSearch's *use as that same
doc-retrieval mechanism*) and rebuild the artifact-generation tool on
[DeepAgents](https://github.com/langchain-ai/deepagents), modeled directly on the sibling
`carqna-agent` project's architecture. Preserve `wolfpack`'s existing behavioral contract — a
spec-driven request that produces rule code, rule configuration, and/or test artifacts — while
replacing vector retrieval with a curated, filesystem-backed knowledge base and replacing ad hoc disk
writes with DeepAgents' backend abstraction. **OpenSearch itself is not retired** — it continues as an
MCP-exposed live-search tool subagents can use (vector and full-text search over application-specific
collections), the same role `AutoGeek` plays for `carqna-agent`; only its prior use *as the knowledge
base* goes away, since the knowledge base is filesystem-backed now.

**This is a general-purpose rule-generation platform, not an `autoins`-specific tool.** Nothing in the
architecture is coupled to `autoins` — every application-specific concept (knowledge base, spec
template/validation, exemplars, config/testing conventions) is per-target-application data, not code.
`autoins` is the reference application used to build and test the platform end to end, the same role
`carqna-agent`'s insurance domain plays for that project's architecture — a worked example, not a
dependency.

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
the tool's user (no ingestion pipeline). **Knowledge-base backend choice is independent of front-end
mode** — it's a deployment/config decision (local disk vs. RustFS/S3), not tied to CLI vs. AG-UI vs.
MCP. A CLI user can just as well point at an S3-hosted knowledge base as a local one; only the
*workspace* backend is mode-determined (see "Workspace" below). **A separate, fully self-contained virtual filesystem per
target application** — not one shared backend, not a runtime-combined shared+per-app pair. Each
application's backend holds its own copy of everything, including `knowledgenet-foundation/`.
Duplicating foundational content across applications is intentional and necessary, not just a
simplicity tradeoff: **different target applications may run on different `knowledgenet` versions with
different functional/programming interfaces**, so a single shared foundational copy would actually be
wrong for any application not pinned to the latest version — each app's foundational docs must match
the `knowledgenet` version that app actually uses. A subagent only ever talks to one backend, the
current app's; no composite/multi-backend mechanism needed. Seven top-level directories per application:

- **`knowledgenet-foundation/`** — `knowledgenet` framework docs (`concepts.md`, `rule-service.md`,
  `rules-authoring.md`, generated API docs) **matching the specific `knowledgenet` version this
  application is built against**. Not assumed identical across applications.
- **`application-domain/`** — business/domain meaning (e.g. `autoins/docs/description.md`,
  `entity-relationships.md`).
- **`application-architecture/`** (renamed from `rules-engine-architecture/` — clearer alongside
  `knowledgenet-foundation/`, which already owns "rules engine") — the app's fact model/entities and
  loaders/helpers.
- **`specification-guidelines/`** (new — split out on its own, not folded into
  `application-architecture/`, since it's authored/versioned as its own unit and is central enough to
  warrant it) — the app's **specification template** the supervisor interprets requests against,
  instructions on how to populate it, and the **sufficiency criteria the rule-spec-validator subagent
  checks a submitted spec against** (see "Graph" below) — what counts as clear enough to proceed
  (possibly with stated assumptions) versus insufficient (must be rejected with specific gaps).
  Written as free-form guidance, consistent with every other directory here, not a rigid
  machine-checkable schema — the validator subagent interprets it the same way the other subagents
  interpret their own guideline directories.
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

**Repository layout — per-application content lives with the application, not with the tool.** The
seven-directory knowledge base above, the app-specific prompts (see "Prompts and configuration" below),
the MCP tool configuration (see "MCP services — live application data" below), and any infrastructure needed to
host that app's live data (e.g. the OpenSearch deployment currently under `knowledgexpert/infrastructure/`
serving `autoins`'s MSRP pricing data) are all curated data *about* a target application, not operational
plumbing for the tool — so they live physically alongside that application, not inside `knowledgexpert`.
For `autoins`: a new sibling folder `knowledgenet-examples/autoins-rulegen/`, not a directory under
`knowledgexpert`:

```
knowledgenet-examples/
  autoins/                    (existing — the application itself)
  autoins-rulegen/            (new)
    knowledge/
      knowledgenet-foundation/
      application-domain/
      application-architecture/
      specification-guidelines/
      configuration-guidelines/
      exemplars/
      testing-guidelines/
    prompts/                  supervisor + subagent prompts tuned for autoins
    mcp/                      optional — omitted entirely if autoins defines no MCP services
    infra/                    optional — docker-compose/admin fixtures/data for whatever live-data
                               service the MCP config above points at (e.g. OpenSearch)
```

`knowledgexpert` itself keeps only what's genuinely generic: the DeepAgents graph/agent code,
LLM/model config, the checkpointer plumbing (SQLite for CLI, Postgres for MCP/AG-UI — see
"Conversational memory" below), and the CLI/MCP-server/AG-UI front-end code — plus,
optionally, a minimal generic fallback prompt template for bootstrapping a brand-new target application
before anyone's curated real content for it. This generalizes beyond `autoins`: any future target
application gets its own `<app>-rulegen/` sibling folder wherever that application's repo lives —
`knowledgexpert` never accumulates a growing pile of per-application subdirectories inside its own repo.

This also makes concrete something "Prompts and configuration" below already implied but left
physically ambiguous: since prompts are application-configurable, not just role-configurable, they're
per-app curated content like the knowledge base — they live in `<app>-rulegen/prompts/`, not in
`knowledgexpert`.

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
seven-directory VFS), the same physical location for every user working on that application, per the
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
- **CLI** — `FilesystemBackend` rooted at a local directory the user points the tool at via a
  `WORKSPACE_ROOT` env var (see "Configuration approach" below; they manage git themselves — in
  practice, one branch/worktree per thing they're working on, `WORKSPACE_ROOT` pointed at whichever
  checkout is currently active; the CLI's local session name is just a conversational label, it doesn't
  drive which directory gets used). Writes/edits land on disk immediately. Always local, regardless of
  what the knowledge-base backend for this run is (local or S3/RustFS) — the two are independent
  choices. No authentication — the CLI runs as whatever local user invoked it, same as `wolfpack_cli.py`
  today.
- **AG-UI** — `FilesystemBackend`/`S3Backend` rooted at a per-user-per-**session**, pre-provisioned
  network-filesystem path. **Git lifecycle (clone/pull/push/branch/worktree) is out of scope, at session
  granularity**: each session corresponds to its own git branch — in practice a `git worktree` so
  multiple sessions' checkouts can coexist and be mounted concurrently — and the human creates that
  worktree/branch themselves, matching the session name they picked when creating the session (see
  "Session picker" below). The tool never clones, branches, or switches anything; it only assumes the
  per-session directory already exists by the time that session is used, the same "assume it already
  exists" contract the per-user case already had, just one level more specific now that sessions exist.
  **Multi-user isolation, resolved**: `FilesystemBackend(root_dir=..., virtual_mode=True)` (the
  default) treats every agent-facing path as virtual and anchored to `root_dir` — `..`/`~` traversal is
  blocked, virtual "absolute" paths are remapped under `root_dir` rather than escaping it, and every
  resolved path is verified to stay within `root_dir` before any I/O — enforced in `_resolve_path()`
  itself, not something a prompt or a confused agent can talk its way around. So the isolation is
  entirely a function of **backend construction**: each session must get its own freshly-built
  `FilesystemBackend` with `root_dir` set to *that specific session's own workspace leaf directory* —
  `/workspace/<user>/<session>/`, not just `/workspace/<user>/` (see "Session picker" under
  "Conversational memory" below: a user may run several rule-gen requests concurrently, and their
  generated artifacts must not collide). The user segment is derived server-side from the
  Okta-authenticated identity (`auth_context`, mirroring `carqna-agent`); the session segment is the
  verified session id from that same user's `user_sessions` row — **never** from anything
  client-supplied. **The mistake to avoid**: rooting the
  backend at a *shared parent* directory (e.g. `/mnt/nfs/workspaces/`) and trusting the agent to "stay
  in its own subdirectory" — `virtual_mode`'s guardrails only block escaping `root_dir`, not what's
  reachable *inside* it, and every other user's (or that same user's other session's) directory would be
  legitimately inside a shared root.
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
the turn that originally generated it (via the checkpointer — see "Conversational memory" below), so
the revising subagent knows where to start — but now it can also `grep`/`glob`/`ls` beyond
that single file through its live workspace-mounted backend if the fix needs broader context. This
also removes the earlier gap around feedback referencing a file the session didn't itself
generate/track: the subagent can find it via `glob`/`grep` instead of requiring a tracked path.

**MCP services — live application data.** A target application may configure **one or more** MCP
services the agent can use during generation, each exposing live, queryable data a rule might need to
check against — not a single fixed integration. OpenSearch is one such service, not the only kind; a
different application (or `autoins` itself, over time) could equally configure a different MCP-exposed
database, a REST-backed service, or several at once. **For `autoins` specifically**, OpenSearch is used
to store pricing tables and contracts (extending the existing MSRP/car-pricing example) — the concrete
instance, not the general mechanism. Distinct from, and orthogonal to, both the knowledge-base backend
and the workspace backend: this is for live data an agent queries through a tool call, not documents it
reads by browsing a directory tree. Mirrors `carqna-agent`'s `car_price_expert`/`AutoGeek` pattern
exactly: an MCP-backed tool set (`ListIndexTool`/`SearchIndexTool`-style — list an index before
searching it, never guess a name) given to whichever subagent needs it, on top of its
`CompositeBackend` file access — MCP tools and backend-provided file tools coexist on the same subagent
without conflict, same as `carqna-agent`'s `main_agent`. The underlying mechanism is what `raven.py`
already does (`_setup_mcp_tools`, `MultiServerMCPClient`, a JSON MCP config) — unchanged as a mechanism,
but now **application-scoped**: which MCP services a target app has, if any, and what each one exposes,
is per-application configuration (alongside the prompts externalization described above and physically
located per "Repository layout" above), not something every application gets by default.

**MCP services are optional per application, not a universal capability.** Many target applications
will need none at all — no live data to check against, everything a rule needs already lives in the
curated knowledge base. Concretely: the MCP config (and the description of what each service/collection
contains) lives in `<app>-rulegen/mcp/`, and that directory simply doesn't exist for an application
with no MCP needs. Subagent construction must treat "no MCP config present for this app" as the normal,
expected default — attach zero MCP tools and move on — rather than requiring every app to explicitly
opt out via a flag (the inverse of `raven.py`'s current `skipMcpTools`, which defaults to *on* and has
to be told to skip). Retirement scope for OpenSearch's *prior* role (doc/rule ensemble retrieval, not
this one) is narrowed accordingly — see "Retirement" below.

**Graph** — a DeepAgents supervisor/subagent graph (mirrors `carqna-agent/src/agent/graph.py`),
replacing `wolfpack.py`:
- **Supervisor** — interprets an app-specific specification template (format varies per application;
  the supervisor must read/understand whatever template the target app defines) plus the free-form
  ask, classifies the request (code-generation / config-generation / test-generation — one or more —
  **feedback on previously generated artifacts** (see "Conversational memory" below), **or a
  clarification reply to the rule-spec-validator** (see "Rule spec validation" below)), and delegates.
  For a fresh generation request, the supervisor routes to **rule-spec-validator first** — it does not
  dispatch to code/config/test-generator until the validator reports the spec sufficient. Behavioral
  equivalent of `wolfpack`'s `analyst` + `request_router_node`, extended with this validation gate.
- **rule-spec-validator** subagent (new — not present in `wolfpack`) — checks a submitted spec against
  the target app's `specification-guidelines/` (template + population instructions + sufficiency
  criteria) before any generation happens. See "Rule spec validation" below for the full behavior.
- **code-generator** subagent — writes `@ruledef` rule code. Grounded in foundational + app-specific +
  exemplar knowledge layers. **Also gets whichever MCP services the target application defines** (see
  "MCP services — live application data" below) — e.g. a rule that needs to check a value against a
  live reference dataset (OpenSearch for `autoins`, something else for another application) rather than
  something curated as static knowledge-base content.
- **config-generator** subagent — writes/edits `rule-config.json` entries. Must actually be built this
  time (`wolfpack`'s `implementor` never was). Routable directly for config-only asks (e.g. "change
  this rule's rank"), and always invoked alongside code-generation for a new rule, per the app's
  convention that new rules need matching config entries.
- **test-generator** subagent — writes the app's test artifacts (test-data, rule-config override,
  expected-results, test-module — four files in `autoins`'s convention). **Does not execute the
  app's test tool** (see "Test tool integration," out of scope below) — produces its best
  understanding of the expected-results artifact from the spec/rules alone, without running anything
  to verify or generate it.

(Resolved: a single supervisor + these 4 subagents — rule-spec-validator, code-generator,
config-generator, test-generator — is sufficient. config-generation stays its own subagent rather than
merging into code-generation, despite the two usually firing together; validation stays its own
subagent rather than folding into the supervisor, since "is this spec good enough" is a materially
different judgment from "which subagent handles this" and deserves its own dedicated grounding in
`specification-guidelines/`.)

**Rule spec validation** — new functionality, the gate every fresh generation request passes through
before code-generator/config-generator/test-generator ever run. Two governing rules:
- If the spec is clear enough to proceed but required filling in some gap with a reasonable
  assumption, generation may proceed, but **the assumption must be explicitly stated** in the
  response — never silently made. This applies at two levels: the validator's own upfront assumptions
  (documented in its sufficiency check) *and* any further assumption a generator subagent discovers
  it needs to make once it's actually deep in code/config/test detail — both must surface, not just
  the first.
- If the spec is not clear enough to proceed at all, **no generator subagent runs**. The validator
  reports why (the specific gaps) and what additional information is required — the supervisor returns
  this to the caller directly instead of dispatching generation work against an insufficient spec.

Output contract (conceptually — mirrors the existing `AnalystOutput`/`CodingOutput`-style structured
outputs in `structures.py`): `sufficient: bool`, `assumptions: list[str]` (stated, non-blocking gaps
it's comfortable proceeding on), `gaps: list[str]` (blocking, populated only when `sufficient=false`).
When `sufficient=true`, the supervisor forwards `assumptions` to whichever generator(s) it dispatches
to, so those assumptions are carried into the generated artifact's own output rather than needing to be
independently rediscovered or silently dropped.

**This is an iterative loop, not a one-shot gate**: when `sufficient=false`, the human (or calling
agentic tool) replies with clarification in the *same* conversation — the supervisor classifies this as
a reply to the validator (not a new request, not feedback on generated output, since nothing was
generated yet) and routes back to rule-spec-validator, which re-checks the accumulated spec against
`specification-guidelines/` and either passes it on or asks for more. This loop rides the same
Postgres-backed checkpointer as the post-generation feedback loop below, but is a **distinct** loop:
pre-generation (validator ↔ human, before any artifact exists) versus post-generation (generator ↔
human, revising an artifact that already exists) are routed differently by the supervisor's
classification and never conflated.

Worth calling out explicitly: this validate → surface gaps → accept clarification → re-validate loop
is, in embryonic form, an interactive spec-authoring tool — a natural direction for this to grow into
(e.g. eventually drafting a spec from scratch through conversation, not just validating one supplied
whole). That's a plausible future extension this design enables, not something scoped/built now — see
"Explicitly out of scope" below.

Note the checkpointer *backend* differs by front-end (SQLite for CLI, Postgres for MCP/AG-UI — see
"Technology" under "Conversational memory" below); "same checkpointer" above means the same *thread*,
not necessarily the same storage engine, for a given front-end.

**Conversational memory / iterative feedback (post-generation loop)** — new functionality, not present
in `wolfpack` today (its `SqliteSaver` checkpointer is wired up but the graph doesn't use conversation
history to inform revision — every request is generated fresh). This is the **post-generation**
counterpart to the pre-generation validator loop described above — it fires only after an artifact has
actually been generated; the two are never conflated (see "Rule spec validation" above). Flow: a human
runs the generated code/tests themselves
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
- **Technology**: mirrors `carqna-agent`'s actual split, not a single uniform backend — verified
  directly against source (`carqna-agent/src/agent/carqna_cli.py` and `copilotkit_server.py`; the
  `CLAUDE.md` claim that the CLI runner is Postgres-backed is stale — the real file uses SQLite):
  - **CLI**: `AsyncSqliteSaver`, a local per-machine SQLite file (carqna's precedent: `carqna_cli.py`'s
    `_get_cli_sqlite_path()` — `~/.carqna/carqna_cli.sqlite`, overridable via `CARQNA_CLI_SQLITE_PATH`,
    directory auto-created). `knowledgexpert` follows the same convention with its own path/env var
    (e.g. `~/.knowledgexpert/knowledgexpert_cli.sqlite`, overridable via `KNOWLEDGEXPERT_CLI_SQLITE_PATH`).
    No setup/migration call needed — `AsyncSqliteSaver` never required one, unlike Postgres. Rationale
    (per carqna's own comment): the CLI is a single local user's tool, so there's no shared resource
    for concurrent CLI users/sessions to collide on — a local file is simpler than standing up Postgres
    for a single-user front-end.
  - **AG-UI**: `AsyncPostgresSaver` (own `knowledgexpert` database/connection string via `POSTGRES_URI`,
    explicit `await checkpointer.setup()` on startup — see `carqna-agent/src/agent/graph.py`'s
    `_get_conn_string()` and `copilotkit_server.py`'s `lifespan()`). Same pattern as the Okta decision
    above: reuse the *mechanism*, not `carqna-agent`'s actual Postgres instance/database.
  - **MCP**: also `AsyncPostgresSaver`, same instance/database as AG-UI — grouped with AG-UI rather than
    CLI because it's a server process potentially serving multiple concurrent sessions
    (`wolfpack_mcp.py`'s `QueryRequest.session_id` already threads a session id through this way — this
    becomes load-bearing instead of decorative), the same reason AG-UI needs a shared backend rather
    than a local file. `carqna-agent` has no MCP front-end to verify this against directly; this is
    `knowledgexpert`-specific reasoning extending carqna's CLI-vs-server split to a third front-end.
- Applies across all three front-ends: CLI (replacing `wolfpack_cli.py`'s existing `SqliteSaver` wiring
  with a used-for-real one), MCP (replacing decorative session-id threading with an actual checkpointer),
  and AG-UI (multi-turn is inherent to that protocol).
- The same checkpointer/thread also carries the pre-generation validator loop (see "Rule spec
  validation" above) — one conversation, one `thread_id`, both loops are just different classification
  outcomes the supervisor routes on at different points in that same conversation's lifecycle.

**Session picker (AG-UI only)** — a user may be working on several rule-generation requests
concurrently (e.g. two different rules, or a fresh spec alongside revising an earlier one), and their
conversational memory (and, per "Workspace" above, their generated artifacts) must not bleed together.
This means AG-UI's checkpoint thread is keyed by **session**, not just by user — `carqna-agent` already
solves exactly this (its "multi-session picker" feature) and the mechanism is directly reusable, not
something to design from scratch:
- **Schema** (Postgres, same database as the checkpointer): a `user_registry` table (maps the opaque
  Okta `sub` claim to a human-readable email/name, populated lazily via the OIDC `/userinfo` endpoint
  on first sight of a user — see `carqna-agent/src/agent/user_tracking.py`) and a `user_sessions` table
  (named sessions per user, `UNIQUE (user_registry_id, session_name)` — see
  `infrastructure/docker/postgres/initdb.d/users_registry.sh`/`users_sessions.sh`). Copy both tables'
  DDL and both Python modules near-verbatim, `carqna`/Auth0 naming aside.
- **Thread key**: `{user_id}:{session_id}`, built server-side from the verified identity and a
  session id the client only ever selects from its own `GET /sessions` list — never trusted raw (see
  `copilotkit_server.py`'s `langgraph_agent_endpoint`, same "never trust a client-supplied user id"
  principle already established for workspace `root_dir`).
- **Endpoints**: `GET /sessions` (list the caller's own sessions, most-recently-accessed first) and
  `POST /sessions` (create a new one) — copy `carqna-agent`'s `list_sessions`/`create_session`/
  `touch_session` (`sessions.py`) and their two route handlers directly; `track_user` (`user_tracking.py`)
  runs on every authenticated request the same way, never blocking the actual chat/generation path on a
  `/userinfo` hiccup.
- **Workspace tie-in**: each session's checkpoint thread and its workspace `root_dir` leaf both derive
  from the same `(user_id, session_name)` pair (see "Workspace" above) — one session picker selection
  determines both which conversation history and which generated-artifacts directory (in practice, which
  git branch/worktree) a turn operates against. The session name doubles as the expected directory-leaf
  convention; the human, not the tool, is responsible for the worktree at that path actually existing
  and being checked out to the matching branch before the session is used (see "Git lifecycle" under
  "Workspace" above) — no extra schema or provisioning logic beyond the `user_sessions` row itself.
- **Not needed elsewhere**: CLI already gets an equivalent of this for free — `carqna_cli.py`'s local
  `sessions` table (find-or-create by `--session <name>`, no `user_id` since the SQLite file itself is
  already scoped to one local user) is part of the CLI reuse already planned above, no separate design
  needed. MCP has no authenticated identity (see "Auth" — AG-UI-only) and no picker UI; its existing
  `QueryRequest.session_id` (client-supplied, used directly as the thread id, no `user_registry` join)
  is a different, simpler mechanism and stays that way.

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
same user-curated, per-application knowledge layer described above, not hardcoded in the package, and
physically located in that application's `<app>-rulegen/prompts/` (see "Repository layout" above), not
inside `knowledgexpert` itself. `knowledgexpert` may ship a minimal generic fallback template for
bootstrapping a brand-new target application, but that's a starting point, not "the" prompts for any
real application. Content is net-new either way: the mechanism (file-based prompts, file-based tool config) carries over
conceptually from `raven.py`/`carqna-agent`, but the actual prompt text and MCP tool configs are
specific to raven's current Q&A/vector-retrieval purpose and don't transfer — every prompt gets
rewritten for this tool's actual purpose (spec interpretation, rule/config/test generation) and for
the rules-engine domain.

**Configuration approach — `carqna-agent`'s env-var pattern, not `knowledgexpert`'s current
config-file/argparse approach.** Verified directly against `carqna-agent/src/agent/graph.py` and
`auth.py`: plain `os.getenv`/`os.environ` reads (via `python-dotenv`'s `load_dotenv()`), not a
settings framework, no dedicated config class. Two kinds of env var:
- **Scalars**, read directly: `LLM_MODEL` (with a sensible default), `POSTGRES_URI` (checkpointer
  connection string — MCP/AG-UI only, see "Conversational memory" above), `KNOWLEDGEXPERT_CLI_SQLITE_PATH`
  (CLI-only, local checkpointer file, defaulting to something like `~/.knowledgexpert/knowledgexpert_cli.sqlite`
  — mirrors carqna_cli.py's `CARQNA_CLI_SQLITE_PATH`), S3 credentials (`S3_ENDPOINT_URL`/
  `S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`/`S3_REGION`, required with no default — fails loud if
  missing), and (AG-UI only) the Okta equivalents of carqna's `AUTH0_DOMAIN`/`AUTH0_AUDIENCE` —
  carqna's own auth module is deliberately generic JWT/JWKS verification, documented there as
  "Okta/Auth0," so the mechanism already supports Okta as-is; only the env var names and values are
  `knowledgexpert`'s own, not shared with carqna (per the earlier Okta decision above).
- **Paths**, pointing at real files/directories rather than embedding their content: carqna's
  `PROMPTS_DIR` (a directory of markdown prompt files) and `MCP_CONFIG_PATH` (one JSON file) are the
  precedent. For `knowledgexpert`, one env var — e.g. `RULEGEN_ROOT` — points at the current target
  application's `<app>-rulegen/` directory (a local path, or an S3-compatible URI when that app's
  knowledge base is S3-backed), with `knowledge/`, `prompts/`, and `mcp/` derived as fixed subpaths
  beneath it. This single knob is what "which target application" means at runtime — replacing the
  `--promptDir`/`--mcpConfig` flag pair with one path that already matches the "Repository layout"
  folder convention above. `mcp/` simply not existing under that root is how "this application defines
  no MCP services" (see above) is expressed — no separate flag needed.
- **Retired**: the current `infrastructure/conf/{expert,raven,wolfpack}/config.json` per-role files and
  the ~30-flag `raven_cli.py`/`wolfpack_cli.py` argparse surface. Most of that surface is
  vector-retrieval-specific (`--baseCollections`, `--ensembleWeights`, `--embeddings`,
  `--vectorDbProvider`, etc.) and already gone once vector retrieval retires (see "Retirement" below);
  what's left (LLM model, prompt/MCP paths, workspace root) moves to env vars per this section instead
  of surviving as a smaller argparse surface.

**Observability — the same OTel tracing mechanism as `carqna-agent`.** Verified directly against
`carqna-agent/src/agent/copilotkit_server.py` and its `CLAUDE.md`: LangChain/LangGraph tracing to a
local Jaeger instance is `langsmith`'s built-in OTel exporter, activated **purely via env vars** — no
extra dependency or code beyond what's already needed for the checkpointer/LLM plumbing:
- `LANGSMITH_TRACING_V2=true` + `LANGSMITH_TRACING_MODE=otel` (or `hybrid`, which also sends to
  LangSmith cloud — needs `LANGSMITH_API_KEY`/`LANGSMITH_PROJECT`, `otel` alone sends to Jaeger only)
  + `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_SERVICE_NAME` (`knowledgexpert`'s own value — never
  carqna's, same "reuse the mechanism, not the instance" rule as Postgres/Okta above). **Must be port
  `4318` (HTTP) with the `/v1/traces` path, not `4317`/gRPC** — `langsmith`'s exporter is hardcoded to
  HTTP and doesn't append the path itself, a specific gotcha worth preserving verbatim in
  `knowledgexpert`'s own `.env.example`/docs, not rediscovering the hard way.
- This part is genuinely front-end-agnostic: nothing in `carqna-agent` wires it up specially for
  `copilotkit_server.py` — `carqna.py`, its plain CLI runner, has no `langsmith`/OTel code at all and
  still gets traced spans, since it's just env config the LangChain/LangGraph callback machinery picks
  up on its own. So once the dependency/infra work below lands, CLI and MCP get tracing for free with
  no code of their own — but that's deliberately deferred to its own last phase (see Phases below)
  rather than added incrementally alongside each earlier phase.
- **AG-UI-specific addition** (part of that same last phase, mirroring `copilotkit_server.py` exactly,
  applicable once AG-UI itself exists from phase 8): an early, explicit `langsmith.Client()`
  construction in the FastAPI `lifespan`, before any real request, so `langsmith` registers its OTel
  `TracerProvider` as the process-global one before `FastAPIInstrumentor.instrument_app(app)`'s
  HTTP-level spans need to nest under it — plus `FastAPIInstrumentor.instrument_app(app)` itself,
  called at **module level, before `app = FastAPI(lifespan=lifespan)`'s first ASGI scope**, not inside
  `lifespan()` — carqna's own comment there documents finding this out the hard way (spans showed up in
  Jaeger with nothing nested under them until the ordering was fixed). Copy this ordering exactly,
  don't rediscover it.
- **MCP-server front-end**: no direct carqna precedent — carqna has no MCP *server* of its own, only an
  MCP *client* (for OpenSearch). Whether FastMCP has an equivalent HTTP/transport-level instrumentation
  library is unverified; LangChain/LangGraph-level tracing via env vars still applies regardless, same
  as CLI.
- **Infra**: `docker-compose.yml` gains a `jaeger` service (`jaegertracing/all-in-one`, OTLP on
  `4317`/gRPC + `4318`/HTTP, UI on `16686`) — copied from `carqna-agent`'s `infrastructure/docker/`.
  This is tool-level observability infra, not application data, so it stays in `knowledgexpert/` per
  "Repository layout" above — not something that moves to `<app>-rulegen/`.
- **Dependencies**: `opentelemetry-exporter-otlp`, `opentelemetry-sdk`,
  `opentelemetry-instrumentation-fastapi` (the last one only actually exercised once AG-UI/phase 8
  lands, but harmless to add to `pyproject.toml` alongside the others in phase 0).

**Tooling** — new `pyproject.toml` + `uv`-managed venv **inside the project** (`.venv` under
`knowledgexpert/`, per-project like `knowledgenet` and each `knowledgenet-examples` app), replacing
`requirements.txt` + the shared `~/ai-venv`. **Deliberately diverges from `carqna-agent` here**:
`carqna-agent` itself uses an external, shared-style venv (`~/carqna.venv`, activated before `uv sync
--active` per its own `CLAUDE.md`), not an in-project one — `knowledgexpert` follows `knowledgenet`'s
in-project convention instead, not carqna's, on this specific point.

**Documentation** — both new authoring and refactoring of what exists, not an end-of-project
afterthought. Each phase below updates the docs it touches as part of that phase, not deferred to a
final documentation pass:
- **New**: a knowledge-base curation guide — how to set up a new target application's virtual
  filesystem across the seven directories (what goes where, with `autoins` as the worked example), how
  to author a specification template and its sufficiency criteria in `specification-guidelines/`, and
  conventions for the per-application prompts/config described above. Analogous to `knowledgenet`'s
  `docs/concepts.md`/`rules-authoring.md` and `knowledgenet-examples/autoins`'s
  `docs/description.md`/`testing.md`.
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
- ChromaDB and Neo4j entirely (both only ever served the old doc-retrieval mechanism, which has no
  successor role): `infrastructure/conf/{expert,raven,wolfpack}/` (the raven/wolfpack per-role configs'
  `baseCollections`/`ensembleWeights`/`embeddings`/vector-db-connection fields specifically — not
  necessarily the whole file, since `promptDir`/MCP-config fields may still be relevant), the ChromaDB
  and Neo4j pieces of `infrastructure/docker/docker-compose.yml`.
- **Not retired, but relocated**: `infrastructure/docker/opensearch-mcp/`, `infrastructure/admin/opensearch/`,
  `infrastructure/conf/mcp/opensearch/`, `data/opensearch/` — OpenSearch carries forward as an
  MCP-exposed tool, per "MCP services — live application data" above, but per "Repository layout" above it moves
  to `knowledgenet-examples/autoins-rulegen/{mcp/,infra/}` rather than staying under `knowledgexpert/`
  — it's infrastructure serving `autoins`'s data specifically, not generic tool infra. Only its *use for
  doc/rule ensemble retrieval* (the `rules_collection`/`app_docs_collection`/`framework_docs_collection`
  mechanism) is retired; the OpenSearch service and its MCP registration itself just move, not retire.
- `linux_exec_mcp.py` and `infrastructure/docker/linux-exec-mcp/` (the `ShellCommandExecutor` MCP
  service) — retired outright, not repurposed. Replaced by the DeepAgents virtual filesystem for the
  knowledge-base/workspace access it used to help provide indirectly; it is **not** replaced by an
  equivalent exec capability — see "Test tool integration," out of scope below.

### Explicitly out of scope

- Git lifecycle management (clone/pull/push/branch/worktree) for AG-UI workspaces — assumed
  pre-provisioned per session (one worktree/branch per session, matching the session name), by the human,
  not the tool. See "Workspace" and "Session picker" above.
- **Test tool integration** — actually running the target application's test tool (running the
  generated tests, inspecting output, generating/verifying `expected.csv`-equivalent results) is out
  of scope for now. Deliberately deferred rather than assumed to be pytest: the application's test
  framework may use a different tool entirely, so this needs its own design (likely a pluggable,
  per-application "how to run tests" concept) rather than hardcoding a pytest-exec tool now.
  `linux_exec_mcp.py` is retired, not repurposed for this — see Retirement above.
- **Standalone interactive spec-authoring wizard** (drafting a spec from scratch through conversation,
  rather than validating one already supplied) — a plausible future extension of the rule-spec-validator
  loop (see "Rule spec validation" above), but not scoped or built now. The validate/clarify/re-validate
  loop itself *is* in scope; a dedicated from-scratch drafting experience is not.
- Anything in the two now-retired plans (see `.plans/` — superseded, not part of this plan's scope):
  `plan-opensearch-chromadb-dual-backend-RETIRED.md`, `plan-replace-neo4j-with-arcadedb-RETIRED.md`.

## Testing approach (phases 2-5, via CLI)

The tool's job ends at generating artifacts — rule code, config, tests. Execution of those artifacts
(running `pytest`, `mypy`, or anything else) and the resulting feedback is the HITL's responsibility,
always — not just at runtime for the deployed agent (already established via "Test tool integration,"
out of scope above), but **also true of how we verify the platform itself while building it**. We do
not build a parallel test-execution harness in our own dev/CI workflow to check generated output either
— that would just relocate the same execution responsibility from the agent to us, not actually respect
the boundary. So testing phases 2-5 is **structural/output-shape verification only, never execution**:

- **Golden fixtures, curated in phase 1**: alongside the reference knowledge base for `autoins`, curate
  2-3 real `autoins` rules with hand-written specs (a mix of clearly-sufficient, sufficient-with-a-
  stated-assumption, and clearly-insufficient) plus their known-good code/config/test artifacts pulled
  from the actual app. Reused by every phase below rather than improvised per phase.
- **Phase 2 (supervisor + rule-spec-validator)** — run the CLI against each golden spec and assert on
  the validator's structured output (`sufficient`/`assumptions`/`gaps`) and the supervisor's routing
  decision. Fully automatable: the output is structured data, not generated code, so no execution is
  ever involved here regardless.
- **Phases 3-5 (code/config/test-generator)** — run the CLI against a validated golden spec, pointed at
  a disposable scratch workspace, and assert purely on shape: the right files exist at the right paths;
  rule code parses as valid Python and contains the expected `@ruledef` structure (a syntax/parse check,
  not running it); `rule-config.json` stays valid JSON with the new entry merged, not clobbered; the
  four test artifacts (`autoins`'s convention) exist and are well-formed EDI/CSV/JSON. All static checks
  on the artifacts as text/data.
- **Whether generated output is actually *correct*** (the rule computes the right thing, the test
  actually passes) is never something this test approach — or the platform — determines. That's a human
  call: someone runs the CLI, then separately and manually runs whatever verification they choose
  (`pytest`, reading the code, anything), and if something's wrong, reports it back in the same
  conversation. That's just dogfooding the post-generation feedback loop already in scope, not a
  separate test harness.

## Open questions

None outstanding — everything raised during design discussion has been resolved above.

## Phases (tentative — sketch only, subject to change as implementation surfaces new information)

0. Tooling: `uv`-managed `pyproject.toml`, in-project `.venv`, drop `requirements.txt`/`~/ai-venv`.
   *Docs*: new `docs/readme-development.md`-equivalent for the `uv` workflow.
1. Knowledge-base backend + content: both `FilesystemBackend` and RustFS-compatible `S3Backend` wired
   together in this single phase (not staged local-first) — `carqna-agent`'s `S3Backend` is already
   well-tested and reusable as-is, so there's no reason to defer it behind a separate later phase.
   Includes creating `knowledgenet-examples/autoins-rulegen/` (see "Repository layout" above) and
   curating foundational/app-specific/exemplar/test-framework/specification content, prompts, and (if
   applicable) MCP config + live-data infra there for `autoins` as the reference application, plus
   migrating the existing OpenSearch infra out of `knowledgexpert/infrastructure/` into
   `autoins-rulegen/{mcp/,infra/}`, **plus the golden fixture set** (see "Testing approach" below) that
   phases 2-5 reuse for CLI verification.
   *Docs*: new knowledge-base curation guide (the seven directories plus prompts/mcp/infra, worked
   `autoins` example).
2. Supervisor + rule-spec-validator subagent (spec interpretation, classification, and the
   validate/clarify/re-validate loop against `specification-guidelines/`) — CLI front-end only, no
   generation yet. Deliberately built before any generator subagent: nothing should be able to generate
   against an unvalidated spec, so the gate has to exist first, not be retrofitted later.
   *Docs*: new spec-template authoring guide, including how to write sufficiency criteria.
3. code-generator subagent — first actual generation, gated by the validator from phase 2. First use of
   the `CompositeBackend`-mounted workspace (`write` for new rule code files).
   *Docs*: `README.md` CLI section rewritten to the new command.
4. config-generator subagent — first consumer of the workspace's `edit` (and `read`) capability, since
   `rule-config.json` must be merged into, not overwritten.
   *Docs*: knowledge-base curation guide gains `configuration-guidelines/` conventions.
5. test-generator subagent (artifact authoring only — no test-tool execution; see "Test tool
   integration," out of scope).
   *Docs*: knowledge-base curation guide gains `testing-guidelines/` conventions.
6. Conversational memory / iterative feedback (post-generation loop): checkpointer wiring — SQLite for
   the CLI (own local file, no setup/migration needed), Postgres for MCP/AG-UI (own database,
   per-instance configurable) — see "Conversational memory" above. Supervisor logic to recognize and
   route feedback on prior artifacts to the subagent that produced them, revised prompts covering
   generate-fresh vs. revise-existing. The `CompositeBackend`-based live workspace access (see
   "Workspace" above) already exists from phases 3-5 — this phase is about the supervisor's
   routing/state logic, not new backend plumbing. Reuses the same checkpointer wiring the phase-2
   validator loop already established. CLI front-end only at this point, so only the SQLite path is
   exercised here — Postgres wiring for MCP/AG-UI lands with those front-ends (phases 7-8).
   *Docs*: `README.md`/CLI docs gain the feedback/revision workflow (how to report an issue in the
   same session so the right subagent picks it up).
7. MCP front-end: `/workspace/` route swapped to `StateBackend`, structured response extraction,
   Postgres checkpointer wired in (see "Conversational memory" above — same instance/database AG-UI
   will use in phase 8).
   *Docs*: `README.md` MCP section rewritten to the new server.
8. AG-UI front-end + Okta auth (real `ag-ui-langgraph` integration, per-instance Okta config,
   Postgres checkpointer setup mirroring `copilotkit_server.py`'s `lifespan()` — explicit
   `await checkpointer.setup()` on startup), **plus the session picker**: `user_registry`/`user_sessions`
   tables and init scripts, `GET`/`POST /sessions` endpoints, composite `{user_id}:{session_id}` thread
   keys — ported from `carqna-agent`'s `sessions.py`/`user_tracking.py` near-verbatim (see "Session
   picker" under "Conversational memory" above). Includes per-**session** (not just per-user) workspace
   `root_dir` derivation from the authenticated identity plus the picked session (see multi-user
   isolation notes under "Workspace" above — this is the critical piece to get right, not optional).
   *Docs*: `README.md` gains AG-UI/Okta/session-picker setup, including the human-managed
   worktree-per-session convention; `CLAUDE.md` updated to describe the now-complete new architecture
   instead of "migration in progress."
9. Retirement of legacy modules/infra listed above (ChromaDB/Neo4j fully; OpenSearch's doc-retrieval
   *use* only — its MCP infra stays, see "Retirement" above).
   *Docs*: `README.md` stripped of every legacy-stack section (pip setup, Docker ChromaDB/Neo4j
   infra, vector/graph data loading, `raven_cli`/`wolfpack_cli`/`wolfpack_mcp`/`copilot_api` commands),
   while gaining an OpenSearch-as-MCP-tool section (how to define an application's collections) if it
   didn't already land in an earlier phase.
10. Observability (see "Observability" above) — deliberately last, once the rest of the platform is
    functionally complete: OTel dependencies, the `jaeger` docker-compose service, env-var-only
    LangChain/LangGraph tracing (covers CLI and MCP retroactively, no code needed), and the AG-UI-only
    `FastAPIInstrumentor`/early-`langsmith.Client()` wiring (mirroring `copilotkit_server.py`'s exact
    ordering).
    *Docs*: `README.md`/dev-setup doc gain the OTel env vars and the `4318`/`/v1/traces` gotcha.
