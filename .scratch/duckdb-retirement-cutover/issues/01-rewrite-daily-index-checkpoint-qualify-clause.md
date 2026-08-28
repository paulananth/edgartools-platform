# 01 — Rewrite the One Surviving `QUALIFY` Clause to SQLite-Compatible Form

**What to build:** `silver_store.py`'s `merge_daily_index_filings` writes
`stg_daily_index_filing` via a `QUALIFY ROW_NUMBER() OVER (PARTITION BY
business_date, accession_number ORDER BY seq DESC) = 1` clause — DuckDB-only
syntax, no SQLite equivalent. Of the 13 `QUALIFY` clauses found across
`silver_store.py` (DuckDB Retirement map, Ticket 05's decision), this is the
**only one** in a method that survives the cutover: the other 12 live in
content-merge methods (`merge_filings`, `merge_adv_filings`,
`merge_adv_private_funds`, `merge_financial_facts`,
`merge_financial_derived`) that are deleted outright once the write path
stops targeting DuckDB — rewriting those would be wasted work.

Rewrite this one clause into the equivalent `WHERE rn = 1` form using an
explicit `ROW_NUMBER()` subquery/CTE, and prove it's semantically identical
against real `stg_daily_index_filing_bulk` data (not just a syntax check) —
same row selected, same tie-breaking on `seq DESC`, same `ON CONFLICT
(business_date, accession_number) DO UPDATE SET ...` behavior downstream.

This is a prerequisite for [Ticket 07](07-complete-sqlite-test-port.md)'s
SQLite port, not the port itself — it just removes the one syntax blocker
standing in the way of that method's tests running under SQLite at all.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The `QUALIFY` clause in `merge_daily_index_filings` is rewritten to
      `WHERE rn = 1` form
- [ ] A test proves the rewritten query selects the identical row (same
      `business_date`/`accession_number` pair, same tie-break on `seq DESC`)
      as the original `QUALIFY` form, against a fixture with real duplicate
      rows
- [ ] The `ON CONFLICT` upsert behavior downstream of the rewritten SELECT is
      unchanged (existing tests covering `stg_daily_index_filing` writes
      still pass)
- [ ] Confirmed via grep: no other `QUALIFY` clause remains in any method
      that isn't already scheduled for deletion by the atomic cutover
      ([Ticket 08](08-atomic-write-path-cutover.md))
