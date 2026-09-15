# 16 — Retire the two remaining local-store couplings (decisions, not edits)

**Type:** grilling

**Status:** resolved 2026-09-14 (operator decisions; the deletions are wired into Ticket 15).

## Question

Two production paths still depend on the local DuckDB file existing, and each needs an operator
decision rather than a mechanical deletion:

1. **`compute-windows` uploads the local file as the identity-refresh reference snapshot.**
   `_execute_warehouse_bronze_capture` passes `Path(context.silver_root.join("silver", "sec",
   "silver.duckdb"))` to `persist_run_manifest` as `reference_snapshot_file`
   (`warehouse_orchestrator.py:831`); `persist_run_manifest` raises "identity refresh reference
   snapshot is missing" when the file is absent, and the manifest consumer only reads the
   snapshot's `sha256` and `path`. Once the opener stops creating a file, every `compute-windows`
   run fails closed. Options: a hash of the reference rows landed this run; drop the field and
   the check. First confirm which root backs that path (`WAREHOUSE_STORAGE_ROOT` is an `s3://`
   URI) — i.e. whether the field ever described a real local artifact. Must land in or before the
   slice that removes the file-backed opener (Ticket 17).
2. **`parse-ownership-bronze` is a prod no-op.** `_run_parse_ownership_bronze`'s first read,
   `db.fetch("SELECT ... FROM sec_company_filing ...")`, hits the local store, which Ticket 10
   stopped hydrating — so the filings list is empty in prod, not just the `already_parsed` set its
   comment flags. Same shape as release mode (Ticket 11) and `parse-adv-bronze` (Ticket 07): retire
   the CLI command, or repoint it at Snowflake silver. It is not in any state machine; check
   Step Functions history / the real warehouse log group for any recent operator use before
   putting the choice to the operator.

**Blocked by:** none — frontier (can run in parallel with Ticket 13).

## Answer (2026-09-14, operator decisions)

**Facts found first:**
- `silver_root` resolves to `/tmp/edgar-warehouse-silver` whenever `WAREHOUSE_STORAGE_ROOT` is an
  `s3://` URI (`warehouse_settings.py`), so the "reference snapshot" is the local DuckDB file the
  opener creates fresh each run — an empty-schema store since Ticket 10 stopped hydration. The last
  three uploads (`daily-incremental-*`, 2026-09-08 and 2026-09-12 twice) are all exactly
  2,371,584 bytes. Its only reader, `reduce-identity-refresh`, was removed from every state machine
  by the stage0-stage1-consolidation map; `load_complete_run_manifest`/`validate_complete_run_manifest`
  and the `batch_*_path` helpers have zero production callers.
- `parse-ownership-bronze`: zero real runs in 90 days of `/aws/ecs/edgartools-prod-warehouse`
  (the five log hits are argparse usage text); in no state machine; its filings query reads the
  never-hydrated local store.

**Decision 1 — reference snapshot: drop it (option a).** Delete the `reference_snapshot_file`
parameter and the upload from `persist_run_manifest`, the manifest's `reference_snapshot` field and
its `_valid_sha256` check, `reference_snapshot_path`, and the dead `reduce-identity-refresh` command
with `load_complete_run_manifest`/`validate_complete_run_manifest`/`batch_*_path`/`batch_id_for_ciks`.
`compute-windows`' `silver_publish_completed` event loses its `identity_refresh_reference_snapshot`
layer entry. Not chosen: hashing the reference rows landed this run (builds a field nobody reads).

**Decision 2 — `parse-ownership-bronze`: retire it (option a).** Delete the CLI parser and handler,
`_run_parse_ownership_bronze`, `tests/application/test_parse_ownership_bronze.py` and the parts of
`test_ownership_lookback.py` that drive it. Same shape as `parse-adv-bronze` (Ticket 07) and release
mode (Ticket 11). A bronze re-parse tool, if ever wanted, grows out of `targeted-resync` (Ticket 10),
which already reads filings from Snowflake silver. Not chosen: repointing at Snowflake silver.

Both deletions are added to [Ticket 15](15-delete-dead-duckdb-readers-and-tools.md)'s scope so they
ship in one slice with the other dead readers.
