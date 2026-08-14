# Decide the Silver-Landing Ingestion Mechanism (Stage/Pipe/Task)

Type: grilling
Status: resolved
Blocked by: none

## Question

[Design the Snowflake-Native Silver Layer's Model Structure](01-design-snowflake-native-silver-model-structure.md)'s
Answer locked the *shape* of landing ingestion in prose ("reuses
`EDGARTOOLS_SOURCE`'s existing apparatus verbatim in shape, simplified in
mechanism: Python writes per-table Parquet + `run_manifest.json` to S3 →
Snowpipe auto-ingest of the manifest only → stream + task → a load
procedure ... plain `INSERT INTO target SELECT * FROM staged`") but never
turned that into a concrete Terraform/SQL plan, and
[Draft the Cutover Script and Ownership Requirements](05-draft-cutover-script-and-ownership-requirements.md)
built only the schema/table/grant DDL (`11_silver_landing_schema.sql`,
`12_silver_schema_and_mdm_reader.sql`) — no stage, pipe, stream, task, or
load procedure exists anywhere for landing today. The Python write path
(`edgar_warehouse/serving/silver_landing_export.py`/`silver_landing_writer.py`,
built and orchestrator-wired on `claude/silver-snowflake-implementation`)
is complete and produces per-table Parquet + a run manifest once an
operator sets `SILVER_LANDING_EXPORT_ROOT` — but nothing downstream reads
it yet. This ticket makes that plan concrete enough to implement.

Grounded in direct inspection of the live apparatus this is meant to
reuse (`infra/terraform/snowflake/modules/native_pull/`), not assumed from
Ticket 01's prose:

- `native_pull` is a **single per-environment module instance** (one
  `module "native_pull"` block in `accounts/{prod,dev}/main.tf`) whose
  `table_definitions` local hardcodes SOURCE's ~20 gold-mirror tables —
  it is not a generic "any schema, any tables" module today.
- Its stream processor (`stream_processor_procedure.sql`) reads
  `workflow_name` off every manifest row but does **not** branch on it —
  every manifest, regardless of which workflow produced it, gets the same
  two calls: the MERGE-based `LOAD_EXPORTS_FOR_RUN` (`source_load_procedure.sql`,
  331 lines) then `REFRESH_AFTER_LOAD` (`refresh_procedure.sql`). There is
  no existing per-workflow routing to extend.
- `SILVER_LANDING_EXPORT_ROOT`'s actual S3 bucket/prefix has never been
  decided or documented anywhere in the repo (confirmed via repo-wide
  grep) — today it's genuinely just "whatever an operator points the env
  var at."
- The manifest pipe is `auto_ingest = true` with `aws_sns_topic_arn` — it
  depends on an S3 bucket event notification wired to a specific SNS
  topic upstream in the AWS Terraform, not something a new pipe gets for
  free by existing in the same Snowflake schema.

Specify:

1. **New parallel apparatus vs. extending the live one.** A second,
   landing-dedicated stage/pipe/stream/task/load-procedure that never
   touches `native_pull`'s existing Terraform resources (isolated blast
   radius, some duplication) — versus teaching the single existing stream
   processor to branch on `workflow_name` and call a new landing load
   procedure for landing manifests (less duplication, but every future
   change to that procedure now risks the already-live, production-critical
   gold-refresh chain, and mixes MERGE and append-only-INSERT semantics in
   one code path).
2. **Does landing even need the Snowpipe-auto-ingest shape at all**, given
   it's pure append (no `mergeKeys`, no manifest-driven MERGE target
   resolution) — or does a plain scheduled `TASK` running `COPY INTO ...
   FILE_FORMAT = (...) PATTERN = ...` per landing table (Snowflake's COPY
   INTO already dedups by file path/metadata, no stream/manifest-table
   indirection needed) cover the same correctness bar with less new
   infrastructure? If yes, the manifest's row-count validation (the one
   piece of real value the current shape adds — catching a partial/corrupt
   Parquet write) needs a different home.
3. **Bucket/prefix for `SILVER_LANDING_EXPORT_ROOT`.** Same bucket as
   `SERVING_EXPORT_ROOT` (share the existing storage integration + S3 event
   notification/SNS topic, distinguish via a `/silver-landing/` prefix and
   pattern-filtered pipe) vs. a new dedicated bucket (new storage
   integration, new S3 event notification wiring in AWS Terraform).
