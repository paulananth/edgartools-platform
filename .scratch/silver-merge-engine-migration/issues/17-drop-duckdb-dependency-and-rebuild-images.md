# 17 — Delete the engine, drop `duckdb`, rebuild the deps images

**Type:** task

**Status:** resolved in code 2026-09-15 (deploy and lifecycle-rule cleanup still open — see Answer)

## Question

With Tickets 13–16 done: delete `silver_store.py`'s DuckDB engine, `_DDL` and
`_schema_migrations()`, `silver_protection.py` (`merge_candidate_into_canonical`, the registries),
`silver.py` (the shim), the file-backed `open_silver_database`, and the `SilverDatabase` alias; swap
Ticket 13's live-schema parity test for its decided successor; remove `duckdb>=1.0.0` from
`pyproject.toml` and `uv.lock`; rebuild both deps images and the warehouse/MDM images (CLAUDE.md's
"When to rebuild which image" table: a `uv.lock` change means both deps images); deploy; delete
the two `expire-retired-silver-*` lifecycle rules once the S3 objects are gone (cutover Ticket 21).
Resolves [Ticket 09](09-remove-duckdb-dependency.md), the destination.

**Blocked by:** [Ticket 13](13-duckdb-free-silver-schema-snapshot.md),
[Ticket 14](14-move-write-path-off-silver-database.md),
[Ticket 15](15-delete-dead-duckdb-readers-and-tools.md),
[Ticket 16](16-retire-remaining-local-store-couplings.md).

## Answer

Resolved in code 2026-09-15 (branch `claude/ticket-17-delete-duckdb-engine`). The deploy half
(images, prod) and the lifecycle-rule cleanup are still open — see the end.

**Decision taken during implementation.** Eight MDM test files (~50 tests: relationship-derivation
watermarks, `run_companies` bounded-limit progress and individual-filer exclusion, ADV bulk
bounded-limit, the real-schema 13F manager test, the source-to-MDM load path, the reader SQL in
`get_ciks_with_new_qualifying_filing` and `_company_identity_ciks_snowflake`) used DuckDB as a
real-schema fixture for the *surviving* Snowflake reader SQL. A SQLite stand-in fails on `QUALIFY`
(Snowflake dialect), so no other local engine runs that SQL. Both deps images build with
`uv sync --no-dev`, so a `[dependency-groups] dev` `duckdb` would never have reached prod.
Offered "dev-group test dependency (recommended)" vs "remove entirely"; the operator chose
**remove entirely**. Those tests are deleted; their files' own docstrings said a substring stub
could not catch the bug each guarded, so that coverage now has no local home (the
CLAUDE.md INSTITUTIONAL_HOLDS lesson — prefer a schema-backed fixture — has no fixture to
prefer any more; the next such bug is caught in prod or by a Snowflake-backed integration test).

**Deleted (prod).** `silver_store.py` (`SilverDatabase`, `_DDL`, 11 schema migrations, `fetch`,
shard reconcile), `silver_protection.py` (merge engine + registries, zero callers),
`silver.py`, `silver_support/session.py` (`open_silver_database`), `silver_support/access.py`,
`scripts/dev/regenerate_silver_schema.py`, `scripts/ops/silver-counts.sh`, verify-pr1 stage 2,
`scripts/verify-pr3/`. Orchestrator: `_hydrate_silver_database_from_storage`,
`_publish_silver_database_if_remote`, `_publish_silver_database_with_retry`,
`_streaming_md5_hexdigest`, `LEASE_ONLY_COMMANDS`/`_lease_command_context` (the lease-only
`silver.duckdb` repoint; leases live in bookkeeping Postgres), the planned `silver_database`
write. `bootstrap-fundamentals`' publish block. `duckdb>=1.0.0` out of `pyproject.toml`;
`uv lock` regenerated.

