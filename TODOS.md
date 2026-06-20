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

**Status:** Stage 1 MERGED to main 2026-06-11 (commits `f1d9eea`, `7226630`, PR #57
/ `8481e6e`). A schema-migration gap in the merged code, flagged by code review
post-merge, is now RESOLVED — see "Stage 1 follow-up: schema migration gap
(RESOLVED)" below. Stage 2 (period_start, residual 2,440 collisions) is now
RESOLVED — see "Stage 2 resolution summary" below. Stage 3 (export/Snowflake
MERGE path doesn't carry `period_start`, so gold can still collapse the QTD/YTD
rows Stage 2 preserves in silver) is now RESOLVED — see "Stage 3 resolution
summary" below. Stage 4 (`SEC_FINANCIAL_DERIVED`'s Snowflake `mergeKeys` omit
`period_end`, same shape of gap as Stage 3 but for the derived table) is now
RESOLVED — see "Stage 4 resolution summary" below. Stage 5
(`financial_derived.sql`'s YoY `lag()` windows had non-deterministic ordering
once a single accession could contribute current + comparative rows) is now
RESOLVED — see "Stage 5 resolution summary" below.

**Stage 1 resolution summary:**
- Added `period_end` to the PK of `sec_financial_fact`
  (`cik, accession_number, concept, fiscal_period, segment, period_end`) and
  `sec_financial_derived` (`cik, accession_number, fiscal_period, period_end`)
  (`edgar_warehouse/silver_store.py`, commit `f1d9eea`).
- Updated `merge_financial_facts`/`merge_financial_derived`'s bulk-staging
  `QUALIFY ROW_NUMBER() OVER (PARTITION BY ...)` and `ON CONFLICT (...)` clauses
  to include `period_end` (commit `7226630`).
- Differential test against real Apple (CIK 320193) companyfacts: row count
  went from 10,227 -> 21,755 (matches audit prediction exactly). The
  `AccountsPayable accn=0001193125-09-153165 fp=Q3` example now correctly
  splits into two rows: `(period_end=2008-09-27, value=5.52e9)` and
  `(period_end=2009-06-27, value=4.854e9)`.
- Migration: checked the dev S3 `silver.duckdb` (monolith) and the 4 CIK-range
  shard files. `sec_financial_fact`/`sec_financial_derived` had 0 rows
  everywhere (the halted 100-CIK benchmark never persisted entity-facts data),
  so no re-bootstrap was needed. Dropped + recreated the two empty tables in
  the monolith with the new PK and re-uploaded to S3. Shards don't have these
  tables yet — they'll be created fresh with the new PK on first write.

**Stage 2 resolution summary:**
- Added `period_start DATE NOT NULL` to `sec_financial_fact`, with a sentinel
  `0001-01-01` (`_INSTANT_FACT_PERIOD_START_SENTINEL`) for "instant" facts
  (balance-sheet concepts) whose SEC companyfacts JSON has no `"start"` key
  (`edgar_warehouse/parsers/financials.py`, `edgar_warehouse/silver_store.py`).
