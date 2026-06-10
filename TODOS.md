# TODOS

Outstanding items surfaced during reviews or planning. Each entry has enough
context to act without re-reading the source session.

---

## INSTITUTIONAL_HOLDS full-universe sync: batch-by-CIK-range to avoid OOM

**What:** Before writing the Phase 6 full-universe sync plan (06-03), design a
batched-read strategy for `INSTITUTIONAL_HOLDS` that reads `sec_thirteenf_holding`
in CIK-range chunks instead of a single `silver.fetch()` call.

**Why:** `SilverDatabase.fetch()` returns `list[dict]` — all rows in memory at
once. `sec_thirteenf_holding` is the largest silver table: large fund managers
(Vanguard, BlackRock) report tens of thousands of positions per quarter. With
multiple years of fundamentals silver data, a full scan could be 10M+ rows
in a single list. ECS task memory limits make this a realistic OOM risk.

**Where:** `edgar_warehouse/mdm/pipeline.py:_derive_institutional_holds` uses
`_fetch_optional_relationship_rows`, which calls `silver.fetch(sql)` with no
chunking. The `_bounded_relationship_sql` helper only applies LIMIT when
`remaining` is not None.

**Fix approach:** Add a CIK-range batch loop in `_derive_institutional_holds`
that queries `sec_thirteenf_holding WHERE cik BETWEEN ? AND ?` in configurable
increments (e.g., 1000 CIKs per batch). The adviser-entity resolution is
per-CIK, so the ordering requirement doesn't apply — this deriver is safely
batchable.

**Depends on:** Phase 6 06-03 full-universe sync plan (write this before that plan)

**Surfaced:** plan-eng-review 2026-06-06

---

## COMPANY_HOLDS `skipped_corporate` counter: clarify semantic inversion

**What:** Add an inline comment to `_derive_company_holds` in `pipeline.py`
explaining that `skipped_corporate` means "skipped because owner is NOT a
company" — the inverse of how the same counter reads in `_derive_is_insider`
and `_derive_holds` (where it means "skipped because owner IS a company").

**Why:** The 5-counter interface (`skipped_corporate`, `skipped_unresolved_source`,
etc.) is consistent across all derivers. But the semantics of `skipped_corporate`
flip between derivers that want non-corporate owners (IS_INSIDER, HOLDS) and
derivers that want corporate owners (COMPANY_HOLDS). A future reader or AI agent
could misread the counter and think COMPANY_HOLDS is misbehaving.

**Where:** `edgar_warehouse/mdm/pipeline.py:_derive_company_holds` around line 563.

**Fix:** One-line comment: `# skipped_corporate here means non-corporate owner
(inverse of IS_INSIDER — COMPANY_HOLDS wants corporate owners only)`

**Surfaced:** plan-eng-review 2026-06-06

---

## backfill_accounting_flags selects nonexistent forensic-score columns from sec_financial_derived

**Status:** RESOLVED in PR #56 (merged to main as `57d10ba`, 2026-06-10).

**What:** `backfill_accounting_flags` (`edgar_warehouse/parsers/accounting_flags.py:51-64`)
runs a `SELECT` against `sec_financial_derived` that includes
`beneish_m_score, altman_z_score, piotroski_f_score`. These columns do not
exist on `sec_financial_derived` — the table DDL
(`edgar_warehouse/silver_store.py` around line 437) explicitly notes forensic
scores live exclusively on `sec_accounting_flag` and are intentionally not
denormalised onto `sec_financial_derived`.

**Why:** DuckDB raises a `BinderException` (referenced column not found) the
moment this query runs, so `backfill_accounting_flags` fails for every CIK
that reaches the post-processing step in `bootstrap_fundamentals`
(`edgar_warehouse/application/commands/bootstrap_fundamentals.py:126-130`).
Forensic scores (Beneish M, Altman Z, Piotroski F) are never backfilled.

**Where:**
- `edgar_warehouse/parsers/accounting_flags.py:51-64` — the offending SELECT.
- `edgar_warehouse/silver_store.py:~437-441` — DDL comment confirming the
  columns are intentionally absent from `sec_financial_derived`.

**Fix approach:** Drop `beneish_m_score, altman_z_score, piotroski_f_score`
from the `sec_financial_derived` SELECT in `accounting_flags.py`. The `prev`
row's prior-period values for these scores (used as fallbacks via
`row.get("beneish_m_score")` etc. at lines 77/80/85) should instead be sourced
from `sec_accounting_flag` (the table that actually carries them), via a
second query or a join — needs design before implementing.

