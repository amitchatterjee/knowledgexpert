# ChromaDB Retirement and OpenSearch Vector DB Migration Plan

## Objective
Retire ChromaDB support in knowledgexpert and migrate vector ingestion/retrieval to OpenSearch with minimal risk, measurable parity, and a rollback path.

## Scope

### In scope
- Runtime vector retrieval migration for Raven/Expert/Wolfpack flows.
- Vector ingestion migration for document chunk storage.
- CLI/config contract updates from Chroma-specific to provider-agnostic/OpenSearch-first.
- Infrastructure, dependency, and documentation updates.
- Validation, rollout, and rollback procedures.

### Out of scope
- Non-vector OpenSearch MCP tools already in use.
- Graph (Neo4j) pipeline behavior changes.
- Prompt redesign (unless retrieval format requires small tuning).

## Current Chroma Touchpoints

### Runtime + ingestion code
- src/knowledgexpert/raven.py
- src/knowledgexpert/expert.py
- src/vector_store.py
- src/vector_query.py

### CLI args and config contract
- src/raven_cli.py
- src/expert_cli.py
- infrastructure/conf/expert/config.json
- infrastructure/conf/wolfpack/analyst/config.json
- infrastructure/conf/wolfpack/developer/config.json
- infrastructure/conf/wolfpack/tester/config.json
- infrastructure/conf/wolfpack-legacy/analyst/config.json
- infrastructure/conf/wolfpack-legacy/developer/config.json
- infrastructure/conf/wolfpack-legacy/tester/config.json

### Infra/deps/docs
- requirements.txt
- infrastructure/docker/docker-compose.yml
- README.md

## Target Architecture
1. Add a vector backend factory/interface used by retrieval and ingest paths.
2. Support provider selection via config during transition: `chroma` and `opensearch`.
3. Make OpenSearch the default provider after parity is demonstrated.
4. Remove Chroma provider and dependencies in a follow-up release.

## Phase Plan

## Phase 0: Design and baseline (1-2 days)
1. Decide OpenSearch vector strategy:
   - Use native OpenSearch vector index (k-NN) and LangChain OpenSearch integration.
2. Freeze index schema:
   - Required fields: `id`, `page_content`, `metadata`, `embedding`.
   - Define metadata mappings and index naming conventions.
3. Capture baseline behavior with current Chroma:
   - Save representative prompt set and expected outputs.
   - Record latency and retrieval quality for top-k results.

### Phase 0 findings from the current repo baseline
- Vector ingest and retrieval are still hard-wired to Chroma in the runtime path: `src/vector_store.py`, `src/vector_query.py`, `src/knowledgexpert/raven.py`, and `src/knowledgexpert/expert.py` all instantiate `chromadb.HttpClient` and `langchain_chroma.Chroma` directly.
- The public CLI/config contract is still Chroma-shaped. Current shipped configs use `chromaHost` and `chromaPort`, and there are no provider-agnostic vector keys yet.
- The OpenSearch target should be treated as password-protected by default, so the migration needs explicit credential handling and an authenticated smoke test rather than assuming anonymous access.
- Chroma is still present in runtime dependencies and local infra: `chromadb` and `langchain-chroma` remain in `requirements.txt`, and `infrastructure/docker/docker-compose.yml` still defines a Chroma service and data volume.
- OpenSearch support already exists elsewhere in the repo for MCP/infrastructure/docs, but the vector DB migration path has not been wired to OpenSearch yet.
- Baseline benchmark material exists as prompt fixtures under `benchmark/`, but there are no committed expected-output snapshots or latency/retrieval measurements yet.

Implication:
- Phase 0 is still documentation and baseline capture work only; no code changes are required for this phase unless we decide to add explicit benchmark artifacts.

Exit criteria:
- Schema and naming conventions documented.
- Baseline benchmark set committed for comparison.

## Phase 1: Provider abstraction (2-4 days)
1. Introduce a shared vector backend module:
   - New module, e.g. `src/knowledgexpert/vector_backend.py`.
   - Factory methods for retriever creation and ingest writer creation.
2. Refactor callers to use factory (no behavior change yet):
   - `src/knowledgexpert/raven.py`
   - `src/knowledgexpert/expert.py`
   - `src/vector_store.py`
   - `src/vector_query.py`
3. Add generic CLI/config keys:
   - `vectorDbProvider`, `vectorDbHost`, `vectorDbPort`, `vectorDbUseSsl`, `vectorDbUsername`, `vectorDbPassword`, `vectorDbIndexPrefix`.
4. Keep backward compatibility:
   - Continue accepting `chromaHost`/`chromaPort` as deprecated aliases.
   - Emit deprecation warnings at startup.

Exit criteria:
- `vectorDbProvider=chroma` behaves exactly as today.
- All existing configs still run.

## Phase 2: OpenSearch implementation (3-5 days)
1. Implement OpenSearch ingest:
   - Create index with vector mapping if missing.
   - Batch writes from chunked docs.
   - Implement `--clear` by deleting/recreating target index.
