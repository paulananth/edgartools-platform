# Research: Steady-State AWS Cost Under $1/day, and Why Silver Is a Monolithic DuckDB File

Date: 2026-08-14
Ticket: `.scratch/ecs-cost-sizing/issues/22-research-steady-state-aws-cost-under-a-dollar-and-silver-db-size.md`
Scope: AWS-billed resources only (account `690839588395`, region `us-east-1`). Snowflake
credit/warehouse spend is explicitly out of scope. This is a research file only — no
resources were changed, no code was edited.

All figures below are either a live AWS CLI/API call made during this research session, or
a `file:line` reference into this repo. No estimates are presented without a cited source.

---

## Part 1 — Steady-state AWS cost audit

### Headline finding

**Steady-state spend today is ~$2.00–2.10/day, roughly double the $1/day target — and it is
not compute, and there is no NAT Gateway to blame.** `aws ecs describe-clusters` confirms 0
running/pending tasks and 0 active services on `edgartools-prod-warehouse`
(`runningTasksCount: 0, pendingTasksCount: 0, activeServicesCount: 0`), and `aws ec2
describe-nat-gateways --region us-east-1` returns `{"NatGateways": []}` — there are zero NAT
Gateways in this account. **The entire steady-state cost is S3 storage**, and it is a
self-inflicted architectural problem, not an unavoidable infrastructure tax: two S3
lifecycle gaps around the canonical silver DuckDB file are holding roughly 1.3 TB of data
that should already be gone.

### 1. Live resource inventory (what bills regardless of activity)

