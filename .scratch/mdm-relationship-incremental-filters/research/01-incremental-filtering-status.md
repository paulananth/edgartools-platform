# Incremental filtering status — all 11 `MDMPipeline.derive_relationships()` types

Read-only investigation, 2026-09-06. Source of truth: direct reading of
`edgar_warehouse/mdm/pipeline.py` (current worktree) plus live queries against Snowflake
`EDGARTOOLS_PROD` (connection `edgartools-prod`, `snow sql`) and MDM Postgres
(`edgartools-prod/mdm/postgres_dsn` secret, queried via a throwaway Python/psycopg2 script that
never printed the DSN — row counts only).

## Headline finding (read this before the table)

The ticket's presumption — "the other 9 types share `_derive_institutional_holds`/
`_derive_holds`'s write-count-bound, full-table-scan `_bounded_relationship_sql` shape" — is
**only partly true**. Reading all 11 methods directly found **four genuinely different
filtering shapes**, not one:

1. **Growing-window LIMIT** (`_bounded_relationship_sql`/`bounded_source_sql`): appends
   `LIMIT existing + max(remaining*50, 100)` to a `SELECT ... ORDER BY ...` against a silver
   table. This is the shape the ticket calls "confirmed." **5 of 11 types use it for their
   entire source scan:** IS_INSIDER, HOLDS, COMPANY_HOLDS, and (partially — see below)
   HAS_PARENT_COMPANY and AUDITED_BY.
2. **CIK/CRD-range batched full scan** (memory-bounded, not count-bounded): the source table
   is read in fixed-size batches (1,000 CIKs or 1,000 CRDs at a time) purely to cap per-batch
   memory; every batch is visited regardless of `remaining`, and `remaining` only short-circuits
   the *batch loop*, not any one batch's own SQL. **2 of 11 types use this:**
   INSTITUTIONAL_HOLDS (already known) and **MANAGES_FUND (not previously confirmed — this
   is new)**.
3. **Fully unbounded MDM-Postgres table scan, Python-side break only**: no SQL `LIMIT`
   anywhere, not even a growing one — the *entire* matching Postgres row set is materialized
   via SQLAlchemy `.all()`/a plain `for row in session.scalars(select(...))` loop, and only a
   Python `if inserted >= remaining: break` bounds how many are actually turned into
   relationships. The un-turned remainder is still fully fetched into memory every call.
   **This is a genuinely different, previously-unflagged shape — 4 of 11 types use it:**
   IS_ENTITY_OF, IS_PERSON_OF, MANAGES_FUND's own adviser-universe prefetch (see caveat below),
   and ISSUED_BY. None of these four read `self.silver.fetch()` at all for their primary
   source — their "source table" is MDM's own Postgres (`mdm_adviser`, `mdm_person`,
   `mdm_security`, `mdm_fund`), not a silver table.
4. **Always-unbounded secondary sub-query bolted onto an otherwise-bounded method**:
   EMPLOYED_BY's second source table (`sec_employment_event`) is fetched with `remaining`
   hardcoded to `None` — i.e. it is a full, unbounded table scan **on every single call**,
   regardless of how small the method's own `remaining` budget is. This is buried inside a
   method that otherwise looks like shape #1.

Two more currently-live wrinkles worth flagging even though they don't change the code shape:

- **HAS_PARENT_COMPANY's presumed-bounded primary path is currently a no-op in prod**: its
  silver source, `sec_subsidiary_evidence`, has **0 rows live** — so the method falls through
  every single call to its fallback branch, which is shape #3 (an unbounded `MdmCompany` scan
  with `parent_company_entity_id IS NOT NULL`, itself currently 0 matching rows). The
  "bounded LIMIT" code path exists but has never actually bounded anything in this account.
- **AUDITED_BY's primary AND fallback silver sources are both currently empty** —
  `sec_auditor_report_evidence` = 0 rows, `sec_accounting_flag` = 0 rows (live-queried). The
  bounded-LIMIT shape is real and correctly implemented, but at today's data volume it
  produces zero candidate rows regardless of filtering strategy — a genuine incremental
  mechanism here would currently have nothing to filter.

