# 16 — Retire the two remaining local-store couplings (decisions, not edits)

**Type:** grilling

**Status:** open

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
