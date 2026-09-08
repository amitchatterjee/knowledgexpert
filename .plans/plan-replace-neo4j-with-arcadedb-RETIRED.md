# Neo4j to ArcadeDB Migration Plan

> **RETIRED (2026-09-05).** Superseded by
> [`001-2026-09-05-deepagents-modernization-plan-INPROG.md`](001-2026-09-05-deepagents-modernization-plan-INPROG.md),
> which retires graph-store-based (Neo4j) retrieval entirely in favor of a filesystem-backed knowledge
> base. Kept for historical reference only — do not act on this plan.

## Objective
Replace Neo4j with ArcadeDB for graph retrieval in knowledgexpert while preserving current Graph RAG behavior, minimizing prompt/code churn, and maintaining a rollback path until parity is confirmed.

Important clarification:
- ArcadeDB migration is graph-only.
- It is independent from vector backend choices (OpenSearch or ChromaDB).

Capability note:
- ArcadeDB can also support vector and search workloads, so it is a potential all-in-one database option.
- This plan intentionally does not include migrating vector/search to ArcadeDB at this time.

## Scope

### In scope
- Graph database migration for Graph RAG flows used by Expert and graph ingestion tooling.
- CLI/config contract updates from Neo4j-specific options to provider-agnostic graph DB settings.
- Infrastructure and documentation changes required to run ArcadeDB locally and in deployment environments.
- Validation and rollout plan with quality, latency, and correctness checks.

### Out of scope
- Vector backend changes (OpenSearch/ChromaDB).
- Non-graph OpenSearch MCP tooling.
- Major prompt redesign outside dialect/terminology adjustments.

Boundary statement:
- This plan does not change vector ingestion or vector retrieval architecture.
- No coupling between ArcadeDB decisions and OpenSearch/Chroma decisions is required.
- Evaluating ArcadeDB as a unified graph+vector+search backend may be considered in a separate future plan.

## Current Neo4j Touchpoints

### Runtime graph query path
- src/knowledgexpert/expert.py
  - Uses Neo4jGraph and GraphCypherQAChain.
  - Accepts Neo4j credentials and database parameters.

### Graph ingestion/build tooling
- src/graph_store.py
  - Uses Neo4j Python driver (GraphDatabase, Neo4jError).
  - Clears and writes graph structures into Neo4j.
  - CLI arguments are Neo4j-specific.

### CLI and config contract
- src/expert_cli.py
  - neo4jUri, neo4jUser, neo4jPassword, neo4jDatabase arguments.
- infrastructure/conf/expert/config.json
- infrastructure/conf/wolfpack-legacy/developer/config.json

### Prompt language and guidance
- infrastructure/conf/expert/graph_prompt.txt
- infrastructure/conf/wolfpack-legacy/developer/graph_prompt.txt

### Local infrastructure
- infrastructure/docker/docker-compose.yml
  - Neo4j service and neo4j_data volume.

### Documentation
- README.md
  - Build graph data command currently references Neo4j.

## Target Architecture
1. Introduce a graph backend abstraction for query and ingest paths.
2. Support provider selection by config during transition: neo4j and arcadedb.
3. Migrate graph query generation/execution to ArcadeDB-compatible dialect and schema.
4. Make ArcadeDB default after parity and soak testing.
5. Remove Neo4j path in a follow-up release (optional, after stabilization).

Note:
- OpenSearch and ChromaDB remain vector backends and are unaffected by this graph migration.

## Proposed Graph Config Contract
Use provider-agnostic graph DB keys:
- graphDbProvider: neo4j | arcadedb
- graphDbHost
- graphDbPort
- graphDbUseSsl
- graphDbUsername
- graphDbPassword
- graphDbDatabase
- graphDbProtocol (bolt/http/https, depending on connector)

Compatibility notes:
- Keep legacy neo4j* keys as temporary aliases during transition.
- Resolve aliases into graphDb* at startup and warn when deprecated keys are used.

## Phase Plan

### Phase 0: Discovery and compatibility design (1-2 days)
1. Confirm ArcadeDB connectivity mode and Python client strategy.
2. Decide query abstraction level:
   - Option A: Keep LangChain chain and swap graph connector.
   - Option B: Introduce custom graph query executor with LLM-generated query dialect.
3. Freeze initial graph schema mapping from current Neo4j model:
   - Module, Class, Function, Attribute nodes.
   - Type hierarchy and call hierarchy edges.
4. Capture baseline from Neo4j:
   - Representative Graph RAG prompts.
   - Query correctness snapshots.
   - Latency baseline.

Exit criteria:
- Chosen client/connector and query execution approach documented.
- Baseline prompts and expected answers captured.

### Phase 1: Graph backend abstraction (2-4 days)
1. Add a backend interface for graph query and graph ingest.
2. Refactor Expert graph path to use backend factory (behavior unchanged under Neo4j).
3. Refactor graph_store ingest path to backend interface.
4. Add graphDb* config support and legacy key aliasing.