2. Implement OpenSearch retrieval:
   - `similarity`.
   - `similarity_score_threshold` (including score interpretation policy).
   - `mmr` equivalent (or fetch + rerank fallback).
3. Preserve logical collection semantics:
   - Map current collection names to index names deterministically.

Exit criteria:
- Raven and Expert can run end-to-end with `vectorDbProvider=opensearch`.
- vector_store/vector_query work against OpenSearch.

## Phase 3: Data migration + dual run (2-4 days)
1. Add dual-write option in ingest path (temporary):
   - Write to Chroma and OpenSearch from one run when enabled.
2. Backfill and validation tooling:
   - Reindex from source documents into OpenSearch.
   - Validate document count, metadata coverage, and retrieval overlap.
3. Shadow-read test mode (non-prod):
   - Run equivalent queries against both backends.
   - Compare top-k overlap and qualitative answer quality.

Suggested parity targets:
- Top-5 retrieval overlap >= 0.70 on regression set.
- No critical quality regressions on accepted prompts.

Exit criteria:
- Parity thresholds met for agreed soak period.

## Phase 4: Default cutover (1-2 days)
1. Switch defaults to OpenSearch in CLI and configs.
2. Update role configs under `infrastructure/conf/**`.
3. Update README setup instructions and query examples.
4. Keep Chroma path available for one release as rollback safety.

Exit criteria:
- Fresh environment setup works with OpenSearch only defaults.
- Existing users can migrate using documented steps.

## Phase 5: Remove Chroma support (next release)
1. Remove Chroma code paths from runtime and tooling.
2. Remove dependencies from `requirements.txt`:
   - `chromadb`
   - `langchain-chroma`
3. Remove Chroma service and volume from `docker-compose.yml`.
4. Remove deprecated CLI args and config aliases.
5. Final grep gate: zero runtime references to `chroma`/`chromadb`.

Exit criteria:
- No Chroma runtime/dependency/infra/doc references remain.

## Detailed Work Breakdown (PR slices)

## PR1: Backend abstraction + compatibility
- Add vector backend factory module.
- Refactor consumers to use factory.
- Add provider-agnostic config keys.
- Keep Chroma as default and maintain existing behavior.

## PR2: OpenSearch backend
- Add OpenSearch ingest and retrieval implementation.
- Add index management and clear semantics.
- Add unit tests for mapping/config resolution and retrieval modes.

## PR3: Migration tooling + validation
- Add optional dual-write mode.
- Add parity checker script (counts + top-k overlap).
- Add test queries fixture and benchmark output format.

## PR4: Cutover defaults + docs
- Update default provider and all shipped configs.
- Update README commands and operational notes.
- Add rollback instructions.

## PR5: Chroma removal
- Remove Chroma code and dependencies.
- Remove Chroma docker resources.
- Final cleanup and release notes.

## Test and Validation Strategy
1. Unit tests:
   - Config parsing and deprecation mapping.
   - Factory provider selection.
   - Index-name mapping from collection config.
2. Integration tests:
   - Ingest + retrieve on OpenSearch for each retrieval mode.
   - Raven CLI and Wolfpack config smoke tests.
3. Regression tests:
   - Prompt set with expected output snapshots (or semantic checks).
4. Non-functional:
   - Indexing throughput and query latency checks.

## Operational Readiness Checklist
- OpenSearch index template and mappings versioned.
- TLS/auth configuration documented and tested.
- Password-protected OpenSearch credentials are sourced from config or environment and validated with a secure connection smoke test.
- Health checks for vector retrieval path added.
- Logging includes provider, index, and retrieval mode.
- Alerting thresholds for OpenSearch errors/timeouts set.

## Rollback Plan
1. During transition, retain `vectorDbProvider=chroma` path.
2. If quality/reliability issues occur after cutover:
   - Switch configs back to Chroma provider.
   - Re-run known-good Chroma workflows.
3. Keep Chroma infrastructure and data until OpenSearch SLOs are stable for one release cycle.

## Risks and Mitigations
1. Retrieval score mismatch across providers.
   - Mitigation: normalize thresholds and tune retrieval mode behavior.
2. Metadata mapping/type drift.
   - Mitigation: strict mapping and pre-ingest validation.
3. Embedding mismatch during migration.
   - Mitigation: pin embedding provider/model for parity runs.
4. Rollout regressions in role-based configs.
   - Mitigation: smoke tests for analyst/developer/tester profiles.

## Proposed Timeline
- Week 1: Phase 0 + PR1
- Week 2: PR2
- Week 3: PR3 + soak
- Week 4: PR4
- Next release window: PR5

## Ownership Suggestion
- Core backend migration: Python maintainers.
- Infra and compose changes: platform/devops.
- Config/profile updates: product/agent maintainers.
- Validation and acceptance sign-off: QA + domain stakeholders.

## Definition of Done
- OpenSearch is default and validated for all active flows.
- Documentation fully reflects OpenSearch vector operations.
- Chroma is removed from runtime code, dependencies, and infrastructure (Phase 5 release).
- Rollback is no longer required because stability targets are met for at least one release cycle.
