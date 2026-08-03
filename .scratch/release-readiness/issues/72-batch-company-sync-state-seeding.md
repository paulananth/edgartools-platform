# Batch company_sync_state seeding instead of a per-CIK read+write loop

Type: task
Status: resolved

## Question

Why was there a silent ~2m20s gap between the `company_tickers.json` and
`company_tickers_exchange.json` SEC fetches in `_sync_reference_data`
(`ComputeIdentityRefreshWindow`), with zero log output in between, and how
should it be fixed?

## Root cause

Found while watching `daily-incremental-ticket70-verify-1785720814` -- the
verification run for tickets 67-70's deploy -- confirm those fixes were working
(they were: daily-index file gaps dropped from 35-53s to 250-424ms, exactly
matching ticket 68's local validation) but surfaced a fifth instance of the same
unbatched-per-row anti-pattern, in a different location.

`_sync_reference_data` (`warehouse_orchestrator.py:4394-4403`) looped over every
row in the freshly-fetched `company_tickers.json` snapshot -- **10,432 rows**,
confirmed live against the real file at the time of this investigation -- doing a
single-row `get_company_sync_state` SELECT followed by a single-row
`upsert_company_sync_state` INSERT/UPDATE, per CIK. Two unbatched DB round-trips
times ~10K rows, no explicit transaction, matches the exact shape tickets 67
(`silver_protection.py`), 68 (`merge_daily_index_filings`), and 69 (implicitly,
via the S3 client) already fixed -- just not yet applied here.

Unlike those three, this bottleneck is a **fixed, bounded cost per run** (once in
`_sync_reference_data`, not scaling with candidate/accession volume), so lower
severity -- but still a real, silent, unnecessary cost paid on every
`ComputeIdentityRefreshWindow`/`daily-incremental` invocation.

## Fix

New `SilverDatabase.seed_company_sync_state_bulk(ciks)` (`silver_store.py`):
stages the CIK list via a registered Arrow table (same primitive as tickets 68's
`merge_daily_index_filings` and the existing `merge_filings`/`_merge_rows_bulk`),
then applies one set-based `INSERT ... SELECT ... ON CONFLICT DO UPDATE`.

Semantics preserved exactly: the original per-row loop read existing
`tracking_status` and re-wrote it unchanged if present, defaulting to
`'bootstrap_pending'` only for genuinely new CIKs, while unconditionally clearing
`last_error_message` to `NULL` for every row. The bulk version replicates this
without any read at all: the `ON CONFLICT` clause deliberately **omits**
`tracking_status` from its `SET` list, so DuckDB leaves existing rows' status
untouched on conflict while new rows get `'bootstrap_pending'` from the `INSERT`
values; `last_error_message = NULL` is set unconditionally in both the insert and
the conflict branch. `_sync_reference_data`'s call site
(`warehouse_orchestrator.py`) collapsed from an 8-line loop to one call:
`db.seed_company_sync_state_bulk([int(row["cik"]) for row in rows])`.

`get_company_sync_state`/`upsert_company_sync_state` themselves were left
untouched -- both still used elsewhere (single-CIK seed-universe/pipeline-tracking
paths) where a per-row call is the right shape; only this one ~10K-row hot path
was changed.

## Validation

- Confirmed the real row count live: `company_tickers.json` currently has 10,432
  entries (`curl` against the real SEC endpoint).
- Six new tests (`tests/unit/test_company_sync_state_seeding.py`), all against a
  real `SilverDatabase`-backed DuckDB file, not mocks: new CIKs seeded as
  `bootstrap_pending`; existing `tracking_status` preserved untouched;
  `last_error_message` always cleared; untouched columns (e.g.
  `bootstrap_completed_at`) survive re-seeding; duplicate CIKs in the input
  handled correctly; empty input is a no-op.
- Timing regression guard: 15,000 CIKs (comfortably above the real 10,432)
  seeded in well under 5s locally -- versus the measured live ~2m20s for ~10K
  rows under the old per-row loop.
- `tests/unit/test_identity_refresh_window.py` (existing `_sync_reference_data`
  coverage) -- 14 passed, no regressions.
- Full suite: `tests/unit tests/application tests/architecture tests/mdm` -- see
  commit for exact count; expected the same one pre-existing unrelated failure
  as tickets 67-70.

## Done when

Done -- fix implemented, validated against real data (row count) and real
semantics (six DB-backed tests), full suite green modulo the one pre-existing
unrelated failure. Merged to `main` as `54ea7485` (PR #334, squash). **Not yet
deployed to prod** as of this entry.
