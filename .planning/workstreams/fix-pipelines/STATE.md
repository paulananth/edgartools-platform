---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: fix-pipelines — Pipeline Data-Source Completeness & Verification
current_phase: 06
current_phase_name: relationship-investigation-and-population
current_plan: 4
status: executing
stopped_at: "06-04 IN PROGRESS (2026-07-12): OOM gold-stage memory fix (2->4GB) deployed to edgartools-dev AND CONFIRMED via live load-history-oomtest execution -- WindowedBootstrap (the exec #3 OOM stage) succeeded, peak 1163/4096 MiB. Also found+fixed a real regression: PR #129 never merged the memory fix to main, so CI's auto-deploy-on-push-to-main silently reverted medium task-def to 2048MB after PR #130 merged; fixed via merge origin/main -> claude/consolidate-workstreams (21796ad), verified 4096MB survives. Bonus: root-caused + fixed unrelated artifact-throttle bug found during the verification run (5,583 cached accessions x 1s unconditional sleep = ~93min dead time on re-runs) -- fix #1 (throttle only on real network fetches, bb74e37), #2 (opt-in load_history artifact_policy input, default preserves new-CIK loading), #3 (lower redundant throttle default 1.0->0.2s), all in 5b49f7c. All pushed to origin/claude/consolidate-workstreams. 06-04's actual required artifact (06-04-EDGE09-EDGE11-DISPOSITION.md, disposing EMPLOYED_BY/INSTITUTIONAL_HOLDS) not yet started -- only skip-vs-miss investigation groundwork (3df6fe4) exists. Next: resume 06-04 Task 1 (EDGE-09) using the now-reliable/fast load_history."
last_updated: "2026-07-12"
last_activity: 2026-07-12
last_activity_desc: "Deployed+verified OOM memory fix live on edgartools-dev; found and fixed a CI-deploy-revert regression (main was missing the fix); root-caused and fixed an unrelated artifact-throttle bug (3 fixes) discovered during verification. All committed and pushed to claude/consolidate-workstreams. Phase 6's actual EDGE-09/EDGE-11 disposition work (06-04) still ahead."
consolidation:
  date: "2026-07-11"
  note: "This is now the single active workstream. Grafted: Phase 10 <- fundamental-factors-v2 P3; Phases 11-15 <- model-builder-contract-gaps P1-6. Sources tombstoned. Excluded (complete): go-live, mdm-neo4j-dashboard, neo4j-snowflake, neo4j-pipe."
progress:
  total_phases: 11
  completed_phases: 1
  native_fix_pipelines_phases: "5-9 (5 done, 6 paused, 7-9 unbuilt)"
  grafted_phases: "10 (planned), 11-13 (unplanned), 14-15 (charter-held)"
  percent: 9
---

# Project State — fix-pipelines

## Current Position

Phase: 06 (relationship-investigation-and-population) — EXECUTING
Plan: 3 of 6
Status: Ready to execute
Last activity: 2026-07-08 — Phase 06 execution started

[██░░░░░░░░] 20% (1/5 phases complete; phase 6 planned, 0/6 plans executed)

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
| 5 — Node And Populated-Relationship Graph Parity | All 6 node types + 4 populated relationship types verified, idempotency established | NODE-01..06, EDGE-01..04, GVER-03 | Complete |
| 6 — Relationship Investigation And Population | Root-cause + populate the 5 ambiguous zero relationship types against their actual artifacts | EDGE-05, 06, 09, 10, 11 | Planned (6 plans, 4 waves) |
| 7 — Source-Coverage Exclusions And Artifact Hygiene | Document the 2 artifact-confirmed exclusions; fix silver-clobber + fetch-idempotency | EDGE-07, 08, ARTF-01, 02 | Not started |
| 8 — Neo4j Native App Verification Gaps | verify-graph separates readiness vs parity; GRAPH_INFO/BFS/LIST_GRAPHS resolved or documented | GVER-01, 02 | Not started |
| 9 — edgartools Crosscheck | Validate platform parsing vs edgartools; replace parsers where it's a clear win; audit API usage | EDGX-01..03 | Not started |

## Progress

**Phases Complete:** 1/5
**Current Plan:** 1

## Session Continuity

**Last session:** 2026-07-12 (this session)

