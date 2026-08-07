# Determine how EDGARTOOLS_GOLD actually gets populated end to end, and whether a brand-new account needs a historical-backfill trigger

Type: task
Status: resolved

## Question

Foundational to everything after it in this map, and not confidently
answerable from docs alone — needs to be traced against the actual code and
SQL, not assumed.

CLAUDE.md's architecture diagram shows `EDGARTOOLS_SOURCE` (native S3 pull)
feeding dbt gold models. Separately, the Gold-build-memory 5-whys section and
the `go-live.sh` plan output (stage 11/12) describe a distinct Python-side
path: `gold-refresh` builds gold tables in-process and writes export
manifests to S3, which `SNOWFLAKE_RUN_MANIFEST_TASK` + `REFRESH_AFTER_LOAD`
then ingest into Snowflake. These sound like they could be the same
mechanism described two ways, or two genuinely different paths (one for
`EDGARTOOLS_SOURCE`'s raw tables, one for `EDGARTOOLS_GOLD`'s dynamic
tables) — resolve which.

Also resolve: native-pull's storage integration + Snowpipe/manifest-task
machinery is normally described as reacting to *new* files landing in S3
after it's stood up. Bronze/silver already exist in S3 from before this
account existed (per this map's Destination). Does a brand-new account's
native-pull layer need an explicit one-time trigger to process that
*existing* S3 history, or does something in the pipeline already handle
this (e.g. an initial full-scan/backfill mode, or does `gold-refresh`
itself just read current silver state directly rather than depending on
historical S3 events at all)?

## Notes

Found one relevant, but not fully answering, precedent while surveying:
`infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql` renamed a target
table specifically to avoid losing already-exported history to a fresh
empty table — suggests the codebase is aware "brand new table = no history"
is a real failure mode elsewhere, which is exactly the shape of risk this
ticket needs to rule in or out for gold/source population.

This is a `task`-type ticket (AFK) because it's a fact-finding trace through
existing code/SQL, not a decision with real alternatives — but its answer
may surface a real decision-shaped follow-up ticket (e.g. "how do we trigger
the backfill") if the answer is "yes, something is needed and nothing
handles it yet."

## Answer

**1. One mechanism, not two — traced end to end through the actual
Terraform/SQL/Python, not assumed from CLAUDE.md's diagram.**
`edgar_warehouse/serving/gold_models.py`'s `gold-refresh` computes ~24
gold-shaped tables from the *current* silver DuckDB state and writes them
as Parquet + one manifest JSON to S3. Snowflake's side
(`infra/terraform/snowflake/modules/native_pull/main.tf`):
`snowflake_pipe.manifest` (Snowpipe, `auto_ingest = true`, SNS-driven)
auto-loads new manifest files into a raw inbox table; a stream + task
(`manifest_processor`, fires on `SYSTEM$STREAM_HAS_DATA`) then calls
`PROCESS_RUN_MANIFEST_STREAM`, which for each new manifest row calls (a)
`LOAD_EXPORTS_FOR_RUN` — a keyed `MERGE` of that run's per-table Parquet
exports into `EDGARTOOLS_SOURCE`'s mirror tables (confirmed reading
`infra/terraform/snowflake/modules/native_pull/sql/source_load_procedure.sql`
directly) — then (b) `REFRESH_AFTER_LOAD`, which forces
`ALTER DYNAMIC TABLE ... REFRESH` on dbt-built `EDGARTOOLS_GOLD` tables so
they immediately reflect the fresh source data. dbt's gold models then do
real transformation, not passthrough — e.g. `company.sql` left-joins MDM's
`MDM_COMPANY_ENTITY` export target onto the mirrored `COMPANY` source
table. **CLAUDE.md's architecture diagram is misleadingly simplified**:
`EDGARTOOLS_SOURCE` is not raw bronze pulled natively from S3 — its tables
are explicitly commented "mirrored from the canonical warehouse gold
export," i.e. downstream of the same Python `gold-refresh` computation that
also (indirectly, via the forced dynamic-table refresh) drives
`EDGARTOOLS_GOLD`. One pipeline, two Snowflake-side steps triggered off one
event, not two independent paths.

**2. No historical-backfill trigger is needed — `gold-refresh` reads
current state, it doesn't replay history.** Because `gold-refresh` computes
fresh from whatever silver DuckDB contains *right now* (not an incremental
scan of past S3 events), the very first successful run against a brand-new
account's already-existing bronze/silver produces one manifest that, once
ingested, populates every `EDGARTOOLS_SOURCE` mirror table via `MERGE` —
a complete population by construction. Snowpipe's usual "only reacts to new
files" limitation doesn't bite here: there's no backlog of *past* manifests
to replay, since the first manifest a new account's storage integration
ever sees already represents complete current state.

**3. Real, unanticipated finding: the canonical Terraform template for
`REFRESH_AFTER_LOAD` is stale, and would silently reintroduce an
already-fixed bug on a brand-new account.**
`infra/terraform/snowflake/modules/native_pull/sql/refresh_procedure.sql`
— the file `terraform apply` actually uses — only refreshes the original 9
gold tables (`COMPANY`, `FILING_ACTIVITY`, `OWNERSHIP_ACTIVITY`,
`OWNERSHIP_HOLDINGS`, `ADVISER_OFFICES`, `ADVISER_DISCLOSURES`,
`PRIVATE_FUNDS`, `FILING_DETAIL`, `TICKER_REFERENCE`). CLAUDE.md's
"Manifest-pipeline ownership" 5-whys documents that this exact gap was
found live in prod and "fixed" — but the fix
(`infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql`, 20 tables,
including `EXECUTIVE_RECORDS`/`EARNINGS_RELEASES`/`INSTITUTIONAL_HOLDINGS`/
`ACCOUNTING_FLAGS`/`FINANCIAL_FACTS`/`FINANCIAL_DERIVED`/
`FINANCIAL_FACTORS`/`EARNINGS_CALENDAR`/`GUIDANCE_FACTS`/
`CONSENSUS_ESTIMATES`/`TRANSCRIPT_EVENTS`) was applied by manually
`CREATE OR REPLACE`-ing the procedure directly against prod, and was never
backported into the Terraform module. Confirmed via grep that nothing in
`deploy-snowflake-stack.sh` or `go-live.sh` ever runs `04_refresh_wrapper.sql`
— it exists only as a file someone must know to run by hand. **A brand-new
account provisioned via the documented `go-live.sh` → Terraform path would
get the stale 9-table procedure**, silently reintroducing the exact "gold
tables never refresh past their empty `ON_CREATE` state" bug CLAUDE.md
already documents as found-and-fixed once.

**4. Broader, not-fully-chased finding: the entire
`infra/snowflake/sql/bootstrap/` directory (8 files, `01`-`08`) is unwired
from any repeatable deploy path.** Confirmed via repo-wide grep — these
files are referenced only in comments and docs, never invoked by
`deploy-snowflake-stack.sh` or `go-live.sh`. Skimming each file's header:
`01`-`04` and `06` read as earlier, likely-superseded versions of what the
Terraform `native_pull` module now creates natively (source stage, refresh
status, load/refresh wrappers); `07` (MDM export target DDL) and `08`
(loader-role ownership) read as genuinely additive fixes with no Terraform
equivalent at all. I have **not** fully audited each file's current
live-vs-Terraform status — that's beyond this ticket's fact-finding scope
and belongs in its own ticket (created below), since it's a real decision
(what, if anything, needs to be reconciled or re-applied), not just a fact
to record.

**Follow-up ticket created**: [Reconcile infra/snowflake/sql/bootstrap/*.sql
manual prod patches against native_pull's Terraform templates](07-reconcile-bootstrap-sql-drift-against-terraform.md)
— appended as Ticket 07 rather than resolved here, since it's a real
decision (what, if anything, needs reconciling or re-applying), not a fact
this task-type ticket should decide. Blocks Ticket 05 (repopulation
sequence) and Ticket 06 (runbook assembly), since neither can be trusted to
actually work on a brand-new account until this drift is resolved.
