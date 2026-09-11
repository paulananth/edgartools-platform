# Production S3 Artifact-Retention Taxonomy

Date: 2026-09-02
Scope: production account `690839588395`; source and policy research only; no AWS mutation.

## Executive finding

The repository has four production S3 buckets/classes: immutable Bronze,
mutable warehouse, Snowflake export, and Terraform state. All are versioned,
but only three warehouse prefixes and the export bucket have lifecycle rules.
There is no repository policy that turns a consumer's filing lookback into
authority to delete the underlying SEC source object.

The safe boundary is therefore:

- **Retain current immutable Bronze source evidence.** A 2-, 3-, or 5-year
  consumer window determines what a workflow reads; it does not settle source
  retention. Old Bronze may be a **transition** candidate after restore-time,
  object-size, request-cost, and replay requirements are tested.
- **Expire only artifact classes with an existing explicit ephemeral contract:**
  `warehouse/silverstage/` after 3 days, `warehouse/identity_refresh/` after 7
  days, noncurrent `warehouse/silver/` versions after 7 days, and the export
  bucket after 30 days. Existing exact-VersionId cleanup contracts also support
  reviewed removal of legacy `_staging/` and superseded warehouse duplicates.
- **Review everything else.** In particular, run controls, release evidence,
  Terraform state history, transcripts, and Bronze conflict quarantine have no
  settled terminal retention period.

## Platform-wide controls

Production bucket names are fixed in `infra/terraform/accounts/prod/main.tf:1-8`.
Bronze is explicitly `prevent_destroy`; all three data buckets are versioned,
encrypted, bucket-owner-enforced, and blocked from public access
(`infra/terraform/modules/storage_buckets/main.tf:12-59,61-104,203-246`). The
module describes Bronze as immutable and warehouse as mutable
(`infra/terraform/modules/storage_buckets/outputs.tf:1-18`). Terraform state is
also versioned, encrypted, public-blocked, and `prevent_destroy`
(`infra/terraform/bootstrap-state/main.tf:8-53`). No S3 Object Lock resource is
declared, so immutability is an application contract, not WORM retention.

AWS behavior matters in this versioned topology: current-version expiration
adds a delete marker and makes the former current object noncurrent; permanent
removal requires `NoncurrentVersionExpiration` or deletion of an exact
VersionId. See [AWS: Expiring objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html)
and [AWS: Lifecycle configuration elements](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html).

## Artifact taxonomy

`Disposition` is evidence-supported today. `Review` means the audit must retain
and emit `insufficient_evidence`, not infer an age cutoff.