**Stopped At:** 06-04 in progress. This session: deployed the 06-03 OOM memory fix (medium
task 2GB→4GB) to edgartools-dev and confirmed it live via `load-history-oomtest-1783868231` —
`WindowedBootstrap` (the exact stage that OOM-killed exec #3) succeeded, peak 1163/4096 MiB.
Along the way, found that PR #129 never merged the memory fix into `main`, so CI's
push-to-main auto-deploy had silently reverted the medium task def back to 2048MB after PR
#130 merged — fixed by merging `origin/main` into `claude/consolidate-workstreams` (`21796ad`),
confirmed 4096MB survives post-merge. Also root-caused and fixed an unrelated artifact-throttle
bug surfaced by the verification run (per-accession 1s sleep firing even on cache hits — 5,583
cached accessions × 1s ≈ 93 min dead time on re-runs): fix #1 (throttle only on real network
fetches), #2 (opt-in `artifact_policy` SM input for `load_history`, default preserves new-CIK
artifact capture), #3 (lower redundant throttle default 1.0→0.2s). All committed (`bb74e37`,
`365190e`, `21796ad`, `5b49f7c`) and pushed to `origin/claude/consolidate-workstreams`.
06-04's actual required artifact (`06-04-EDGE09-EDGE11-DISPOSITION.md`) has not been started —
only skip-vs-miss investigation groundwork exists (`3df6fe4`). A PR from
`claude/consolidate-workstreams` → `main` is still needed to land these fixes where CI reads
from, or the next `main` deploy will revert the memory bump again.

**Resume File:** None — proceed directly to 06-04 Task 1 (EDGE-09 EMPLOYED_BY disposition)
using `06-04-PLAN.md`. Wave 2 (06-03, complete) and one plan in Wave 3 (06-05) each have a
blocking human-verify checkpoint (fundamentals/Codex coordination for 06-05).

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

- **`main` is missing this branch's OOM memory fix + artifact-throttle fixes** (2026-07-12).
  PR #129 only merged the earlier consolidation commit into `main`, not the later work on the
  same branch. CI auto-deploys from `main` on every push, so any future `main`-triggered deploy
  will silently re-revert the medium task def's memory 4096→2048 until a new PR lands
  `claude/consolidate-workstreams` (currently at `5b49f7c`) into `main`. Not blocking 06-04
  execution (dev is currently correct after the manual merge+redeploy), but must be resolved
  before this branch's work is considered durably shipped.

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
| Phase 05 P03 | 25min | 2 tasks | 2 files |
| Phase 06 P01 | 25min | 2 tasks | 2 files |
| Phase 06 P02 | 16min | 2 tasks | 1 files |

## Decisions

- [Phase ?]: 05-02: MdmEntity has no is_active column -- is_quarantined.is_(False) is the correct 'live entity' filter for node-idempotency count assertions (resolvers upsert-by-identity, not soft-delete).
- [Phase ?]: 05-02: GVER-03 is now fully satisfied -- both node/relationship-derivation idempotency (this plan) and graph-sync/full-rebuild idempotency (05-01) have committed real-DB regression tests.
- [Phase ?]: 05-03: Named per-type parity checks in verify-graph fail closed when a type is entirely absent from parity rows, closing the FULL-OUTER-JOIN silent-omission gap -- POPULATED_RELATIONSHIP_TYPES scopes edge checks to only the 4 already-populated types (COMPANY_HOLDS, HOLDS, ISSUED_BY, IS_INSIDER).
- [Phase ?]: 05-03: Phase 5 is now fully complete -- NODE-01..06, EDGE-01..04, and GVER-03 (05-01/05-02) all satisfied.
- [Phase 06]: CIK-range bounds are always passed as bound params (fetch(sql, params=[lo, hi])), never interpolated into the SQL string -- directly enforced by a test assertion (T-06-01).
- [Phase 06]: 06-01: batch-equivalence tests must compare edges by (adviser CIK, security CUSIP), not raw entity_id -- entity_ids are freshly-generated UUIDs per independent test session and never match across separate single-batch/multi-batch sessions.
- [Phase ?]: 06-02: Root cause of the 2026-07-06 bootstrap failure is an external/operational timing gap (non-atomic go-live.sh Postgres-provision -> secret-bootstrap sequencing), not a code/config bug -- already self-resolved by an operator secret rotation on 2026-07-06T12:30:44 ET.
- [Phase ?]: 06-02: load_history readiness verdict is GO, with pre-flight condition 1 (mdm-check-connectivity) satisfied live during this investigation (preflight-06-02-1783525375, SUCCEEDED) rather than deferred to 06-03.
