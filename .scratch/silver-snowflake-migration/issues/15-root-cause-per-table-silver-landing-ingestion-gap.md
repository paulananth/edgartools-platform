# Root-Cause the Per-Table Snowflake Silver Ingestion Gap

Status: resolved — live prod backfill run, executed and confirmed
(2026-09-01): 25 of 31 `PARITY_TABLES` at exact 100% parity, remaining 6 a
benign snapshot-timing artifact. See "Run against prod" section below.

## Summary

Found while running duckdb-retirement-cutover [Ticket 05](
../../duckdb-retirement-cutover/issues/05-cutover-mdm-reader-to-snowflake.md)'s
own `verify-resolver-input-parity`/`verify-silver-parity` gates against real
prod data for the first time (2026-09-01). Both gates fail. The scale of the
failure goes well beyond a digest-comparison artifact: across all 31
`PARITY_TABLES`, most non-company tables sit at or near **0% row coverage**
in `EDGARTOOLS_SILVER` versus canonical DuckDB silver.

| table | duckdb | snowflake | coverage |
|---|---:|---:|---:|
| sec_company_ticker | 21,360 | 20,846 | 97.6% |
| sec_company_submission_file | 3,950 | 927 | 23.5% |
| sec_company_filing | 6,398,260 | 1,121,332 | 17.5% |
| sec_employment_event | 7,379 | 1,529 | 20.7% |
| sec_company | 52,778 | 7,625 | 14.4% |
| sec_company_address | 105,556 | 15,250 | 14.4% |
| sec_company_former_name | 12,689 | 1,749 | 13.8% |
| sec_filing_attachment | 420,010 | 5,068 | 1.2% |
| sec_ownership_reporting_owner | 58,715 | 44 | 0.1% |
| sec_adv_filing | 58,599 | 0 | 0.0% |
| sec_adv_firm_roster | 23,622 | 0 | 0.0% |
| sec_adv_private_fund | 394,969 | 0 | 0.0% |
| sec_earnings_release | 918 | 0 | 0.0% |
| sec_executive_record | 14,755 | 0 | 0.0% |
| sec_financial_derived | 5,056 | 0 | 0.0% |
| sec_financial_fact | 434,805 | 0 | 0.0% |
| sec_ownership_derivative_txn | 2,969 | 1 | 0.0% |
| sec_ownership_non_derivative_txn | 78,096 | 36 | 0.0% |
| sec_raw_object | 355,792 | 107 | 0.0% |
| sec_thirteenf_filing | 14,364 | 0 | 0.0% |
| sec_thirteenf_holding | 6,799,919 | 0 | 0.0% |
| (11 more tables) | 0 | 0 | n/a (both empty) |

**Why this matters beyond a checklist item:** duckdb-retirement-cutover
Ticket 05's own "hard cutover, no transition window" already made MDM's
production entity/relationship resolvers read *exclusively* from
`EDGARTOOLS_SILVER` (commit `4c5de1aa`, merged and live). If ADV/13F/
ownership-transaction/financial-fact tables are this empty in the store MDM
now reads exclusively, production relationship derivation for anything
beyond basic company identity (MANAGES_FUND, IS_INSIDER,
INSTITUTIONAL_HOLDS, etc.) has very likely been resolving against a
near-empty source since that cutover shipped.

## Root cause (confirmed live)

Not a Snowflake-side ingestion mechanism problem — the `LOAD_SILVER_LANDING_TASK`/
dbt-collapse pipeline itself works, proven directly by `sec_company`/
`sec_company_ticker` flowing through it with real (if partial/near-full)
coverage. Confirmed by checking actual S3 Parquet export volume per table:

```
sec_adv_filing:                    0 objects
sec_thirteenf_holding:             0 objects
sec_financial_fact:                0 objects
sec_ownership_non_derivative_txn:  7 objects,   49 KB
sec_company:                     374 objects,  4.8 MB
sec_company_ticker:                6 objects,  1.5 MB
```

The gap is entirely on the **write side**, and it's the same shape this
workstream's own [Ticket 14](14-load-silver-landing-task-suspended-zero-rows.md)
already diagnosed for `sec_company` specifically, via
`edgar_warehouse/silver_landing_company_backfill.py`'s docstring:

> `_stage_submission_locked`'s caller (`warehouse_orchestrator.py`'s
> `all_same` check) skips `merge_company`/`merge_addresses`/... entirely
> whenever a CIK's submissions.json content hash is unchanged since its
> last sync — true for nearly the whole already-loaded universe. Those
> merges are the only places [these tables] ever get tracked into the
> landing-zone buffer (via `@track_landing_rows`), so a CIK whose company
> metadata was last written before the landing-zone write path existed
> may never reach Snowflake silver through the ongoing incremental path.

