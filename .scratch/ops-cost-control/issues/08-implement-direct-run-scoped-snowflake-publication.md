# Implement Direct Run-Scoped Snowflake Publication

Type: task
Status: superseded (never completed, never committed — see outcome note)
Blocked by: 07

## Objective

Replace the Snowflake-export S3 transport and duplicate Warehouse Gold Parquet
with a direct authenticated ECS-to-Snowflake publication path. Preserve
run-scoped completeness, fail-closed promotion, deterministic replay, and
operator-visible evidence while reducing the durable AWS data model to Bronze
and Silver.

## Acceptance

- Gold tables are serialized once and uploaded to a Snowflake internal stage.
- A run manifest is submitted and processed only after every expected table is
  staged successfully; partial or failed runs are not promoted.
- The warehouse orchestration no longer writes `warehouse/gold/**` or serving
  export Parquet to S3.
- Warehouse task definitions receive a dedicated Snowflake writer secret and
  no longer require a Snowflake-export bucket/root or export-bucket IAM access.
- Snowflake bootstrap provisions the internal stage and synchronous run loader
  without an S3 storage integration, notification pipe, or manifest stream.
- Passive AWS Terraform no longer creates the Snowflake-export bucket, KMS key,
  or manifest SNS topic.
- Documentation describes the two-bucket data model and an ordered, reversible
  cutover. Production bucket deletion occurs only after immutable-image E2E
  acceptance proves the direct path.

## Comments

### Implementation (2026-08-01, claimed — never independently re-verified)

- Added a direct Snowflake publisher that writes one temporary Parquet file per
  mapped Gold table, hashes it with bounded memory, uploads it to a run-scoped
  internal-stage path, inserts the complete manifest, and synchronously invokes
  source load then Gold refresh. Failed loads do not refresh or remove evidence.
- Warehouse orchestration no longer writes Warehouse Gold Parquet or S3 serving
  exports. The Silver `gold_manifest` now records internal-stage checksum,
  byte-size, row-count, and run lineage after successful promotion.
- Passive AWS Terraform now declares only Bronze and Warehouse data buckets and
  a dedicated empty Snowflake-writer secret container. Export-bucket KMS/SNS,
  Snowflake reader IAM, and warehouse export permissions were removed.
- Snowflake Terraform now provisions an internal stage and synchronous loader;
  the external S3 stage, storage integration, Snowpipe, stream, and scheduled
  manifest task were removed. Access Terraform grants the loader stage,
  manifest-inbox, and procedure privileges.
- The direct publisher and Snowflake loader both reject missing, duplicate, or
  unexpected tables; `PUT` results are verified before manifest publication.
  Source load and all Gold dynamic-table refreshes must finish before success.
- Release evidence now binds the direct manifest digest, run/business date,
  source-load status, and refresh status instead of the removed S3 manifest.
- `verify-direct-write-cutover.sh` gates legacy export-bucket destruction on a
  successful immutable-image direct-write run recorded in Snowflake.
- Focused release/direct-write verification passed 172 tests; the full
  unit/architecture suite passed 914 tests with 4 expected skips. AWS provisioning, AWS access, Snowflake
  provisioning, and Snowflake access Terraform roots all validated.

Production acceptance remains open: populate the new writer secret, apply the
Snowflake direct-write and access roots, deploy an immutable warehouse image,
run a bounded Gold publication, verify source/status/Gold rows, then apply the
AWS plan that destroys the now-empty legacy export bucket and schedules its KMS
key deletion.

## Outcome (2026-08-16, recovered from an orphaned worktree)

This ticket's code was written entirely in one sitting (every file shared an
identical mtime) inside an uncommitted worktree, never committed once (git
reflog shows only the branch's creation, no commits), never pushed, never
opened as a PR — abandoned mid-flight with "production acceptance remains
open" still true five days later when `silver-snowflake-migration` shipped a
different design instead (native pull + landing zone, kept live in prod).

Two findings before closing this out:

1. **A separate, unrelated claim from the same worktree/session (an
   `ops-cost-control` map.md edit describing a "2026-08-01 manual cleanup:
   4,939 versions / 237,619,641,296 bytes") was independently checked against
   live AWS evidence and found false** — real cleanups happened that day, with
   different numbers, already correctly documented via ADR-0005. This ticket's
   own "172/914 tests passed" and "all Terraform roots validated" claims were
   **not** independently re-run or re-verified before this closure; given the
   sibling claim's inaccuracy, take them as unverified, not confirmed.
2. **Cost comparison (2026-08-16, using this platform's own `ecs-cost-sizing`
   research):** what this ticket set out to save was small — S3 manifest/export
   transport overhead measured at ~$0.0001/run, and Gold Parquet duplication at
   ~$0.003/day (both negligible). The one real dollar cost this direction would
   have addressed — Snowflake warehouse credits burned by
   `SNOWFLAKE_RUN_MANIFEST_TASK` polling too frequently (~67 credits/week
   pre-fix) — was fixed independently and far more cheaply on 2026-08-14 by
   widening the poll to 6 hours (one-line schedule change, live-verified
   ~$1-2/day post-fix), and is being reduced further by the separately-resolved
   `snowflake-daily-load-trigger` map's event-driven design, without touching
   native pull at all. The platform's actual dominant steady-state cost (~$2/day,
   per the `aws-steady-state-cost-and-silver-size` research) is S3 Silver/staging
   version bloat, unrelated to native-pull vs. direct-publication, with its own
   cheap one-line-Terraform fix already scoped and not yet applied.

Filed as **out of scope** for this map (see `map.md`) rather than resolved or
revived — replacing native S3 pull is a data-architecture redesign beyond this
map's Destination, the savings it targeted are largely already captured a
cheaper way, and the code itself is 443 files / ~49,000 lines behind current
`main`, making a straight revival impractical regardless. The worktree and
branch this lived in were deleted after this record was written; no patch was
kept — this ticket and its sibling are the complete surviving record.