## Row-count and timestamp inventory

All Snowflake counts are `EDGARTOOLS_PROD.EDGARTOOLS_SILVER` (live-queried 2026-09-06 via
`snow sql --connection edgartools-prod`), confirmed against `INFORMATION_SCHEMA.TABLES` and,
for the three zero-row tables, re-verified with a direct `COUNT(*)`. **Caveat inherited from
CLAUDE.md's own "silver-snowflake-migration" note:** DuckDB (`silver_store.py`) is still
canonical for most MDM consumers as of this writing; Snowflake's `EDGARTOOLS_SILVER` mirror is
real, live-ingesting data, but has not been shown to always match DuckDB's row counts for every
table. Where a table's Snowflake count came back 0, that is reported as-is (live-verified, not
assumed) but may not reflect the DuckDB store the running pipeline actually reads. MDM Postgres
counts were queried live via `edgartools-prod/mdm/postgres_dsn` (a real DSN, never displayed).

| # | Relationship type | Method (line) | Confirmed filtering shape | Source table(s) | Row count (source, method) | Timestamp/versioning column(s) available |
|---|---|---|---|---|---|---|
| 1 | IS_INSIDER | `_derive_is_insider` (1082) | Shape 1 — bounded `_bounded_relationship_sql`, `ORDER BY accession_number, owner_index` | `sec_ownership_reporting_owner` JOIN `sec_company_filing` | reporting_owner **59,030** rows; company_filing **6,551,594** rows (Snowflake `EDGARTOOLS_SILVER`, live) | Neither has `ingested_at`. `sec_ownership_reporting_owner` has only `last_sync_run_id` (TEXT run id, not a timestamp). `sec_company_filing` has `last_synced_at TIMESTAMPTZ` (usable). Natural ordering: `accession_number` (roughly chronological, not guaranteed). |
| 2 | HOLDS | `_derive_holds` (1225) | Shape 1 — bounded, `ORDER BY accession_number, owner_index, txn_index` | `sec_ownership_non_derivative_txn` UNION `sec_ownership_derivative_txn` JOIN reporting_owner JOIN company_filing | non_derivative **78,469** + derivative **2,969** = **~81,438** combined (Snowflake, live; matches `EDGARTOOLS_SOURCE.OWNERSHIP_ACTIVITY`'s 81,455) | No `ingested_at` on either txn table — only `last_sync_run_id`. Natural ordering: `accession_number, owner_index, txn_index`. |
| 3 | COMPANY_HOLDS | `_derive_company_holds` (1375) | Shape 1 — bounded, identical query/ordering to HOLDS | Same as HOLDS | Same as HOLDS (~81,438) | Same as HOLDS. |
| 4 | INSTITUTIONAL_HOLDS | `_derive_institutional_holds`/`_derive_institutional_holds_batch` (3142/3276) | Shape 2 — CIK-range batched (1,000-CIK chunks, `_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE`), full scan across all batches, write-count bound only via early-exit across the batch loop (**re-confirmed, matches ticket's prior finding**) | `sec_thirteenf_holding` JOIN `sec_thirteenf_filing` | holding **6,799,919** rows; filing **14,364** rows (Snowflake, live) | **Both tables have real `ingested_at TIMESTAMPTZ DEFAULT NOW()` columns** — one of only two source-table families among all 11 with a genuine wall-clock ingestion timestamp. Natural ordering: `cik, accession_number, cusip`. |
| 5 | IS_ENTITY_OF | `_derive_is_entity_of` (1506) via `_adviser_company_pairs` (3382) | **Shape 3 — NOT `_bounded_relationship_sql` at all.** Full unbounded `session.execute(select(...)).all()` against MDM Postgres `mdm_adviser` filtered `linked_company_entity_id IS NOT NULL`; no SQL LIMIT; Python `break` on `remaining` only after the whole result set is already materialized. | **MDM Postgres `mdm_adviser`** (not silver — no `self.silver.fetch()` call at all) | `linked_company_entity_id IS NOT NULL`: **0 rows** (live Postgres query, 2026-09-06) | `mdm_adviser.valid_from`/`valid_to` (TIMESTAMPTZ, SCD2-style versioning) exist. No content-diff/ingested_at column. |
| 6 | HAS_PARENT_COMPANY | `_derive_has_parent_company` (1525) | **Mixed.** Primary path: Shape 1 — bounded `_fetch_optional_relationship_rows`, `ORDER BY registrant_cik, accession_number, document_name, row_ordinal`. Fallback (fires whenever primary returns 0 rows — **which is every call today**, see headline): Shape 3 — full unbounded `session.scalars(select(MdmCompany)...)` scan, `ORDER BY cik`, no LIMIT, Python `break` only. | Primary: `sec_subsidiary_evidence`. Fallback: **MDM Postgres `mdm_company`**. | `sec_subsidiary_evidence`: **0 rows** (Snowflake, live, re-verified with direct `COUNT(*)`). Fallback candidate set (`mdm_company.parent_company_entity_id IS NOT NULL`): **0 rows** (live Postgres). | `sec_subsidiary_evidence` has no `ingested_at` — only `effective_date` (business date) + `last_sync_run_id`. `mdm_company.valid_from`/`valid_to` (TIMESTAMPTZ) exist for the fallback table. |
| 7 | IS_PERSON_OF | `_derive_is_person_of` (1657) via `_adviser_person_pairs` (3390) | Shape 3 — same as IS_ENTITY_OF: full unbounded join query, no LIMIT, Python `break` only | **MDM Postgres `mdm_adviser` JOIN `mdm_person`** (not silver) | `WHERE a.cik IS NOT NULL AND a.linked_company_entity_id IS NULL`: **0 rows** (live Postgres query) | `mdm_adviser.valid_from`/`valid_to` and `mdm_person.valid_from`/`valid_to` (both TIMESTAMPTZ) exist. |
| 8 | MANAGES_FUND | `_derive_manages_fund`/`_derive_manages_fund_batch` (1676/1771) | **New finding — not `_bounded_relationship_sql`.** CRD-range batched (1,000-CRD chunks, `_MANAGES_FUND_CRD_BATCH_SIZE`), full scan across all batches (Shape 2, same mechanics as INSTITUTIONAL_HOLDS). The adviser-universe prefetch that drives batching (`adviser_ids_by_crd`) is itself an unbounded, no-LIMIT `session.execute(select(MdmAdviser...))` (Shape 3) run once up front. A degenerate fallback (when both `sec_adv_filing` and `sec_adv_private_fund` are entirely empty) scans the whole `mdm_fund` table, also unbounded (Shape 3). | Batched-path silver source: `sec_adv_filing` + `sec_adv_private_fund`. Adviser-universe prefetch source: **MDM Postgres `mdm_adviser`**. Fallback source: **MDM Postgres `mdm_fund`**. | `sec_adv_filing` **61,223** rows; `sec_adv_private_fund` **414,968** rows (Snowflake, live). `mdm_adviser` with `crd_number IS NOT NULL`: **24,447** rows (live Postgres). `mdm_fund` with `adviser_entity_id IS NOT NULL`: **130,615** rows (live Postgres — this is the table CLAUDE.md's schema-conventions section already flags for its `fund_index` SMALLINT-overflow outlier, i.e. a table already known to have a very unevenly-distributed, fast-growing single-filer shape). | `sec_adv_filing`/`sec_adv_private_fund`: no `ingested_at` — only `effective_date` (business date) + `last_sync_run_id`. Natural ordering used for versioning logic: `crd_number, effective_date, accession_number` (this method's own "latest filing per CRD" comparison already relies on this ordering, just not as an incremental-read filter). `mdm_adviser`/`mdm_fund`: `valid_from`/`valid_to` (TIMESTAMPTZ). |
| 9 | ISSUED_BY | `_derive_issued_by` (1903) | Shape 3 — full unbounded `session.scalars(select(MdmSecurity)...)` scan, no LIMIT, Python `break` only | **MDM Postgres `mdm_security`** (not silver) | `issuer_entity_id IS NOT NULL`: **3,143** of **3,240** total `mdm_security` rows (live Postgres) | `mdm_security.valid_from`/`valid_to` (TIMESTAMPTZ) exist. |
| 10 | EMPLOYED_BY | `_derive_employed_by` (2716) | **Mixed, two sub-queries.** Primary (`sec_executive_record`): Shape 1 — bounded, `ORDER BY cik, fiscal_year, accession_number, exec_name`. Secondary (`sec_employment_event`): **Shape 4 — always fully unbounded**, called with `remaining=None` explicitly regardless of the method's own `remaining` argument, so this sub-query does a full table scan on literally every `derive_relationships()` call. | `sec_executive_record` (bounded) + `sec_employment_event` (always unbounded) | `sec_executive_record` **14,755** rows; `sec_employment_event` **7,676** rows (Snowflake, live) | **Both tables have real `ingested_at TIMESTAMPTZ DEFAULT NOW()` columns** — the other of the two source-table families (with INSTITUTIONAL_HOLDS's tables) that actually carries a genuine wall-clock ingestion timestamp. Natural ordering: `cik, fiscal_year, accession_number, exec_name` (executive) / `effective_date, accession_number, event_index` (event). |
| 11 | AUDITED_BY | `_derive_audited_by` (2969) | Shape 1 — bounded for both the primary and (if primary returns 0 rows) fallback query; `ORDER BY registrant_cik, audited_period_end, report_date, accession_number` (primary) / `ORDER BY cik, fiscal_year` (fallback) | Primary: `sec_auditor_report_evidence`. Fallback (fires whenever primary is empty — **currently every call**): `sec_accounting_flag`. | Both **0 rows** (Snowflake, live, re-verified with direct `COUNT(*)`) — so this type currently derives nothing regardless of filtering shape. | `sec_auditor_report_evidence` has no `ingested_at` — only `report_date`/`audited_period_end` (business dates) + `last_sync_run_id`. `sec_accounting_flag` **does** have `ingested_at TIMESTAMPTZ DEFAULT NOW()` plus Ticket 33's `valid_from`/`valid_to`/`is_current` retirement columns — the richest versioning surface of any table in this inventory, currently unused because the table is empty. |

## Growth rate

No reliable growth-rate signal was captured this session — that would require either a
historical row-count snapshot to diff against, or a live streaming-ingestion metric, neither of
which this read-only pass pulled. The one directly relevant, dated, already-documented growth
signal already in CLAUDE.md is the schema-conventions section's note that
`sec_adv_private_fund.fund_index` (the same table `MANAGES_FUND` reads) hit 22,277 for a single
adviser's one March-2026 filing — evidence this table's *shape* (a few outlier filers
contributing a large share of rows) is already known to be volatile, not evidence of an
overall row/day rate. Do not treat the absence of a growth-rate number here as "flat" — it is
simply unmeasured in this pass.

## What this means for the next ticket (not decided here — read-only ticket)

The next ticket's checkpoint-mechanism design needs to account for at least three distinct
source shapes, not one:

- Silver tables with a genuine `ingested_at` (INSTITUTIONAL_HOLDS's pair, EMPLOYED_BY's pair,
  and AUDITED_BY's currently-empty fallback `sec_accounting_flag`) can support a real
  timestamp-based incremental filter.
- Silver tables with only `last_sync_run_id`/business dates and no wall-clock ingestion
  timestamp (IS_INSIDER, HOLDS, COMPANY_HOLDS, HAS_PARENT_COMPANY's primary,
  MANAGES_FUND's silver pair, AUDITED_BY's primary) would need either a schema change (add
  `ingested_at`) or an accession-number/natural-ordering-based watermark instead.
- The four types reading MDM's own Postgres tables directly (IS_ENTITY_OF, IS_PERSON_OF,
  ISSUED_BY, and MANAGES_FUND's/HAS_PARENT_COMPANY's fallback paths) aren't reading a silver
  table at all — any incremental mechanism for them has to filter `mdm_adviser`/`mdm_person`/
  `mdm_security`/`mdm_company`/`mdm_fund` by their own `valid_from`/`valid_to` versioning
  columns, a different mechanism than a silver-table watermark.
