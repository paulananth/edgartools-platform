# 02 — Accession-level incremental scoping for per-filing/thirteenf

Type: task
Status: done

**Blocked by:** none — independent of Ticket 01 (doesn't touch
`sec_financial_fact`/`sec_accounting_flag`).

## What to build

Add a DuckDB-local table via the same `_schema_migrations()` mechanism (not
a new Postgres/`BookkeepingStore` dependency — these modes are pure-DuckDB
today; a cross-store dependency here would be a bigger, riskier structural
change than staying in-file):

```sql
sec_fundamentals_processed_accession(
  mode TEXT,
  accession_number TEXT,
  processed_at TIMESTAMP,
  PRIMARY KEY (mode, accession_number)
)
```

Write to it **atomically alongside** each accession's real output rows —
same transaction/merge unit — so a crash mid-parse can never mark an
accession "processed" without its real rows also having landed. This
specifically closes the thirteenf partial-write edge case (one
INFORMATION TABLE can produce many `holding_index` rows per accession;
checking "does any `sec_thirteenf_holding` row exist for this accession"
would wrongly skip re-processing a partially-written filing).

Before iterating `sec_company_filing` for candidate accessions
(`fundamentals_ingest.py:156-164` for per-filing, `:501-510` for
thirteenf), bulk-prefetch the processed set for the CIK window's mode and
filter candidates against it — the same bulk-prefetch-instead-of-per-row
idiom already established repeatedly in this codebase (e.g.
`BookkeepingStore`'s bulk methods, `daily_incremental`'s own recent
bulk-batching fix).

## Tests

- Unit test proving a second run over already-processed accessions does no
  work and writes no new rows.
- A companion test proving a genuinely new accession in the same CIK
  window is still processed.

## Acceptance

- [x] A manual `bootstrap-fundamentals --mode per-filing` (and `--mode
      thirteenf`) run against a real CIK window skips already-processed
      accessions on a second invocation, verified live (not just unit
      tests) — this is Phase 4 step 2's own verification requirement.
- [x] `/gof-refactor-reviewer` consulted before editing
      `fundamentals_ingest.py`/`silver_store.py` (repo hard rule).
- [x] `/code-review` (Standards, Spec, GoF) run before this ticket's PR is
      considered ready.

## Answer

Implemented as specified: `sec_fundamentals_processed_accession` table
(same `mode, accession_number, processed_at` shape), written atomically
alongside each accession's real output rows, bulk-prefetched before
iterating candidates. Landed on PR
[#603](https://github.com/paulananth/edgartools-platform/pull/603),
merged into `main` (commit `6813190c`).

Live verification required two prerequisite fixes this ticket's own text
didn't anticipate — `bootstrap-fundamentals` reading from a permanently
unhydrated local DuckDB ([duckdb-retirement-cutover Ticket 17](../../duckdb-retirement-cutover/issues/17-repoint-bootstrap-fundamentals-reads-to-snowflake.md))
and never writing to the Snowflake landing zone at all
([Ticket 18](../../duckdb-retirement-cutover/issues/18-bootstrap-fundamentals-never-wires-landing-export-buffer.md)).
Once both landed and were deployed to prod, live verification against CIK
908311 confirmed the full loop: run 1 processed 15 filings; run 2 showed
`filings_already_processed: 15, filings_parsed: 0` — re-confirmed a second
time after the real prod deploy (`edgartools-prod-large:299`), not just
against a throwaway verification task definition.
