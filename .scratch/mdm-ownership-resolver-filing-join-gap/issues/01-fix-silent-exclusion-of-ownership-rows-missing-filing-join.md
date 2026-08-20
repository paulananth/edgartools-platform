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

**Status:** resolved (2026-08-19)

- [x] Root cause confirmed: read `sec_company_filing`'s write path
      (`edgar_warehouse/silver_store.py`) and determine *why* some
      accessions' ownership rows land before their `sec_company_filing`
      row does — e.g. different parser paths, different write ordering
      within `_run_submissions_bronze_then_silver`, or a genuinely separate
      ingestion pass — before picking a fix, since the right fix differs
      depending on whether this is "eventually consistent, just needs a
      retry" vs. "these filings will never get a `sec_company_filing` row."
- [x] `run_persons()`/`run_securities()` no longer permanently lose these
      rows — either the query stops silently dropping them (e.g. `LEFT
      JOIN` plus a fallback issuer-CIK source, if the join was only ever
      needed for `issuer_cik` and another column already carries it), or
      an explicit, logged "excluded — no filing record" path exists so the
      gap is visible and revisited on a later run instead of vanishing.
- [x] A regression test reproduces the exact shape: an ownership row with
      an `accession_number` that has no `sec_company_filing` counterpart,
      asserting it is not silently dropped by `run_persons`/`run_securities`
      (or, if the decision is "explicitly log and skip," asserting that
      skip is observable rather than silent).
- [x] Confirm whether this same gap affects any other resolver with a
      similar `JOIN sec_company_filing` pattern (grep the file for the
      exact join condition — don't assume person/security are the only
      two).
- [x] Full test suite still green after the fix.

## Answer

**Root cause:** `sec_company_filing` is populated exclusively by
`merge_filings()` (`edgar_warehouse/silver_store.py`), which walks a *tracked
company's* bulk-fetched `submissions.json` history — an issuer-centric,
CIK-scoped write path. Ownership-document parsing
(`edgar_warehouse/parsers/ownership.py`) is a *separate* ingestion pass keyed
off the filer/accession, not the issuer's own submissions history, and it
never requires the issuer to be a tracked company at all. So any Form 3/4/5
whose issuer was never bootstrapped as a tracked company (e.g. an insider
filing against a company nobody ever ran `bootstrap`/`load_history` for)
produces `sec_ownership_reporting_owner`/`sec_ownership_non_derivative_txn`/
`sec_ownership_derivative_txn` rows with **no** corresponding
`sec_company_filing` row — not "eventually consistent," genuinely never
populated for that accession under this design. `run_persons()` and
`run_securities()` selected their candidate rows via `INNER JOIN
sec_company_filing f ON <table>.accession_number = f.accession_number`
purely to recover `issuer_cik` (a nice-to-have for downstream resolution,
not a hard requirement — both `PersonResolver.resolve_one` and
`SecurityResolver.resolve_one`/the security bulk-prefetch path already treat
`issuer_cik`/`issuer_entity_id` as optional), so the INNER JOIN silently and
permanently excluded these rows from the resolver's candidate set on every
single `mdm run`, forever — not deferred, not logged, not retried.

**Fix:** changed `INNER JOIN sec_company_filing` to `LEFT JOIN
sec_company_filing` in three places: `run_persons()` and both sub-queries
inside `run_securities()` (`edgar_warehouse/mdm/pipeline.py`). `issuer_cik`
now resolves to `NULL` for an untracked issuer instead of dropping the row;
both resolvers already handle a `NULL`/`None` issuer correctly (person: no
CIK-based issuer scoping needed for core matching; security: an explicit
NULL-issuer resolution path already existed). The existing `--cik`/
`issuer_ciks` explicit-filter path in `run_persons()` (`AND f.cik IN
(...)`) still works correctly under `LEFT JOIN`, since a `NULL` never
satisfies `IN (...)` — an explicitly CIK-scoped run still excludes
untracked issuers as intended; only the default unscoped run now picks them
up.

