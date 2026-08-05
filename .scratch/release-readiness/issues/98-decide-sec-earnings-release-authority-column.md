# Fix sec_earnings_release (and 8 sibling tables') dead authority_column

Type: task
Status: resolved

## Question (as originally framed — corrected below)

Ticket 42's F5 scale-mismatch fix (PR #355, hardened by PR #356) is correct and safe as
deployed, but its re-run against the 20 sample CIKs failed to publish with
`30 ambiguous same-key conflict(s) block publication` on `sec_earnings_release`'s
`revenue_gaap`/`net_income_gaap`. Originally framed this as "the table has no
`authority_column`, needs a strategy decided" — mirroring ticket 97's shape. **That premise
was wrong** — checked live and corrected before implementing anything.

## Root cause (found by reading the registry directly, not assuming)

`sec_earnings_release` **already declares** `authority_column="ingested_at"`
(`silver_protection.py:216`) — in fact **all 9** fundamentals/relationship tables do
(`sec_financial_fact`, `sec_financial_derived`, `sec_earnings_release`, `sec_accounting_flag`,
`sec_executive_record`, `sec_thirteenf_holding`, `sec_thirteenf_filing`, `sec_employment_event`,
`sec_guidance_fact`). This is a completely different bug shape from ticket 97
(`sec_filing_attachment` genuinely had no authority_column at all).

`_resolve_conflict` (`silver_protection.py:778`) requires the candidate's authority-column
value to be **strictly greater** than canonical's for the candidate to win; an exact tie is
still ambiguous. Every one of these 9 tables' merge functions (`silver_store.py`) INSERTs via
`... ON CONFLICT (...) DO UPDATE SET <business columns>`, and **none of the 9 `DO UPDATE SET`
clauses listed `ingested_at`** — confirmed by direct grep, not inferred. The DDL's
`ingested_at TIMESTAMPTZ DEFAULT NOW()` only applies `DEFAULT` on `INSERT`; DuckDB (like
standard SQL) never re-applies a column default during `ON CONFLICT ... DO UPDATE`. So
re-processing an *existing* row (a genuine parser fix, exactly ticket 42/97's F5 scenario)
silently updated the business columns while leaving `ingested_at` frozen at whatever it was on
first insert — forever, no matter how many times the row is legitimately re-parsed.

At publish time this meant: canonical's `ingested_at` and the freshly-re-parsed candidate's
`ingested_at` were **identical** (neither had ever been bumped), so `_resolve_conflict` always
landed on the tie branch — ambiguous, blocking publication — regardless of how much later, or
how much more correct, the candidate's actual values were. Confirmed live 2026-08-05: this is
exactly what blocked republishing the corrected (now-nulled) F5 values for the 20 sample CIKs.

`update_accounting_flag_scores` (a separate direct-`UPDATE` backfill path on
`sec_accounting_flag`, not going through the merge-row helpers) had the identical omission.

## Fix

`edgar_warehouse/silver_store.py`: added `ingested_at = now()` to all 9 affected
`ON CONFLICT ... DO UPDATE SET` clauses (`merge_financial_facts`, `merge_financial_derived`,
`merge_earnings_releases`, `merge_guidance_facts`, `merge_accounting_flags`,
`merge_executive_records`, `merge_employment_events`, `merge_thirteenf_holdings`,
`merge_thirteenf_filings`) plus the standalone `update_accounting_flag_scores` UPDATE. No schema
change, no new decision, no strategic tradeoff — this restores the behavior the
`authority_column="ingested_at"` declaration already implied and every DDL comment already
promised ("the row's ingestion time"), which had simply never been wired into the UPDATE path.

Confirmed via grep that no other write path to these 9 tables exists that could have been
missed (every `INSERT INTO <table>` site in `silver_store.py` accounted for).

## Validation

- `tests/unit/test_silver_store_ingested_at_bump.py` (10 tests, one per write path, covering
  both the simple-upsert and bulk-staged-upsert merge helpers): each inserts a row, re-merges the
  same key with a genuinely different value, and asserts `ingested_at` strictly increases.
  Confirmed via `git stash` to fail with byte-identical timestamps pre-fix (all 10), pass
  post-fix.
- `tests/application/test_warehouse_orchestrator_mdm.py::test_merge_lets_fresher_authority_timestamp_republish_corrected_gaap_values`:
  end-to-end `merge_candidate_into_canonical` test proving a candidate with a genuinely later
  `ingested_at` now wins outright and republishes the corrected `revenue_gaap`, instead of
  raising `SemanticMergeConflictError` — the exact live scenario.
- Full suite (`tests/unit tests/application tests/architecture tests/mdm`) green, no
  regressions (verification in progress as of this write-up).

## Impact

Not a strategy decision after all — a straightforward, mechanically-scoped bug fix.

**Done — confirmed live 2026-08-05.** Merged (PR #357, `071f93df`), warehouse image rebuilt
(digest `sha256:1e967d73a6442c7fb21aaa6cd5515be51bf7cba3fcc22aaad8a845b78d0d5507`, confirmed via
`docker run` that `merge_earnings_releases`'s source contains `ingested_at = now()`), deployed
to prod (`edgartools-prod-large:136`). Re-ran ticket 42's exact 20-CIK per-filing sample a third
time (`ticket42-perfiling-authorityfix-1785928000`, ECS `c430e507cab44ab09006b8a5be0e8c8f`):
**exited 0**, `silver_database_uploaded: true` — the first successful publish of corrected F5
data across 3 total per-filing attempts. Live `silver_table_merged` event for
`sec_earnings_release`: `rows_updated: 30` (candidate correctly won the authority-timestamp
comparison, no longer ambiguous).

Downloaded the freshly-published canonical and verified directly: Avery Dennison's
`revenue_gaap` (defect #1, row-classification) is now `NULL` with a fresh `ingested_at`, not
the wrong `2298.5` value; Oxford Industries' `net_income_gaap` (defect #2's sibling, row-
selection) is likewise `NULL`, not the earlier `$500,000,000,000` corruption. 104 rows remain
flagged as suspicious across the sample — confirmed these are exactly the known, documented,
out-of-scope defect #2 (upstream edgartools scale-detection-miss, e.g. Crown Crafts/CIK 25895,
Louisiana-Pacific/CIK 60519) — same CIKs as originally found, correctly left untouched (no
reliable signal to safely act on), not a new regression.

`load_history`'s full-universe run is no longer at risk of the silent-partial-publish-failure
mode described in ticket 42's readiness assessment — confirmed no running executions on any
lease-sharing state machine as of this entry.
