# 01 — Fix Silent, Permanent Exclusion of Ownership Rows Missing a `sec_company_filing` Join

**What to build:** `MDMPipeline.run_persons()` and `MDMPipeline.run_securities()`
(`edgar_warehouse/mdm/pipeline.py`) both select their candidate rows via an
`INNER JOIN sec_company_filing f ON <ownership_table>.accession_number =
f.accession_number` to get the issuer CIK. Any ownership row whose
`accession_number` has no matching row in `sec_company_filing` yet is
silently dropped from the candidate set entirely — not deferred, not
logged, not retried on the next run, since the exclusion happens inside
the SQL itself before any Python-level "already resolved" check even
applies. Fix this so such rows are either resolved once their filing
metadata catches up, or at minimum surfaced (logged/counted) as
unresolvable-for-now rather than disappearing invisibly on every single
`mdm run` forever.

**Discovered while:** verifying the mdm-ahead-of-silver backfill sweep
(`.scratch/mdm-ahead-of-silver/`) for the person/security entity types
(2026-08-19) — the sweep itself works correctly (confirmed resolving
thousands of new persons/securities in the same session), but a specific
81-row backlog (44 `sec_ownership_reporting_owner` + 37 ownership-txn rows)
never resolved no matter how many `mdm run` passes were triggered. Traced
to this root cause, not a bug in the backfill sweep or the mdm-ahead-of-
silver plan.

**Evidence (live, 2026-08-19, `EDGARTOOLS_PROD`):**

```sql
SELECT COUNT(*) AS total_pending,
       COUNT(f.accession_number) AS has_filing_match,
       COUNT(*) - COUNT(f.accession_number) AS missing_filing_match
FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_OWNERSHIP_REPORTING_OWNER o
LEFT JOIN EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY_FILING f
  ON o.accession_number = f.accession_number
WHERE o.mdm_entity_id IS NULL
-- total_pending=44, has_filing_match=13, missing_filing_match=31
```

31 of 44 pending `sec_ownership_reporting_owner` rows (spanning many
distinct accession numbers and filing dates from 2024 through 2026, not
one bad batch) have no corresponding `sec_company_filing` row at all. The
identical `JOIN sec_company_filing f ON t.accession_number =
f.accession_number` pattern exists in `run_securities()`'s query for both
`sec_ownership_non_derivative_txn` and `sec_ownership_derivative_txn` —
same structural gap, not independently re-verified row-by-row but the
query shape is byte-for-byte the same join condition.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Root cause confirmed: read `sec_company_filing`'s write path
      (`edgar_warehouse/silver_store.py`) and determine *why* some
      accessions' ownership rows land before their `sec_company_filing`
      row does — e.g. different parser paths, different write ordering
      within `_run_submissions_bronze_then_silver`, or a genuinely separate
      ingestion pass — before picking a fix, since the right fix differs
      depending on whether this is "eventually consistent, just needs a
      retry" vs. "these filings will never get a `sec_company_filing` row."
- [ ] `run_persons()`/`run_securities()` no longer permanently lose these
      rows — either the query stops silently dropping them (e.g. `LEFT
      JOIN` plus a fallback issuer-CIK source, if the join was only ever
      needed for `issuer_cik` and another column already carries it), or
      an explicit, logged "excluded — no filing record" path exists so the
      gap is visible and revisited on a later run instead of vanishing.
- [ ] A regression test reproduces the exact shape: an ownership row with
      an `accession_number` that has no `sec_company_filing` counterpart,
      asserting it is not silently dropped by `run_persons`/`run_securities`
      (or, if the decision is "explicitly log and skip," asserting that
      skip is observable rather than silent).
- [ ] Confirm whether this same gap affects any other resolver with a
      similar `JOIN sec_company_filing` pattern (grep the file for the
      exact join condition — don't assume person/security are the only
      two).
- [ ] Full test suite still green after the fix.

## Answer

<!-- filled in on resolution -->