**Same pattern found and fixed in a second place, not just the two
resolvers:** `edgar_warehouse/mdm/coverage.py`'s `person_silver`/
`security_silver` counts (used by `mdm coverage-report`) had the identical
`JOIN sec_company_filing` bug, explicitly commented in that file as
mirroring `run_persons`/`run_securities`. Left as INNER JOIN, `mdm
coverage-report` would have kept reporting an artificially *low* "expected"
silver count for these two domains — masking exactly the gap this ticket
fixes, since the coverage report's own denominator excluded the same rows
the resolvers were dropping. Fixed identically (`LEFT JOIN`).

**Checked for the same pattern elsewhere in the codebase, deliberately left
unfixed (out of scope for this ticket):** the exact `JOIN sec_company_filing`
condition also appears in `edgar_warehouse/serving/source_dimensional_export.py`
(12 occurrences total: 9 plain `JOIN`/INNER JOIN that could hide the same
silent-exclusion shape, plus 3 already `LEFT JOIN`, pre-existing and
unrelated to this ticket) and `edgar_warehouse/application/relationship_bulk_load.py`
(1 occurrence, INNER JOIN). Neither is part of the MDM entity-resolution path this
ticket is scoped to — the first feeds the source-layer dimensional export
consumed by dbt (a different consumer with its own semantics for what an
"unmatched" row means there), the second is relationship *derivation*
(`_derive_is_insider`, `_derive_holds`, `_derive_company_holds` in
`pipeline.py` itself also have 5 more occurrences of this join, all
correctly left as INNER JOIN — relationship derivation genuinely needs both
real entities to exist, unlike entity *resolution*). Whether either of
those two files' occurrences hides an analogous silent-exclusion bug is a
real open question, but a distinct one from this ticket's scope; flagging
here rather than fixing opportunistically.

**Regression tests:** two new tests in
`tests/mdm/test_source_to_mdm_load_path.py`
(`test_run_persons_resolves_owner_with_no_filing_match`,
`test_run_securities_resolves_txn_with_no_filing_match`), plus a new fixture
accession (`0009999999-24-000099`) in `_create_silver_fixture()` with
deliberately no matching `sec_company_filing` row — reproducing the live
prod shape. Both tests failed (red) before the fix, confirming the
reproduction, and pass (green) after. One collateral fixture-driven failure
surfaced and was fixed along the way: `TestCoverageReport::
test_zero_gap_against_complete_fixture` broke once the new fixture row
existed, exposing `coverage.py`'s identical bug (see above) — fixed
identically. A second, transient collateral issue surfaced *after* that:
the new fixture row's `security_title` was initially `"Common Stock"`,
which happens to collide with the *existing* fixture's `sec_company`-backed
security row's title. `SecurityResolver` groups concurrent resolution by
canonical title and has an intentional "claim/upgrade a NULL-issuer
security" merge path (`edgar_warehouse/mdm/resolvers/security.py`,
`resolve_one`) — with two rows sharing a title but only one row having a
resolved issuer, whichever row's `UNION ALL SELECT DISTINCT` fetch order
(unordered, not guaranteed stable in DuckDB) processes *second* claims/
merges into the entity the first row created, regardless of issuer. That
made `TestCoverageReport::test_zero_gap_against_complete_fixture` flaky
(passed in isolation, occasionally failed under the full suite) — not a bug
this ticket introduced or is scoped to fix, just an accidental title
collision in the new fixture row exercising it. Fixed by giving the new
fixture row a distinct title (`"Untracked Co Common Stock"`), which keeps
the regression test focused purely on the JOIN-gap fix without touching
`SecurityResolver`'s separate, pre-existing, order-sensitive merge
behavior. Re-ran the affected test 5× and the full `tests/mdm/` directory
2× after the title fix with zero failures.

**Full suite:** green — `2226 passed, 4 skipped` plus the 2 pre-existing,
already-documented, unrelated `test_bootstrap_dbt_snowflake_secret.py`
failures (same 2 failures present on every full-suite run this session,
predating this ticket).