| Artifact class | Production bucket and prefix | Purpose and write/version behavior | Current lifecycle | Date basis / years in active scope | Protection evidence | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| Terraform state | `edgartools-prod-tfstate-690839588395/{accounts/prod,snowflake/prod}/terraform.tfstate` | Current infrastructure authority plus historical rollback versions. | None. | Backend key and S3 version `LastModified`; no business-year scope. | Bucket `prevent_destroy`, versioning, encryption, public block (`bootstrap-state/main.tf:8-53`); canonical keys in `infra/terraform/access/aws/accounts/prod/variables.tf:8-33`. | **Retain current; review noncurrent.** Never couple to filing years. |
| SEC reference snapshots | Bronze `/warehouse/bronze/reference/sec/{company_tickers,company_tickers_exchange}/{YYYY/MM/DD}/...` | Date-stamped SEC universe/ticker snapshots. | None in Bronze. | Key date is fetch date, not filing date. No consumer-year deletion contract. | Path catalog `warehouse_paths.properties:1-3`; Bronze application immutability. | **Retain / transition review; do not expire.** |
| Bronze run-control and resume artifacts | Bronze `/warehouse/bronze/reference/{cik_universe,identity_refresh_lease,sec_fetch_lease,mdm_company_resume,mdm_generation}/runs/...`; `/reference/relationship_release/...`; optional `/reference/cohorts/...` | Step Functions fan-out inputs, leases, frozen CIK sets, resume outcomes, graph-generation side channels, and release candidate manifests. Usually unique run keys; some writers use ordinary writes rather than conditional immutable writes. | None. | Run ID and S3 `LastModified`; run IDs are not guaranteed parseable timestamps. No business-year scope. | Catalog `warehouse_paths.properties:4-9`; resume purpose `mdm/company_resume.py:1-12,30-84`; graph side-channel `mdm/cli.py:1248-1289`; release manifest examples `docs/release-readiness/ticket20-production-remediation-evidence.json:52-59`. | **Review.** Likely bounded run retention, but rollback/audit/retry windows must be settled first. |
| SEC submissions snapshots | Bronze `/warehouse/bronze/submissions/sec/cik=.../{main,pagination}/{YYYY/MM/DD}/...` | Raw SEC submissions JSON and pagination history; date-keyed captures used for replay/discovery. | None. | Key date is fetch date; contained filings span other years. | Paths `warehouse_paths.properties:11-16`; architecture purpose `docs/data-architecture.md:63,90`. | **Retain / transition review; do not expire by key year.** |
| SEC daily form indexes | Bronze `/warehouse/bronze/daily_index/sec/{YYYY/MM/DD}/form.YYYYMMDD.idx` | Immutable daily SEC index used for incremental discovery and replay. | None. | Business date is explicit in key. That date is not a settled retention window. | Paths `warehouse_paths.properties:15-16`; architecture purpose `docs/data-architecture.md:64,91`. | **Retain / transition review.** |
| SEC filing indexes, primary documents, attachments, and normalized text | Bronze `/warehouse/bronze/filings/sec/cik=.../accession=.../...` and `/text/sec/...`; conflict variants at `<identity-key>.conflict/<sha256>` | Exact SEC evidence and parser/replay input. Conditional `If-None-Match: *`; different bytes fail closed and are retained at a content-addressed quarantine sibling. | None. A manual historical script can select filing current versions by accession year, but labels them `REVIEW_REQUIRED_NOT_DELETE_AUTHORIZED`. | Accession encodes filing year; S3 `LastModified` may be copy time. Mixed-form prefix prevents safe form policy from key alone. Active consumer windows are discussed below and confer no delete authority. | Paths `warehouse_paths.properties:18-23`; immutable/conflict behavior `object_storage.py:41-54,351-470`; historic review guard `create-bronze-historic-review-manifest.sh:13-27,117-153,188-193`. | **Retain current and quarantine; transition review.** Existing delete script is an operator capability, not an approved policy. |
| Bronze and per-layer run manifests | Bronze `/warehouse/bronze/runs/...`, `/daily-index/...`; warehouse `/warehouse/{staging,silver,gold,artifacts}/...` | Run-level and layer completion/provenance manifests. | No matching lifecycle except where a broader prefix below applies. | Run ID, business date where present, and completion timestamps; no filing-year retention. | Templates `warehouse_paths.properties:29-39`; architecture purpose `docs/data-architecture.md:69`. | **Review.** Durable provenance period is unsettled. |
| Canonical Silver and shard manifest | Warehouse `/warehouse/silver/sec/{silver.duckdb,shard-manifest.json,shards/shard-N.duckdb}` | Live mutable canonical database/shards. Publishing creates new versions. | **Current retained; noncurrent versions expire after 7 days.** | Publication/noncurrent time, not filing year. | Terraform deliberately omits current expiration and explains why (`storage_buckets/main.tf:163-187`); exact cleanup code denies current canonical versions (`warehouse_duplicate_reclaim.py:12-24,146-190,216-227`). | **Retain current; expire noncurrent at 7 days.** |
| Canonical Silver staging candidates | Warehouse `/warehouse/silverstage/<uuid>/...` | Fresh immutable promotion candidates; conflicts stay for inspection/retry. | **Current and noncurrent expire after 3 days.** | S3 creation/successor time; no business years. | Writer path `object_storage.py:333-349`; lifecycle rationale and rule `storage_buckets/main.tf:106-140`. | **Expire at 3 days** (already configured). |
| Legacy abandoned staging | Warehouse `/warehouse/_staging/` | Pre-rename promotion copies, no longer canonical. | No lifecycle. One-time exact-VersionId cleanup selects versions older than 24 hours. | S3 `LastModified`. | ADR and script scope/dry-run/review gates `docs/adr/0004-one-time-version-aware-staging-cleanup.md:1-3`; `cleanup-s3-staging.sh:4-9,24-32,126-203`. | **Expire by reviewed exact-VersionId manifest;** do not add it to year-based deletion. |
| Identity-refresh run snapshots/deltas/outcomes | Warehouse `/warehouse/identity_refresh/runs/<run>/...` | Immutable run plan, reference snapshot, per-batch DuckDB deltas/outcomes, completion manifest. | **Current and noncurrent expire after 7 days.** | Object creation/noncurrent time. | Immutable checksummed run binding `identity_refresh_publication.py:31-75,88-155`; lifecycle `storage_buckets/main.tf:142-161`. | **Expire at 7 days** (already configured). |
| Warehouse-local Gold Parquet | Warehouse `/warehouse/gold/<table>/run_id=<run>/...` | Derived reproducible table snapshots. | No Terraform lifecycle. Existing duplicate reclaim retains newest complete run and selects older runs. | Run completeness and object `LastModified`, not source filing year. | Paths `warehouse_paths.properties:45-47`; keep-set logic `warehouse_duplicate_reclaim.py:79-130,178-190`. | **Expire older complete/superseded runs only via reviewed exact-VersionId manifest; retain newest complete run.** |
| Platform-held transcript text | Warehouse `/warehouse/transcripts/cik=.../event_id=.../transcript.txt` | Manually supplied/licensed text referenced by Gold metadata. Ordinary write may create versions. | None. | Authoritative `event_date` is in the pointer row, not guaranteed in key; no retention/license contract in storage layer. | Path `warehouse_paths.properties:25-27`; pointer and hash behavior `explore/transcript_events.py:254-303`; operator example `docs/er-transcript-events.md:86-106`. | **Review/retain.** Require provenance and licensing retention policy before transition or expiration. |
| Release evidence and control state | Warehouse `/warehouse/release-evidence/...`, `/warehouse/release/{ecr_rollback_registry.json,ecr_rollback_cleanup.lock,ecs_sizing_ticket28.lock}` | Pre/post-delete evidence, release gates, rollback cohorts, and durable coordination locks. Registry is mutable/versioned; locks may require explicit release. | None. | Evidence run ID/record timestamp and S3 `LastModified`; no business years. | Cleanup writes evidence before deletion (`cleanup-s3-staging.sh:238-243`; `delete-bronze-historic-manifest.sh:174-179`); ECR registry/lock and no-auto-expiry contract `ecr_rollback_cli.py:82-83,123-176`. | **Retain evidence and registry; review old versions. Never age-delete a current lock.** |
| Snowflake table exports and manifests | Export bucket `/warehouse/artifacts/snowflake_exports/{table}/business_date=.../run_id=.../...` and `/manifests/...` | Derived Parquet plus load manifest consumed by Snowflake native pull. | **Whole bucket: current and noncurrent expire after 30 days.** | Explicit business date plus run ID; no direct source-year meaning. | Paths `warehouse_paths.properties:45-50`; lifecycle `storage_buckets/main.tf:248-262`; KMS encryption `storage_buckets/main.tf:218-229`. | **Expire at 30 days** (already configured), subject to load-lag monitoring. |
| Silver landing exports and manifests | Export bucket sibling `/warehouse/artifacts/silver_landing/{table}/business_date=.../run_id=.../...` and `/manifests/...` | Derived landing Parquet/manifest for Snowpipe; reuses export key shapes under separate root. | Same whole-bucket **30-day current/noncurrent expiration**. | Business date and run ID. | Root derivation `infra/terraform/snowflake/accounts/prod/main.tf:15-20`; write shape `serving/silver_landing_writer.py:1-16,79-110`. | **Expire at 30 days** (already configured), subject to ingestion reconciliation. |

