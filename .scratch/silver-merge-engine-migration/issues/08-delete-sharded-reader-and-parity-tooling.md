# 08 — Delete `ShardedSilverReader` and `verify-resolver-input-parity`

**Type:** task

**Status:** resolved in code 2026-09-14, with a corrected scope (below): the parity tooling is
deleted; `ShardedSilverReader` stays until Ticket 09.

## Question

`silver_support/sharded_reader.py` survives only for `mdm verify-resolver-input-parity`
(`mdm/silver_parity.py`), which diffs DuckDB against Snowflake. Once no writer produces DuckDB
rows there is nothing to diff. Delete the reader, the parity command, and the `RESOLVER_INPUT_TABLES`
exclude-column machinery CLAUDE.md's "verify-resolver-input-parity 100% false-positive" entry
describes; `silver_support/session.py`'s `open_silver_shard` and `mdm/cli.py`'s six references
go with it.

**Blocked by:** [Ticket 05](05-thirteenf-tables-landing-only.md),
[Ticket 06](06-submissions-and-artifact-tables-landing-only.md).

## Corrected scope (2026-09-14)

Every caller was checked before any edit, as Ticket 07 did. The premise ("survives only for
`verify-resolver-input-parity`") failed for one caller:

| Item | Finding | Outcome |
|---|---|---|
| `mdm verify-silver-parity`, `mdm verify-resolver-input-parity`, `mdm/silver_parity.py` | Not in `infra/`, `scripts/` or `.github/`. duckdb-retirement-cutover Tickets 19 and 21 (open) need a DuckDB-vs-Snowflake comparison, but both name `table-reconcile`, which reads through `open_silver_database`/`SnowflakeSilverReader`, not this tooling. | **Deleted.** |
| `mdm/cli.py` `_duckdb_silver_reader`, `_require_duckdb_silver_reader` | Only the two parity handlers called them. | **Deleted.** |
| `warehouse_orchestrator._hydrate_all_shards`, `_hydrate_shard_for_window` | Only `_duckdb_silver_reader` reached them. `_read_shard_manifest` also serves the live `_shard_partition_ciks` (seed-bronze-batches). | **Deleted**; `_read_shard_manifest` kept. |
| `silver_support/session.py` `open_silver_shard` | No callers (one test patch). | **Deleted.** |
| `ShardedSilverReader` | `backfill-silver-landing-historical` (`silver_landing_historical_backfill.py`) still reads the retired canonical monolith through it and its `copy_table_to_parquet`, and imported `PARITY_TABLES`. Ticket 09 deletes that module, gated on cutover Ticket 21 (the old canonical objects must be dispositioned before the tools that read them go). | **Kept** until Ticket 09; docstring names its one remaining caller. The backfill's 30-table list is now a literal in that module. |

## Implementation (resolved 2026-09-14 in code)

- Deleted the two `mdm` subcommands (parsers and handlers), `mdm/silver_parity.py`, the two
  DuckDB-reader helpers in `mdm/cli.py`, `_hydrate_all_shards`, `_hydrate_shard_for_window`
  and `open_silver_shard`.
- Deleted their tests: `tests/mdm/test_silver_parity.py`, `tests/unit/test_resolver_input_parity.py`,
  `tests/mdm/test_silver_reader_monolith_fallback.py`, the `_duckdb_silver_reader` s3 test in
  `test_source_to_mdm_load_path.py`, the STORE-02 shard-hydrate test and a dead patch in
  `test_sharding.py`, and a dead `open_silver_shard` patch in `test_warehouse_orchestrator_mdm.py`.
  `test_silver_reader_read_target.py` no longer patches the deleted reader.
- `silver_landing_historical_backfill._BACKFILL_TABLES` is a literal list (same 30 tables);
  its test pins the count and the `sec_company_ticker` exclusion instead of comparing against
  `PARITY_TABLES`.
- Comments and docs: orchestrator dispatch and shard-helper notes, `backfill-silver-landing-historical`
  help text, `table_reconciliation/contracts.py`, `sharded_reader.py` docstring,
  `docs/data-architecture-issues.md`, and two `CLAUDE.md` passages (the MDM reader paragraph and
  a dated note on the 5-whys entry). Ticket 09's question now names `sharded_reader.py`.
- **Tests:** `tests/mdm/test_parity_commands_removed.py` (4 tests, red first: both commands
  rejected by the parser, the module and the reader helpers gone).
  Full suite excluding `tests/integration`: 3483 passed, 5 skipped (Ticket 07 had 3508; the
  deleted parity, resolver-input and fallback tests account for the drop). The review fixes
  below landed after that run started; their touched test files were re-run (42 passed). Ruff
  and mypy: nothing new against HEAD (mypy's three `no-redef` hits in the orchestrator only
  moved line numbers). Integration tests and dbt compile were not run locally.
- **Review (Standards, Spec, GoF).** GoF: no findings (the old `PARITY_TABLES` never changed
  after it was created, so the inlined list has nothing to drift from). Fixed:
  - the backfill list's comment and test docstring claimed it was "the tables EDGARTOOLS_SILVER's
    dbt models cover"; the dbt silver models have since grown to 33, so both now say it is the
    frozen set the parity gate tracked;
  - `MDM_SILVER_DUCKDB` / `MDM_LOCAL_SILVER_DUCKDB` are now read by nothing:
    `docs/aws-mdm-source-to-mdm.md`'s prerequisites, "Silver Source" section, local-run note,
    mastering note and two Common Errors rows still called them required; rewritten to the
    Snowflake-only reader;
  - a test class and banner in `test_source_to_mdm_load_path.py` named the deleted s3-download
    behaviour; stale `PARITY_TABLES` / `_hydrate_all_shards` wording in the backfill tests;
  - the unused `typing.Any` import in `session.py`;
  - the orchestrator dispatch comment and `backfill-silver-landing-historical` help text also
    said "every EDGARTOOLS_SILVER table";
  - duckdb-retirement-cutover Ticket 12 still said the reader and shard read path were kept for
    the parity check; it has a dated update note.

  Follow-ups, not done here (deploy or ops surface, not dead Python):
  - `infra/scripts/deploy-aws-application.sh` still has `--mdm-silver-duckdb` and injects
    `MDM_SILVER_DUCKDB` into MDM task definitions. Harmless (unread); removing it changes task
    definitions on the next deploy, so it belongs with Ticket 09's deploy-script sweep.
  - `scripts/ops/full-universe-sync.sh` and `sync-relationships.sh` accept `MDM_SILVER_DUCKDB`
    as one of two alternatives in a precondition check.
  - `docs/aws-mdm-source-to-mdm.md`'s "Silver Readiness Diagnostics" still describes checking a
    local DuckDB; stale since cutover Ticket 05, not made worse here.