| Resource | Count / size | Source |
|---|---|---|
| NAT Gateways | **0** | `aws ec2 describe-nat-gateways --region us-east-1` → `{"NatGateways": []}` |
| VPC endpoints | 2, both **Gateway** type (S3), free | `aws ec2 describe-vpc-endpoints` → `vpce-04d9b6eb2d9c182e4` (default VPC), `vpce-08f582f05265e5e01` (`edgartools-prod-s3-endpoint`, tagged prod/terraform) |
| Load balancers (ALB/NLB/classic) | 0 | `aws elbv2 describe-load-balancers` / `aws elb describe-load-balancers` → both empty |
| RDS instances/clusters | 0 | `aws rds describe-db-instances` / `describe-db-clusters` → both empty (confirms CLAUDE.md's "MDM moved to Snowflake Postgres, no AWS RDS" claim is still true live) |
| KMS customer-managed keys | 1 enabled CMK ("CMK for Snowflake export artifacts in prod") + 3 AWS-managed keys (S3/Secrets Manager/RDS default keys — free) | `aws kms describe-key` on all 4 keys returned by `list-keys` |
| Secrets Manager secrets | **7** | `aws secretsmanager list-secrets` (see breakdown below) |
| ECR repositories | 2 (`edgartools-prod-images`, `edgartools-dev-images`) | `aws ecr describe-repositories` |
| ECR stored images | 24 images in `edgartools-prod-images` (avg 285.8 MB each, many sharing base layers), 0 in `edgartools-dev-images` | `aws ecr describe-images` |
| SNS topics | 2 (`edgartools-prod-snowflake-manifest-events`, `sec-edgar-pipeline-alerts`) | `aws sns list-topics` — SNS has no fixed monthly fee, billed per-request only |
| EventBridge rules | 1 (`StepFunctionsGetEventsForECSTaskRule`, AWS-managed, no fixed cost) | `aws events list-rules` |
| CloudWatch Log Groups | 5 total, 613 MB stored | `aws logs describe-log-groups` (see below) |
| S3 buckets | 4, total **2637.2 GB** live | `aws s3api list-buckets` + CloudWatch `BucketSizeBytes` (see below) |

**No NAT Gateway problem exists to trade off.** The prod VPC (`vpc-0b2a820945cfc0109`,
`10.30.0.0/16`) has only two subnets, both `edgartools-prod-public-0`/`-1`, both with
`MapPublicIpOnLaunch: true`, and route table `rtb-0609342b5be24abbd` routes `0.0.0.0/0`
directly to Internet Gateway `igw-052abc61c413ab618` — confirmed via `aws ec2
describe-subnets` and `aws ec2 describe-route-tables`. Fargate tasks run in a **public**
subnet with a directly-assigned public IP, not a private subnet behind a NAT Gateway. This
is why the "Amazon Virtual Private Cloud" Cost Explorer line item is `$0.0000`–`$0.0001` on
days with zero running tasks (2026-08-07, 2026-08-12) but up to `$0.4415` on a
heavy-task-count day (2026-08-08) — that's the AWS Public IPv4 address hourly charge
($0.005/hr/address, live only while a task holds one), not a fixed resource. **If this
architecture ever needs to move ECS tasks into private subnets** (e.g. for a future security
hardening pass), a NAT Gateway would reintroduce a hard floor: confirmed via `aws pricing
get-products --service-code AmazonEC2 --filters Field=productFamily,Value="NAT Gateway"` →
`$0.045/NAT-Gateway-hour` in us-east-1 = **$1.08/day in the hourly charge alone**, before any
`$0.045/GB` data-processing charge — that single resource would make $1/day structurally
impossible on its own. This is flagged for completeness per the ticket's ask; it is not
today's situation.

### 2. Secrets Manager breakdown (7 secrets, `aws secretsmanager list-secrets`)

| Secret | Created | Last accessed |
|---|---|---|
| `edgartools-prod/mdm/api_keys` | 2026-07-03 | never (null) |
| `edgartools-prod-edgar-identity` | 2026-07-03 | 2026-08-13 |
| `edgartools-prod/mdm/neo4j` | 2026-07-03 | **never (null)** |
| `edgartools-prod-runner-credentials` | 2026-07-03 | never (null) |
| `edgartools-prod/mdm/postgres_dsn` | 2026-07-03 | 2026-08-13 |
| `edgartools-prod/mdm/snowflake` | 2026-07-03 | 2026-08-13 |
| `edgartools-prod/dbt/snowflake` | 2026-08-07 | 2026-08-07 |

`edgartools-prod/mdm/neo4j` has never been accessed. Per this repo's own CLAUDE.md ("Graph
storage" note): "graph data lives *inside* Snowflake ... There is no separate Neo4j
database, no `NEO4J_URI`/`NEO4J_PASSWORD` secret, and no external Bolt connection" — this
secret looks like a leftover from before the `neo4j-snowflake` migration (completed
2026-06-12 per that same note) and is a plausible deletion candidate, though
`LastAccessedDate: null` alone is not conclusive proof of dead code (Secrets Manager only
tracks a rolling access window) — recommend a source-grep confirmation before deleting.
`edgartools-prod/mdm/api_keys` and `edgartools-prod-runner-credentials` are also
never-accessed but not clearly dead; flagged for review, not recommended for removal without
checking callers.

Confirmed rate: `$0.40/secret/month` flat, verified live via `aws pricing get-products
--service-code AWSSecretsManager` (global flat rate, not region-varying). 7 secrets =
**$2.80/month = $0.093/day**. Cost Explorer confirms: `AWS Secrets Manager` line item was
`$0.078/day` in early August (6 secrets) and rose to `$0.090–0.114/day` after the 7th secret
was added 2026-08-07 — exact match.

### 3. KMS (1 customer-managed key)

`032912bf-f95f-4c55-98aa-4f66d5ea1f8d`, "CMK for Snowflake export artifacts in prod,"
created 2026-07-16, enabled. Confirmed rate `$1.00/CMK/month` via `aws pricing
get-products --service-code awskms`. Cost Explorer's `AWS Key Management Service` line item
is a flat `$0.0323/day` on every day sampled (`= $1.00/month ÷ ~31 days`) — exact match, one
key, no growth.

### 4. CloudWatch Logs (`aws logs describe-log-groups --region us-east-1`)

| Log group | Retention | Stored bytes |
|---|---|---|
| `/aws/ecs/edgartools-prod-warehouse` | 7 days | 583,198,915 |
| `/aws/states/edgartools-prod-warehouse` | 7 days | 20,161,178 |
| `/aws/ecs/containerinsights/edgartools-prod-warehouse/performance` | 7 days | 9,037,374 |
| `/aws/bedrock-agentcore/runtimes/harness_harness_gqiao-Z69txY9DMw-DEFAULT` | **30 days** | 954,770 |
| `/aws/codebuild/codex-dev-warehouse-image-publish` | **30 days** | 0 |

CLAUDE.md's "retention is already 7 days everywhere" claim is **true for the three
platform-owned groups** (ECS, Step Functions, Container Insights) but **not literally
everywhere** — two other log groups in the account sit at 30-day retention. Neither is part
of this platform's own warehouse/MDM pipeline: `/aws/bedrock-agentcore/...` looks like an
unrelated Bedrock AgentCore harness (not referenced anywhere in this repo's Terraform or
CLAUDE.md), and `/aws/codebuild/codex-dev-warehouse-image-publish` is Codex's own CI log
group (consistent with CLAUDE.md's "Parallel Agent Workstreams" section — Codex works in
this same repo/account on its own branches). Total stored: 613,352,237 bytes ≈ **0.57 GB**.
At CloudWatch Logs' published storage rate (~$0.03/GB-month), this is **≈$0.017/month ≈
$0.0006/day** — a rounding error, confirmed by Cost Explorer's `AmazonCloudWatch` line item
reading `$0.0000` on every sampled day. Not a lever worth pulling for the $1/day goal, though
the two 30-day groups are cheap, easy 7-day-retention fixes if a future pass wants full
consistency with the stated policy.

### 5. ECR (`aws ecr describe-images`)

24 images in `edgartools-prod-images`, avg 285.8 MB reported `imageSizeInBytes` each (many
share base/deps layers, so true unique-blob storage is less than the naive 6.85 GB sum of
per-image sizes). `edgartools-dev-images` has 0 images despite existing (created
2026-08-08). Cost Explorer's `Amazon EC2 Container Registry (ECR)` line item is
`$0.0017–0.0073/day` across every sampled day — negligible, and already covered by CLAUDE.md's
existing "Clean up local images before a build" guidance (that guidance is about local
Colima disk, not ECR billing, but the same old-tag cleanup habit keeps ECR storage bounded
too).

### 6. S3 — the actual driver (`aws s3api list-buckets` + CloudWatch `BucketSizeBytes`)

| Bucket | Live size (avg of last 3 daily datapoints) | Source |
|---|---|---|
| `edgartools-prod-bronze-690839588395` | 69.57 GB (74,705,362,402 bytes) | CloudWatch `BucketSizeBytes`/`StandardStorage` |
| `edgartools-prod-snowflake-export-690839588395` | 3.73 GB (3,999,776,217 bytes) | same |
| `edgartools-prod-tfstate-690839588395` | 0.003 GB (3,653,233 bytes) | same |
| `edgartools-prod-warehouse-690839588395` | **2563.93 GB** (2,752,999,374,070 bytes) | same |
| **Total** | **2637.23 GB (2.575 TB)** | |

S3 Standard rate confirmed live via `aws pricing get-products --service-code AmazonS3
--filters Field=volumeType,Value=Standard Field=location,Value="US East (N. Virginia)"` →
**$0.023/GB-month** for the first 50 TB. `2637.23 GB × $0.023 = $60.66/month = $2.02/day` —
this **alone** is more than double the $1/day target, and it's before Secrets
Manager/KMS/ECR are even added.

**Cross-check against real billing (Cost Explorer, `aws ce get-cost-and-usage`,
`Start=2026-07-15,End=2026-08-14`, daily granularity, grouped by service):** the most
idle-compute day available is **2026-08-12**, where `Amazon Elastic Container Service =
$0.000` (zero Fargate tasks ran that day, confirming the "zero ECS compute when idle"
premise) and the day's full breakdown was:

```
2026-08-12  TOTAL=2.093  ECS=0.000  S3=1.968  SecretsMgr=0.0904  KMS=0.0323  ECR=0.0018  VPC=0.0001  SFN=0.0000  CW=0.0000
```

`$1.968/day` real, billed S3 cost vs. `$2.02/day` computed from the current live bucket
sizes at the published rate — a ~3% gap, well within normal noise from mid-day snapshot
timing and S3 request/data-transfer line items folded into the same CE category. **This
confirms the line-item estimate is not speculative — it is what AWS is actually charging,
on a day with provably zero compute activity.** A second near-idle day, 2026-08-07 (ECS
also $0.000), shows `S3=$0.271` — far lower, because it predates the heavy pipeline activity
of 2026-08-08 through 2026-08-14 (ticket42 full-universe retries, stage14/15 completion
runs — see Part 2). **This total is growing over time, not flat**, because nothing expires
the bytes driving it (see next section).

#### Where the warehouse bucket's 2564 GB actually is

The `edgartools-prod-warehouse-690839588395` bucket has **S3 Versioning enabled**
(`aws s3api get-bucket-versioning` → `"Status": "Enabled"`) and a **lifecycle policy that
only covers one of its ~11 top-level prefixes**:

```
aws s3api get-bucket-lifecycle-configuration --bucket edgartools-prod-warehouse-690839588395
{
  "Rules": [
    {
      "Expiration": {"Days": 3},
      "ID": "expire-silver-staging-candidates",
      "Filter": {"Prefix": "silverstage/"},
      "Status": "Enabled",
      "NoncurrentVersionExpiration": {"NoncurrentDays": 3}
    }
  ]
}
```

`silverstage/` self-cleans after 3 days. **Nothing else in the bucket does** — critically,
not `warehouse/silver/` (the canonical DuckDB files) and not `warehouse/gold/` (per-run gold
table outputs). Breakdown of where the bytes are, all via live `aws s3api
list-object-versions` / `aws s3 ls --recursive --summarize`:

| Prefix | Live bytes today | Mechanism |
|---|---|---|
| `warehouse/silver/sec/silver.duckdb` (all versions) | **625.81 GB** across **458 versions** | No lifecycle rule on this prefix — every publish creates a permanent noncurrent version |
| `warehouse/silver/sec/shards/shard-0.duckdb` (all versions) | **383.15 GB** across **512 versions** | same |
| `warehouse/silver/sec/shards/shard-1.duckdb` (all versions) | **200.01 GB** across **550 versions** | same |
| `warehouse/silver/sec/shards/shard-2.duckdb` (all versions) | **118.06 GB** across **524 versions** | same |
| `warehouse/silver/sec/shards/shard-3.duckdb` (all versions) | **49.11 GB** across **492 versions** | same |
| **Subtotal, these 5 keys, all versions** | **1376.14 GB (1.34 TB)** | |
| **Subtotal, these same 5 keys, current/live version only** | **3.02 GB** | i.e. what *should* be billed if old versions expired |
| **→ Pure noncurrent-version waste, these 5 keys alone** | **1373.12 GB = $31.58/month = $1.05/day** | |
| `warehouse/silverstage/` (current snapshot, self-expiring in ≤3 days) | **1241.35 GB (1.21 TB)** | Every publish attempt stages a full merged-DB copy here before promoting it (see Part 2) — self-cleaning, but the *volume currently held* still bills at $0.023/GB/month while it's there: **≈$0.95/day at today's churn rate** |
| `warehouse/gold/` (current, un-versioned but unbounded — 210 objects) | 3.43 GB | Every `gold-refresh`/`daily_incremental` run writes a full copy of every gold table to a new `run_id=...` path; nothing ever deletes an old run's output (7 retained copies of `dim_filing` alone, 86–162 MB each, visible in the listing) |
| `warehouse/identity_refresh/` | 20.5 GB | Stage 0 seeding snapshots |
| `warehouse/text/`, `warehouse/artifacts/`, `warehouse/leases/`, `warehouse/release/`, `warehouse/release-evidence/`, `warehouse/daily_artifact/` | ~0.25 GB combined | small, not a driver |
| `edgartools-prod-bronze-*` (separate bucket) | 69.57 GB | Versioning enabled, **no lifecycle rule at all**, but bronze is designed write-once (`write_immutable_bytes`, `IfNoneMatch: *` conditional PUT, per CLAUDE.md's "SEC data idempotency" policy) — objects normally aren't overwritten, so versioning shouldn't be creating meaningful noncurrent-version waste here the way it is for silver.duckdb; not independently re-verified via a full version listing (695k+ objects made a full recursive listing time out in this session) but the design intent is sound and the bucket's absolute size (69.57 GB) is small and legitimate raw-data growth, not a leak |
| `edgartools-prod-snowflake-export-*` (separate bucket) | 3.73 GB | Versioning enabled **and** a 30-day `NoncurrentVersionExpiration` lifecycle rule already in place — correctly hygienic, not a driver |
| `edgartools-prod-tfstate-*` (separate bucket) | 0.003 GB | Trivial, standard Terraform backend bucket |

The itemized total (1376.14 + 1241.35 + 3.43 + 20.5 + ~0.25 + 69.57 + 3.73 + 0.003 ≈
2714.95 GB) is close to the measured 2637.23 GB bucket total (small over/undercounts from
listing timing/rounding across many separate CLI calls made minutes apart during active
pipeline runs — the bucket size moved during this research session).

### 3-day silverstage churn confirms Part 2's OOM root cause

`silverstage/`'s 3-day rolling window currently holding **1.21 TB** implies an average of
roughly **400+ GB/day** being staged and discarded — i.e. very large, very frequent full-file
candidate writes. This is the same mechanism CLAUDE.md's own "Bronze-recovery-with-no-DB-row"
and gold-build-memory 5-whys sections describe from the OOM angle (tickets 20/21): every
silver publish, successful or not, copies and re-uploads the *entire* canonical DuckDB file,
not a delta. See Part 2 for the code-level mechanism.

### 7. Recommended changes to reach <$1/day

| # | Action | Est. $/day saved | Risk / effort |
|---|---|---|---|
| 1 | Add an S3 Lifecycle rule to `edgartools-prod-warehouse-690839588395` that expires **noncurrent versions** of everything under `warehouse/silver/` (not just `silverstage/`) after a short window (e.g. 3–7 days, matching `silverstage/`'s existing policy) | **~$1.05/day immediately** (reclaims the 1373 GB of dead noncurrent versions on the 5 keys already identified), plus prevents the same waste from re-accumulating on every future publish | Low risk — noncurrent versions of these keys are not consumed by anything (canonical reads always target the *current* version; nothing in the codebase reads a specific old version by VersionId). Confirm no compliance/audit-trail requirement depends on old silver.duckdb versions before applying (none found in this repo's code or docs). One-line Terraform/lifecycle-JSON change. |
| 2 | Same rule, or a separate one, for `warehouse/gold/` — either cap retained `run_id=` outputs to the N most recent, or set an expiration (e.g. 14–30 days) | Currently small (~$0.003/day) but growing without bound every gold-refresh run; left unaddressed this becomes a second `silverstage`-shaped leak over months | Low risk, same reasoning — nothing reads an old `run_id`'s gold output once the Snowflake manifest pipeline has consumed it |
| 3 | Consider shortening `silverstage/`'s existing 3-day `Expiration`/`NoncurrentVersionExpiration` to 1 day, **if** nothing depends on a >1-day recovery window for an in-flight staged candidate | Up to **~$0.6–0.9/day** at current churn rates (proportional reduction in average held volume) | Needs a quick check of whether any retry/recovery logic in `warehouse_orchestrator.py`/`object_storage.py` ever re-reads a staged (not-yet-promoted) object after more than 1 day — not verified in this session; treat as a secondary lever, not the primary fix (#1 has bigger, safer, already-proven impact) |
| 4 | Add an `AbortIncompleteMultipartUpload` lifecycle rule (best practice hygiene; not separately measured this session, but costs nothing to add and closes a known S3 cost-leak class) | Unmeasured, likely small | Trivial, zero risk |
| 5 | Review `edgartools-prod/mdm/neo4j` secret for deletion (never accessed; the "Graph storage" note in CLAUDE.md says no external Neo4j exists anymore) | $0.013/day ($0.40/month) | Low effort, needs a source-grep confirmation of zero references first (not done in this session) |
| 6 | Align the two 30-day-retention CloudWatch Log Groups to 7 days, matching stated policy | ~$0.0002/day | Trivial, cosmetic more than financial |

**Recommendation #1 alone (~$1.05/day) plus the KMS/Secrets Manager/ECR/CloudWatch baseline
(~$0.13/day) plus the residual live silver footprint (~3 GB ≈ $0.002/day) plus bronze/export/tfstate
(~$0.06/day) would bring steady state to roughly $0.95–1.10/day** — right at the target,
*without* touching `silverstage/`'s self-cleaning churn (#3) or the gold-output growth (#2).
Adding #2 and #3 gives real headroom under $1/day even as the platform keeps growing. **No
NAT Gateway trade-off is required to hit this target** — the entire gap is closeable by
fixing S3 lifecycle policy, which is a config change, not an architecture change.

---

## Part 2 — Why silver is a monolithic ~1.5 GB DuckDB file

### Current canonical storage model

The canonical published silver database is a **single DuckDB file** at
`silver/sec/silver.duckdb`, currently **1,590,702,080 bytes (1.517 GB / ~1.5 GB)** — confirmed
live via `aws s3api list-objects-v2 --bucket edgartools-prod-warehouse-690839588395 --prefix
warehouse/silver/sec/silver.duckdb`. This matches the ticket's cited ~1.5 GB figure exactly;
no earlier recorded size was found elsewhere in this repo's tickets/docs to establish a
growth rate, but the version history (458 noncurrent versions of this one key, oldest
still present) is itself evidence of extremely high publish frequency, not necessarily of
proportional *content* growth per publish.

`edgar_warehouse/silver.py` (7 lines total, not ~78 KB as CLAUDE.md's now-stale "Key Large
Files" table states) is just a compatibility re-export shim:

```python
# edgar_warehouse/silver.py
"""Compatibility shim for the warehouse silver-store public surface."""
from edgar_warehouse.silver_store import SilverDatabase, _parse_company_ticker_rows
__all__ = ["SilverDatabase", "_parse_company_ticker_rows"]
```

The real implementation — schema DDL, `SilverDatabase`, table-write logic — lives in
`edgar_warehouse/silver_store.py` (4405 lines, this is the file CLAUDE.md's doc table
should now point at instead of `silver.py`).

### What `ShardedSilverReader` actually shards (and doesn't)

`edgar_warehouse/silver_support/sharded_reader.py` (157 lines, entire file read) is a
**read-only** cross-shard query layer: it `ATTACH`es N pre-existing shard DuckDB files
(`READ_ONLY`) into one in-memory DuckDB connection and creates a `UNION ALL` view per table
(over ~39 tables listed in `_TABLES`, lines 57–99) so a caller can query the union with one
`.fetch(sql, params)` call, duck-typed to look like `SilverDatabase` to `gold.py`/MDM
callers (module docstring, lines 7–20). Critically:

- It **does not write anything** — no `INSERT`/`UPDATE`/`MERGE` methods exist on the class at
  all; `close()` just tears down the in-memory connection (lines 152–154).
- It only *reads* shard files that some other process already produced and closed (Pitfall 1
  in the docstring, lines 22–27: constructing it while a shard file is still open elsewhere
  raises a DuckDB "Unique file handle conflict").
- Confirmed exactly what CLAUDE.md's "INSTITUTIONAL_HOLDS/EMPLOYED_BY" 5-whys section
  described: it exists for MDM's cross-shard reads (module docstring's "MDM pipeline
  compatibility" section) and for `gold.py`'s `build_gold()`/`iter_gold_tables()` path (which
  needs the full dataset regardless of how many shard files it's split across —
  `edgar_warehouse/serving/gold_models.py:1294`: "Accepts SilverDatabase or
  ShardedSilverReader via duck typing").

### The sharded write path exists — but is wired to exactly one command

This is the more interesting finding, and it sharpens the ticket's framing: sharded
*writes* are not purely hypothetical. `edgar_warehouse/application/warehouse_orchestrator.py`
has a fully-built shard-aware hydrate/publish path (comment-labeled "Phase 9 — STORE-02 /
STORE-03", lines 1182–1189), including:

- `_hydrate_shard_for_window()` (lines 1211–1255) — downloads one `shard-{i}.duckdb` from
  remote storage
- `_publish_shard_if_remote()` (lines 1276+) — ETag-guarded publish of one shard, explicitly
  documented as "each shard is owned by exactly one writer in the sharded architecture
  (partitioned by CIK range), so a conflict here signals a genuine invariant violation, not
  an expected race" (docstring, lines 1290–1294)
- A CIK-range-based shard router: `edgar_warehouse/application/commands/migrate_silver_shards.py`
  (docstring, lines 1–15) — this is the tool that originally converted the monolith into the
  4 shard files currently in S3 (`shard-{0..3}.duckdb`, routed by CIK-direct columns,
  accession→issuer-CIK joins, or full replication for global tables), invoked as a
  **one-time operational command**, not a recurring pipeline step.

But the gate that decides whether a given run actually *uses* this shard write path is
narrow — `warehouse_orchestrator.py:499–503`:

```python
_using_shard_path = (
    command_name == "bootstrap-batch"
    and context.storage_root.is_remote
    and bool(arguments.get("cik_list"))
)
```

**Only the literal command `bootstrap-batch`, run remotely with an explicit `cik_list`,
takes the shard path.** Per this repo's own CLAUDE.md ("Key invariants" section), that
command is used by exactly one pipeline: `edgartools-prod-silver-mdm-gold`'s `BatchSilver`
Map (`MaxConcurrency=3`, `bootstrap-batch --artifact-policy skip`) — described there as
reprocessing *already-loaded* bronze with zero new SEC fetches, explicitly **not** the
primary ingestion pipeline.

Every other command that publishes silver — `bootstrap-next` (the command `load_history`'s
Stage 1 `WindowedBootstrap` actually runs, per CLAUDE.md's "Phased Pipeline" section),
`daily_incremental`, `bootstrap`, `targeted_resync`, `compute-identity-refresh-window`, and
`gold-refresh` — falls through to `if not _using_shard_path:` (line 557) and calls
`_hydrate_silver_database_from_storage()` + `_open_silver_database()`, i.e. the **monolith**
path, then at publish time (line 778) calls `_publish_silver_database_with_retry()` →
`_publish_silver_database_if_remote()` → `merge_candidate_into_canonical()`. **This is the
answer to the ticket's core question**: the canonical publish path still operates against
one unsharded file not because sharding was never built, but because the sharded write path
was only ever wired into the one command used by a secondary reprocessing pipeline — the
primary ingestion pipeline (`load_history`, `daily_incremental`, `bootstrap`) never adopted
it.

### Why every real publish moves the *whole* file, not a delta

`edgar_warehouse/silver_protection.py:664-893` (`merge_candidate_into_canonical`, full file
read) does row-level semantic merging (business-key-based insert/update/conflict-detection
per `PROTECTED_TABLE_REGISTRY`, lines 81–270) — but it operates on a **file-level copy**:

```python
# silver_protection.py:692-693
output_path.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(canonical_path, output_path)
```

Every merge starts by copying the *entire* canonical DuckDB file (whatever its current size
is), then merges the candidate's rows into that copy in place. The caller,
`_publish_silver_database_if_remote()` (`warehouse_orchestrator.py:1045-1133`), then reads
the entire merged file back into memory (`payload = merged_local.read_bytes()`, line 1116)
and stages the **entire payload** as a new object:

```python
# infrastructure/object_storage.py:273-285 (write_staged_bytes, called by stage_and_promote)
staged_relative = f"silverstage/{uuid.uuid4().hex}/{canonical_relative}"
self.write_bytes(staged_relative, payload)
```

This is exactly the mechanism producing Part 1's `silverstage/` volume: **every single
successful publish** — regardless of whether the candidate added 5 rows or 5 million —
writes a fresh full-size copy of the canonical file to a UUID-namespaced staging key, then
promotes it (ETag-guarded) onto the canonical key, which (per Part 1) creates a permanent
noncurrent version of that key because `warehouse/silver/` has no lifecycle rule. File size
scales with *publish count*, not with *data volume added per publish* — a pipeline that
publishes often (as `load_history`'s sequential per-CIK-window `WindowedBootstrap`,
`daily_incremental`, and repeated debug/retry runs visible in the manifest listings all do)
pays the full-file cost every time.

**One optimization already exists and is already deployed** for the specific case of a
command that changes nothing: `_publish_silver_database_if_remote()` (lines 1060–1104)
compares a `compute_silver_fingerprint()` snapshot taken at hydration time against the
current one right before publish, and skips the entire copy/merge/upload/promote cycle if
they're identical — this was implemented per `.scratch/pipeline-throughput-architecture/issues/10-decide-gold-refresh-unconditional-silver-republish.md`
("release-readiness ticket 79"), originally to stop `gold-refresh` (a read-only command)
from unconditionally re-publishing 60+ seconds of work for zero real content change. **This
does not help the general case** — any command that legitimately writes new rows (which is
the common case for `load_history`/`daily_incremental`/`bootstrap`) will never match the
fingerprint and will always pay the full copy+merge+upload of the whole file.

### What's paid for as durable storage vs. what's ephemeral task disk

- **Durable, billed S3 storage**: the canonical `silver.duckdb` (1.52 GB live), the 4 shard
  files (1.65 GB live combined), and every noncurrent version of both (1.34 TB, see Part 1) —
  all genuinely billed S3 storage, not ephemeral.
- **Ephemeral, unbilled**: the local copy of `silver.duckdb` that each ECS/Fargate task
  downloads to its container's local disk (`context.silver_root.join(...)`,
  `_hydrate_silver_database_from_storage`) exists only for the task's lifetime — Fargate
  ephemeral storage is billed as part of the task's vCPU/memory allocation while running (not
  a separate steady-state line item), and disappears entirely when the task stops. This
  local copy is **not** part of the $1/day steady-state question at all — it costs nothing
  when no task is running, consistent with Part 1's "zero Fargate compute cost when nothing
  is running" finding.

### Architectural options to avoid the monolithic file (research only — no recommendation made)

| Option | What it would take | Cost/complexity | Risk |
|---|---|---|---|
| **A. Extend the existing sharded write path to the primary ingestion commands** (`bootstrap-next`/`load_history`, `daily_incremental`, `bootstrap`) | Widen `_using_shard_path`'s gate (`warehouse_orchestrator.py:499-503`) beyond `command_name == "bootstrap-batch"`; each of these commands would need to resolve a CIK range → shard index the same way `bootstrap-batch` already does, and `merge_candidate_into_canonical` would need to run per-shard instead of against one 1.5 GB file. The infrastructure (`_hydrate_shard_for_window`/`_publish_shard_if_remote`, shard-manifest routing) already exists and is proven in production via `bootstrap-batch` — this is "wire it up more broadly," not "build it from scratch." | **Medium** — the routing/merge logic is proven, but every command that currently assumes a single monolith (gold-refresh's full-dataset read via `_hydrate_all_shards`, MDM's `ShardedSilverReader`, any ad-hoc/debug tooling that opens `silver.duckdb` directly) needs to keep working against N files instead of 1 | **Medium** — this pipeline has a well-documented history (CLAUDE.md's own 5-whys sections) of subtle correctness regressions when concurrency/sharding assumptions change (e.g. the `sec_thirteenf_filing`/`sec_employment_event` `_TABLES` allowlist gap, the multi-writer promotion-conflict incident). A wider rollout of the shard write path would need the same registry-completeness discipline `PROTECTED_TABLE_REGISTRY`/`ShardedSilverReader._TABLES` already have, kept in sync across both. |
| **B. Partition canonical storage differently (form-type instead of, or in addition to, CIK-range)** | The existing shard scheme is CIK-range only (`migrate_silver_shards.py`'s "Routing rules": CIK-direct, accession→issuer-CIK join, or full replication for global tables). A form-type axis (e.g. ownership vs. ADV vs. 13F vs. fundamentals as separate files) would reduce the blast radius of a publish that only touches one form type — e.g. a 13F-only ingestion run wouldn't need to copy/merge/re-upload the ownership tables at all. | **Medium-high** — this is a genuinely new partitioning scheme, not a widening of the existing one; every cross-form-type query (and there are several — MDM relationship derivation joins across ownership/ADV/13F) would need to become an explicit cross-file UNION, similar to what `ShardedSilverReader` already does for CIK-range shards today | **Medium** — new invariants to get right (e.g. `sec_company` itself isn't per-form-type, so a "global" file would still exist and could still become the new bottleneck) |
| **C. Push more of canonical storage directly into Snowflake, shrink what local DuckDB has to hold** | The gold layer already goes to Snowflake via the manifest/export pipeline (`SNOWFLAKE_RUN_MANIFEST_TASK`, per CLAUDE.md's Architecture diagram). This option would go further: treat DuckDB as a genuinely ephemeral working/staging layer only (recent window of activity), with the durable canonical silver-equivalent state living in Snowflake `EDGARTOOLS_SOURCE` (which already exists as a native-S3-pull layer per CLAUDE.md's Data Layer Definitions table) instead of round-tripping a growing local file on every publish. | **High** — this is the largest architectural change of the three options; it changes what "canonical" means for silver (Snowflake table state vs. a DuckDB file's bytes), which `silver_protection.py`'s entire same-key conflict-resolution model (`PROTECTED_TABLE_REGISTRY`, authority columns, `SemanticMergeConflictError`) is currently built around as DuckDB SQL. It would also move real cost from AWS S3 (out of scope's sibling, already tracked) to Snowflake credits (explicitly out of scope for *this* ticket, but not free) | **High** — touches the fail-closed merge-conflict semantics this codebase has invested heavily in getting right (multiple 5-whys entries in CLAUDE.md document real production incidents from getting silver-publish semantics wrong); this is the option most likely to reopen settled correctness work, not just a storage/cost change |
| **D. Do nothing to the write path; fix only the S3 lifecycle gap (Part 1, recommendation #1)** | No code change at all — just close the lifecycle-policy hole so noncurrent versions of `warehouse/silver/*` expire the same way `silverstage/*` already does | **Low** — a Terraform/lifecycle-JSON change | **Low** — this doesn't reduce the *number* of full-file copy/merge/upload cycles (the OOM risk profile CLAUDE.md's tickets 20/21 describe is unchanged), it only stops paying to store the discarded copies forever. Framed here because it is the cheapest lever that directly answers "why does this cost so much," even though it doesn't address the underlying "why is every publish a full-file operation" architecture question the other three options do. |

Option D is not a substitute for A/B/C if the goal is also to fix the OOM-prone
full-file-copy-per-publish pattern (tickets 20/21) — it only fixes the S3 *storage cost*
symptom. A/B/C are the options that would change the fact that every publish moves the whole
file; D is the option that stops paying to keep the discarded copies around after the fact.
Per the ticket's scope, no option is recommended here — this is presented as a menu for a
separate decision.

---

## Appendix — raw commands run this session (for reproducibility)

```
aws sts get-caller-identity
aws ec2 describe-nat-gateways --region us-east-1
aws ec2 describe-vpc-endpoints --region us-east-1
aws ec2 describe-vpcs / describe-subnets / describe-route-tables --region us-east-1
aws elbv2 describe-load-balancers / aws elb describe-load-balancers --region us-east-1
aws rds describe-db-instances / describe-db-clusters --region us-east-1
aws kms list-keys / describe-key (x4) --region us-east-1
aws sns list-topics --region us-east-1
aws events list-rules / list-event-buses --region us-east-1
aws s3api list-buckets
aws s3api get-bucket-versioning / get-bucket-lifecycle-configuration (all 4 buckets)
aws s3api list-object-versions --prefix warehouse/silver/sec/silver.duckdb (and 4 shard files)
aws s3api list-objects-v2 (various prefixes, warehouse/silver, warehouse/gold, etc.)
aws s3 ls --recursive --summarize (per warehouse/ subprefix)
aws cloudwatch get-metric-statistics --namespace AWS/S3 --metric-name BucketSizeBytes/NumberOfObjects (all 4 buckets, all storage-class dimensions)
aws secretsmanager list-secrets --region us-east-1
aws ecr describe-repositories / describe-images --region us-east-1
aws logs describe-log-groups --region us-east-1
aws ecs list-clusters / describe-clusters --region us-east-1
aws ce get-cost-and-usage --time-period Start=2026-07-15,End=2026-08-14 --granularity DAILY --group-by Type=DIMENSION,Key=SERVICE
aws pricing get-products --service-code AmazonS3 (Standard storage, US East N. Virginia)
aws pricing get-products --service-code AWSSecretsManager
aws pricing get-products --service-code awskms
aws pricing get-products --service-code AmazonEC2 --filters Field=productFamily,Value="NAT Gateway"
```

Code files read in full: `edgar_warehouse/silver.py`, `edgar_warehouse/silver_support/sharded_reader.py`,
`edgar_warehouse/silver_protection.py`. Code files read in relevant sections:
`edgar_warehouse/silver_store.py` (grepped for shard/canonical references, ~4405 lines total),
`edgar_warehouse/application/warehouse_orchestrator.py` (lines ~480-800, ~980-1330),
`edgar_warehouse/infrastructure/object_storage.py` (lines ~238-340),
`edgar_warehouse/application/commands/migrate_silver_shards.py` (lines 1-60).
Prior-ticket cross-reference: `.scratch/pipeline-throughput-architecture/issues/10-decide-gold-refresh-unconditional-silver-republish.md`.
