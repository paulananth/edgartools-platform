---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: fix-pipelines — Pipeline Data-Source Completeness & Verification
current_phase: 07
current_phase_name: source-coverage-exclusions-and-artifact-hygiene
current_plan: 0
status: phase_6_complete_phase_7_not_started
stopped_at: "Phase 6 (relationship-investigation-and-population) COMPLETE (2026-07-13): all 6 plans (06-01..06-06) executed, each with a SUMMARY.md. 06-06 closed the phase: EDGE-05/EDGE-06 disposed as source-coverage exclusions (D-04 SQL zero-overlap, d375964); EDGE-09's 06-04 'open item' resolved -- root cause found and shared with EDGE-11 (_is_configured_parser_form gates the bulk artifact-fetch pipeline to ownership/ADV forms only, so DEF14A/8-K/13F-HR never get sec_filing_attachment populated at scale; confirmed via live Step Functions execution history + CloudWatch logs + platform-wide silver queries, 2cd0156); EDGE-11's disposition corrected (fix committed but unreachable via bulk pipeline without the same upstream gate fix); EDGE-10 remains excluded (structural SEC companyfacts API limitation). POPULATED_RELATIONSHIP_TYPES correctly left unchanged (no type reached graph-verified-populated status this phase). 06-PHASE-CLOSURE-LEDGER.md records all 5 EDGE IDs in exactly one evidenced disposition (introducing a third 'ROOT-CAUSED / FIX DEFERRED' category for EDGE-09/EDGE-11 alongside POPULATED/EXCLUDED); REQUIREMENTS.md reconciled (removed premature Complete status on EDGE-09/EDGE-11). 3 commits (d375964, 2cd0156, 0aa65ba) ahead of origin/claude/consolidate-workstreams, NOT YET PUSHED. A deferred, concrete next step (not this phase's scope): widen _is_configured_parser_form to cover 8-K/DEF14A/13F-HR, then deploy+re-fetch+re-derive+sync+graph-count EDGE-09/EDGE-11. Phase 7 (EDGE-07/08, ARTF-01/02) not yet started."
last_updated: "2026-07-13"
last_activity: 2026-07-13
last_activity_desc: "Closed out Phase 6 end-to-end: ran 06-06's 3 tasks inline (no subagents, per explicit user instruction), plus resolved EDGE-09's previously-open root cause using live dev AWS access unavailable to earlier worktree executors. Wrote the phase closure ledger and reconciled REQUIREMENTS.md. Phase 6 is now fully complete; Phase 7 has not been started."
consolidation:
  date: "2026-07-11"
  note: "This is now the single active workstream. Grafted: Phase 10 <- fundamental-factors-v2 P3; Phases 11-15 <- model-builder-contract-gaps P1-6. Sources tombstoned. Excluded (complete): go-live, mdm-neo4j-dashboard, neo4j-snowflake, neo4j-pipe."
progress:
  total_phases: 11
  completed_phases: 2
  native_fix_pipelines_phases: "5-9 (5 done, 6 done, 7-9 unbuilt)"
  grafted_phases: "10 (planned), 11-13 (unplanned), 14-15 (charter-held)"
  percent: 18
---

# Project State — fix-pipelines

## Current Position

Phase: 06 (relationship-investigation-and-population) — COMPLETE
Phase: 07 (source-coverage-exclusions-and-artifact-hygiene) — NOT STARTED
Last activity: 2026-07-13 — Phase 06 closed out (06-06, all 3 tasks + EDGE-09 root-cause follow-up)

