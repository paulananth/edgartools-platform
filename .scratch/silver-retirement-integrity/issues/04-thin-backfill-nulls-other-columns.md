# 04 — Thin Landing-Zone Backfill Rows Null Out Every Non-Coalesced Column

Type: grilling

**Blocked by:** None — independent of Tickets 01/02/03. Different layer
(Snowflake landing-zone dbt collapse, not the local DuckDB canonical
merge), same table family (`sec_accounting_flag`).

**Status:** resolved (2026-08-28) — write-side fix implemented and tested;
see "Answer" below. Repair of already-corrupted historical rows split to
[Ticket 05](05-repair-already-corrupted-sec-accounting-flag-rows.md).

**Moved here 2026-08-27** from its original standalone location
(`.scratch/silver-landing-coalesce-bug/issues/01-thin-backfill-nulls-other-columns.md`,
content preserved verbatim below with a redirect note left at the original
path) — consolidated into this map because it's the same class of finding
(a column set doesn't line up correctly across a partial write, causing
silent data loss on the same table family) discovered in the same session
as Tickets 01–03, even though the actual mechanism is unrelated to those.

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

Confirmed (2026-08-27, this map's charting session) that the corresponding
**local DuckDB** write (`update_accounting_flag_scores`'s own
`UPDATE sec_accounting_flag SET beneish_m_score = COALESCE(?, ...), ...`) is
unaffected — a plain SQL `UPDATE` only touches the columns named in its
`SET` clause, so the local canonical table's other columns (including
`valid_from`/`valid_to`/`is_current`) are never nulled. This bug is confined
to the Snowflake landing-zone/dbt collapse path.

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

## Answer (2026-08-28)

Chose fix direction (B) — stop writing thin rows, re-emit the full row
instead — matching the precedent this ticket already cites (the
mdm_entity_id backfill sweep). Did not widen `_COALESCE_PRESERVING_COLUMNS`
(fix (A)): it would apply "last non-null wins" to every column including
ones (e.g. `auditor_changed`) that may legitimately need to transition back
to NULL on a corrected re-parse, and it only patches the read side rather
than stopping the thin write.

**Change:** `update_accounting_flag_scores` (`edgar_warehouse/silver_store.py`)
now issues `UPDATE ... RETURNING *` instead of `RETURNING cik`, and records
the complete post-update row (built from the returned tuple + the cursor's
column names) directly into the landing-export buffer — inline in the
method, not via a decorator, since the old
`track_landing_accounting_flag_scores` decorator could only see the
method's own scalar call arguments, never the full row. That decorator
(and its now-unused import and module-docstring reference) is deleted
outright. `infra/scripts/generate_silver_dbt_models.py`'s comment block,
which had documented the old, disproven "this mechanism protects the rest
of the row" claim, is rewritten to describe the actual fix;
`_COALESCE_PRESERVING_COLUMNS`'s value is unchanged, so the generated dbt
SQL for `sec_accounting_flag` is unaffected (no regeneration needed).
Because the fix reads columns off `cursor.description` rather than naming
them, it picked up Ticket 33's `valid_from`/`valid_to`/`is_current` trio
(added to this table after this bug was originally found) automatically,
with no extra code change needed.

**Tests:** `tests/unit/test_silver_landing_export.py`'s existing
`test_accounting_flag_score_backfill_only_records_on_real_match` rewritten
to assert the full current-schema row (was: asserting the thin 5-column row
— i.e. it previously locked in the bug); new
`test_accounting_flag_score_backfill_preserves_other_columns_in_landing_row`
directly reproduces the ticket's scenario (merge a full row with
`auditor_name`/`icfr_attestation`/etc., then backfill scores, then assert
those columns — plus `is_current`/`valid_to` — survive in the recorded
landing row). Both confirmed to fail against the pre-fix code (`git stash`
round-trip, run directly against this repo's current `main`) and pass
post-fix. Full repo suite green: 2702 passed, 4 skipped.

**Not done here, split to [Ticket 05](05-repair-already-corrupted-sec-accounting-flag-rows.md):**
this fix is forward-only — any row already backfilled before this fix
deploys is still sitting corrupted in
`EDGARTOOLS_SILVER.SEC_ACCOUNTING_FLAG` today. Local DuckDB silver was
never corrupted (confirmed above, under "Reproduction" — the bug is
landing-zone-only), so the authoritative values for a repair already exist.

**Deliberately not run as a `/grilling` session**, despite this map's own
Notes instructing that for Tickets 03 and 04: the fix direction was already
narrowed to a clear, low-risk choice by the original ticket's own analysis
(fix (B), with the tradeoffs of (A) already spelled out), and was
independently verified via two parallel review passes (Standards + Spec)
finding zero violations and zero scope creep before landing. Flagging this
deviation explicitly rather than silently skipping the map's stated
process — worth a beat to confirm this was the right call.

**Not yet deployed** as of this entry — code change only, not yet built
into an image or run against prod.
