# 02 — Wire the identical AdvBulkFetch Stage into `daily_incremental`

**What to build:** The same Stage shape as ticket 01 (`FetchAdvBulk` +
`IngestAdvBulkSources`, `ForceCheck`/`DatasetPeriodCheck`/`DatasetPeriodDefault`, lenient
`Catch` to `MdmRun`), inserted into `daily_incremental`'s branch of
`write_warehouse_mdm_gold_definition` (same file), after `RunWarehouseTask` and before
`MdmRun`. This is a separate Python heredoc from `write_load_history_definition` with no
shared helper — the same "keep in sync" duplication `Stage0CompanyIdentity` already
established as this file's convention for a shape that must exist identically in both
state machines. `daily_incremental`'s existing daily cron schedule
(`cron(0 12 * * ? *)`) needs no changes — `fetch-adv-bulk`'s own local-check-first logic
already makes the ~29 no-op days/month cheap.

**Blocked by:** None — independent Python heredoc from ticket 01; can start immediately
and in parallel.

Status: superseded by the rebuild (2026-10-13 17:31 ET): the pipeline it changes (daily_incremental) was retired (platform validation 2a/2b, #764 and #766; the DuckDB silver store, silver-merge-engine-migration 17); the configured platform (Rules, Bookkeeping, Change Journal, Clean MDM) replaces it. Reopen as a new ticket if the need still applies

- [x] The generated `daily_incremental` JSON has the same new stage running after
      `RunWarehouseTask` and before `MdmRun`.
- [x] Same command-shape, Choice-branching, manifest-path, and Catch behavior as ticket
      01's acceptance criteria, verified against `daily_incremental`'s generated JSON.
- [x] `bootstrap`'s generated JSON (which shares `write_warehouse_mdm_gold_definition`
      but is a separate `workflow_name` branch) is confirmed unaffected by this change.
- [x] New structural tests in `tests/architecture/test_daily_incremental_state_machine.py`
      cover all of the above, following the file's existing naming/assertion conventions.
- [x] All pre-existing tests in `test_daily_incremental_state_machine.py` still pass.