- Extended `sec_financial_fact`'s PK to `(cik, accession_number, concept,
  fiscal_period, segment, period_end, period_start)`. New
  `_migrate_financial_fact_period_start_pk()` (called from
  `_ensure_schema_evolution()`, same drop+recreate pattern as Stage 1's
  `_migrate_financial_period_end_pk()`) handles stores created on the Stage 1
  PK (period_end but no period_start).
- `merge_financial_facts`'s staging table, `QUALIFY ROW_NUMBER() OVER
  (PARTITION BY ...)`, and `ON CONFLICT (...)` clauses extended with
  `period_start`; rows without an explicit `period_start` fall back to the
  same sentinel.
- `sec_financial_derived`'s PK was NOT changed — it already includes
  `period_end` from Stage 1, which is sufficient (this supersedes/corrects
  original "Recommended fix" step 3 below, written before Stage 1 landed).
  However, a real downstream issue was found and fixed: a single
  `(accn, fiscal_period, period_end)` group passed to
  `compute_derived_for_accession` can now legitimately contain BOTH a QTD
  (e.g. "3 months ended") and YTD (e.g. "6 months ended") row for the same
  duration concept (same `period_end`, different `period_start`). The
  fact_map build in `edgar_warehouse/parsers/financials_derived.py` now
  prefers the row with the LATEST `period_start` (shortest/incremental
  duration) per concept, instead of first-value-seen — avoiding
  nondeterministic QTD/YTD flip-flop in `sec_financial_derived` based on JSON
  iteration order.
- Migration: no re-bootstrap needed (dev `sec_financial_fact` tables were
  empty after Stage 1's drop+recreate); the new PK applies on first write.
- Tests: `tests/unit/test_silver_store_schema_migration.py` gained 2 tests
  (Stage-1-PK store migrates to add `period_start` to the PK and drops old
  rows; `merge_financial_facts` upserts a QTD/YTD pair sharing every Stage 1
  PK column as two distinct rows post-migration). New
  `tests/unit/test_financials_period_start.py` (4 tests): `period_start`
  capture for duration facts, sentinel for instant facts, and
  `compute_derived_for_accession`'s QTD-preference (and no-op when only one
  duration is present).

**Stage 1 follow-up: schema migration gap (RESOLVED)**

**What:** `edgar_warehouse/silver_store.py:408`'s `CREATE TABLE IF NOT EXISTS`
DDL for `sec_financial_fact`/`sec_financial_derived` does not migrate
pre-existing tables created with the OLD PK (pre-PR-#57:
`(cik, accession_number, concept, fiscal_period, segment)` /
`(cik, accession_number, fiscal_period)`, no `period_end`). `IF NOT EXISTS`
is a no-op against an existing table, so its constraint stays the old PK,
while `merge_financial_facts`/`merge_financial_derived`'s
`ON CONFLICT (..., period_end)` clauses (added in `7226630`) assume the new
PK exists.

**Why:** Flagged as `[P1]` by `codex review` against the merged diff
(`codex/main-sync` PR #59 review pass, 2026-06-11): "For any existing
`silver.duckdb` where these tables were already created with the old primary
key, ... the new `ON CONFLICT (..., period_end)` targets ... are then not
backed by a unique/primary-key constraint and DuckDB raises a binder error on
the first financial merge." This session's dev S3 monolith was manually
drop-recreated (see resolution summary above) and is fine, but any OTHER
environment (other dev shards once they get these tables, prod, a fresh
clone of an older `silver.duckdb`) will hit a `BinderException` on the first
`merge_financial_facts`/`merge_financial_derived` call after pulling PR #57.

**Where:**
- `edgar_warehouse/silver_store.py:408` (and the analogous
  `sec_financial_derived` DDL) — `CREATE TABLE IF NOT EXISTS` with the new PK.
- `edgar_warehouse/silver_store.py:2020-2078` — `merge_financial_facts`/
  `merge_financial_derived` `ON CONFLICT (..., period_end)` clauses that
  require the new PK to exist as a real constraint.

**Fix approach:** Add a schema-evolution check on `SilverDatabase` init (or a
dedicated migration step) that detects `sec_financial_fact`/
`sec_financial_derived` tables with the OLD PK (e.g. via
`PRAGMA table_info`/`duckdb_constraints()`) and drop+recreates them with the
new PK — same drop+recreate already done manually for the dev monolith this
session, but automated so it runs wherever `SilverDatabase` opens an
older-PK store. Drop+recreate is safe per CLAUDE.md SEC-data-idempotency
(re-bootstrappable), but the migration must run BEFORE the first
`merge_financial_facts`/`merge_financial_derived` call, not be left as a
manual per-environment step.

**Resolution:** Implemented in `edgar_warehouse/silver_store.py`:
`_ensure_schema_evolution()` now calls a new
`_migrate_financial_period_end_pk()`, which queries
`duckdb_constraints()` for each of `sec_financial_fact`/
`sec_financial_derived`. If a table exists and its `PRIMARY KEY` does not
include `period_end`, it logs a `WARNING` and `DROP TABLE`s it; `_DDL`
(already `CREATE TABLE IF NOT EXISTS`) then recreates it with the
period_end-inclusive PK. Runs automatically on every `SilverDatabase.__init__`,
before any merge call, and is a no-op once a store has the new PK. Covered by
`tests/unit/test_silver_store_schema_migration.py` (3 tests: migration drops
old-PK rows + adds `period_end` to PK, `merge_financial_facts` succeeds
post-migration on the exact collision shape from the codex finding, and a
fresh/already-migrated store is a silent no-op).

**Surfaced:** `codex review` of PR #59 diff (`codex/main-sync` vs `main`),
2026-06-11.

---

**Stage 3 resolution summary:**
- `_SEC_FINANCIAL_FACT_SCHEMA` (`edgar_warehouse/serving/gold_models.py`) gains
  `period_start` (`date32`, `nullable=False`, matching silver's
  `DATE NOT NULL` with the `0001-01-01` sentinel).
- `_build_sec_financial_fact()`'s SELECT and `ORDER BY` now include
  `period_start` alongside `period_end`.
- `infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql`'s
  `mergeKeys.SEC_FINANCIAL_FACT` extended to
  `["CIK", "ACCESSION_NUMBER", "CONCEPT", "FISCAL_PERIOD", "SEGMENT", "PERIOD_END", "PERIOD_START"]`
  (the comment at the top of the file is updated to match).
- `infra/snowflake/sql/bootstrap/01_source_stage.sql`'s
  `EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` `CREATE TABLE IF NOT EXISTS` DDL gains
  `period_start DATE NOT NULL DEFAULT '0001-01-01'`, plus an idempotent
  `ALTER TABLE SEC_FINANCIAL_FACT ADD COLUMN IF NOT EXISTS period_start DATE
  NOT NULL DEFAULT '0001-01-01'` for already-deployed tables — Snowflake
  backfills existing rows with the sentinel, so this is non-destructive.
  `PERIOD_END` was already a column on this table (added for Stage 1's
  PyArrow schema but never in the MERGE keys); it is now also part of the
  MERGE keys above. It remains nullable in the DDL — making it `NOT NULL`
  would require confirming no existing rows have a NULL `period_end`, which
  is a separate, lower-priority follow-up (the Stage-1-era DDL gap).
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_facts.sql` (a
  straight passthrough `select`, no grouping) now selects `period_start` too,
  and its grain comment is updated to
  `(cik, accession_number, concept, fiscal_period, segment, period_end,
  period_start)`. `gold.yml`'s `financial_facts` description updated to match.
- Tests: new `tests/unit/test_gold_models_financial_fact.py` — a QTD/YTD pair
  sharing every column except `period_start`/`value` round-trips through
  `_build_sec_financial_fact()` as two distinct rows with the correct
  `period_start`/`value` pairing, against `_SEC_FINANCIAL_FACT_SCHEMA`; plus an
  empty-table case.
- **Remaining (live-validation, not done here):** re-export Apple CIK 320193
  and confirm a real QTD/YTD pair survives the Snowflake MERGE into
  `EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` as two rows (requires live Snowflake
  creds, not available in this session).
---

