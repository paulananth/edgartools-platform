---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: fix-pipelines — Pipeline Data-Source Completeness & Verification
current_phase: 5
current_phase_name: Node And Populated-Relationship Graph Parity
current_plan: 3 of 3 in current phase (05-02 complete)
status: in_progress
stopped_at: Phase 5 Plan 02 complete
last_updated: "2026-07-08T06:37:58.162Z"
last_activity: 2026-07-08
last_activity_desc: 05-02 complete (node-resolution idempotency tests for all 6 MDM entity types; GVER-03 fully satisfied)
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 3
  completed_plans: 2
  percent: 67
---

# Project State — fix-pipelines

## Current Position

Phase: 5 (Node And Populated-Relationship Graph Parity) — in progress
Plan: 3 of 3 in current phase
Status: 05-02 complete; ready to plan/execute 05-03
Last activity: 2026-07-08 -- 05-02 complete (node-resolution idempotency tests for all 6 MDM entity types; GVER-03 fully satisfied)

[███████░░░] 67% (0/5 phases complete, 2/3 plans in phase 5)

## Milestone Context

**v2.0 fix-pipelines — Pipeline Data-Source Completeness & Verification**

Goal: Every MDM node type and relationship type is either verified-populated or has a written,
evidenced source-coverage exclusion traced to its actual source artifact (or explicit absence
of one); Neo4j Native App verification cleanly separates readiness from parity failures;
platform parsing is cross-checked against edgartools.

Requirements: NODE-01..06, EDGE-01..11, GVER-01..03, ARTF-01..02, EDGX-01..03 (26 total, see
REQUIREMENTS.md)

## Phase Summary

| Phase | Goal | Requirements | Status |
|-------|------|--------------|--------|
| 5 — Node And Populated-Relationship Graph Parity | All 6 node types + 4 populated relationship types verified, idempotency established | NODE-01..06, EDGE-01..04, GVER-03 | Not started |
| 6 — Relationship Investigation And Population | Root-cause + populate the 5 ambiguous zero relationship types against their actual artifacts | EDGE-05, 06, 09, 10, 11 | Not started |
| 7 — Source-Coverage Exclusions And Artifact Hygiene | Document the 2 artifact-confirmed exclusions; fix silver-clobber + fetch-idempotency | EDGE-07, 08, ARTF-01, 02 | Not started |
| 8 — Neo4j Native App Verification Gaps | verify-graph separates readiness vs parity; GRAPH_INFO/BFS/LIST_GRAPHS resolved or documented | GVER-01, 02 | Not started |
| 9 — edgartools Crosscheck | Validate platform parsing vs edgartools; replace parsers where it's a clear win; audit API usage | EDGX-01..03 | Not started |

## Progress

**Phases Complete:** 0/5
**Current Plan:** 3 of 3 in current phase (05-02 complete)

## Session Continuity

**Last session:** 2026-07-08T06:36:52.245Z

**Stopped At:** Phase 5 Plan 02 complete — real-DB node-resolution idempotency regression tests
committed for all 6 MDM entity types (5 silver-resolved via `test_node_resolution_is_idempotent_across_entity_types`,
plus the seeded `audit_firm` type via `test_audit_firm_seed_is_idempotent`). GVER-03 is now fully
satisfied (node/relationship-derivation side here + graph-sync/full-rebuild side from 05-01).
Committed on `claude/fix-pipelines-v2`. Not yet planned: 05-03.
**Resume File:** .planning/workstreams/fix-pipelines/phases/05-node-and-populated-relationship-graph-parity/05-02-SUMMARY.md

## Accumulated Context

### Active Decisions

- Artifact triage is embedded per-relationship (EDGE-05..11) rather than as a separate generic
  audit, so each zero relationship type's source artifact (or explicit absence of one) is
  traceable — user-directed adjustment during milestone setup (2026-07-08).

- AUDITED_BY (EDGE-10) and any fundamentals-pipeline work must coordinate with the active
  `fundamental-factors-v2` workstream (Codex) — do not run fundamentals in dev without checking
  for overlap first.

