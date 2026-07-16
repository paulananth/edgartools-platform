---
phase: 07
plan: 07
task: 3
verification_status: PENDING_HUMAN_APPROVAL
---

# Phase 7 Verification Ledger

**Overall status: `pending`, not `passed`.** Per `07-07-PLAN.md`'s own verification
clause: "Verification status is `passed` only after human approval of Task 2." Task 2
(`07-DEV-REHEARSAL.md`) has not been run yet — it is a `checkpoint:human-verify` step
that requires a human operator with real AWS-dev/Snowflake-dev access, and this ledger
is not entitled to mark itself `passed` on its own authority. This document records
what automated evidence exists today (all of it real and passing) and exactly what
live evidence is still outstanding.

## Requirement ledger

| ID | Automated evidence | Live evidence | Status |
|----|---------------------|----------------|--------|
| EDGE-07 | `edgar_warehouse/mdm/coverage.py:compute_edge07_manages_fund_coverage`; unit tests (07-02) | Live `coverage-report` stage not yet run | `Complete` (excluded classification is evidence-based, not a live-graph claim — see 07-02-SUMMARY.md) |
| EDGE-08 | `edgar_warehouse/mdm/coverage.py:compute_edge08_has_parent_company_coverage`; unit tests (07-02) | Live `coverage-report` stage not yet run | `Complete` (same basis as EDGE-07) |
| ARTF-01 | `edgar_warehouse/silver_protection.py` + `tests/application/test_warehouse_orchestrator_mdm.py` (07-06); `uv run pytest tests/application/test_warehouse_orchestrator_mdm.py` passes | N/A — silver publication is proven at the unit/integration layer per `07-VALIDATION.md`'s test-layer table, not a live-dev-only scenario | `Complete` (07-06) |
| ARTF-02 | `tests/unit/test_loader_idempotency.py` (07-06); `uv run pytest tests/unit/test_loader_idempotency.py` passes | N/A, same basis as ARTF-01 | `Complete` (07-06, CLI `--operator`/`--reason` flag wiring caveated — see REQUIREMENTS.md) |
| RPRE-01 | N/A (this requirement *is* a live-dev preflight) | Verified GO 2026-07-12, human-approved (07-00) | `Complete` |
| RSYNC-01 | `edgar_warehouse/mdm/publication.py` (07-03), `snowflake_graph.py` activation (07-05) | Live `plan`→`graph-activate` chain not yet run | `Partial` (unchanged by this plan — MDM serving reads are not generation-pinned; architectural, not rehearsal-closeable) |
| RSYNC-02 | `_render_exact_node_parity`/`_render_exact_relationship_parity`/`_render_missing_edge_endpoints` (07-05) | Live `verify-graph`/`hosted-e2e` stages not yet run | `Complete` (07-05, coverage-manifest CLI-default wiring caveated) |
| RSYNC-03 | `edgar_warehouse/mdm/publication.py::compute_publication_freshness` boundary tests (07-03) | Live `watermark` stage not yet run | `Complete` (07-03) |
| RSYNC-04 | `edgar_warehouse/mdm/generation.py` (07-04); `TestConcurrentGenerationsNotBlocked` | Live `build-partitions`/`retry-failed` stages not yet run | `Partial` (unchanged by this plan — per-partition Snowflake write and pipeline chaining deferred) |
| RSYNC-05 | `activate_graph_generation`/`rollback_graph_generation`/`cleanup_retired_generations` (07-05) | Live `graph-rollback` stage not yet run (no retained generation IDs exist yet — none has been created outside unit tests) | `Complete` (07-05) |
| RTEMP-01 | `render_graph_tables` temporal columns (07-05) | Live `hosted-e2e` stage not yet run | `Complete` (07-05) |
| RTEMP-02 | `api/routers/graph.py` `neighborhood`/`traversal` as-of-date tests (07-05) | Live `hosted-e2e` stage not yet run | `Complete` (07-05) |
| RTEMP-03 | `relationship_kind` tests (07-01) | N/A | `Complete` (07-01) |
| RTEMP-04 | `mdm_relationship_source_priority` + supersede/quarantine tests (07-01) | N/A | `Complete` (07-01) |
| RCOV-01 | `compute_relationship_coverage_manifest`/`verify_relationship_coverage_manifest` tests (07-02) | Live `coverage-report` stage not yet run | `Complete` (07-02) |
| RCOV-02 | Same as EDGE-07/EDGE-08 (07-02) | Live `coverage-report` stage not yet run | `Complete` (07-02) |
| RLINE-01 | `GRAPH_ENTITY_MERGE_LINEAGE` view + `_canonical_groups`/`_canonicalize` tests (07-05) | Live `entity-merge` stage not yet run | `Complete` (07-05) |

