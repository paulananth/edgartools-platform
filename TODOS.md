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
(RESOLVED)" below. Stage 2 (period_start, residual 2,440 collisions) remains
OPEN — see "Recommended fix" step 1-3 below for the Stage 2 plan.

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