**Stage 4 resolution summary:**
- `infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql`'s
  `mergeKeys.SEC_FINANCIAL_DERIVED` extended from
  `["CIK", "ACCESSION_NUMBER", "FISCAL_PERIOD"]` to
  `["CIK", "ACCESSION_NUMBER", "FISCAL_PERIOD", "PERIOD_END"]` (comment at the
  top of the file updated to match). `_SEC_FINANCIAL_DERIVED_SCHEMA` and
  `_build_sec_financial_derived()` already selected `period_end` (Stage 1), so
  no Python/PyArrow change was needed — only the Snowflake MERGE key was
  missing it.
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql`'s
  grain comment updated to
  `(cik, accession_number, fiscal_period, period_end)`; `gold.yml`'s
  `financial_derived` description updated to match.
- `EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED.period_end` remains nullable in the
  DDL (same Stage-1-era nullability gap as `SEC_FINANCIAL_FACT.period_end`,
  item above) — silver guarantees `period_end NOT NULL` so the export always
  carries a real value; no DDL change made here.
- Tests: new `tests/unit/test_gold_models_financial_derived.py` — a
  "current period" + "comparative prior period" row pair sharing
  `(cik, accession_number, fiscal_period)` but differing in `period_end`
  round-trips through `_build_sec_financial_derived()` as two distinct rows
  matching `_SEC_FINANCIAL_DERIVED_SCHEMA`; plus an empty-table case.
- **New follow-up discovered, now RESOLVED (Stage 5):**
  `financial_derived.sql`'s YoY `lag()` windows partition by
  `(cik, fiscal_period)` ordered by `fiscal_year`. Now that a single accession
  can contribute two rows (current + comparative, distinguished by
  `period_end`), if two rows ever share `(cik, fiscal_period, fiscal_year)`
  — e.g. one filing's comparative row and a later filing's current row both
  reporting the same `fiscal_year` — `lag()` ordering between them is
  non-deterministic (no tiebreaker). Needs its own follow-up: either add
  `period_end`/`accession_number` as a `lag()` tiebreaker or de-duplicate to
  one row per `(cik, fiscal_period, fiscal_year)` before windowing.

---

**Stage 5 resolution summary:**
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql`'s
  three `lag(...) over (partition by cik, fiscal_period order by fiscal_year)`
  windows (revenue/ebitda/net_income "prior" values) replaced with a
  `prior_year_values` CTE + `left join`. `prior_year_values` picks ONE
  canonical row per `(cik, fiscal_period, fiscal_year)` via
  `qualify row_number() ... = 1`, ordered by:
  1. `(period_end = max(period_end) over (partition by cik, accession_number,
     fiscal_period)) desc` — prefer the row that is each accession's own
     "current" period (max `period_end` within that accession's filing) over
     a later filing's "comparative" restatement of the same `fiscal_year`.
  2. `accession_number desc` — final tiebreaker (most-recently-filed accession
     wins, e.g. a 10-K/A amendment over the original 10-K).
- `with_growth` then `left join`s `base` to `prior_year_values` on
  `(cik, fiscal_period, fiscal_year - 1)` to compute
  `revenue_yoy_growth`/`ebitda_yoy_growth`/`net_income_yoy_growth` — same
  output columns/semantics as before, but deterministic regardless of how
  many current/comparative rows share a `fiscal_year`.
- File header comment rewritten to document the tiebreaker rationale in place
  of the old "not addressed here" note.
- Verification: `uv run --with dbt-snowflake dbt compile --select
  financial_derived` — Jinja/SQL parses successfully (16 models, 36 data
  tests, 16 sources, 528 macros found); fails only at the live-connection step
  with dummy credentials (expected, no Snowflake creds in this session).
- **Live validation: RESOLVED via T6, 2026-06-13.** Re-ran this dynamic table
  against real `EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` data (Apple, CIK
  320193, 282 rows) containing exactly the current+comparative-row fan-in
  scenario described above (9 `(fiscal_year, fiscal_period, period_end)`
  groups with 2 rows each, spanning 2010-2012). Confirmed not just
  determinism but correctness — Tension 3's underlying point was that
  determinism alone doesn't prove the *values* are right:
  `revenue_yoy_growth`/`ebitda_yoy_growth`/`net_income_yoy_growth` match
  expected real-world Apple YoY figures (e.g. FY2025 revenue $416.16B vs
  FY2024 $391.04B -> ~6.4% growth, matches `revenue_yoy_growth`), and every
  2-row fan-in group produces identical YoY values across both rows. The
  earliest periods (2007-2009, no prior-year comparative available)
  correctly show zero/null YoY. Full run log in the "EDGARTOOLS_DEV_DEPLOYER
  lacks direct SELECT..." section below (T6 entry).

---

<details>
<summary>Stage 3 original analysis (for reference)</summary>

**What:** Stage 2 makes `period_start` part of `sec_financial_fact`'s silver PK
so a QTD row (e.g. "3 months ended 2024-06-30") and a YTD row ("6 months ended
2024-06-30") for the same concept are stored as two distinct rows. But the
export/Snowflake path drops that distinction again:
- `_build_sec_financial_fact()` (`edgar_warehouse/serving/gold_models.py:1112`)
  SELECTs `period_end` but not `period_start` from `sec_financial_fact`.
- `_SEC_FINANCIAL_FACT_SCHEMA` (`edgar_warehouse/serving/gold_models.py:246`)
  has no `period_start` field.
- The Snowflake `SEC_FINANCIAL_FACT` MERGE keys
  (`infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql:51`,
  `["CIK", "ACCESSION_NUMBER", "CONCEPT", "FISCAL_PERIOD", "SEGMENT"]`) include
  neither `PERIOD_END` nor `PERIOD_START` — so a QTD and YTD row exported in the
  same run MERGE onto the same target row, and the later one wins.

**Why:** Without `period_start` (and `period_end`) in the export schema and
MERGE keys, the Stage 2 silver-layer fix doesn't reach
`EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` / gold — the QTD/YTD collision Stage 2
resolves in silver re-appears in gold via the MERGE collapsing one of the two
rows.

**Where:**
- `edgar_warehouse/serving/gold_models.py:246` — `_SEC_FINANCIAL_FACT_SCHEMA`
  (add `period_start`).
- `edgar_warehouse/serving/gold_models.py:1112` — `_build_sec_financial_fact()`
  SELECT list (add `period_start`).
- `infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql:51` —
  `mergeKeys.SEC_FINANCIAL_FACT` (add `PERIOD_END`, `PERIOD_START`).
- `EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` table DDL — add `PERIOD_START` column
  (and confirm `PERIOD_END` exists; it's in the PyArrow schema but not in the
  current MERGE keys either).

**Fix approach:** Mirror Stage 1/2's PK change through the export path: add
`period_start` to the PyArrow schema and builder SELECT, add `PERIOD_END` and
`PERIOD_START` to the Snowflake `SEC_FINANCIAL_FACT` MERGE keys, and add the
corresponding column(s) to the `EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` table DDL.
Needs a differential check against real data (e.g. re-export Apple CIK 320193
sec_financial_fact and confirm the QTD/YTD pair survives into
`EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` as two rows, not one).

**Surfaced:** `codex review` of PR #62 diff (`claude/silver-financial-period-start-pk`
vs `codex/main-sync`), 2026-06-12: "[P2] Carry period_start through the export
path ... the Snowflake MERGE on (CIK, ACCESSION_NUMBER, CONCEPT, FISCAL_PERIOD,
SEGMENT) can collapse one value, so gold still loses the collision this change
is meant to preserve."

</details>

---

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

**Recommended fix (two-stage) — HISTORICAL, see "Stage 2 resolution summary"
above for what was actually implemented.** Step 3 below was superseded:
Stage 1 already added `period_end` to `sec_financial_derived`'s PK, so no
further PK change was needed there; Stage 2 instead fixed
`compute_derived_for_accession`'s fact-map QTD/YTD selection.
1. Capture `period_start` in `_extract_financial_fact_row` (new nullable
   column on `sec_financial_fact`).
2. Extend PK to `(cik, accession_number, concept, fiscal_period, segment,
   period_end, period_start)` (or `period_start` nullable + `COALESCE` to a
   sentinel for instant facts where `start` is absent).
3. ~~`sec_financial_derived` has the analogous issue — its PK
   `(cik, accession_number, fiscal_period)` collapses the same
   `(fy, period_end)` groups that `compute_derived_for_accession`'s caller
   already groups by (`fundamentals_ingest.py:200-208`); the derived PK needs
   `period_end` (and likely `fiscal_year`) added too.~~ (Already done in
   Stage 1; see Stage 2 resolution summary above for the actual fix.)
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

---

## financial_derived YoY tiebreaker approximates filed_date with accession_number desc (Issue 3B, deferred)

**Status:** Deferred, not blocking PR #66 (`claude/financial-derived-lag-tiebreaker`,
Stage 5).