No row above is marked complete on the strength of live evidence that doesn't exist yet —
every `Complete` verdict rests on the automated evidence column, matching what
`REQUIREMENTS.md`'s existing traceability table already states (unchanged by this plan).
This ledger's only new contribution is: (a) the repeatable rehearsal tool
(`scripts/ops/verify-relationship-generations.sh` + its hermetic integration test) that
Task 2 will use, and (b) an explicit statement that the live-dev column is `pending` for
every scenario Task 2 covers, not silently assumed passing.

## Residual risks

- **RSYNC-01, RSYNC-04 remain architecturally partial.** No live rehearsal outcome
  changes this — they require additional implementation work (MDM serving-read
  generation-pinning; per-partition Snowflake row write plus `generation_build` chaining
  into `load_history`/`bootstrap`/`daily_incremental`), tracked as follow-up, not phase-blocking
  per the existing `REQUIREMENTS.md` entries.
- **ARTF-02's `--operator`/`--reason` CLI wiring gap** (documented in 07-06-SUMMARY.md)
  is unchanged by this plan.
- **RSYNC-02's coverage-manifest CLI-default wiring gap** (the live `mdm verify-graph`
  invocation does not yet default to passing an explicit coverage manifest) is unchanged
  by this plan.
- **Pre-existing, unrelated test failure discovered while running this plan's own verify
  command** (`uv run pytest tests/mdm tests/application tests/unit tests/architecture
  tests/integration/test_relationship_generation_e2e.py`):
  `tests/architecture/test_load_history_state_machine.py::test_total_cik_limit_check_defaults_to_no_limit_sentinel`
  fails (`expected Next == "ComputeWindows", got "ArtifactPolicyCheck"`). Confirmed via
  `git stash` that this fails identically on the pre-07-07 base commit (`571e691`) —
  it predates this plan and is unrelated to any file this plan touches. Root cause: the
  `ArtifactPolicyCheck`/`ArtifactPolicyDefault` states (CLAUDE.md's artifact-throttle
  5-whys mitigation #2, `deploy-aws-application.sh`) were inserted between
  `TotalCikLimitCheck` and `ComputeWindows`, but this specific architecture test's
  `Next` assertion was never updated to expect the new intermediate state. Out of
  07-07's declared file scope (`deploy-aws-application.sh` is not in `files_modified`);
  left unfixed here and flagged for a separate follow-up rather than silently
  re-excluding the file or fixing it under this plan's authority.

## Retained generation IDs

None yet. No generation has been created outside unit-test fixtures — Task 2 has not
run. Once it runs, the operator must record every `generation_id` produced by the
`plan`/`sync-graph`/`graph-activate` stages here, plus which one ends up retained as the
rollback target, by appending to this section (do not overwrite this line — append below it).

## Exact rollback command

```bash
SNOW_CONNECTION=snowconn bash scripts/ops/verify-relationship-generations.sh \
  --stage graph-rollback \
  --rollback-to-generation-id <retained verified+activated generation_id> \
  --snowflake-database EDGARTOOLS_DEV
```

This is the same command path the live rehearsal (Task 2) will exercise for scenario
#12 in `07-DEV-REHEARSAL.md`; it is not a new mechanism invented for this ledger — it
shells out to the existing `mdm graph-rollback` CLI command from 07-05.

## Phase exit gate

Phase 7 may be marked `passed` only when:
1. `07-DEV-REHEARSAL.md`'s scenario ledger has no `PENDING` rows, and
2. Its Sign-off section has a human reviewer, date, and `approved` verdict.

Until then this document's `verification_status` remains `PENDING_HUMAN_APPROVAL`.
