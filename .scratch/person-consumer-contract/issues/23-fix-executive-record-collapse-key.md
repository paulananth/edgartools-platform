# Add fiscal_year to the sec_executive_record collapse and gold grain

Type: task
Status: resolved (2026-09-21)
Blocked by: none — but **blocks the ticket 10 re-export**

## Resolution

Done on `claude/person-ticket-23`. The collapse key now mirrors the landing
key in all three places it is declared.

| Item | Change |
|---|---|
| 1 | `models/silver/sec_executive_record.sql`: `fiscal_year` in the `qualify` partition and in the `silver_not_retired` business key (`concat_ws('\|', cik, accession_number, fiscal_year, exec_name)`), with a comment citing `silver_schema.py`'s REQUIRED set |
| 2 | `models/gold/executive_records.sql`: grain header and `fact_key = surrogate_key(cik, accession_number, fiscal_year, exec_name)` — `cik` in the hash for the reason `filing_activity` has it (one accession can carry more than one cik); `gold.yml` tests `fact_key` `unique` + `not_null`, `fiscal_year` `not_null` (no `dbt_utils` package installed, so no `unique_combination_of_columns`) |
| 2b | **Derived columns now computed within one filing** (found by the Standards axis). With `fiscal_year` in the grain, a fiscal year is reported by up to three consecutive proxies, so the old `lag(total_comp) over (partition by cik, exec_name order by fiscal_year)` had ties with no tiebreaker — the DuckDB replay shows a "prior year" that is the *same* fiscal year from the other filing — and `rank() over (partition by cik, accession_number)` ranked 5 rows across 3 years as one list. Now: `comp_rank_within_filing` partitions by `(cik, accession_number, fiscal_year)`; `comp_pct_change_yoy` lags within `(cik, accession_number, exec_name)` and only fires when the prior row is `fiscal_year - 1`; `role_recency_rank` gets a deterministic `accession_number desc, exec_name` tiebreak. Tie-free by construction (the grain is unique on each partition) and a YoY never compares against another filing's restatement. New gold unit test `_executive_records_unit_tests.yml` constructs the overlapping-year, two-accession case with a gap year. |
| 3 | **Zero retirement rows exist under the old key, by construction.** `SILVER_LANDING_RETIREMENT` has had exactly two writers in the repo's history: `reference_catalog_silver_acceptance._record_landing_retirements` (`target_table = 'sec_company_ticker'`) and `scripts/ops/aws_cost_optimizer.record_retirements` (`target_table = 'sec_filing_text'`). Nothing has ever written a `sec_executive_record` retirement (`git log -S'"sec_executive_record"'` over the acquisition and ops paths finds only the landing write). Deployer pre-flight, to make the same fact live: `select count(*) from EDGARTOOLS_SILVER_LANDING.SILVER_LANDING_RETIREMENT where lower(target_table) = 'sec_executive_record'` must return 0 before `--full-refresh`. |
| 4 | Deploy note is now in the model's header comment, where a deployer reads it: `dbt run --select sec_executive_record executive_records --full-refresh`, silver before gold |

**Proof against the resolution criterion.** Three dbt unit tests in
`models/silver/_sec_executive_record_unit_tests.yml`: three fiscal years for
one executive on one accession all survive; a `--force` re-parse at a higher
`parse_sequence` replaces the same year only; a retirement keyed on the full
business key retires one year and leaves the other. They need a Snowflake
target to execute, so `research/23-prove-collapse.py` replays the model's SQL
shape in DuckDB over the same rows: the old key keeps **1 of 3** Tim Cook
years, the new key keeps **3 of 3**, and all three unit-test expectations
reproduce. The same script replays the gold windows over the gold unit
test's fixture and reproduces all seven expected rows. `dbt parse` / `dbt ls`
offline are clean.

**Review.** Three-axis code review: Standards — one blocking (the gold
window functions were written for the old grain: ties in `lag`, rank across
years — fixed, item 2b), two should-fix (both chained dynamic tables need
`--full-refresh`, silver first — in the model header; `fact_key` omitted
`cik` against the grain it asserts — added); Spec — one blocking (item 3
unverified — resolved above by enumerating the writers), one should-fix
(deploy note not visible to a deployer — moved into the model header), one
nit (the DuckDB script re-implements the macro inline and would drift
silently if the macro changed — accepted, it is evidence for this ticket,
not a regression gate; the dbt unit tests are the gate); GoF — leave it, the
triple-declared key has changed once in the file's history and the targeted
unit tests are the proportionate guard.

**Not reached by this ticket.** Landing the model does not reparse the
~14,755 existing rows or redeploy the dynamic tables. The re-export sequence
is recorded on [ticket 10](10-fix-proxy-executive-name-parser-leak.md).

## Question

Nothing to decide; found by the Spec axis of ticket 10's code review and
verified against the models.

The silver **landing** dedupe key for `sec_executive_record` is
`(cik, accession_number, fiscal_year, exec_name)`
(`edgar_warehouse/silver_schema.py:591-596`). The dbt **collapse** keeps only
one row per `(cik, accession_number, exec_name)`:

```sql
qualify row_number() over (
    partition by cik, accession_number, exec_name
    order by parse_sequence desc
) = 1
```

(`infra/snowflake/dbt/edgartools_gold/models/silver/sec_executive_record.sql:22-24`,
plus the same key inside `silver_not_retired`'s concat at `:26`). Gold repeats
the omission: `models/gold/executive_records.sql` is grain
`(cik, accession_number, exec_name)` with
`fact_key = surrogate_key(accession_number, exec_name)` (research 12 F4).

**Why ticket 10 makes this urgent rather than merely wrong.** A Summary
Compensation Table lists three fiscal years per executive. Before the parser
fix, those three rows carried *different* corrupted names, so they survived
the collapse under three distinct (wrong) keys. After the fix they correctly
share one name — so the collapse discards two of the three, keeping whichever
has the highest `parse_sequence`. Correcting the name therefore costs two of
every three fiscal years of real compensation unless this key is fixed first.

That directly contradicts what the Person consumer contract relies on this
source for: "the richest **tenure** source — one row per named executive
officer per fiscal year" (`docs/specs/person/consumer.md`, Source authority).

## What to do

1. Add `fiscal_year` to the `qualify` partition and to the
   `silver_not_retired` concat key in the silver model.
2. Add `fiscal_year` to the gold `executive_records` grain and `fact_key`,
   and check its `unique`/`not_null` tests accordingly.
3. Confirm no retirement rows were written under the old concat key; if any
   exist, migrate or re-key them.
4. Redeploy: a dynamic table's SQL body change is a **silent no-op** under
   plain `dbt run` — use `--full-refresh` (CLAUDE.md, "dbt gold model SQL
   changes — smoke test convention").

Resolved when a single accession with a three-year Summary Compensation Table
yields three silver rows and three gold facts for one executive.