Stage 5's `prior_year_values` CTE in
`infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql` picks
one canonical row per `(cik, fiscal_period, fiscal_year)` via `qualify
row_number() ... = 1`, with `accession_number desc` as the final tiebreaker —
i.e. "most recently filed accession wins" (e.g. a 10-K/A amendment over the
original 10-K). SEC accession numbers are assigned sequentially per filer at
submission time, so within a single `cik` they correlate very strongly with
actual filing date, but `accession_number desc` is a proxy, not a real
`filed_date` timestamp.

**Why deferred:** neither `sec_financial_derived` (silver) nor
`SEC_FINANCIAL_DERIVED` (Snowflake source) currently has a `filed_date`
column. Adding one would require the same multi-stage silver -> export ->
gold migration pattern as Stages 1-4: extend the silver schema/parser to
capture `filed_date` from the SEC companyfacts/submissions payload, add it to
the export manifest and `SEC_FINANCIAL_DERIVED` DDL/MERGE keys, then update
`financial_derived.sql`'s tiebreaker to order by `filed_date desc` (falling
back to `accession_number desc` for any pre-migration rows without it).

**Risk if left as-is:** low in practice — the accession-number proxy is
expected to agree with `filed_date` for the vast majority of filings. Edge
cases (e.g. a filing submitted in multiple parts, or SEC accession-number
allocation quirks) could theoretically produce a different tiebreaker
ordering than true filing chronology, but this has not been observed in real
data (see T6's validation against Apple, CIK 320193).

**Surfaced by:** plan-eng-review of PR #66 (Issue 3B), 2026-06-12.

---

## CI does not run dbt against live Snowflake (Issue 2B, deferred per T4)

**Status:** Deferred, not blocking PR #66 (`claude/financial-derived-lag-tiebreaker`,
Stage 5).

`dbt compile` only validates Jinja templating and SQL syntax — it cannot
catch errors that only surface when Snowflake actually plans/executes the
SQL (e.g. the Issue 1 nested-window-function bug in `financial_derived.sql`,
which `dbt compile` passed but a live `dbt run --select financial_derived`
against `EDGARTOOLS_DEV` would have failed on). T4 documented the manual
`dbt run --select <model_name> --full-refresh` smoke-test convention in
`CLAUDE.md` (see "dbt gold model SQL changes — smoke test convention"), but
there is no CI job that runs this automatically, so a future change could
reintroduce a Snowflake-execution-only error and still pass CI.

**Why deferred:** enabling this in CI requires:
1. Snowflake credentials (keypair or password) provisioned as CI secrets,
   scoped to a role/warehouse that can run `dbt run`/`dbt test` against
   `EDGARTOOLS_DEV` without affecting other environments.
2. A decision on scope/cadence — full `dbt run` on every PR touching
   `infra/snowflake/dbt/**`, vs. `--select state:modified+` for changed
   models only, vs. a nightly scheduled run.
3. Handling for the `EDGARTOOLS_DEV_DEPLOYER` grants gap documented in the
   section below — CI would hit the same "not authorized" error on
   `--full-refresh` until that grant is codified in Terraform/bootstrap SQL.

