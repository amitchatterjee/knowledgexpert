# OpenSearch + ChromaDB Dual-Backend Plan

## Objective
Run OpenSearch and ChromaDB side-by-side:
- OpenSearch for production-grade vector retrieval.
- ChromaDB as a lightweight development and local testing backend.

This plan replaces the previous Chroma retirement direction.

## Status Snapshot (as of 2026-06-07) — DONE
- Phase 0: Completed
- Phase 1: Completed
- Phase 2: Completed
- Phase 3: Completed
- Phase 4: Completed
- Validation: copilot-api and MCP test runs — Completed
- Marked done: 2026-06-07

## Scope

### In scope
- Maintain both vector providers (`opensearch`, `chroma`) behind one backend abstraction.
- Keep provider-agnostic CLI/config contract (`vectorDb*` settings).
- Validate parity and operational readiness across providers.
- Make OpenSearch default for non-local deployments while retaining Chroma for local/dev.
- Update docs and runbooks to reflect dual-backend support.

### Out of scope
- Removing Chroma from runtime, infra, or dependencies.
- Changes to non-vector OpenSearch MCP tooling.
- Prompt redesign unless retrieval output format requires minor adjustment.

## Architecture Decision
1. Single vector backend interface/factory for ingest and retrieval.
2. Provider selected by config: `vectorDbProvider=opensearch|chroma`.
3. OpenSearch is the recommended default for staging/prod.
4. Chroma remains supported for local/dev and fallback scenarios.

## Completed Work

### Phase 0: Design and baseline (Completed)
1. Defined migration direction from provider-specific code to provider abstraction.
2. Established vector schema expectations for OpenSearch (`id`, `page_content`, `metadata`, `embedding`).
3. Identified baseline benchmark inputs and parity requirements.

### Phase 1: Provider abstraction (Completed)
1. Added a shared backend abstraction in `src/knowledgexpert/vector_backend.py`.
2. Refactored runtime callers to consume backend factory instead of directly coupling to one provider.
3. Standardized config surface on provider-agnostic `vectorDb*` keys.

Exit state:
- Chroma behavior preserved when `vectorDbProvider=chroma`.
- Runtime no longer requires direct provider coupling at call sites.

### Phase 2: OpenSearch backend implementation (Completed)
1. Implemented OpenSearch ingest path including index creation/management.
2. Implemented OpenSearch retrieval modes used by Raven/Expert flows.
3. Preserved deterministic mapping between logical collection names and physical index names.

Exit state:
- End-to-end ingest and query available with `vectorDbProvider=opensearch`.
- OpenSearch backend is functionally usable alongside Chroma.

## Remaining Plan

### Phase 3: Validation and dual-provider hardening (Completed)
1. Add/complete parity harness:
   - Compare Chroma vs OpenSearch top-k overlap and answer quality on benchmark prompts.
2. Add optional dual-write and shadow-read modes where useful for validation.
3. Validate operational behavior:
   - Auth/TLS, retries, timeout handling, and error observability.

Progress update (as of 2026-06-06):
1. OpenSearch runtime hardening completed for current flows:
   - OpenSearch provider path is active for ingest/query in the shared vector backend.
   - OpenSearch 3.x compatibility issue addressed by using a supported vector engine for new index creation.
2. Access-control hardening completed for dual-provider operations:
   - Added vector-specific OpenSearch roles and mappings for write/read paths.
   - `bob` permissions now cover clear/create/ingest/refresh lifecycle for vector indices.
   - `alice` permissions now cover vector retrieval/search for query flows.
3. Operator workflow/docs progress completed:
   - Added shared env setup script (`sh/setup_env.sh`) for provider selection (`chroma` or `opensearch`).
   - Updated README vector build/query and Raven CLI sections to use provider-driven arguments from the setup script.
4. Current validation status:
   - Vector store and vector query were exercised on both ChromaDB and OpenSearch.
   - Early parity checks are positive.
   - Phase 3 acceptance is complete for the current scope.
   - Remaining explicit test runs to execute next: copilot-api and MCP tests.

Suggested parity targets:
- Top-5 retrieval overlap >= 0.70 on regression set.
- No critical quality regressions on accepted prompts.

Exit criteria:
- Parity thresholds met and documented for agreed soak period.

### Phase 4: Documentation and default guidance (Completed)
1. Update docs to present recommended backend selection by environment:
   - Local/dev: ChromaDB (recommended default).
   - Staging/prod: OpenSearch (recommended default).
2. Update role/profile config examples under `infrastructure/conf/**`.
3. Publish troubleshooting and fallback guide for provider switching.

Exit criteria:
- Clear operator guidance exists for when to use each backend.
- Configuration examples are consistent across docs and profiles.

## Work Breakdown (PR slices)

### PR1 (Completed): Backend abstraction + compatibility
- Shared backend factory abstraction.
- Caller refactors.
- Provider-agnostic config keys.

### PR2 (Completed): OpenSearch backend
- OpenSearch ingest/retrieval implementation.
- Index and clear semantics.

### PR3 (Completed): Validation tooling + parity reporting
- Parity checker (counts, overlap, quality notes).
- Benchmark output format and acceptance report.

### PR4 (Completed): Docs + operational runbooks
- Environment-based backend recommendations.
- Switching/fallback procedures.

## Test and Validation Strategy
1. Unit tests:
   - Provider selection and config parsing.
   - Collection-to-index naming rules.
2. Integration tests:
   - Ingest + retrieve for both providers.
   - Raven/Expert/Wolfpack smoke tests by profile.
3. Regression tests:
   - Benchmark prompt set with expected quality checks.
4. Non-functional checks:
   - Ingest throughput and retrieval latency comparisons.

## Operational Readiness Checklist
- OpenSearch index template/mapping versioned.
- Auth/TLS path documented and validated.
- Provider-specific health checks available.
- Logs include provider, index/collection, retrieval mode, and error class.
- Runbook includes backend switching steps and expected side effects.

## Risks and Mitigations
1. Score behavior differences between providers.
   - Mitigation: normalize thresholds and tune provider-specific defaults.
2. Metadata mapping drift.
   - Mitigation: enforce schema validation pre-ingest.
3. Environment drift between local and production.
   - Mitigation: parity tests run in CI and before release.

## Timeline (Updated)
- Week 1-2: Phase 0-2 complete.
- Week 3: Phase 3 parity and soak.
- Week 4: Phase 4 docs and operational sign-off.

## Definition of Done
- OpenSearch and ChromaDB are both supported in active flows.
- Phase 1 and Phase 2 deliverables are complete and stable.
- Benchmark and parity results are documented.
- Docs clearly define backend choice by environment and fallback procedure.