- MANAGES_FUND (EDGE-07) is a confirmed dead end from EDGAR: all 30 ADV filings in the active
  universe are paper filings with no electronic document. See
  `.planning/workstreams/claude-mdm-source-recovery/FINDINGS.md`.

- This workstream continues phase numbering from v1.0 (ended at Phase 4) — v2.0 starts at
  Phase 5, per default (non-reset) numbering behavior.

- 05-01: `GRAPH_NODE_AUDITFIRM` identifier (not the CONTEXT.md prose spelling
  `GRAPH_NODE_AUDIT_FIRM`) is authoritative — matches the pre-existing `NODE_TABLES` tuple entry
  and the `result.node_tables` test assertion already in `test_snowflake_graph_migration.py`.

- 05-01: GVER-03 was only partially satisfied by that plan (graph-sync/full-rebuild side only,
  via `test_graph_sync_is_idempotent_full_rebuild`). **Superseded by 05-02:** GVER-03 is now
  fully satisfied — 05-02 added `test_node_resolution_is_idempotent_across_entity_types` and
  `test_audit_firm_seed_is_idempotent`, covering the node/relationship-derivation side for all
  6 entity types. REQUIREMENTS.md marks GVER-03 Complete as of 05-02.

- 05-01: `uv sync`/`uv run` for `tests/mdm/*` requires the `mdm` extra (for `sqlalchemy` via
  `tests/mdm/conftest.py`), not just `s3`+`snowflake` — future 05-03 plan verify commands
  should include `--extra mdm`.

- 05-02: `MdmEntity` has no `is_active` column (unlike `MdmRelationshipInstance`/
  `MdmRelationshipType`/`MdmEntityTypeDefinition`) — `is_quarantined.is_(False)` is the correct
  "live entity" filter for node-count idempotency assertions, since resolvers upsert-by-identity
  rather than soft-delete.

- 05-02: Real-session tests that exercise `MDMPipeline.run_companies`/`run_advisers`/etc. must
  independently seed `MdmSourcePriority` (`entity_type='all'`) rows — `MDMRuleEngine.load()`
  raises `KeyError` without them, and the shared `_seed_registry()` fixture in
  `tests/mdm/test_pipeline_relationships.py` does not provide them (no prior test in that file
  exercised node resolution against a real session).

### Blockers

- Phase 6 EDGE-10 (AUDITED_BY) is blocked on a fundamentals entity-facts run landing in the
  unified `silver/sec/silver.duckdb` — external dependency on `fundamental-factors-v2` timing.

### Roadmap Evolution

None yet — roadmap just created.

### Pending Todos

None yet.

---

## Archived: v1.0 Pipeline Observability (complete 2026-05-16)

Full archive: `milestones/v1.0-ROADMAP.md`, `milestones/v1.0-REQUIREMENTS.md`,
`milestones/v1.0-phases/`.

All 4 phases shipped: Failure Surfacing, Status Completeness, Failure Notifications, SEC Rate
Limiting. Pipeline failures surface as hard Step Functions FAILED states, `status.sh` covers all
5 state machines, operators receive SNS email within 60 seconds of failure, SEC EDGAR calls are
rate-limited to 9 req/sec per ECS task. One known low-severity residual gap: the live-behavior
test script for OBS-01 (`scripts/ops/test-failure-surfacing.sh`) has its own injection-mechanism
race condition — definition-level verification is complete, runtime re-test tooling was never
redesigned.

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 05 P02 | 25min | 2 tasks | 1 files |

## Decisions

- [Phase ?]: 05-02: MdmEntity has no is_active column -- is_quarantined.is_(False) is the correct 'live entity' filter for node-idempotency count assertions (resolvers upsert-by-identity, not soft-delete).
- [Phase ?]: 05-02: GVER-03 is now fully satisfied -- both node/relationship-derivation idempotency (this plan) and graph-sync/full-rebuild idempotency (05-01) have committed real-DB regression tests.