**Interim mitigation:** the manual `dbt run --select <model> --full-refresh`
convention in `CLAUDE.md` is the current substitute — contributors changing a
gold model's SQL body are expected to run it against `EDGARTOOLS_DEV` before
merging.

**Surfaced by:** plan-eng-review of PR #66 (Issue 2B, deferred per task 2A/T4),
2026-06-12.

---

## EDGARTOOLS_DEV_DEPLOYER lacks direct SELECT on EDGARTOOLS_SOURCE — blocks `dbt run --full-refresh` for any gold dynamic table

**Status:** RESOLVED for dev 2026-06-13. Discovered while attempting T1 live
verification of the Stage 5 `financial_derived.sql` change (PR #66,
`claude/financial-derived-lag-tiebreaker`), but is generic to **any**
`EDGARTOOLS_GOLD` dynamic table, not specific to that PR.

**Dev fix applied (ad-hoc, as ACCOUNTADMIN):**
```sql
GRANT SELECT ON ALL TABLES IN SCHEMA EDGARTOOLS_DEV.EDGARTOOLS_SOURCE
  TO ROLE EDGARTOOLS_DEV_DEPLOYER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA EDGARTOOLS_DEV.EDGARTOOLS_SOURCE
  TO ROLE EDGARTOOLS_DEV_DEPLOYER;
```
17 existing tables affected, plus a FUTURE grant for new ones. Verified
`dbt run --select financial_derived --full-refresh` now succeeds
(`CREATE OR REPLACE DYNAMIC TABLE` completes, owner is now
`EDGARTOOLS_DEV_DEPLOYER`, `data_timestamp` updated, deployed SQL body now
matches the Stage 5 `prior_year_values`/`is_current_period` logic).

**Still open / not done here:**
- This grant is ad-hoc and not codified in Terraform/bootstrap SQL — it will
  not survive an environment rebuild and should be added to the
  `account_baseline` module (or `01_source_stage.sql`) as a follow-up so dev
  doesn't drift.
- `EDGARTOOLS_PROD_DEPLOYER` likely needs the analogous grant — not checked.
- T6 (before/after row-level comparison vs the pre-Stage-5 `lag()` output) is
  **RESOLVED 2026-06-13** — populated dev with real data for Apple (CIK
  320193) via `bootstrap-fundamentals --mode entity-facts --cik-list 320193`
  (282 `sec_financial_derived` rows), manually uploaded
  `silver/fundamentals/shard-0.duckdb` to S3 (no existing code path does this
  — see follow-up below), ran `gold-refresh` to export to
  `EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` (282 rows), then
  `ALTER DYNAMIC TABLE FINANCIAL_DERIVED REFRESH` (282 rows inserted).
  Spot-checked `revenue_yoy_growth`/`ebitda_yoy_growth`/`net_income_yoy_growth`
  for CIK 320193: values match expected Apple YoY (e.g. FY2025 revenue
  $416.16B vs FY2024 $391.04B → ~6.4% growth, matches `revenue_yoy_growth`).
  Confirmed the Stage 5 fan-in fix on real duplicate-accession groups: every
  `(fiscal_year, fiscal_period, period_end)` group with 2 rows (2010-2012
  series) produces consistent non-zero YoY across both rows; the earliest
  periods (2007-2009, no prior-year comparative available) correctly show
  zero/null YoY.
- **T1 RESOLVED 2026-06-17:** `bootstrap-fundamentals` had no S3 upload step
  after writing `silver/fundamentals/shard-0.duckdb` — in ECS the shard was
  silently discarded on container exit. Fixed by adding
  `_publish_fundamentals_shard_if_remote` to `warehouse_orchestrator.py`
  (mirror of `_hydrate_fundamentals_shard`) and calling it from
  `bootstrap_fundamentals.execute` after `db.close()`. Upload is gated on
  `WAREHOUSE_STORAGE_ROOT` env var (absent in local dev → no-op). Upload
  failure returns exit code 1 (distinct from config error 2) so Step Functions
  marks the task failed rather than silently losing data. Tests added to
  `tests/application/test_warehouse_orchestrator_mdm.py`.

**What:** `dbt run --select financial_derived --full-refresh` (run as
`EDGARTOOLS_DEV_DEPLOYER`, the standard dbt deploy role) fails:

```
SQL compilation error: Failed to refresh dynamic table with refresh_trigger
INITIAL ... Object 'EDGARTOOLS_DEV.EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED'
does not exist or not authorized. (Note: the primary role is the owner role
of the dynamic table)
```

**5-whys:**
1. `dbt run --full-refresh` issues `CREATE OR REPLACE DYNAMIC TABLE ...
   initialize = ON_CREATE`, which triggers an immediate INITIAL refresh.
2. The INITIAL refresh fails with "not authorized" on the source table,
   even though an ad-hoc `SELECT * FROM
   EDGARTOOLS_DEV.EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` run in the same
   session/role succeeds.
3. Ad-hoc queries succeed because `EDGARTOOLS_DEV_DEPLOYER` has
   `CURRENT_SECONDARY_ROLES() = {"roles":"ACCOUNTADMIN,ORGADMIN","value":"ALL"}`
   — secondary roles ARE consulted for ad-hoc session queries.
4. Dynamic table refresh (including the `ON_CREATE` INITIAL refresh) checks
   privileges **strictly against the dynamic table's owner role's DIRECT
   grants only** — it does not consult secondary roles. `CREATE OR REPLACE
   DYNAMIC TABLE` run as `EDGARTOOLS_DEV_DEPLOYER` makes that role the new
   owner.
