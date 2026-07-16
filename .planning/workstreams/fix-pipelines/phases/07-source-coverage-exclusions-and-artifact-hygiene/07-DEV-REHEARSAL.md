---
phase: 07
plan: 07
task: 2
status: PENDING_HUMAN_EXECUTION
---

# 07-07 Task 2: Bounded Dev Rehearsal — Evidence Template

**This rehearsal has not been run yet.** Task 2 is a `checkpoint:human-verify` step
(`autonomous: false` in `07-07-PLAN.md`) that requires a human operator with real
AWS-dev (`sec_platform_deployer` profile) and Snowflake-dev (`SNOW_CONNECTION=snowconn`)
access. An assistant cannot run this: it mutates live dev MDM/graph state, and the
plan's own `<verify>` clause requires "Human reviews evidence and types `approved`."

This document is the fill-in-the-blank evidence ledger the operator completes while
running the rehearsal. Every PASS/FAIL cell below is currently `PENDING`.

## Precondition (must be checked before running anything)

- [ ] Confirm no overlapping runtime owns the dev graph/silver surface: no other Claude/Codex
      session or Step Functions execution (`load_history`, `bootstrap`, `daily_incremental`,
      `mdm_*`, `generation_build`) is active against `EDGARTOOLS_DEV` / dev Postgres MDM /
      the dev S3 warehouse right now. `scripts/ops/verify-relationship-generations.sh`'s
      `preflight` stage checks `edgartools-dev-load-history` specifically; the operator must
      separately confirm no MDM/graph/generation-build execution is running, since the
      script does not check those state machines.

## How to run

```bash
export SNOW_CONNECTION=snowconn
bash scripts/ops/verify-relationship-generations.sh --all \
  --aws-profile sec_platform_deployer \
  --entity-merge-keep <real dev entity_id to keep> \
  --entity-merge-discard <real dev entity_id to discard> \
  --rollback-to-generation-id <a prior verified+activated generation_id, once one exists>
```

Run `--stage <name>` individually to retry a single stage (see `--help` for the full
list). Evidence accumulates as JSONL under `./evidence/relationship-generations/<run-id>/`.

## Scenario ledger

Scenarios already proven by the unit/integration suites (07-01..07-06) are cited, not
re-run live, per `07-VALIDATION.md`'s test-layer table ("Live dev" row scope is the
generation/graph pipeline specifically).

| # | Scenario (from 07-CONTEXT.md required phase-exit evidence) | Proof mechanism | Result | Evidence ref |
|---|---|---|---|---|
| 1 | Partial silver candidate merges without losing canonical business keys | Unit: `tests/application/test_warehouse_orchestrator_mdm.py::test_merge_preserves_canonical_only_rows_from_a_partial_candidate` | PASS (automated, 07-06) | 07-06-SUMMARY.md |
| 2 | Ambiguous same-key row conflict aborts with a report | Unit: `test_merge_raises_row_level_conflict_report_when_ambiguous` | PASS (automated, 07-06) | 07-06-SUMMARY.md |
| 3 | Simulated concurrent canonical update prevents promotion | Unit: `test_promote_staged_raises_on_*` (object_storage ETag conflict) | PASS (automated, 07-06) | 07-06-SUMMARY.md |
| 4 | Cached bronze artifacts cause zero SEC network calls | Unit: `tests/unit/test_loader_idempotency.py` (DEF 14A, 13F-HR, ownership cache-hit tests) | PASS (automated, 07-06) | 07-06-SUMMARY.md |
| 5 | EDGE-07 reports `source_unavailable` without synthetic graph edges | Unit: `compute_edge07_manages_fund_coverage` tests (07-02) | PASS (automated, 07-02) | 07-02-SUMMARY.md |
| 6 | EDGE-08 reports `capability_not_implemented` without synthetic graph edges | Unit: `compute_edge08_has_parent_company_coverage` tests (07-02) | PASS (automated, 07-02) | 07-02-SUMMARY.md |
| 7 | A deliberately stale exclusion fails verification and prevents activation | Unit: coverage manifest staleness tests (07-02) | PASS (automated, 07-02) | 07-02-SUMMARY.md |
| 8 | MDM and Neo4j match by stable node/edge identities and query-relevant properties for the active generation | **Live**: `--stage verify-graph` / `--stage hosted-e2e` | PENDING | _fill in EVIDENCE_FILE path_ |
| 9 | Temporal direct and multi-hop queries respect `[valid_from_date, valid_to_date)` and strict unknown-date behavior | **Live**: `--stage hosted-e2e`, plus manual `api/routers/graph.py` traversal calls with/without `include_unknown_dates` | PENDING | _fill in_ |
| 10 | Entity merges preserve source lineage while restoring canonical graph connectivity | **Live**: `--stage entity-merge` (requires two real dev entity IDs), then re-query traversal through both old IDs | PENDING | _fill in_ |
| 11 | A failed partition retries without rebuilding unchanged content-addressed partitions | **Live**: `--stage build-partitions` with one partition's input deliberately broken, then `--stage retry-failed`; confirm unchanged partitions report `reused`, not rebuilt | PENDING | _fill in_ |
| 12 | A failed generation leaves the prior verified generation active; rollback succeeds within the retention window | **Live**: `--stage graph-rollback --rollback-to-generation-id <prior>`; confirm MDM serving + Neo4j views both switch together and the failed generation's pointer was never written | PENDING | _fill in_ |
| 13 | Complete staged generation lifecycle (plan → build → fan-in → activate → sync → verify → graph-activate) | **Live**: `--all` run, stages `plan` through `graph-activate` | PENDING | _fill in_ |
| 14 | Publication freshness/alert state (5-minute warn / 15-minute hard alert) observed on real dev watermark | **Live**: `--stage watermark` | PENDING | _fill in_ |
| 15 | EDGE-07/EDGE-08 coverage categories present in a real generation's coverage report | **Live**: `--stage coverage-report` | PENDING | _fill in_ |
| 16 | A failed generation never changes the active pointer (mechanical proof: `--all` halts on first stage failure, no later stage in `STAGE_ORDER` ever runs) | Hermetic integration test: `tests/integration/test_relationship_generation_e2e.py::test_failed_stage_halts_all_and_never_reaches_activation` (proves the halt mechanic); **live** confirmation still needed that the real Snowflake pointer was untouched after an injected failure | PASS (mechanic, automated) / PENDING (live pointer confirmation) | test file above |

## Residual/architectural gaps this rehearsal cannot close

These are documented in `REQUIREMENTS.md` as `Partial` and are out of scope for this
rehearsal — a live run proves the mechanisms that exist, it does not change what was built:

- **RSYNC-01** (partial): MDM's own serving reads (`api/routers/graph.py`) are not pinned
  to a generation concept; they read live/current Postgres state. This is architecturally
  intentional per 07-05's design, not a rehearsal-provable gap.
- **RSYNC-04** (partial): the per-partition Snowflake row write and chaining
  `generation_build` into `load_history`/`bootstrap`/`daily_incremental` remain future work.

## Sign-off

- **Reviewer**: _pending_
- **Date**: _pending_
- **Verdict**: _pending_ (`approved` / `rejected` — required before `07-VERIFICATION.md` may be marked `passed`)