4. Whichever shape is chosen, name the concrete new artifacts (Terraform
   resources and/or SQL bootstrap files) this ticket's answer commits the
   next implementation pass to building — matching this map's standing
   requirement that every provisioning step is committed and re-runnable.

## Answer

**New, isolated apparatus** — its own stage/task/procedure, never touching
`native_pull`'s live Terraform resources. **Scheduled `COPY INTO`, not
Snowpipe+stream+task** — landing is pure append with no `mergeKeys`, so the
manifest/stream indirection buys nothing SOURCE's MERGE-target-resolution
needed it for. **Same bucket as `SERVING_EXPORT_ROOT`**, new prefix.

### Why scheduled COPY INTO, concretely

`stream_processor_procedure.sql` exists to solve two problems landing
doesn't have: (a) resolving *which* MERGE target a manifest's rows belong
to (`source_load_procedure.sql`'s `mergeKeys` map), and (b) draining an
append-only stream exactly once via `INSERT...SELECT` before a task
commits. Landing has one shape for every table (plain INSERT) and
Snowflake's own `COPY INTO` already tracks loaded-file history per stage
(`LOAD_HISTORY`/`VALIDATION_MODE`) — re-running `COPY INTO` against files
it already loaded is a no-op by default, so the manifest's row-count
validation isn't the only safety net; it's redundant with a capability
Snowflake already provides for free. The one thing lost is *event-driven*
latency (Snowpipe fires within seconds of the S3 PUT; a scheduled task
waits for its next tick) — acceptable here since nothing downstream reads
`EDGARTOOLS_SILVER_LANDING` synchronously yet (Ticket 01's dbt silver
`dynamic_table` models refresh on their own `TARGET_LAG`, not on landing's
write latency).

### Storage: one small, additive Terraform change, not zero

Checked live: `native_pull`'s `snowflake_storage_integration_aws` sets
`storage_allowed_locations = [var.export_root_url]` — a single **exact**
URL, not the whole bucket. Snowflake enforces this as a prefix allowlist,
so a new stage under a sibling prefix in the same bucket (e.g.
`s3://<serving-export-bucket>/warehouse/artifacts/silver_landing/`) is
**not** covered by the existing integration until that list gains a
second entry. Required change: widen `storage_allowed_locations` to
`[var.export_root_url, var.silver_landing_export_root_url]` (or similar) —
additive, one Terraform apply, touches only the storage integration
resource, not the pipe/stream/task SOURCE already depends on. This is the
only AWS/Terraform-side change this decision requires; no new bucket, no
new S3 event notification, no new SNS topic.

### Concrete artifacts for the next implementation pass

1. **Terraform** (`infra/terraform/snowflake/accounts/{prod,dev}/main.tf`
   or a small module var change): widen `native_pull`'s
   `storage_allowed_locations` as above. This is the only piece that must
   go through Terraform rather than a bootstrap SQL script, since the
   storage integration resource is Terraform-managed today.
2. **New hand-authored SQL bootstrap file**, continuing this map's own
   precedent (`11_silver_landing_schema.sql`/`12_silver_schema_and_mdm_reader.sql`
   were hand-authored/generated SQL, not Terraform) —
   `infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql`:
   - `CREATE FILE FORMAT IF NOT EXISTS EDGARTOOLS_SILVER_LANDING.PARQUET_FORMAT TYPE = PARQUET` (new, scoped to the landing schema — not a reuse of `native_pull`'s SOURCE-schema-scoped format resource).
   - `CREATE STAGE IF NOT EXISTS EDGARTOOLS_SILVER_LANDING.LANDING_STAGE URL = '<bucket>/warehouse/artifacts/silver_landing/' STORAGE_INTEGRATION = <existing integration name> FILE_FORMAT = ...` — reuses the existing (now-widened) storage integration; no new integration object.
   - One `CREATE OR REPLACE PROCEDURE LOAD_SILVER_LANDING()` (JavaScript or Scripting, matching this repo's existing procedure style) that loops the 30 landing-eligible tables and issues `COPY INTO EDGARTOOLS_SILVER_LANDING.<table> FROM @LANDING_STAGE/<table>/ FILE_FORMAT = (...) PATTERN = '.*[.]parquet' ON_ERROR = ABORT_STATEMENT` per table — table list generated the same way `generate_silver_landing_ddl.py` already derives the 30-table set, so the two can't silently drift apart.
   - One `CREATE TASK IF NOT EXISTS LOAD_SILVER_LANDING_TASK ... SCHEDULE = '5 MINUTE' ... AS CALL LOAD_SILVER_LANDING()`, owned by `EDGARTOOLS_PROD_LOADER` (same owner as everything else this map provisions — no new role). 5-minute cadence is a starting default, not load-bearing on anything downstream yet; tune once real volume exists.
   - Grants: `EDGARTOOLS_PROD_LOADER` needs `USAGE` on the stage/file format, `EXECUTE TASK`, plus the `SELECT, INSERT` it already has on the landing tables from Ticket 05.
3. **Python side unaffected** — `silver_landing_export.py`/`silver_landing_writer.py` already write per-table Parquet to a `StorageLocation`; only `SILVER_LANDING_EXPORT_ROOT`'s actual deployed value changes (a real `s3://.../silver_landing/` path), which is a deploy-time env var, not a code change.
4. **Not building**: any run-manifest inbox table, pipe, or stream for landing — the manifest the writer already produces (`run_manifest.json`) stays useful as an audit/debug artifact per run but is not consumed by the ingest path itself under this design; nothing currently reads it downstream.

### Built and applied live to prod — 2026-08-13, plus three corrections the design above didn't anticipate

Implemented as `infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql` and a small `native_pull` Terraform change (`additional_storage_locations` variable), applied end-to-end against the real prod Snowflake account. Note on sequencing: prod Snowflake was cut over mid-implementation from the old `xcpclkf-kb19989` account to a fresh `pijjxma-ppb32800` account (`.scratch/snowflake-account-cutover/map.md`) — `11_silver_landing_schema.sql`/`12_silver_schema_and_mdm_reader.sql` (Ticket 05) had never actually been applied to any live account before this session, so this pass applied the full `11_` → `12_` → Terraform-widen → `13_` chain, not `13_` alone.

**Ownership caught and fixed before applying**: the first draft of `13_` created `LOAD_SILVER_LANDING`/`LOAD_SILVER_LANDING_TASK` under `ACCOUNTADMIN` — the exact pattern CLAUDE.md's "Manifest-pipeline ownership + cursor-syntax incident" documents as an explicit user-prohibited pattern for pipeline objects. Fixed before anything was applied: both are created directly as `EDGARTOOLS_PROD_LOADER`, which required granting the loader `CREATE FILE FORMAT/STAGE/PROCEDURE/TASK` on the schema and the account-level `EXECUTE TASK` (ACCOUNTADMIN-only grants, done once).

**Three real bugs found only by testing live against real prod Snowflake, not assumed from docs:**

1. **`COPY INTO ... MATCH_BY_COLUMN_NAME` does not invoke a target column's `DEFAULT`** for a column absent from the source Parquet — it leaves it `NULL`. This broke `parse_sequence` (`NOT NULL`, `DEFAULT PARSE_SEQ.NEXTVAL`) outright on the very first live test (`NULL result in a non-nullable column`). Fixed at the schema level: `generate_silver_landing_ddl.py` no longer emits `NOT NULL` on `parse_sequence` (regenerated `11_silver_landing_schema.sql` — diff confirmed to be exactly that one change across all 31 tables, live `ALTER TABLE ... ALTER COLUMN parse_sequence DROP NOT NULL` applied to the already-created prod tables — safe, since Snowflake's `PRIMARY KEY` is declarative-only/unenforced). `LOAD_SILVER_LANDING` now follows every table's `COPY INTO` with `UPDATE ... SET parse_sequence = PARSE_SEQ.NEXTVAL WHERE parse_sequence IS NULL`. This also required reversing part of Ticket 05's "SELECT + INSERT only, no legitimate UPDATE caller" grant policy — the backfill is that caller now; `13_` grants `UPDATE` on all landing tables to the loader, documented inline as a deliberate, narrow reversal.
2. **`ResultSet.getColumnValue('rows_loaded')` by name throws** ("Given column name/index does not exist") against a real `COPY INTO` result set in the JS Stored Procedure API — fixed by using the documented positional index instead (column 4).
3. **`COPY INTO`'s result-set shape differs by outcome**: a real load returns the 10-column per-file shape, but zero matching files returns a *different*, single-column informational row (`"Copy executed with 0 files processed."`). `rs.next()` is `true` in both cases, so checking row presence alone crashed on the single-column shape. Fixed by checking `copyStmt.getColumnCount() > 1` before reading file-level columns.

**Also found and fixed**: the AWS IAM role Snowflake assumes for S3 reads (`edgartools-prod-snowflake-s3`) has its own separate exact-prefix allowlist (mirroring Snowflake's own `STORAGE_ALLOWED_LOCATIONS`) — widening the Snowflake-side storage integration alone wasn't sufficient; the first live `COPY INTO` test failed with `s3:ListBucket ... AccessDenied` until the IAM policy (`infra/terraform/access/aws/modules/runtime_access/main.tf`'s `snowflake_storage_reader` policy) was also widened. Applied live via `aws iam put-role-policy` (same zero-collateral-alternative-to-a-full-root-apply reasoning as the Snowflake-side widen below); the Terraform source for this AWS-side change was not committed in this pass — **follow-up needed**: mirror the `additional_storage_locations`-style pattern into `runtime_access`'s policy so this isn't only a live, uncommitted IAM change (same class of risk CLAUDE.md's cutover incidents warn about — living config that isn't captured in a re-runnable script).

**Both storage-integration/IAM-policy widens applied via direct `ALTER STORAGE INTEGRATION`/`aws iam put-role-policy`, not `terraform apply`** — the Snowflake accounts/prod Terraform root's `terraform plan` couldn't run in this session (missing password credential for the configured `snowflake_authenticator = "snowflake"` provider auth; not solicited from the user per this repo's own "never ask for secrets via `!` prefix" convention), and the `snowflake-account-cutover` map's own Ticket 07 already found `native_pull`'s Terraform templates materially stale versus live prod — applying that whole root blind risked reverting real, already-corrected prod state. The Terraform edits (`additional_storage_locations` in `native_pull`, its use in `accounts/prod/main.tf`) are committed and will converge cleanly on the next full, reviewed apply of that root; they were not the mechanism actually used to make the live change.

**Verified end-to-end against real prod Snowflake** (not just a syntax check): a hand-built Parquet file uploaded to the real S3 prefix, loaded through the actual deployed `LOAD_SILVER_LANDING` procedure (not an isolated manual `COPY INTO`), confirmed a correct non-null `parse_sequence` on the landed row, confirmed the zero-files case returns `tables_with_new_data: 0` cleanly, confirmed the whole `13_` script re-runs cleanly a second time (`ALTER TASK ... RESUME` on an already-started task is a no-op, not an error). All test rows and S3 test objects deleted afterward; all 31 landing tables confirmed at 0 rows before the task was resumed for real. The task was briefly suspended mid-session to stop it autonomously reprocessing test uploads on its 5-minute schedule while corrections were still in progress, then resumed once verified clean.

**Still not done** (deliberately, out of this ticket's scope): `SILVER_LANDING_EXPORT_ROOT` is not set anywhere in deployed task definitions, so the landing export remains fully opt-in/off in every real pipeline run — flipping it on is the next, separate decision.

### AWS IAM Terraform follow-up closed — 2026-08-13

The one flagged gap above (live IAM widen with no committed Terraform source) is now closed. `runtime_access`'s `variables.tf` gained `additional_export_prefixes` (`list(string)`, default `[]`), mirroring `native_pull`'s `additional_storage_locations` pattern exactly; `ListSnowflakeExportPrefix`/`ReadSnowflakeExportObjects` now iterate `snowflake_export_prefix` plus every `additional_export_prefixes` entry instead of one hardcoded prefix. prod's access root (`access/aws/accounts/prod/main.tf`) wires in the silver-landing prefix via the same trim/append derivation the Snowflake account root already uses for `silver_landing_export_root_url`. Verified against live state before trusting it: fetched the real `edgartools-prod-snowflake-export-s3-read` policy via `aws iam get-role-policy` first to confirm the exact prefix-list shape, then ran `terraform plan` after editing — **0 changes** on `aws_iam_role_policy.snowflake_storage_reader`, confirming the new source reproduces the live policy exactly (no `apply` needed; the live policy was already correct, only the source was missing). One unrelated, pre-existing drift on `aws_sns_topic_policy.snowflake_manifest_events` surfaced in the same plan — left untouched, out of scope. dev is unaffected (default empty list). PR: [#411](https://github.com/paulananth/edgartools-platform/pull/411).