5. `SHOW GRANTS TO ROLE EDGARTOOLS_DEV_DEPLOYER` confirms the role has only
   `USAGE`/`CREATE *` on the `EDGARTOOLS_SOURCE`/`EDGARTOOLS_GOLD` schemas
   and `EDGARTOOLS_DEV` database — **no direct `SELECT` on any
   `EDGARTOOLS_SOURCE` table**. Root cause: this `SELECT` grant was never
   provisioned for the deployer role (gap exists in both Terraform
   `account_baseline` module, which defines `local.roles` but has no
   `snowflake_grant_privileges_to_role` resource for it in the files read so
   far, and in `infra/snowflake/sql/bootstrap/01_source_stage.sql`, which
   references `$deployer_role_name` but has no `GRANT SELECT` statements).

**Why this was latent until now:** the currently-deployed `FINANCIAL_DERIVED`
dynamic table is owned by `ACCOUNTADMIN` (created directly as ACCOUNTADMIN or
by a process with the right grants at some earlier point) and still runs the
pre-Stage-5 `lag()`-based SQL from 2026-06-05. The canonical deploy path
(`infra/scripts/deploy-snowflake-stack.sh`) runs `dbt run --target dev`
**without** `--full-refresh`, and dbt-snowflake's dynamic-table materialization
only diffs *configuration*, not SQL body — so it has never issued a
`CREATE OR REPLACE` for this table and never hit the missing grant. Confirmed
generic (not Stage-5-specific) via two throwaway dynamic tables
(`ZZ_TEST_FD` from `SEC_FINANCIAL_DERIVED`, `ZZ_TEST_COMPANY` from
`COMPANY`) — both `CREATE OR REPLACE DYNAMIC TABLE ... initialize =
ON_CREATE` as `EDGARTOOLS_DEV_DEPLOYER` fail identically; both cleaned up
(`DROP DYNAMIC TABLE IF EXISTS` — no orphaned objects left).

**Fix approach:** Grant `EDGARTOOLS_DEV_DEPLOYER` direct `SELECT` on
`EDGARTOOLS_SOURCE`:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA EDGARTOOLS_DEV.EDGARTOOLS_SOURCE
  TO ROLE EDGARTOOLS_DEV_DEPLOYER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA EDGARTOOLS_DEV.EDGARTOOLS_SOURCE
  TO ROLE EDGARTOOLS_DEV_DEPLOYER;
