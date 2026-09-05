# 04 — Step Functions wiring for the three fundamentals modes

Type: task
Status: open

**Blocked by:** 01 (retirement fix), 02 (accession-level scoping), 03
(entity-facts refresh trigger) — needs all three ready so the new states
don't ship an unbounded, unscoped, or crash-unsafe full re-parse.

## What to build

In `write_warehouse_mdm_gold_definition()`
(`infra/scripts/deploy-aws-application.sh`), add three new ECS states
after `CaptureAndVerifyNewFilings` and before `ReleaseSecFetchLease`
(entity-facts needs the still-held `sec_fetch_active` lease for its SEC
calls; per-filing/thirteenf make no network calls but should run in the
same window for ordering simplicity) — all three before `RunMdmChain`, so
MDM entity resolution sees complete data, matching `load_history`'s own
Stage-1B-before-Stage-2 ordering rationale.

Each new state: `bootstrap-fundamentals --mode <mode> --run-id
$$.Execution.Name`, no `--cik-list`/window needed as a windowed Map —
Tickets 02/03's incremental scoping should keep the daily working set
small enough that a single ECS task invocation per mode suffices (unlike
`load_history`'s full-universe bootstrap, which needs CIK-windowed Map
fan-out). Task profile: `wh_large_arn`, matching `load_history`'s own
OOM-driven choice for the identical `merge_candidate_into_canonical` risk.
Follow the established AD-13 pattern for these exact three modes (`Catch`
routing to the next stage on any failure, non-fatal, matching
`load_history`'s own `stage1b_entity_facts_catch`/`stage1b_per_filing_catch`/
`stage1b_thirteenf_catch`) rather than a hard abort.

**Verify** the Step Functions comment block at the top of
`write_warehouse_mdm_gold_definition()` and this file's own
`daily_identity_refresh` sibling machine to make sure only
`daily_incremental`'s branch gains these states — same "keep in sync but
verify no bleed" discipline this file already documents for
`Stage0CompanyIdentity`/`FetchAdvBulk` insertions.

## Tests

Primary seam: `tests/architecture/test_daily_incremental_state_machine.py`
(the same generated-JSON structural harness already used for the
`FetchAdvBulk`/`Stage0CompanyIdentity` insertions) — assert the three new
states run after `CaptureAndVerifyNewFilings` and before
`ReleaseSecFetchLease`/`RunMdmChain`, on `wh_large_arn`, with `Catch`
routing to the next stage, and that `bootstrap`'s/`daily_identity_refresh`'s
generated JSON is unaffected.

## Acceptance

- [ ] Generated `daily_incremental` JSON has all three new states correctly
      placed, task-profiled, and Catch-wired.
- [ ] `bootstrap`/`daily_identity_refresh`'s generated JSON confirmed
      unaffected by this change.
- [ ] New structural tests pass; all pre-existing tests in
      `test_daily_incremental_state_machine.py` still pass.
- [ ] `/gof-refactor-reviewer` consulted before editing
      `deploy-aws-application.sh` (repo hard rule).
- [ ] `/code-review` (Standards, Spec, GoF) run before this ticket's PR is
      considered ready.