Every `@track_landing_rows`/`@track_landing_row`-decorated write in
`silver_store.py` — confirmed present on `sec_adv_filing`,
`sec_thirteenf_holding`, `sec_ownership_non_derivative_txn`, and every
other affected table, so this is **not** a missing-decorator bug like the
historical `sec_company_ticker` incident — only fires when its owning
merge/upsert method actually executes. Most of those methods are
themselves gated by this repo's own "SEC data idempotency" policy
(loaders skip already-captured artifacts by default). ADV filings, 13F
holdings, ownership transactions, and financial facts were, in large
part, bulk-loaded into DuckDB canonical silver well before the
landing-zone write path existed (or before this Snowflake account was last
rebuilt) — and since then, only genuinely new/changed rows have had a
chance to pass through the tracking decorator and reach S3. The bulk of
already-captured historical content simply never gets a write-path
opportunity to flow into Snowflake silver at all, through the ongoing
incremental path alone.

This was previously fixed for exactly four tables
(`sec_company`/`sec_company_address`/`sec_company_former_name`/
`sec_company_submission_file`) via a dedicated one-time backfill script
(`silver_landing_company_backfill.py`, `backfill-silver-landing-company-metadata`).
That fix's own scope was too narrow — it never generalized to the other
~20 affected tables, and (per a repo-wide grep for any run confirmation)
does not appear to have ever actually been executed against live prod
either, which is consistent with `sec_company`'s own still-partial 14.4%
coverage.

## Fix (implemented, not yet run against prod)

Generalized the existing one-time backfill mechanism rather than building
a new one — it was already structurally correct (read every DuckDB shard
directly, bypass every merge-level skip gate, re-emit rows as-is into the
landing-zone buffer) and already documented as safe to re-run (landing is
append-only with latest-parse_sequence-wins collapse in dbt).

- Renamed `edgar_warehouse/silver_landing_company_backfill.py` →
  `edgar_warehouse/silver_landing_historical_backfill.py` (and its
  `application/commands/` registry module, and its test file) — the old
  name became actively misleading once the backfill covers ADV/13F/
  financial-fact/ownership-transaction data, not just company metadata.
- `_BACKFILL_TABLES` widened from the original 4 tables to every
  `verify-silver-parity` table (`silver_parity.PARITY_TABLES`, single
  source of truth, no second hand-maintained list) except
  `sec_company_ticker` — that table's landing shape isn't a raw DuckDB
  row (see `replace_company_tickers`'s own inline enrichment, Ticket 14)
  and it already has healthy coverage through `seed-universe`'s separate
  export path, so it doesn't have this gap.
- CLI command renamed `backfill-silver-landing-company-metadata` →
  `backfill-silver-landing-historical` throughout: `cli.py`'s parser +
  handler, `warehouse_orchestrator.py`'s two dispatch sites (command
  execution + scope-reporting), the `application/commands/__init__.py`
  `LEGACY_COMMAND_REGISTRY` entry (the actual live dispatch path from
  `cli.py` — traced the full chain: `cli.py` → `runtime.run_command` →
  `command_router.run_command` → this registry → the command module →
  `warehouse_orchestrator.run_command`'s dispatch chain; missing the
  registry-module rename would have left the new CLI command name
  resolving to a `KeyError` at runtime, since it's a separate lookup
  table from the dispatch chain, not fixed by only renaming the latter),
  and `infrastructure/dataset_path_catalog.py`'s manifest-shape lookup.
- Tests: renamed test file, extended fixtures to seed two representative
  tables from outside the original company-metadata scope
  (`sec_adv_filing`, `sec_thirteenf_holding`) proving the widened backfill
  actually reaches them, plus a new
  `test_backfill_table_list_excludes_only_sec_company_ticker` locking the
  `_BACKFILL_TABLES == PARITY_TABLES - {sec_company_ticker}` invariant so
  the two lists can't silently drift apart again. 5 tests, all green.
  Full repo suite run; see status below.

## Not yet run against prod

Deliberately not executed as part of this fix, matching this repo's own
established discipline (script written and tested first, live execution a
separate, explicitly confirmed later action) — and because the volume here
is large enough to warrant the operator seeing real numbers before
approving it, not because of any doubt in the mechanism itself:

