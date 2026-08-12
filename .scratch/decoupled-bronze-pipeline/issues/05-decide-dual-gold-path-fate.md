# Decide the fate of the dual gold path

Type: grilling
Status: resolved
Blocked by: (none)

## Question

Today gold exists via two parallel paths: (1) warehouse-computed Python
gold tables (`edgar_warehouse/gold.py`/`serving/gold_models.py`) exported
as Snowflake manifests, loaded via the S3->SNS->task pipe; (2) Snowflake-
native `EDGARTOOLS_SOURCE` (native S3 pull from bronze) -> dbt models ->
`EDGARTOOLS_GOLD`. Decide: collapse into one (retire warehouse Python gold
in favor of dbt-on-source, or the reverse), keep both but make each
independently async/message-driven, or some other resolution. This is
possibly the single highest-leverage, highest-risk decision on this map —
touches every downstream gold consumer (dashboards, Decision Contract
surfaces).

## Answer

**The premise is factually wrong — there is no dual gold *computation* path
to collapse.** Verified against the live code and the bootstrap SQL, not
just docs:

- `edgar_warehouse/serving/gold_models.py`'s `iter_gold_tables()` is the
  **sole builder** for all ~26 gold tables, including the ones that looked
  like they might be independently Snowflake-native
  (`SEC_FINANCIAL_FACT`, `SEC_THIRTEENF_HOLDING`, `EARNINGS_RELEASE`,
  `EXECUTIVE_RECORD`, `ACCOUNTING_FLAG`, the ADV/Firm-Roster passthroughs).
  Every one of these has a `_build_*` function in that one module and is
  routed through `GOLD_EXPORT_MAP` -> `write_gold_table_to_serving_export`.
- `infra/snowflake/sql/bootstrap/01_source_stage.sql` sets the
  `EDGARTOOLS_SOURCE_EXPORT_STAGE` stage's `URL` to the same
  `SERVING_EXPORT_ROOT`/export-root S3 prefix Python writes to — not the
  bronze root, not a second independent stage. Every table in that schema
  is commented "mirrored from the canonical warehouse gold export" or
  "Passthrough from silver `<table>`." No `EXTERNAL TABLE`s, no second
  ingestion path anywhere in `infra/snowflake/sql/bootstrap/`.
- dbt's `models/gold/*.sql` (confirmed to be dbt's entire model tree — no
  staging/intermediate layer exists) then builds `EDGARTOOLS_GOLD` dynamic
  tables from that already-Python-computed `EDGARTOOLS_SOURCE` schema.
  Nearly all are literal mirrors. Three carry real SQL logic worth naming:
  `company.sql` (left-joins MDM's `MDM_COMPANY_ENTITY`, itself written by a
  *third*, distinct path — MDM's own Python/SQLAlchemy MERGE straight into
  `EDGARTOOLS_GOLD`, bypassing `EDGARTOOLS_SOURCE` and dbt entirely for
  that one table), `financial_factors.sql` (derives from the
  `financial_derived` model), and `adv_fund_count_reconciliation.sql`
  (joins two sources for a real cross-check).
- One genuine exception, not a competing computation of the same data: the
  Explore trio (`earnings_calendar`, `consensus_estimates`,
  `transcript_events`) is built by a separate Python subsystem
  (`edgar_warehouse/explore/*`), outside the main `gold_refresh` loop, from
  external pilot sources (finnhub/yahoo/firm_manual) — different data, not
  a second path for the same business tables.

So "Snowflake-native `EDGARTOOLS_SOURCE` -> dbt -> `EDGARTOOLS_GOLD`" isn't
an independent computation from bronze — the Snowflake native-pull
mechanism is purely the *ingestion/delivery* leg for content Python already
fully computed. There's nothing to retire in favor of the other, because
only one of the two "paths" this ticket named actually computes anything.

**Resolution:** close this ticket as a factual correction, not a design
choice. The map's Destination/Notes carried the same wrong premise and have
been amended accordingly (see map). The real open architectural question —
given gold compute already lives entirely in Python/DuckDB and
Snowflake/dbt is already a thin publish/mirror layer, should that split be
formalized as intentional, or is there a real case for moving some/all
computation into Snowflake SQL — is split off as
[Decide whether gold compute stays in Python/DuckDB or moves into Snowflake
SQL](08-decide-gold-compute-location.md).