```

Should be codified as the source of truth (Terraform `account_baseline`
module and/or `01_source_stage.sql`), not just an ad-hoc ACCOUNTADMIN grant,
to avoid drift — exact location TBD, needs a focused look at the
`account_baseline` module's variables/other `.tf` files for where
`local.roles` is (or should be) wired to grant resources. The prod role
(`EDGARTOOLS_PROD_DEPLOYER`) likely needs the analogous grant too, and should
be checked before it hits the same wall.

**Impact:** blocks `dbt run --full-refresh` for ANY `EDGARTOOLS_GOLD` dynamic
table (not just `financial_derived`) — i.e. blocks recovering from the
known dbt-snowflake dynamic-table SQL-diffing gap (see
`financial_derived.sql`'s deployed body being stale since 2026-06-05 despite
multiple `dbt run`s).

**Surfaced:** T1 live verification of PR #66 (Stage 5), 2026-06-13.

---

## Dev Terraform MDM-cutover state reconciliation — RESOLVED

**Status:** RESOLVED 2026-06-11. `infra/terraform/accounts/dev/` now matches AWS
exactly (`terraform plan` → "No changes. Your infrastructure matches the
configuration.").

**What:** After the MDM RDS→Snowflake-Postgres cutover removed `module "mdm"`
from `main.tf` (PRs #51-54), 10 `module.mdm[0].*` resources remained in dev
state. `infra/terraform/accounts/dev/mdm_secret_moves.tf` had `moved` blocks
for `postgres_dsn` and `api_keys` only — `aws_secretsmanager_secret.neo4j` had
no `moved` block, and the new `mdm_snowflake`/`edgar_identity[0]` resources
were never reconciled with pre-existing out-of-band secrets.

**Why (5-whys):**
1. `terraform apply` of the cutover-cleanup plan (4 add/4 change/6 destroy)
   partially failed with 3 `ResourceExistsException` on `CreateSecret`.
2. `mdm_neo4j` failed because, lacking a `moved` block, its predecessor
   (`module.mdm[0].aws_secretsmanager_secret.neo4j`) was destroyed and a
   same-named secret immediately recreated in the *same* apply.
3. AWS Secrets Manager blocks name reuse for 30 days (default
   `recovery_window_in_days`) after a delete — the create-after-destroy in one
   apply hit that window.
4. `mdm_snowflake` and `edgar_identity[0]` failed because active secrets with
   those exact names already existed in AWS but were never imported into
   Terraform state (created out-of-band during earlier MDM work).
5. Root cause: secret renames during the cutover were only partially captured
   as `moved` blocks, and out-of-band secret creation was never reconciled
   with state.

**Resolution:**
- `aws secretsmanager restore-secret --secret-id edgartools-dev/mdm/neo4j`
  (cancelled the pending deletion from step 2/3).
- `terraform import` for all 3 secrets into their `module.runtime.*` addresses
  (`mdm_neo4j`, `mdm_snowflake`, `edgar_identity[0]`).
- Re-ran `terraform apply` — remaining diff was tag/description metadata only
  (0 add, 3 change, 0 destroy). Final `terraform plan` is clean.
- Confirmed `module.mdm[0].aws_db_instance.mdm` is fully gone from both state
  and AWS (no leftover anomaly).
- Real AWS resources destroyed as part of this cleanup (intentional, part of
  the cutover): `edgartools-dev-mdm-subnets` DB subnet group, 2 private
  subnets, MDM RDS security group + rules, old `edgartools-dev/mdm/neo4j`
  secret (immediately restored under the same name).

**Surfaced:** carried over from `.continue-here.md` (Stage-1 PK-collision
handoff), resolved 2026-06-11.

---

## Production dashboard UAT

**What:** Run dashboard UAT against production Snowflake/MDM connections
once prod credentials and infrastructure are available.

**Why:** Phase 4 dashboard UAT (go-live workstream) ran only against dev
credentials; the launch gate matrix lists "Dashboard operator inspection
views" as BLOCKED until a prod UAT pass is recorded as separate evidence.
Dev evidence is precedent only and does not substitute for prod proof.

**Where:** `.planning/workstreams/go-live/phases/04-operator-dashboard-and-data-issue-triage/` (dev UAT evidence); prod UAT evidence to be captured under the go-live workstream when prod credentials exist.

---

## Production MDM secrets population runbook execution

**What:** Execute the MDM secrets runbook against real production values to
populate `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake`
in Secrets Manager.

**Why:** The launch gate matrix's "MDM Snowflake Postgres secret container
and connectivity" row is BLOCKED — the runbook steps are documented but have
not yet been executed against real prod secret values, so prod MDM
connectivity is unverified.

**Where:** `.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md` (runbook to execute); `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md` (Required Production Identifiers checklist).

---

## EDGARTOOLS_PROD_DEPLOYER direct SELECT grants on EDGARTOOLS_SOURCE

**RESOLVED (2026-06-19, Phase 7 branch takeover):** The `access/snowflake/
accounts/prod` Terraform root's `deployer_source_all_objects`/
`deployer_source_future_objects` grants already cover this — confirmed live
by creating the `EDGARTOOLS_PROD_DEPLOYER` user, authenticating as it using
only credentials read back from `edgartools-prod/dbt/snowflake`, and running
a real `SELECT` against `EDGARTOOLS_SOURCE` tables, which succeeded. No
additional grant was needed beyond what Terraform already applies. Leaving
the rest of this entry for context; the `EDGARTOOLS_DEV_DEPLOYER` dev-side
gap referenced below may still be worth checking separately.

**What:** Grant the `EDGARTOOLS_PROD_DEPLOYER` role direct `SELECT` on
`EDGARTOOLS_SOURCE` tables before any `dbt run --full-refresh` is attempted
against production dynamic tables.

**Why:** This is the production analog of the dev gap already documented
above for `EDGARTOOLS_DEV_DEPLOYER` — Snowflake's dynamic-table INITIAL
refresh checks the owner role's *direct* grants only, and a role lacking
direct `SELECT` on `EDGARTOOLS_SOURCE` will fail `--full-refresh` with
"not authorized" even though ad-hoc queries succeed via secondary roles.
Without this grant in place ahead of time, the first production
`--full-refresh` of any `EDGARTOOLS_GOLD` dynamic table will fail.

**Where:** `infra/snowflake/dbt/edgartools_gold/` (dbt project); CLAUDE.md
"dbt gold model SQL changes — smoke test convention" section (dev-side
precedent and known gap).

---

## External Neo4j runtime remnant deprecation

**What:** Formally remove or deprecate any remaining external (Aura) Neo4j
runtime references and infrastructure remnants now that the platform is
fully migrated to the Snowflake-hosted graph Native App.

**Why:** Phase 4 already cleaned up `NEO4J_*` environment variable
references from the dashboard README, but a formal Neo4j runtime remnant
deprecation pass (any remaining Terraform resources, secrets, or
documentation pointing at an external Neo4j runtime) has not been done.
This is tracked as a deferred "Future Requirements" item in
REQUIREMENTS.md and should not silently expand the go-live milestone
scope.

**Where:** REQUIREMENTS.md ("Future Requirements" section); search for
remaining `NEO4J_*`/Aura references outside the dashboard README already
cleaned up in Phase 4.

---

## Password leak via Python quoting bug (resolved in-session)

**Problem:** While creating the `EDGARTOOLS_PROD_DEPLOYER` Snowflake user
during Phase 7's branch takeover, a generated password briefly appeared in
plaintext in agent tool output (a Claude Code session transcript), not in
any committed file.

1. Symptom: a Python `json.dumps({...})` one-liner, passed as a `python3 -c`
   argument nested inside `$(...)` command substitution inside an outer
   double-quoted string, threw 6 separate `SyntaxError`s — one per dict key —
   and one of the error traces echoed the literal password value.
2. Why did it throw 6 separate errors instead of one? The shell/tool layer
   that executes the agent's Bash command appears to have split the
   multi-line `-c` argument into multiple invocations at single-quote
   boundaries, rather than passing it through as one atomic string — each
   resulting in `python3 -c '<one dict line>'` being run on its own.
3. Why did this expose the value at all? The dict's `os.environ[...]` lookup
   pattern was not used in the first attempt; the password was interpolated
   directly into the Python source text via shell variable expansion before
   the command was sent, so the broken-up fragments still contained the
   resolved literal value, and Python's syntax-error trace printed the
   offending source line verbatim.
4. Why was the password interpolated directly instead of read from an env
   var inside the script? Convenience — written as a single inline `-c`
   string instead of a script file, to avoid an extra `Write` call.
5. Root cause: inline multi-line `python3 -c "..."` strings with nested
   quoting are unsafe in this environment when they carry secret values,
   because (a) the command-splitting behavior above is not obvious in
   advance, and (b) any resulting syntax error reprints the source text
   that produced it, including any interpolated secret.

**Resolution:** The leaked password was immediately rotated
(`ALTER USER ... SET PASSWORD`) before being stored anywhere, so the exposed
value was never persisted to Secrets Manager. The retry used a `Write`-created
script file that reads the secret only from `os.environ["NEW_PW"]` (never
interpolated into source text), with all command output redirected to a log
file and only `grep -vi password`-filtered lines ever surfaced — this
succeeded with no further exposure.

**Going forward:** When a Bash command must build a secret-bearing payload
(JSON, SQL, etc.) in Python, always write the logic to a file via the `Write`
tool first and have it read the secret from an environment variable via
`os.environ`, never interpolate a secret into Python (or any) source text via
shell expansion inside an inline `-c`/`-e` one-liner — even when the line
looks like it should be safe, a downstream parse error can reprint it
verbatim.

---

## SEC_FINANCIAL_FACT missing PERIOD_START column blocked `dbt run --target prod` (resolved in-session)

**Problem:** Running `dbt deps/run/test --target prod` (Phase 7, SNOW-04) built
15 of 16 gold models successfully, but `FINANCIAL_FACTS` failed with
`SQL compilation error: error line 44 ... invalid identifier 'PERIOD_START'`.

1. Symptom: the dbt model's `select ... period_start ... from
   {{ source("edgartools_source", "SEC_FINANCIAL_FACT") }}` failed to compile
   against the live table.
2. Why? `INFORMATION_SCHEMA.COLUMNS` confirmed the live
   `EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` table has only 13
   columns — no `PERIOD_START`.
3. Why, when the model expects it? Checked `EDGARTOOLS_DEV`'s identical
   table — also missing the column. Not a prod-only gap; systemic across both
   environments.
4. Why is it missing from both, when the Python silver parser
   (`edgar_warehouse/parsers/financials.py:172`) and the PyArrow serving
   schema (`edgar_warehouse/serving/gold_models.py`'s
   `_SEC_FINANCIAL_FACT_SCHEMA`) both already produce/expect this field?
   `infra/snowflake/sql/bootstrap/01_source_stage.sql` already declares
   `period_start DATE NOT NULL DEFAULT '0001-01-01'` in the `CREATE TABLE IF
   NOT EXISTS` body and carries an explicit migration line
   (`ALTER TABLE SEC_FINANCIAL_FACT ADD COLUMN IF NOT EXISTS period_start
   DATE NOT NULL DEFAULT '0001-01-01';`) intended for tables created before
   the column existed.
5. Root cause: `CREATE TABLE IF NOT EXISTS` is a no-op once the table already
   exists, and the bootstrap script's migration step has never actually been
   (re-)executed against either live database since it was added to the file
   — the fix existed in the repo but was never deployed.

**Resolution:** Applied the migration directly against
`EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT` via the `snowconn`
(ACCOUNTADMIN) SnowCLI connection. The checked-in statement's exact literal
form (`DEFAULT '0001-01-01'` and `DEFAULT TO_DATE('0001-01-01')`) both failed
in this Snowflake account — `ADD COLUMN ... DEFAULT '<string>'` was
type-coerced as VARCHAR instead of DATE, and `DEFAULT TO_DATE(...)` was
rejected with "Invalid column default expression" (Snowflake's `ALTER TABLE
ADD COLUMN` only accepts literal constants as defaults, not function calls).
Used the 3-step non-literal-safe form instead: `ADD COLUMN period_start
DATE` (nullable) → `UPDATE ... SET period_start = DATE '0001-01-01' WHERE
period_start IS NULL` (0 rows affected — table was empty, no backfill data
loss possible) → `ALTER COLUMN period_start SET NOT NULL`. A trailing
`ALTER COLUMN ... SET DEFAULT` additionally failed with "Unsupported feature
'Alter Column Set Default'" (Snowflake does not support setting a default on
an existing column at all) — left without a stored default, which is safe
here because this is a passthrough loader-managed table where every
INSERT already supplies `period_start` explicitly. Re-ran
`dbt run --target prod --select financial_facts` (SUCCESS) and
`dbt test --target prod` (47/47 PASS, 0 ERROR). **`EDGARTOOLS_DEV`'s
identical table was not touched — same gap exists there but is out of scope
for this prod-only task.**

**Going forward:** `01_source_stage.sql`'s `ALTER TABLE ... ADD COLUMN`
migration statements are not automatically re-applied by any deploy
script when a column is added to an existing table — they must be run
explicitly (and on this Snowflake account, with a non-literal-constant
default, via the 3-step `ADD COLUMN` → `UPDATE` → `SET NOT NULL` pattern, not
a single `ADD COLUMN ... DEFAULT` statement). If `01_source_stage.sql` gains
further such migrations, re-run them against dev before running `dbt run
--target dev`, or `FINANCIAL_FACTS` will fail there with the identical
error.

---

## runtime_access module: shared, non-namespaced IAM roles across dev/prod

**What:** `infra/terraform/access/aws/modules/runtime_access/main.tf` hardcodes
3 role names (`sec_platform_runner_execution`, `sec_platform_runner_task`,
`sec_platform_runner_step_functions`) without `${var.name_prefix}` env
namespacing, unlike every other resource in the same file. Confirmed live
that dev created these roles first and prod's already-deployed (Phase 6) ECS
task definitions already reference the identical literal role ARNs — dev and
prod genuinely share these 3 roles today, in the same AWS account.

**Why this matters:** Renaming the roles now would break live ECS task
definitions in both environments (their `executionRoleArn`/`taskRoleArn`
fields are the literal ARN string, which changes if the role is renamed).
The 3 *inline policies* attached to these roles were namespaced during Phase
7's branch takeover (`${var.name_prefix}-runner-execution-secret` etc.) to
stop one environment's apply from silently overwriting the other's secret/
bucket grants — but the roles themselves remain intentionally shared and
un-namespaced, which is a real environment-isolation gap (a policy change
intended for prod's role trust, attached managed-policy set, or assume-role
policy would also affect dev, and vice versa).

**Where:** `infra/terraform/access/aws/modules/runtime_access/main.tf` lines
17-19 (`local.runner_execution_role_name` etc.); live AWS IAM roles
`sec_platform_runner_execution`/`_task`/`_step_functions` in account
`077127448006`. A proper fix would need to namespace the role names AND
re-point both dev's and prod's ECS task definitions at the new ARNs in a
single coordinated change — out of scope for an ad-hoc unblock.