**Surfaced:** merge-perf differential testing, 2026-06-10 (observation #1156, #1160)

---

## sec_financial_fact PK omits period_end — same-period restatements collide and silently drop ~58% of facts

**Status:** AUDITED 2026-06-10 — confirmed GENUINE DATA CORRUPTION, not expected
dedup. Fix needs design + migration; not yet implemented.

**Audit results** (real Apple/CIK 320193 companyfacts data, 24,195 raw fact rows,
script `/tmp/audit_period_end_collision.py`, since deleted):

- 10,227 distinct PK groups `(cik, accession_number, concept, fiscal_period,
  segment)`; 8,784 (85.9%) have >1 raw row.
- Of those collisions, 8,733 (99.4%) have IDENTICAL `fiscal_year` but
  DIFFERENT `period_end` — these are the "current period" vs "comparative
  prior-period" instant-fact pairs that XBRL balance sheets report side by
  side (e.g. `AccountsPayableCurrent` reported for both the current
  quarter-end AND the prior fiscal year-end, same `accn`/`fy`/`fp`).
- 8,500 of 8,784 colliding groups (96.8%) produce a stored row whose
  `(period_end, value)` pair matches **NEITHER** raw observation — the
  bulk merge takes `period_end` from the first-seen row (chronologically the
  prior-period comparative) and `value` from the last-seen row (the current
  period's value), via `_merge_rows_bulk`'s split first/last UPSERT
  (`silver_store.py:2040-2068`, `period_end` is set by `insert_first_sql` and
  never updated by `insert_last_sql`'s `DO UPDATE SET`). Example:
  `accn=0001193125-09-153165 concept=AccountsPayable fp=Q3` has raw rows
  `(fy=2009, end=2008-09-27, val=5.52B)` and `(fy=2009, end=2009-06-27,
  val=4.854B)` — the stored row is `(end=2008-09-27, val=4.854B)`, a pairing
  that was never reported by Apple.
- **Adding `period_end` to the PK** resolves 89% of the corruption: 24,195
  raw rows -> 21,755 PK groups, collisions drop from 8,784 to 2,440.
- The remaining 2,440 residual collisions: 2,423 have differing `value` for
  the same `(accn, concept, fp, segment, period_end)` — these are
  duration-concept QTD-vs-YTD pairs (e.g.
  `AntidilutiveSecuritiesExcludedFromComputationOfEarningsPerShareAmount`
  reported for both a 3-month and 6-month window ending on the same date).
  Disambiguating these needs `period_start` (currently NOT captured by
  `_extract_financial_fact_row` in `parsers/financials.py:139-170` — `fact.get("start")`
  is dropped). Only 17 residual collisions are exact duplicates (harmless).

**Recommended fix (two-stage, needs design sign-off before implementing):**
1. Capture `period_start` in `_extract_financial_fact_row` (new nullable
   column on `sec_financial_fact`).
2. Extend PK to `(cik, accession_number, concept, fiscal_period, segment,
   period_end, period_start)` (or `period_start` nullable + `COALESCE` to a
   sentinel for instant facts where `start` is absent).
3. `sec_financial_derived` has the analogous issue — its PK
   `(cik, accession_number, fiscal_period)` collapses the same
   `(fy, period_end)` groups that `compute_derived_for_accession`'s caller
   already groups by (`fundamentals_ingest.py:200-208`); the derived PK needs
   `period_end` (and likely `fiscal_year`) added too.
4. **Migration**: existing `sec_financial_fact`/`sec_financial_derived` rows
   already contain Frankenstein pairings — a schema PK change alone won't fix
   stored data. Re-bootstrapping (`bootstrap-fundamentals --mode entity-facts
   --force`) per CIK is the simplest correct fix since SEC data is
   re-fetchable and idempotent per CLAUDE.md.

**What:** `sec_financial_fact`'s primary key is
`(cik, accession_number, concept, fiscal_period, segment)`
(`edgar_warehouse/silver_store.py:404`) — it does not include `period_end`.
When a single accession's XBRL data contains multiple facts for the same
`(concept, fiscal_period, segment)` but with *different* `period_end` dates
(common for comparative-period restatements in 10-Q/10-K filings — e.g. a
Q3 filing reporting both the current-quarter and a restated prior-year
quarter under the same `fiscal_period` label), those rows collide on the PK
and only one survives.

**Why:** Confirmed empirically via the merge-perf differential test on real
Apple (CIK 320193) `companyfacts` data: 24,195 raw fact rows reduce to
10,227 stored rows after merge — a ~58% reduction. Spot-checked rows show
the *value* is preserved correctly (last-write-wins, by design) but the
*period_end* recorded against that value can belong to a different filing's
period than the value itself — e.g.
`(320193, '0000320193-17-000009', 'Q3', 'AccountsPayableCurrent', value=31915000000.0)`
is stored with `period_end=2016-09-24` even when other rows in the same
batch carry `period_end=2017-07-01` for the same PK. Downstream consumers
joining on `period_end` for this PK get a mismatched value/period pairing.

**Where:** `edgar_warehouse/silver_store.py:404` (PK definition) and the
`merge_financial_facts` UPSERT logic that depends on it
(`edgar_warehouse/silver_store.py:2020-2078`).

**Fix approach:** Needs design discussion — likely either (a) add
`period_end` to the PK (changes UPSERT/dedup semantics significantly, may
need a migration for existing data), or (b) determine whether the ~58%
"duplicates" are actually the *same* economic fact reported under multiple
accessions/periods (in which case current behavior may be correct and the
58% figure is expected dedup, not data loss) — confirm with a sample audit
before deciding the PK needs to change.

**Surfaced:** merge-perf differential testing, 2026-06-10 (observation #1198)
