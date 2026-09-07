Type: research
Status: resolved

**Spawned by:** the map's own charting session — 2 of 11 `_derive_*` types were confirmed live in code (`_derive_institutional_holds`, `_derive_holds`), the other 9 were presumed to share the same `_bounded_relationship_sql` write-count-bound-not-recency shape but never individually checked.

## Question

For every one of `MDMPipeline.derive_relationships()`'s 11 `_derive_*` methods (`_derive_is_insider`, `_derive_holds`, `_derive_company_holds`, `_derive_institutional_holds`, `_derive_is_entity_of`, `_derive_has_parent_company`, `_derive_is_person_of`, `_derive_manages_fund`(`_batch`), `_derive_issued_by`, `_derive_employed_by`, `_derive_audited_by`):

1. **Confirm the actual filtering shape in code** — does it genuinely scan the full source table bounded only by write-count (`_bounded_relationship_sql`'s `remaining`/`existing` pattern), or does at least one of the "presumed same shape" 9 already have some real incremental/diff mechanism this map's charting session missed? Read each method directly; don't extrapolate from the 2 already confirmed.
2. **Confirm real data-volume risk per type** — for each type's source table(s), get the live row count (Snowflake `EDGARTOOLS_PROD.EDGARTOOLS_SOURCE`/`EDGARTOOLS_SILVER`, whichever this method's `self.silver.fetch(...)` call actually reads) and, where available, growth rate. `INSTITUTIONAL_HOLDS` is already known at 6.8M rows (`sec_thirteenf_holding`); this ticket should produce the equivalent number (or a credible estimate) for the other 10.
3. **Note what source-table timestamp/versioning columns exist per type** — this doesn't need to design the checkpoint mechanism (that's the next ticket), just inventory what's available (an `ingested_at`-equivalent column, a natural accession-number ordering, nothing usable, etc.) per source table, since the next ticket's mechanism choice depends on this.

Read-only investigation — no code changes, no decisions. Use `/research` per this map's own workflow.

## Answer

Full detail (row-count/timestamp table per type, plus how each number was obtained):
[`research/01-incremental-filtering-status.md`](../research/01-incremental-filtering-status.md).

**Headline: the "presumed same shape" assumption was wrong for 4 of the 9 unconfirmed types,
and the map's list of "confirmed" types was incomplete.** Reading all 11 `_derive_*` methods
directly (not extrapolating) found **four distinct filtering shapes**, not the one
`_bounded_relationship_sql` shape the map assumed:

1. **Growing-window LIMIT** (`_bounded_relationship_sql`, write-count bound, matches the map's
   description): IS_INSIDER, HOLDS, COMPANY_HOLDS, and — only partially, see below —
   HAS_PARENT_COMPANY and AUDITED_BY. (5 of 11)
2. **CIK/CRD-range batched full scan** (memory-bounded per batch, but every batch still runs —
   `remaining` only short-circuits the batch loop): INSTITUTIONAL_HOLDS (already known) **and
   MANAGES_FUND, which is a new finding — it does NOT use `_bounded_relationship_sql` at all**,
   contrary to the map's presumption. (2 of 11)
3. **Fully unbounded MDM-Postgres table scan, Python-side `break` only — no SQL LIMIT
   whatsoever**: IS_ENTITY_OF, IS_PERSON_OF, ISSUED_BY, plus MANAGES_FUND's own
   adviser-universe prefetch and HAS_PARENT_COMPANY's fallback path. These four/five don't call
   `self.silver.fetch()` for their primary source at all — they read MDM's own Postgres tables
   (`mdm_adviser`, `mdm_person`, `mdm_security`, `mdm_company`, `mdm_fund`) directly via
   SQLAlchemy, with the entire matching row set always materialized into memory regardless of
   `remaining`. **This shape was not on the map's radar at all.**
4. **An always-unbounded secondary sub-query inside an otherwise-bounded method**: EMPLOYED_BY's
   second source table (`sec_employment_event`) is called with `remaining=None` explicitly, so
   it does a full table scan on every single call no matter how small the method's overall
   budget is — a divergence hidden inside a method that otherwise looks like shape 1.

**Two currently-live wrinkles, not code-shape findings but relevant to prioritization:**
HAS_PARENT_COMPANY's presumed-bounded primary path is a no-op today because
`sec_subsidiary_evidence` has 0 rows — every real call falls through to the unbounded
`mdm_company` fallback. AUDITED_BY's primary (`sec_auditor_report_evidence`) and fallback
(`sec_accounting_flag`) sources are both 0 rows today — the bounded-LIMIT code is correct but
currently filters nothing.

**Data volume** (live-queried 2026-09-06; Snowflake `EDGARTOOLS_PROD.EDGARTOOLS_SILVER` via
`snow sql --connection edgartools-prod`; MDM Postgres via `edgartools-prod/mdm/postgres_dsn`,
DSN never displayed): INSTITUTIONAL_HOLDS' `sec_thirteenf_holding` remains the largest at
6,799,919 rows. Next largest: `sec_company_filing` 6,551,594 (IS_INSIDER's join target),
`sec_adv_private_fund` 414,968 (MANAGES_FUND — the same table CLAUDE.md's schema-conventions
section already flags for a 22,277 `fund_index` outlier on one filer), `mdm_fund` 130,615.
Everything else is under ~82K rows. The four MDM-Postgres-only types (IS_ENTITY_OF,
IS_PERSON_OF, ISSUED_BY, HAS_PARENT_COMPANY's fallback) currently have low or zero live
candidate rows (0, 0, 3,143, and 0 respectively) — real today, but the unbounded-scan code
shape itself is what carries forward risk as these tables grow, independent of today's size.

**Timestamp/versioning columns**: only two silver source-table families across all 11 types
have a genuine wall-clock `ingested_at TIMESTAMPTZ` column — `sec_thirteenf_holding`/
`sec_thirteenf_filing` (INSTITUTIONAL_HOLDS) and `sec_executive_record`/`sec_employment_event`
(EMPLOYED_BY) — plus `sec_accounting_flag` (AUDITED_BY's empty fallback), which additionally
carries Ticket 33's `valid_from`/`valid_to`/`is_current`. Every other silver table in this
inventory has only `last_sync_run_id` (a run-id string, not a timestamp) and/or business dates
(`effective_date`, `report_date`), plus a natural `accession_number`-based ordering that's
roughly but not guaranteed chronological. The five MDM-Postgres-sourced tables
(`mdm_adviser`/`mdm_person`/`mdm_security`/`mdm_company`/`mdm_fund`) all carry SCD2-style
`valid_from`/`valid_to` (TIMESTAMPTZ), a different versioning surface than any silver table's.

No reliable growth-rate number was captured this session (would need a historical snapshot or
streaming metric neither pulled here) — see the research file for what's known instead.

**Implication for Ticket 02** (which is a decision/design ticket, not touched here): a single
checkpoint mechanism won't cover all 11 types — at minimum it needs a genuine-timestamp variant
(for the 2-3 tables that have `ingested_at`), a natural-ordering/schema-addition variant (for
the silver tables that only have `last_sync_run_id`), and an entirely separate
`valid_from`/`valid_to`-based variant for the newly-identified MDM-Postgres-only shape (3), which
Ticket 02 should treat as a first-class case rather than an oversight to patch into shape 1.