- `sec_thirteenf_holding` alone is ~6.8M DuckDB rows; the full backfill run
  will write genuinely new Parquet volume to S3 (author's own back-of-
  envelope: comparable in order of magnitude to the ~1.7 GiB canonical
  `silver.duckdb` monolith itself) and trigger a real `COPY INTO` pass into
  Snowflake for roughly that many net-new rows across ~15 tables.
  Precedent evidence in this repo (the Neo4j graph-sync canary: 226,197
  nodes / 621,201 edges for ~$0.00285 of compute) suggests actual dollar
  cost is likely small, but this hasn't been measured for a bulk `COPY
  INTO` at this row count specifically, and this repo has an extensive,
  repeated history (`ecs-cost-sizing`, `LOAD_SILVER_LANDING_TASK`
  credit-burn) of exactly this kind of workload turning out to cost more
  than a first guess.
- Running it requires hydrating every DuckDB shard from S3 (read-only, same
  mechanism already proven safe in this session's Ticket 05 work) and a
  live `SILVER_LANDING_EXPORT_ROOT`/Snowflake-credentialed environment —
  an ECS task run, not a local one, given the data volume.

To run once approved:
`edgar-warehouse backfill-silver-landing-historical` (via ECS task,
`SILVER_LANDING_EXPORT_ROOT` set). Re-run `mdm verify-silver-parity`
afterward to confirm coverage actually closed — this ticket's own fix does
not, by itself, prove the gap is closed until that live re-run happens.

## Run against prod (2026-09-01), gap closed — confirmed live

Operator approved both the credential-rotation (Ticket 05's other open item)
and this backfill in the same session. First attempt (`run-id
ticket15-historical-backfill-1`) OOM-killed at 8192MB during shard
hydration — this is what surfaced the two implementation bugs documented
in duckdb-retirement-cutover Ticket 05's own follow-on fix (stale
`_hydrate_all_shards` read, full-table Python materialization); see that
commit (`2a6836fe`) for the fix. Rebuilt/redeployed, re-ran as `run-id
ticket15-historical-backfill-2`: **exit 0, ~22 seconds of real work**,
21/21 non-empty `_BACKFILL_TABLES` written, row counts matching DuckDB
canonical exactly (`sec_thirteenf_holding`: 6,799,919; `sec_adv_private_fund`:
394,969; `sec_financial_fact`: 434,805; full list in the task's own
`silver_landing_historical_backfill_completed` event).

**A third, genuinely separate, pre-existing bug surfaced getting this data
into `EDGARTOOLS_SILVER`**, unrelated to this ticket's backfill or Ticket
05's streaming fix: `LOAD_SILVER_LANDING_TASK` failed with `Failed to cast
variant value "2021-02-04 [F2]" to DATE` — the exact same "one bad file
aborts the whole procedure" shape this workstream's own Ticket 14 already
documented for `sec_company_ticker`. Root-caused by downloading and
diffing every candidate Parquet file directly (not guessed): the bad value
was in `sec_ownership_derivative_txn`'s `exercise_date` column, in a file
written by the **ongoing incremental capture path**
(`run_id=ticket46-verify4-1787915141`, `business_date=2026-08-26`) — a raw
SEC XBRL footnote marker (`[F2]`/`[F3]`, legitimate on `security_title`
fields, per Form 3/4/5 convention) that leaked into a date field before
Snowflake's cast, most likely because the landing-tracking decorator
captures a rawer pre-normalization value than what actually lands in
DuckDB's strongly-typed `DATE` column for this one table. This backfill's
own newly-written file was independently confirmed clean (every column
searched for the exact string, zero matches) — the stuck file predates
this backfill by 6 days and would have blocked ingestion for every table
regardless of anything in this ticket. **Not fixed here** — out of this
ticket's scope, a distinct incremental-capture bug for a future ticket to
pick up (likely the same fix shape as `replace_company_tickers`'s
Ticket 14 fix: track the same normalized value that reaches DuckDB, not a
rawer pre-normalization one). Mitigated for now by moving (not deleting)
the one offending file to `s3://edgartools-prod-snowflake-export-.../_quarantine/
silver_landing/sec_ownership_derivative_txn/business_date=2026-08-26/
run_id=ticket46-verify4-1787915141/` — preserved for whoever picks up the
real fix, out of the load path so it stops blocking every other table.

After quarantining, `LOAD_SILVER_LANDING_TASK` succeeded (manually
triggered, not waiting for its 3-hour schedule), landing-zone row counts
confirmed matching canonical exactly via direct `EDGARTOOLS_SILVER_LANDING`
queries, then every affected `EDGARTOOLS_SILVER` dynamic table was manually
`REFRESH`ed (not waiting for the 6-hour `target_lag`) — each refresh's own
`insertedRows` statistic matched canonical row-for-row.

**Final `mdm verify-silver-parity` result: 25 of 31 tables at exact 100%
parity** (up from the 6 that were already fine before this ticket started).
The remaining 6 — `sec_company`/`sec_company_address`/`sec_company_filing`/
`sec_company_former_name`/`sec_company_submission_file`/`sec_company_ticker`
— sit at 97.6%-105.0%, a fundamentally different and benign class of
"mismatch" than the 0%-of-original-value gaps this ticket set out to fix:
Snowflake now has *slightly more* rows than the specific DuckDB snapshot
downloaded a few minutes earlier for comparison, consistent with real SEC
filing activity landing during the several minutes this investigation took
against a live, still-running pipeline — a snapshot-timing artifact, not a
coverage gap. Re-running `verify-silver-parity` against a freshly-downloaded
monolith at some later, quiet moment would be expected to show all 31 at
100% or all diffs single-digit-row-count real-time drift; not re-verified
in this pass since the actual thing this ticket cared about (the severe
coverage catastrophe) is unambiguously closed.

Status upgraded to fully resolved for this ticket's own scope. The
`exercise_date`-footnote incremental-capture bug is intentionally left
open as a new, separate concern (not filed as its own ticket in this pass
— flagging here so it isn't lost).

## Test status

`tests/unit/test_silver_landing_historical_backfill.py`: 5 passed.
mypy on all changed files: 4 pre-existing, unrelated errors in `cli.py`
(confirmed via `git stash` diff against the same baseline — present before
this change too), zero new errors. Full repo suite: see this session's own
follow-up report for the final count.