**Kept / moved.** `_parse_company_ticker_rows` → `silver_landing_store.py` (three live callers).
`SilverLandingStore` is the only silver store; `_open_silver_database(landing_export=)` stays in
the orchestrator as the test seam; the five discovery drivers, `bootstrap-fundamentals` and the
parity CLI construct it directly. `silver_schema.py` is hand-maintained now, minus
`retirement_state_observed_at` on two tables (only DuckDB had it; no writer stamped it), so the
snapshot equals `11_silver_landing_schema.sql` exactly and `_DUCKDB_ONLY_COLUMNS` is gone.
`reference_catalog_silver_acceptance` gains a `prior_members` seam (its prior-membership read
had no production source either way — still the map's "Not yet specified" gap).

**`uv.lock` caveat.** `duckdb` remains in the lock as splink's transitive dependency under the
`mdm` extra (API/admin tooling). Neither deps image installs that extra
(`uv sync --frozen --no-dev --extra s3 --extra mdm-runtime`); checked with `uv export` for that
set (no duckdb) and by importing the orchestrator and MDM CLI in a venv with duckdb uninstalled.
Removing it from the lock entirely means dropping or replacing splink — not this ticket.

**Tests.** Full suite (integration excluded): 3227 passed, 5 skipped. `tests/architecture/test_boundaries.py`
now forbids `db._conn` anywhere. Ruff F-class: the same three pre-existing findings as `main`.

**Reviews.** `/gof-refactor-reviewer` before each production edit (Rule 0 both times: straight
deletions, no pattern-shaped change) and the three-axis `/code-review` after:

- **Standards — one regression, fixed.** `bootstrap-fundamentals --identity-refresh-run-id`
  (`daily_incremental`'s identity fan-out) still passed the local `silver.duckdb` to
  `persist_batch_outcome(delta_file=...)`, which uploaded it as the batch "delta". Nothing creates
  that file any more, so every identity batch would have exited 1 ("identity refresh batch delta
  is missing"). The delta was the same empty-store file Ticket 16 stopped uploading as the reference
  snapshot, and nothing ever read its bytes (the reducer only checked that `delta_path` and
  `sha256` were present). Dropped: the `delta_file` parameter, the `delta.duckdb` upload, the
  outcome's `delta_path`/`sha256`, the "lacks immutable delta identity" check. Kept: the run
  manifest + per-batch outcome completeness gate. Regression test at the real seam
  (`test_identity_refresh_batch_persists_an_outcome_the_reducer_accepts`), red before the fix.
  Also fixed: stale `SilverDatabase`/`silver_store.py` claims in live docstrings, comments,
  `docs/runbook.md` and CLAUDE.md's pipeline diagram; one unused import.
- **Spec — two fixes.** 36 dbt silver model headers and the 11/13 bootstrap SQL files told
  editors to follow `silver_store.py`'s schema; now they point at the landing DDL (+
  `silver_schema.py`). `test_silver_landing_retirement.py` was deleted wholesale, but only its two
  DuckDB tests were DuckDB-bound: the `silver_model_config` lag test is restored, and the
  `silver_not_retired` macro gets structural guards (latest event per key, strict
  `parse_sequence >`, target-table scope) — text checks, not execution. CLAUDE.md's "no DuckDB in
  the images" is qualified until the images are rebuilt.
- **GoF — no change.** One evidenced note: the five discovery drivers took the same silver-store
  edit twice in nine days (Tickets 10 and 17); extract a shared store/flush helper when the first
  of them gets a landing export, not before.

**Follow-ups, not done here:** `--silver-root`/`WAREHOUSE_SILVER_ROOT` now configure nothing;
the `silver_publish_started/completed` events carry `silver_database=None` except on the
identity-refresh branch (check consumers before renaming); the deleted real-schema reader-SQL
tests and the `silver_not_retired` semantics have no executing test until a Snowflake-backed dbt
or integration test exists.

**Still open (this ticket, needs go-ahead):**
1. Rebuild both deps images (`uv.lock` changed) and the warehouse/MDM images; verify
   `docker run ... python -c "import duckdb"` fails in each; deploy with
   `deploy-aws-application.sh --env prod --enable-mdm`.
2. Delete the two `expire-retired-silver-*` lifecycle rules in
   `infra/terraform/modules/storage_buckets/main.tf` once the S3 objects are gone (Ticket 21
   applied 7-day expiration 2026-09-14; delete markers land ~2026-09-15/16, noncurrent versions
   expire ~2026-09-22/23). Also retire `edgar_warehouse/infrastructure/warehouse_duplicate_reclaim.py`'s
   `silver.duckdb`/shard key entries and `infra/scripts/reclaim-warehouse-duplicates.sh`'s prefixes then.
3. `infra/scripts/install.sh`'s operator "known pitfalls" text (lines ~415, ~814) still describes
   the monolith `silver.duckdb` fallback; stale, harmless, not touched here.
