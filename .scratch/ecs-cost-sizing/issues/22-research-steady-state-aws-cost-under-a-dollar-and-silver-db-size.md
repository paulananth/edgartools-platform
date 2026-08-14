# Research: Get Steady-State AWS Spend Under $1/day, and Why Silver Is a 1.5GB Monolithic File

Type: research
Status: resolved
Blocked by: none
Related: 20/21 (both root-caused to the single-monolithic-silver-DuckDB-file
model under memory pressure; this ticket looks at that same architecture
from the storage/cost angle instead of the OOM angle)

## Question

Two related questions, AWS-only (Snowflake credit spend is out of scope —
already tracked separately via the manifest-task-schedule/window-size fixes
earlier this session):

1. What AWS resources in account `690839588395` cost money regardless of
   whether any ECS task is running (NAT Gateways, VPC endpoints, S3 storage
   across all buckets, CloudWatch Logs storage + ingestion, Secrets Manager
   secret-months, ECR image storage, SNS, EventBridge, KMS, any load
   balancer)? Quantify each against real AWS Pricing/Cost Explorer data, not
   estimates, and total them into an actual current $/day steady-state
   figure. Then propose concrete, specific changes (delete/resize/retire
   which resource, expected $/day saved by each) to get that steady-state
   figure under $1/day. Flag plainly if any single always-on resource (e.g.
   a NAT Gateway) makes $1/day structurally unreachable without removing
   that resource entirely, so the recommendation is honest about the
   trade-off (e.g. losing outbound internet access from private subnets)
   rather than papering over it.

2. Why is the canonical silver store a single ~1.5GB DuckDB file, and what
   would it take to not have that? This is the same architecture that's now
   been root-caused (tickets 20/21, and earlier this session's "single
   monolithic DuckDB file model" discussion) as the reason nearly every OOM
   this session traced back to one cause: the whole canonical dataset held
   in one process's memory during merge/publish. Read
   `edgar_warehouse/silver.py`, `edgar_warehouse/silver_store.py`, and
   `edgar_warehouse/silver_support/sharded_reader.py` (a sharded reader
   already exists for MDM's cross-shard reads — understand exactly what it
   shards, what it doesn't, and why the canonical publish path in
   `silver_protection.py` still operates against one unsharded file).
   Quantify: current file size, growth rate (compare against an earlier
   known size if one is recorded anywhere in this repo's docs/tickets), and
   what portion of that 1.5GB is being paid for as S3/EBS/task-ephemeral
   storage today vs. what's just transient per-task disk during a run.
   Propose options (e.g. extending the existing sharding to the canonical
   publish path, not just MDM's reads; partitioning by form-type or
   CIK-range; moving more of the canonical store to Snowflake directly and
   shrinking what DuckDB has to hold) with a rough cost/complexity/risk
   read on each — this is a research ticket, not an implementation
   decision, so stop at "here are the real options and what each costs,"
   don't pick one.

## Deliverable

One findings file, every dollar figure and every code claim cited to its
source (AWS Pricing API/Cost Explorer output, or a `file:line` reference),
written to
`.scratch/ecs-cost-sizing/research/aws-steady-state-cost-and-silver-size-2026-08-14.md`.

## Answer

Full findings:
[`aws-steady-state-cost-and-silver-size-2026-08-14.md`](../research/aws-steady-state-cost-and-silver-size-2026-08-14.md).

**Part 1 (cost).** No NAT Gateway problem exists (zero NAT Gateways; Fargate
tasks run in public subnets with direct IGW routing). Steady-state spend is
~$2.00–2.10/day, confirmed both by summing live resource inventory at
published AWS rates and by cross-checking against real Cost Explorer billing
on 2026-08-12 (a day with zero ECS tasks): `TOTAL=$2.093, ECS=$0.000,
S3=$1.968`. **The entire gap is one cause: S3 lifecycle.**
`edgartools-prod-warehouse-690839588395` has versioning enabled but its
lifecycle rule only expires the `silverstage/` prefix — `warehouse/silver/`
(the canonical `silver.duckdb` + 4 shard files) has no rule at all, so 458+
noncurrent versions per key have accumulated **1.34 TB of dead weight**
(~$1.05/day). Recommended fix: extend the existing lifecycle rule to
`warehouse/silver/`. That single one-line/Terraform change alone brings
steady state to **~$0.95–1.10/day** — right at target, no NAT Gateway
trade-off needed, no architecture change required.

**Part 2 (silver size).** `silver.py` is a 7-line shim; real code is
`silver_store.py`. `ShardedSilverReader` is **read-only** (MDM/gold
cross-shard queries). A sharded **write** path already exists
(`warehouse_orchestrator.py`'s "Phase 9 STORE-02/03") but is gated to
exactly one command: `bootstrap-batch` with an explicit `cik_list`, used
only by the secondary `bootstrap-batch --artifact-policy skip` reprocessing
pipeline. Every primary ingestion command (`load_history`,
`daily_incremental`, `bootstrap`) still goes through
`merge_candidate_into_canonical`, which `shutil.copy2()`s the *entire*
canonical file on every publish regardless of how much data changed — file
size scales with publish count, not data volume added. Four options
presented (extend sharded writes to primary ingestion; partition by
form-type; push more of canonical into Snowflake; or just fix S3 lifecycle),
no recommendation made per this ticket's research-only scope — that's a
separate decision.

**Not yet implemented** — this ticket is research only.