## Consumer windows are not deletion windows

The mixed Bronze filing prefix can contain documents used by multiple products
and parsers. Therefore a cutoff cannot be derived from the accession year alone.
The known consumer windows are:

- Forms 3/4/5 ownership: 2 years of activity plus current derived holds
  (`warehouse_orchestrator.py:230-240`; `cli.py:1092-1127`).
- Item 5.02 8-K: 2 years (`warehouse_orchestrator.py:237-240`).
- ADV: current plus a 2-year material-change window appears in the canonical
  relevance document, but is explicitly a default pending product grilling
  (`docs/release-readiness/agent-and-research-source-relevance-windows.md:49-56`).
- The same relevance document records historical first-GO windows of 3 years
  for 13F and 5 years for proxies (`...source-relevance-windows.md:31-40`).
  Current implementation is narrower: 13F is 3 months and proxy is 1 year
  (`relationship_bulk_load.py:36-51`). This drift is another reason not to
  encode `2/3/5 years` as S3 deletion policy.
- Financial feature consumers use 3- and 5-year fiscal inputs, but these are a
  derived-feature requirement, not a relationship-freeze or raw-object
  retention grant (`...source-relevance-windows.md:42-47`).

Even if a filing is outside every current consumer window, deleting its Bronze
objects would remove parser replay, reconciliation, provenance, and conflict
repair evidence. A separate operator-approved policy must specify which source
families may expire, the authoritative date field, Explore/research obligations,
and whether Silver/Snowflake already provides sufficient reconstructability.

## Gaps the recurring audit should report

1. **Unmatched objects:** retain with `insufficient_evidence`; never default to
   S3 `LastModified` or parse a year from an unrecognized key.
2. **Bronze archive economics:** report bytes/object-count by retention class.
   Do not recommend Glacier blindly: AWS documents transition request cost,
   per-object archive overhead, retrieval cost, and 90/180-day minimum duration
   charges. See [AWS: Lifecycle transition considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-transition-general-considerations.html)
   and [AWS: Storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html).
3. **Incomplete multipart uploads:** no Terraform rule currently aborts them in
   any data/state bucket. Inventory them and recommend a separately reviewed
   bucket-wide abort rule; AWS states uploaded parts remain billed until the
   upload completes or is aborted and recommends lifecycle cleanup. See
   [AWS: Abort incomplete multipart uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpu-abort-incomplete-mpu-lifecycle-config.html).
4. **Delete markers:** inventory counts because current expiration in versioned
   buckets is not itself permanent deletion. Any cleanup must preserve exact
   VersionId evidence and reconcile post-state.
5. **Unsettled retention:** run controls/manifests, release evidence, Terraform
   state history, transcripts, Bronze conflict quarantine, and Bronze sources
   require explicit owner decisions. The audit may rank their cost but must not
   emit executable deletion commands for them.

## Recommended retention-class contract for the audit

Each finding should bind exact `bucket`, `prefix`, artifact class, authoritative
date basis, current/noncurrent status, minimum age, disposition, and protection
checks. Only the existing explicit `expire` rows above may be called deletion
candidates. `Transition` findings must model object size/count and restore
requirements. Every other row is `retain` or `review`; missing evidence is never
converted to zero value or safe deletion.
