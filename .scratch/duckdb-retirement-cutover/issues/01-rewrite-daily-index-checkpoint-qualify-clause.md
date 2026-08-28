# 01 — Rewrite the One Surviving `QUALIFY` Clause to SQLite-Compatible Form

**What to build:** `silver_store.py`'s `merge_daily_index_filings` writes
`stg_daily_index_filing` via a `QUALIFY ROW_NUMBER() OVER (PARTITION BY
business_date, accession_number ORDER BY seq DESC) = 1` clause — DuckDB-only
syntax, no SQLite equivalent. **Corrected count during implementation**: a
direct grep of `silver_store.py` found **11** real `QUALIFY ROW_NUMBER`
clauses (not the 13 estimated by DuckDB Retirement's Ticket 05), across 6
methods. This is the **only one** in a method that survives the cutover: the
other 10 live in content-merge methods (`merge_filings` x2, `merge_adv_filings`
x2, `merge_adv_private_funds` x2, `merge_financial_facts` x2,
`merge_financial_derived` x2) that are deleted outright once the write path
stops targeting DuckDB — rewriting those would be wasted work. (A 12th real
clause exists outside `silver_store.py`, in `source_dimensional_export.py`'s
`_build_fact_ownership_holding_snapshot` — one of the 23 orphaned Gold
builders the `dbt-gold-silver-rewiring` chain deletes; irrelevant to this
ticket's SQLite-test-port concern since gold builders never ran under the
local test suite this way. A 13th, in `mdm/snowflake_graph.py`, runs against
Snowflake, which supports `QUALIFY` natively — also irrelevant here.)

Rewrite this one clause into the equivalent `WHERE rn = 1` form using an
explicit `ROW_NUMBER()` subquery/CTE, and prove it's semantically identical
against real `stg_daily_index_filing_bulk` data (not just a syntax check) —
same row selected, same tie-breaking on `seq DESC`, same `ON CONFLICT
(business_date, accession_number) DO UPDATE SET ...` behavior downstream.

This is a prerequisite for [Ticket 09](09-complete-sqlite-test-port.md)'s
SQLite port, not the port itself — it just removes the one syntax blocker
standing in the way of that method's tests running under SQLite at all.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] The `QUALIFY` clause in `merge_daily_index_filings` is rewritten to
      `WHERE rn = 1` form, via a `FROM (SELECT ..., ROW_NUMBER() OVER (...)
      AS rn FROM stg_daily_index_filing_bulk) ranked WHERE rn = 1` derived
      table — a plain derived-table subquery rather than a `WITH` CTE
      placed before `INSERT`, to sidestep any doubt about CTE-in-INSERT
      placement portability across DuckDB and SQLite
- [x] A new test, `test_merge_daily_index_filings_dedupes_same_key_rows_within_one_batch`
      (`tests/unit/test_daily_index_filing_merge.py`), proves the rewritten
      query selects the identical row (same `business_date`/`accession_number`
      pair, same tie-break on `seq DESC`, highest-seq wins) as the original
      `QUALIFY` form — run against the pre-rewrite code first to confirm it
      passed as a baseline, then re-run unchanged after the rewrite to prove
      equivalence, not just correctness in isolation. Additionally hand-verified
      the exact rewritten SQL shape against Python's stdlib `sqlite3` module
      directly (outside the test suite, since SQLite isn't this table's
      target yet) to confirm the derived-table + `ROW_NUMBER()` +
      `ON CONFLICT ... DO UPDATE` shape is valid, portable syntax ahead of
      Ticket 09's actual port.
- [x] The `ON CONFLICT` upsert behavior downstream of the rewritten SELECT is
      unchanged — all 3 existing tests in `test_daily_index_filing_merge.py`
      (upsert-updates-existing-row, the new dedup test, and the
      thousands-of-rows perf regression guard) pass unchanged. Full repo
      suite green: 2706 passed, 4 skipped.
- [x] Confirmed via grep: no other `QUALIFY` clause remains in any method
      that isn't already scheduled for deletion by the atomic cutover
      ([Ticket 10](10-atomic-write-path-cutover.md)) — the 10 remaining
      `silver_store.py` clauses are all in the 5 content-merge methods
      named above.
