# Reconcile infra/snowflake/sql/bootstrap/*.sql manual prod patches against native_pull's Terraform templates

Type: task
Status: resolved

Blocks: 05, 06

## Question

Surfaced while resolving Ticket 02 (how `EDGARTOOLS_GOLD` actually gets
populated). Confirmed one concrete, load-bearing drift and flagged a
broader, unaudited one — this ticket resolves the broader one and confirms
the fix for the concrete one before either the repopulation sequence
(Ticket 05) or the go-live runbook (Ticket 06) can be trusted against a
brand-new account.

**Confirmed drift:** `infra/terraform/snowflake/modules/native_pull/sql/refresh_procedure.sql`
— the file `terraform apply` actually deploys — only lists the original 9
gold tables to force-refresh after a manifest load. A live prod incident
(CLAUDE.md's "Manifest-pipeline ownership" 5-whys) found this was silently
leaving 11 newer gold tables permanently empty past their initial
`ON_CREATE` refresh, and fixed it by manually reapplying
`infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql` (20 tables) directly
against prod via `CREATE OR REPLACE PROCEDURE`. That fix was never
backported into the Terraform template. Confirmed via grep that nothing in
`deploy-snowflake-stack.sh` or `go-live.sh` runs `04_refresh_wrapper.sql` —
a brand-new account provisioned via the documented Terraform path gets the
stale 9-table procedure and silently reintroduces the same bug.

**Unaudited, broader gap:** the entire `infra/snowflake/sql/bootstrap/`
directory (`01_source_stage.sql` through `08_loader_role.sql`, 8 files) is
not invoked by any repeatable deploy script — confirmed via repo-wide grep,
referenced only in comments/docs. A quick skim of each file's header
comment suggests `01`-`04` and `06` are earlier, likely-superseded versions
of what the Terraform `native_pull` module now creates natively (source
stage, refresh status, load/refresh wrappers, fundamentals load wrapper);
`07` (`07_mdm_export_targets.sql`, the 5 MDM golden-record export target
tables `export.py` MERGEs into) and `08` (`08_loader_role.sql`, the
`EDGARTOOLS_PROD_LOADER` role that owns the gold dynamic tables and
manifest-pipeline procedures) read as genuinely additive fixes with **no**
Terraform equivalent at all — meaning a brand-new account's Terraform apply
would not create these objects, and nothing else would either unless
someone knows to run these 2 files by hand.

Resolve, file by file, for each of the 8:

1. Is it superseded by something the Terraform `native_pull` module (or
   another Terraform root) already creates? If so, is its *content*
   identical to what Terraform creates, or has it drifted (like
   `04_refresh_wrapper.sql` has)?
2. If not superseded, is it a one-time historical fix (irrelevant to a
   brand-new account, e.g. renaming an existing table to preserve history —
   `07_mdm_export_targets.sql`'s stated purpose) or a genuinely required
   provisioning step for any account, old or new?
3. For anything in category "genuinely required, not in Terraform": decide
   whether it becomes a new Terraform resource (folded into `native_pull`
   or another module), a new `go-live.sh` stage that runs the SQL file
   directly (consistent with how the Neo4j grants SQL is already run), or
   stays a documented manual step in the runbook Ticket 06 assembles.

## Notes

`task`-type (AFK) — mostly fact-finding (file-by-file drift comparison), but
likely to surface real per-file decisions under point 3 above; those can be
resolved inline here rather than spawned as further tickets, since they're
narrow enough to fit in one pass once the drift is mapped.

## Answer

Read all 8 files in full and cross-checked each against Terraform, the live
manifest-processing call graph, and (for the source-table question) the
actual Python code that decides what `gold-refresh` exports
(`edgar_warehouse/infrastructure/run_manifest_builder.py`'s
`SNOWFLAKE_EXPORT_TABLES` dict — the true source of truth, independent of
either SQL file or Terraform). The drift is **much larger than Ticket 02's
single finding**, and three files are not superseded/historical at all —
they're the current, live procedure bodies, more current than what
Terraform deploys.

### File-by-file

**`01_source_stage.sql` — NOT superseded (correction of my Ticket 02
skim).** Its table DDL is the live, current shape — it creates 9 tables
Terraform's `native_pull` module's `table_definitions` local
(`main.tf:6-316`) never creates at all: `SEC_SUBSIDIARY_EVIDENCE`,
`SEC_AUDITOR_REPORT_EVIDENCE`, `SEC_EMPLOYMENT_EVENT`,
`SEC_ADV_FIRM_ROSTER`, `SEC_ADV_PRIVATE_FUND`, `EARNINGS_CALENDAR`,
`GUIDANCE_FACTS`, `CONSENSUS_ESTIMATES`, `TRANSCRIPT_EVENTS`. Confirmed via
3 independent sources agreeing: this file's own DDL, `03`'s `targetTables`
map (below), and — most authoritatively — Python's own
`SNOWFLAKE_EXPORT_TABLES` dict, which is what `gold-refresh` actually
consults to decide which tables to export as Parquet in the first place.
**Category: genuinely required, not in Terraform.**

**`02_refresh_status.sql` — genuinely superseded, safe to skip.** Creates
the same `SNOWFLAKE_REFRESH_STATUS` table and manifest stream Terraform's
`native_pull` module already creates (`table_definitions[status]` +
`snowflake_stream_on_table.manifest`), identical shape. **Category:
superseded, no drift.**

**`03_source_load_wrapper.sql` — NOT superseded (correction).** This is the
**live, current `LOAD_EXPORTS_FOR_RUN` body** — 22 tables in its
`targetTables` map, vs. Terraform's `source_load_procedure.sql` template's
19. Its own comment dates the fix: "found 2026-07-27 while landing ERDP-01:
GUIDANCE_FACTS ... had never actually loaded into EDGARTOOLS_SOURCE." This
is the exact sibling drift to Ticket 02's `REFRESH_AFTER_LOAD` finding, on
the LOAD side rather than the REFRESH side — same pattern, same
never-backported-into-Terraform gap. **Category: genuinely required, stale
Terraform template.**

**`04_refresh_wrapper.sql` — already found by Ticket 02.** Live 20-table
`REFRESH_AFTER_LOAD`, vs. Terraform's stale 9-table template. No new
finding here; included for completeness of the file-by-file pass.
**Category: genuinely required, stale Terraform template.**

**`05_refresher_keypair.sql` — genuinely superseded, safe to skip.** Its own
header says it plainly: "Deprecated bootstrap step retained as a
compatibility marker. The Snowflake mirror no longer relies on an
AWS-managed Snowflake sync task or RSA key-pair authentication from ECS."
**Category: superseded, no drift.**

**`06_fundamentals_load_wrapper.sql` — genuinely superseded, safe to
skip.** Creates a separate `LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN` procedure —
confirmed via repo-wide grep that **nothing in the live manifest-processing
chain ever calls it**: `PROCESS_RUN_MANIFEST_STREAM` (both the Terraform
version and `04`'s live-patched version) only ever calls
`LOAD_EXPORTS_FOR_RUN` and `REFRESH_AFTER_LOAD`. Only reference left is in
`scripts/verify-pr1/` (an old, one-off PR verification script). `03`'s
comment confirms why: its unified MERGE generator now "handles" composite
keys too, absorbing the reason `06` was split out in the first place.
**Category: superseded, no drift.**

**`07_mdm_export_targets.sql` — genuinely additive, no Terraform equivalent
at all.** Creates the 5 MDM golden-record export target tables
(`MDM_COMPANY_ENTITY`, `MDM_ADVISER`, `MDM_PERSON`, `MDM_SECURITY`,
`MDM_FUND`) that `edgar_warehouse/mdm/export.py`'s
`MDMExporter.export_pending()` MERGEs into. Confirmed Terraform's
`account_baseline` module creates only the database, 2 schemas, and 2
warehouses — no domain tables at all, so nothing else could be creating
these. **Directly load-bearing for what Ticket 02 traced**: `company.sql`
(dbt) reads `{{ source("mdm_export", "MDM_COMPANY_ENTITY") }}` — without
this table, that gold model breaks on a brand-new account. **Category:
genuinely required, not in Terraform.**

**`08_loader_role.sql` — genuinely additive, but *already* documented as
deliberately complementary to Terraform, not an oversight.** Creates
`EDGARTOOLS_PROD_LOADER`'s ownership of the 20 gold dynamic tables + 3
manifest procedures, plus 2 object-level grants Terraform's grant model
can't express. Confirmed by reading
`infra/terraform/access/snowflake/modules/account_access/main.tf:177-186`
— its own comment names this file explicitly: "[two grants] aren't modeled
here ... they're granted by
`infra/snowflake/sql/bootstrap/08_loader_role.sql`, which also owns
transferring ownership of the EDGARTOOLS_GOLD dynamic tables and the 3
manifest procedures onto this role — object ownership isn't something this
Terraform module manages for any role, including deployer." So `access/snowflake`
*does* create the `EDGARTOOLS_PROD_LOADER` role and its schema/warehouse-level
grants — but never runs `08`, so on a brand-new account the role would
exist with no ownership of anything. This is the single most load-bearing
gap of all 8: without it, `REFRESH_AFTER_LOAD`'s `ALTER DYNAMIC TABLE ...
REFRESH` (which requires the *direct owner* role, per CLAUDE.md's
"Manifest-pipeline ownership" 5-whys) fails on the very first
manifest-processing run. **Category: genuinely required, not in Terraform
— by design, not oversight.**

### Decision: two different fix shapes for two different kinds of gap

**`01`, `03`, `04` — backport current content into the Terraform
templates.** These are warehouse-schema declarative state that Terraform's
`native_pull` module already owns and is simply stale on. Folding the
newer content back into `table_definitions` (extend with the 9 missing
tables) and swapping in `03`'s/`04`'s current procedure bodies for
`source_load_procedure.sql`/`refresh_procedure.sql` keeps exactly one
source of truth — the alternative (a permanent go-live.sh stage that
re-runs raw SQL over what Terraform already declares) would leave two
competing definitions of the same objects, guaranteeing this exact drift
recurs. **Not done in this ticket** — this is real, sizeable mechanical
work (transcribing 9 tables' column shapes into HCL, diffing two ~150-line
JavaScript procedure bodies), belongs to an "implement ticket 07" session,
same as every other implementation step on this map.

**`07`, `08` — new `go-live.sh` stages that run the SQL files directly,
not Terraform resources.** Both differ in kind from `01`/`03`/`04`: `07`'s
table shapes are derived from Python SQLAlchemy models
(`edgar_warehouse/mdm/database.py`), which can drift independently of
Terraform's release cadence — keeping it as directly-run SQL means it stays
adjacent to the Python code it mirrors, the same reasoning that already
governs how the Neo4j grants SQL is run (a precedent this map's Ticket 01
already established). `08` is *explicitly* out of Terraform's remit by the
Terraform module author's own words — object ownership isn't something
`snowflake_grant_privileges_to_account_role` can express, so there's no
"fold it into Terraform" option available even in principle. Sequencing
matters for both: `07` needs the `gold` schema to exist (Terraform, already
does); `08` needs the loader role's schema-level grants (Terraform,
already does) *and* the gold dynamic tables to exist first (needs at least
one `dbt run` to have created them) — so `08` must run after the first dbt
run, not before it.

**`02`, `05`, `06` — skip entirely for a brand-new account.** Confirmed
dead: `02` is byte-identical to what Terraform already creates; `05` says
it's deprecated in its own header; `06`'s procedure is called by nothing
live.

Feeds directly into **Ticket 06** (runbook assembly), now unblocked along
with **Ticket 05**: the runbook needs the `01`/`03`/`04` Terraform
backport done *before* the first native-pull apply on the new account, and
new `07`/`08` stages sequenced correctly relative to the first dbt run.
