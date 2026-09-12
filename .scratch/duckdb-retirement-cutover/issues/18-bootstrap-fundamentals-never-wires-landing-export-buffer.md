# 18 — bootstrap-fundamentals never wires a LandingExportBuffer (write side of Ticket 17's bug)

**Type:** bugfix
**Status:** ready-for-agent

## What was found

Ticket 17 fixed the *read* side of bootstrap-fundamentals's DuckDB-retirement
gap (per-filing/thirteenf/entity-facts now read Branch A metadata + prior
fundamentals output from Snowflake via `SnowflakeSilverReader`, not the
permanently-empty local `db`). Live verification of that fix surfaced a
second, independent, more severe gap on the *write* side: bootstrap-fundamentals's
own writes never reach Snowflake either, and never have since the Ticket 10
hydration-removal deploy (2026-09-07).

Live evidence: a verification run against CIK 908311 logged
`"rows_executive_record": 20` newly written, but a direct query
immediately after —

```sql
SELECT MAX(ingested_at), COUNT(*) FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_EXECUTIVE_RECORD WHERE cik = 908311
```

— returned `latest = 2026-07-22 20:42:41.485863-07:00, n = 35`, over 7 weeks
stale. This is not limited to Tickets 02/03's two new tables — it's every
table bootstrap-fundamentals writes (`sec_earnings_release`,
`sec_executive_record`, `sec_financial_fact`, `sec_accounting_flag`,
`sec_thirteenf_holding`, plus the new `sec_fundamentals_processed_accession`/
`sec_entity_facts_refresh_watermark`).

Root cause: `bootstrap_fundamentals.py` builds its own bespoke
`WarehouseCommandContext` (`_build_silver_context`) instead of going through
`command_context_factory.build_warehouse_context`, and that bespoke builder
never resolves `SILVER_LANDING_EXPORT_ROOT` into
`context.silver_landing_export_root` — so it is always `None`, a
`LandingExportBuffer` is never constructed, `open_silver_database` is never
given one, and every `merge_*`/`upsert_*`/`mark_*` write's
`landing_export.record(...)` call (the mechanism every other command uses to
get its writes into the Snowflake landing zone — see
`_execute_warehouse_bronze_capture` in `warehouse_orchestrator.py`) is a
silent no-op. Confirmed via grep: zero occurrences of `LandingExportBuffer`/
`landing_export`/`flush_landing_export` in `bootstrap_fundamentals.py`.

Confirmed the fix needs no infra change: `SILVER_LANDING_EXPORT_ROOT` is
already set as an ECS task environment variable for the warehouse profile
bootstrap-fundamentals runs under (`infra/scripts/deploy-aws-application.sh`,
same env-var block every warehouse command shares) — this is purely a
missing wire-up in `bootstrap_fundamentals.py` itself.

## What to build

- `_build_silver_context` resolves `SILVER_LANDING_EXPORT_ROOT` (same env var
  `WarehouseSettings.from_env` reads) into
  `WarehouseCommandContext.silver_landing_export_root`.
- `execute()` constructs a `LandingExportBuffer` when that root is set (same
  `LandingExportBuffer() if ... is not None else None` idiom
  `_execute_warehouse_bronze_capture` uses) and passes it to
  `open_silver_database(..., landing_export=landing_export)`.
- After all per-mode writes succeed, flush the buffer via
  `write_landing_export(...)` (same call shape as the orchestrator's), before
  the existing unconditional `db.close()`. A flush failure is treated as a
  command failure (`return 1`), matching this file's existing
  "Failed to upload silver database to remote storage" convention — silently
  discarding the buffer on a flush error would just reproduce this exact bug
  intermittently.
- Record `metrics["silver_landing_export_row_counts"]` in the success payload
  for observability, mirroring `_execute_warehouse_bronze_capture`'s
  `silver_landing_export_row_counts` field.

## Acceptance

- [ ] Unit tests confirming `LandingExportBuffer` is constructed and passed to
      `open_silver_database` when `SILVER_LANDING_EXPORT_ROOT` is set, and
      `write_landing_export` is called with the buffer before `db.close()`.
- [ ] Unit test confirming a `write_landing_export` failure returns exit code
      1 rather than silently swallowing the loss.
- [ ] Live verification: a real `bootstrap-fundamentals --mode per-filing` ECS
      run against a CIK with real new filings, followed by a direct Snowflake
      query confirming `MAX(ingested_at)` on a written table actually advances
      to the run's own timestamp.
- [ ] Once confirmed, re-run Ticket 02/03's own outstanding verification (a
      second per-filing run against the same CIK should show
      `filings_already_processed > 0`).