[████░░░░░░] 40% (2/5 native phases complete; phase 7 not started)

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
| 6 — Relationship Investigation And Population | Root-cause + populate the 5 ambiguous zero relationship types against their actual artifacts | EDGE-05, 06, 09, 10, 11 | Complete (all 6 plans; see 06-PHASE-CLOSURE-LEDGER.md — 2 populated-path exclusions, 1 structural exclusion, 2 root-caused/fix-deferred, 0 undocumented) |
| 7 — Source-Coverage Exclusions And Artifact Hygiene | Document the 2 artifact-confirmed exclusions; fix silver-clobber + fetch-idempotency | EDGE-07, 08, ARTF-01, 02 | Not started |
| 8 — Neo4j Native App Verification Gaps | verify-graph separates readiness vs parity; GRAPH_INFO/BFS/LIST_GRAPHS resolved or documented | GVER-01, 02 | Not started |
| 9 — edgartools Crosscheck | Validate platform parsing vs edgartools; replace parsers where it's a clear win; audit API usage | EDGX-01..03 | Not started |

## Progress

**Phases Complete:** 2/5 (5, 6)
**Current Plan:** Phase 7 not yet planned

## Session Continuity

**Last session:** 2026-07-13 (this session)

**Stopped At:** Phase 6 fully complete. This session executed 06-06 inline (no subagents, per
explicit user instruction) and, along the way, resolved EDGE-09's previously-open root cause
using live dev AWS access that 06-04's worktree executors lacked:

- **06-06 Task 1** (from a prior session, `d375964`): EDGE-05/EDGE-06 disposed as source-coverage
  exclusions via a live D-04 SQL zero-overlap check against dev MDM Postgres.
- **EDGE-09 root cause found** (`2cd0156`): re-tested `parse_proxy_fundamentals` against the real
  bronze-captured Apple DEF14A bytes (5 rows, correct) — ruling out a parser bug. Traced via live
  Step Functions execution history + CloudWatch logs (`load-history-oomtest-1783868231`) that
  `Stage1BPerFiling` silently skips 100% of candidate filings (1822/1822, no errors). Root cause:
  `_is_configured_parser_form` (`warehouse_orchestrator.py:1859-1861`) gates the bulk
  artifact-fetch pipeline to `OWNERSHIP_FORMS`/`ADV_FORMS` only — DEF14A/DEFA14A/8-K/13F-HR are
  never selected for attachment fetch platform-wide (confirmed via live silver queries: 8-K
  104/266,634, DEF14A-family 23/52,200, 13F-HR 0/48,877).
- **EDGE-11 disposition corrected** (`2cd0156`): its already-committed bronze-fetch fast-path fix
  shares the same root cause — it's downstream of the gate above and unreachable via the standard
  bulk pipeline (confirmed: `refresh_filing_artifacts` has exactly 2 callers, and the gated one
  excludes 13F-HR entirely). Fix is real but not sufficient alone.
- **06-06 Task 2** (`0aa65ba`): confirmed `POPULATED_RELATIONSHIP_TYPES` correctly stays
  unchanged this phase (no type reached graph-verified-populated status); updated the docstring
  comment; re-verified `tests/mdm/test_cli_snowflake_graph.py` (18 tests) still passes.
- **06-06 Task 3** (`0aa65ba`): wrote `06-PHASE-CLOSURE-LEDGER.md` covering all 5 EDGE IDs, each
  in exactly one evidenced disposition (introducing a third "ROOT-CAUSED / FIX DEFERRED"
  category for EDGE-09/EDGE-11 alongside POPULATED/EXCLUDED, per advisor guidance, since neither
  is a true source-coverage exclusion). Reconciled `REQUIREMENTS.md` (removed premature
  `[x] Complete` on EDGE-09/EDGE-11, which had been set during the 2026-07-11 consolidation
  commit before this phase's plans had actually run).

3 commits (`d375964`, `2cd0156`, `0aa65ba`) are ahead of `origin/claude/consolidate-workstreams`
and **not yet pushed**.

**Resume File:** None — Phase 6 is closure-complete. Next work is planning Phase 7
(source-coverage-exclusions-and-artifact-hygiene: EDGE-07, EDGE-08, ARTF-01, ARTF-02) via
`/gsd-plan-phase 7`, or landing a PR from `claude/consolidate-workstreams` → `main` (see
Blockers — still outstanding from an earlier session, unrelated to Phase 6's own scope).

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
