# Thin Landing-Zone Backfill Rows Null Out Every Non-Coalesced Column

Status: open

## Summary

`update_accounting_flag_scores` (`edgar_warehouse/silver_store.py:4100-4129`)
writes a **thin** landing-zone row — only `cik`, `accession_number`, and the
three forensic-score columns (`beneish_m_score`, `altman_z_score`,
`piotroski_f_score`); every other `sec_accounting_flag` column absent from
that row (`track_landing_accounting_flag_scores`,
`edgar_warehouse/serving/silver_landing_export.py:105-144`). The generated
dbt model (`infra/snowflake/dbt/edgartools_gold/models/silver/
sec_accounting_flag.sql`) wraps those three score columns in
`LAST_VALUE(col IGNORE NULLS) OVER (...)` specifically to protect them from
this thin row — via `generate_silver_dbt_models.py`'s
`_COALESCE_PRESERVING_COLUMNS` — and the surrounding code's docstrings assert
this mechanism prevents the thin row from "wiping out the rest of the row."

**That claim is false.** `QUALIFY row_number() OVER (partition by cik,
accession_number order by parse_sequence desc) = 1` still picks exactly
**one** winning row for the whole result, and every column *not* wrapped in
`LAST_VALUE(... IGNORE NULLS)` is a plain literal select — it reads that one
winning row's own value, not a coalesced value across versions. Once the
thin backfill row has the highest `parse_sequence` for that key (which it
always will, since `PARSE_SEQ.NEXTVAL` only increases), it becomes the
`QUALIFY`-winning row, and every column it doesn't carry — `auditor_name`,
`auditor_pcaob_id`, `auditor_location`, `icfr_attestation`,
`auditor_changed`, `fiscal_year`, `period_end`, `form_type`,
`parser_version`, `ingested_at` — reads back **NULL**, not the value from
the original full row.

## Reproduction

Verified empirically against DuckDB (same `QUALIFY`/`LAST_VALUE` window
semantics as Snowflake), not just reasoned about:

```python
import duckdb
con = duckdb.connect(":memory:")
con.execute("""
CREATE TABLE landing (
    cik INTEGER, accession_number VARCHAR, auditor_name VARCHAR,
    beneish_m_score DOUBLE, parse_sequence BIGINT
)
""")
con.execute("INSERT INTO landing VALUES (1, 'acc-1', 'Deloitte', NULL, 1)")   # full row
con.execute("INSERT INTO landing VALUES (1, 'acc-1', NULL, 2.5, 2)")          # thin backfill row, newer

result = con.execute("""
    select cik, accession_number, auditor_name,
        last_value(beneish_m_score ignore nulls) over (partition by cik, accession_number order by parse_sequence) as beneish_m_score
    from landing
    qualify row_number() over (partition by cik, accession_number order by parse_sequence desc) = 1
""").fetchall()
print(result)  # [(1, 'acc-1', None, 2.5)] -- auditor_name is None, not 'Deloitte'
```

## Impact

Live in production today, independent of anything in the
mdm-ahead-of-silver map. Every `sec_accounting_flag` row that has ever
received a forensic-score backfill via `update_accounting_flag_scores` has
had its `auditor_name`/`fiscal_year`/`period_end`/`form_type`/
`auditor_pcaob_id`/`auditor_location`/`icfr_attestation`/
`auditor_changed`/`parser_version`/`ingested_at` columns silently
nulled in the `EDGARTOOLS_SILVER.SEC_ACCOUNTING_FLAG` dynamic table (and
anything gold/dbt builds on top of it) — not a hypothetical risk, an actual
data-quality gap for however many rows this backfill has already touched.

## Found while

Investigating whether a thin landing-zone append was safe as the storage
mechanism for the mdm-ahead-of-silver map's Phase B backfill sweep
(`.scratch/mdm-ahead-of-silver/issues/06-narrow-backfill-storage-target.md`).
That map's own sweep was redirected to full-row re-emission instead
specifically because of this finding — this issue exists to track the
**pre-existing** `sec_accounting_flag` case separately, since it predates
and is unrelated to that map.

## Candidate fixes (not decided, not attempted here)

- Wrap **every** non-key column of `sec_accounting_flag` in
  `LAST_VALUE(col IGNORE NULLS)`, not just the three forensic scores — makes
  the collapse genuinely column-wise. Changes semantics for every column on
  this table; needs review of whether "last non-null wins" is correct for
  every column (a column that can legitimately need to transition from a
  value back to NULL would behave differently under this rule).
- Stop writing thin rows from `update_accounting_flag_scores` — re-read and
  re-emit the full row instead (same fix direction chosen for the
  mdm_entity_id sweep). Requires that call site to have the rest of the
  row's current values available at call time.
- A backfill sweep for already-corrupted rows, once the write-side fix
  lands, to repair rows that already lost data this way.

## Next step

Not triaged or assigned. Flagged for a human decision on priority and fix
approach — this file exists so the finding isn't lost, not to prescribe the
fix.
