# Add fiscal_year to the sec_executive_record collapse and gold grain

Type: task
Status: open
Blocked by: none — but **blocks the ticket 10 re-export**

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