Exit criteria:
- graphDbProvider=neo4j preserves current behavior.
- All Neo4j direct coupling isolated behind backend module(s).

### Phase 2: ArcadeDB implementation (3-6 days)
1. Implement ArcadeDB ingest writer:
   - Create/update schema objects as needed.
   - Upsert nodes/edges from build_graph output.
   - Implement clear semantics equivalent to current --clear behavior.
2. Implement ArcadeDB query executor for Graph RAG:
   - Prompt and query-template updates for ArcadeDB syntax.
   - Result normalization to match existing graph_context expectations.
3. Add robust connection/error handling:
   - Auth failures, unavailable service, retry/timeouts.

Exit criteria:
- Expert Graph RAG runs end-to-end with graphDbProvider=arcadedb.
- graph_store can clear and ingest into ArcadeDB.

### Phase 3: Parity validation and dual-run (2-4 days)
1. Add side-by-side validation mode:
   - Execute equivalent graph question set on Neo4j and ArcadeDB.
2. Compare outputs:
   - Structural correctness of retrieved graph facts.
   - Downstream answer quality impact in Expert workflows.
3. Fix schema/query gaps and tune prompts.

Suggested targets:
- No critical factual regressions on accepted Graph RAG prompt set.
- Median graph query latency within agreed tolerance band.

Exit criteria:
- Parity report approved for production trial.

### Phase 4: Default cutover and docs (1-2 days)
1. Change default graphDbProvider to arcadedb in configs.
2. Update docker-compose to include ArcadeDB as primary graph DB.
3. Update README commands and migration notes.
4. Keep Neo4j as fallback for one release cycle.

Exit criteria:
- Fresh setup works with ArcadeDB defaults.
- Rollback steps are documented and tested.

### Phase 5: Neo4j deprecation/removal (next release, optional)
1. Remove Neo4j runtime code and legacy key aliases.
2. Remove Neo4j dependency and docker resources.
3. Remove Neo4j-specific prompt wording where no longer needed.
4. Final grep gate: no runtime references to neo4j except migration notes.

Exit criteria:
- No active runtime/infrastructure dependency on Neo4j.

## Work Breakdown (PR slices)

### PR1: Graph abstraction + config compatibility
- Add backend interfaces/factory.
- Add graphDb* settings + legacy alias translation.
- Keep Neo4j path as default.

### PR2: ArcadeDB backend
- Add ArcadeDB ingest and query integration.
- Add query/result normalization layer.

### PR3: Validation tooling
- Add parity harness and benchmark fixture outputs.
- Add acceptance criteria report template.

### PR4: Cutover + docs
- Switch defaults to ArcadeDB.
- Update compose and README.
- Add rollback runbook.

### PR5: Neo4j cleanup (optional next release)
- Remove deprecated Neo4j path and artifacts.

## Test and Validation Strategy
1. Unit tests
- Config parsing and alias mapping.
- Backend provider selection.
- Graph schema mapping and edge/node upsert logic.

2. Integration tests
- graph_store ingest and clear against ArcadeDB.
- Expert Graph RAG query path with ArcadeDB.

3. Regression tests
- Curated graph prompt set with expected factual checkpoints.

4. Non-functional checks
- Graph query latency and ingestion throughput.

## Operational Readiness Checklist
- ArcadeDB container/service configuration versioned.
- Auth/TLS settings documented.
- Health checks and startup readiness probes added.
- Logging includes provider, database, query mode, and errors.
- Backup/restore path validated for graph data.

## Rollback Plan
1. Keep graphDbProvider=neo4j available during transition.
2. If regressions occur after cutover:
   - Switch configs back to neo4j.
   - Re-run known-good Graph RAG validation set.
3. Keep Neo4j data/service for one release cycle after ArcadeDB cutover.

## Risks and Mitigations
1. Query dialect mismatch (Cypher variants/features).
- Mitigation: constrain generated query patterns and add translation/validation layer.

2. Ingestion semantic drift.
- Mitigation: schema conformance checks and deterministic upsert keys.

3. Prompt fragility due to graph backend change.
- Mitigation: minimal prompt edits plus benchmark-based tuning.

4. Operational surprises in ArcadeDB setup.
- Mitigation: explicit smoke tests, readiness checks, and rollback drills.

## Proposed Timeline
- Week 1: Phase 0 + Phase 1
- Week 2: Phase 2
- Week 3: Phase 3
- Week 4: Phase 4
- Next release: Phase 5 (optional)

## Definition of Done
- ArcadeDB is the default graph backend for active graph flows.
- Graph RAG quality and latency targets are met.
- Rollback to Neo4j is tested for one release cycle (until final deprecation decision).
- Documentation and configuration are consistent with ArcadeDB-first operation.
