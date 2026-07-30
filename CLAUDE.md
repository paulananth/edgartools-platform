# EdgarTools Platform

This repo is the full data platform built on top of the `edgartools` PyPI package. It extracts SEC EDGAR filings data via an ETL runtime, stages Parquet files in S3, loads them into Snowflake, and transforms them into production-ready dynamic tables consumed by a Streamlit dashboard. The platform is designed to track a universe of public companies and investment advisers across all major SEC form types.

## AWS account map (READ THIS before running any AWS command)

**The platform lives in AWS account `690839588395` (current/active).** All `edgartools-*`
resources, ECR images, ECS clusters, and Terraform state should target `690839588395`.

**Account `077127448006` is DECOMMISSIONED (emptied 2026-07-11, `claude/destroy-old-account`).**
Everything was migrated to `690839588395` first, then the old account was torn down with
`infra/scripts/destroy-aws-complete.sh --env all` plus an all-regions + tagging-API sweep:
all S3 buckets (incl. the 198 GB warehouse and both `*-tfstate` buckets), 45 Step Functions,
ECS, ECR, 13 secrets, all IAM roles, dev+prod VPCs, 17 default VPCs, and 280 ECS task
definitions. Verified zero billable resources remaining.
- **Final closure is a ROOT action.** The `cli-access` IAM user in `077127448006` *cannot*
  close the account — closure/suspension must be done via root sign-in or the AWS
  Organizations management account. `cli-access`, 2 `PendingDeletion` KMS keys (auto-delete
  2026-07-18), INACTIVE ECS cluster tombstones, and the payment-instrument were left in place
  and are reaped automatically when the account is closed.
- **State backups** (the only surviving record of the destroyed account) live at
  `~/edgartools-077-tfstate-backups-FINAL` and `infra/.aws-tfstate-backups/`.
- Do NOT reprovision anything into `077127448006`. If an old ARN/bucket/`aws-prod-application.json`
  still references `077127448006`, it is stale — the live target is `690839588395`.

## Snowflake DEV is DECOMMISSIONED (2026-07-29) — READ THIS before running any `snowconn`/dev Snowflake command

**AWS-side dev (`edgartools-dev-*` S3/ECS/Step Functions, incl. the `edgartools-dev-tfstate`
Terraform state bucket) was decommissioned first, separately from this Snowflake teardown.**
By the time this Snowflake decommission ran, the `edgartools-dev-tfstate` bucket no longer
existed — so `terraform destroy` was **not** viable for either
`infra/terraform/snowflake/accounts/dev` or `infra/terraform/access/snowflake/accounts/dev`
(no remote state to read). Decommissioned instead via a direct live-object sweep against
Snowflake account `xcpclkf-kb19989` (same account prod lives in — dev/prod are separate
**databases**, not separate accounts): `EDGARTOOLS_DEV` database (dropped CASCADE — all 8
schemas: `EDGARTOOLS_GOLD`, `EDGARTOOLS_SOURCE`, `EDGARTOOLS_DASHBOARD`, `MDM`,
`MDM_GRAPH_REVIEW`, `NEO4J_GRAPH_MIGRATION`, `PUBLIC`, plus `INFORMATION_SCHEMA`), both
warehouses (`EDGARTOOLS_DEV_READER_WH`, `EDGARTOOLS_DEV_REFRESH_WH`), all 4 roles
(`EDGARTOOLS_DEV_LOADER`, `EDGARTOOLS_DEV_DASHBOARD_OWNER`, `EDGARTOOLS_DEV_DEPLOYER`,
`EDGARTOOLS_DEV_READER`), the `EDGARTOOLS_DEV_EXPORT_INTEGRATION` storage integration, and
the account-level `EDGARTOOLS_DEV_MDM` Snowflake Postgres instance (MDM's dev operational
store — a distinct object type from the database, `retention_time=0`, no undrop safety net;
its `EDGARTOOLS_DEV_MDM_POSTGRES_POLICY` network policy had to be dropped first since a
network rule inside `EDGARTOOLS_DEV.MDM` was bound to it, which otherwise blocks
`DROP DATABASE ... CASCADE` with "includes network rule - policy associations"). Verified
live afterward: zero `EDGARTOOLS_DEV%`-named objects of any kind remain in the account.

**No state backup exists for this teardown** — unlike the AWS `077127448006` decommission,
which had `~/edgartools-077-tfstate-backups-FINAL`, dev Snowflake's Terraform backend was
already gone before this ran, so there was nothing to pull. The live-object inventory
gathered immediately before the drop (captured in this session's transcript) is the only
record of what existed.

**Everywhere else in this file that references dev Snowflake is now stale**, including but
not limited to: the `snowconn` SnowCLI connection convention, the "Dev Terraform/Snowflake
go-live blockers" 5-whys section below, `EDGARTOOLS_DEV_LOADER`/`EDGARTOOLS_DEV_DEPLOYER`
role references, `dbt run --target dev` (the default target), and the
`WAREHOUSE_BRONZE_ROOT="s3://edgartools-dev-bronze/..."` env-var example. Do not run any
dev-targeted command (`dbt ... --target dev`, `deploy-snowflake-stack.sh --env dev`,
`bootstrap-*` against dev) without first reprovisioning the dev Terraform roots from
scratch — there is currently no dev Snowflake environment to target. Prod
(`EDGARTOOLS_PROD`, `edgartools-prod` connection) is unaffected and was not touched by this
teardown.

## Parallel Agent Workstreams

Claude and Codex may work on this repository independently, but they must not share an uncoordinated edit surface.

- **HARD RULE: Claude and Codex must NEVER commit to the same branch.** Each
  runtime works on its own dedicated branch (or worktree). If you find
  yourself about to commit and `git log -1` shows a commit authored by the
  other runtime's current work that you did not expect, STOP — do not
  commit — and ask the user how to proceed (e.g. branch off, rebase onto a
  new branch, or hand off).
- Branch naming convention: prefix branches with the owning runtime, e.g.
  `claude/<topic>` or `codex/<topic>`. Before starting work or committing,
  run `git branch --show-current` — if the current branch is prefixed for
  the *other* runtime (or is a shared branch like `main`/`codex/main-sync`
  that the other runtime is actively using), create/check out your own
  branch (or worktree) before making any commits.
- Treat current Codex work as protected unless the user explicitly hands it off.
- Use separate GSD workstream directories under `.planning/workstreams/<name>/`; do not edit another runtime's active workstream files.
- Before editing, run `git status --short` and `git log -1` and inspect
  `.planning/active-workstream` when present.
- Avoid overlapping source files, Terraform roots, generated application JSON, and planning artifacts across runtimes unless the user assigns the same task to both.
- If overlap is unavoidable, stop and ask for an ownership decision instead of merging assumptions.
- Do not overwrite, revert, stage, or commit changes created by the other runtime unless explicitly instructed.

## Quick Navigation

| Need | Location |
|------|----------|
| ETL runtime (form parsing, S3 writes) | `edgar_warehouse/runtime.py` |
| Silver-layer transformations | `edgar_warehouse/silver.py` |
| Gold-layer aggregations (Python) | `edgar_warehouse/gold.py` |
| Ownership / Form 3-4-5 parser | `edgar_warehouse/parsers/ownership.py` |
| ADV parser (investment advisers) | `edgar_warehouse/parsers/adv.py` |
| CLI entry point | `edgar_warehouse/cli.py` |
| Batch scripts per form type | `scripts/batch/` |
| dbt gold models (8 dynamic tables) | `infra/snowflake/dbt/edgartools_gold/models/gold/` |
| Snowflake bootstrap SQL | `infra/snowflake/sql/bootstrap/` |
| MDM graph (Snowflake-hosted, NOT external Neo4j) | `edgar_warehouse/mdm/graph_readonly.py`, `mdm sync-graph`/`mdm verify-graph` CLI, `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` |
| Operator MDM/graph review dashboard | `examples/mdm_graph_dashboard/` |
| Streamlit-in-Snowflake dashboard | `infra/snowflake/streamlit/streamlit_app.py` |
| Standalone Streamlit dashboard | `examples/dashboard/edgar_universe_dashboard.py` |
| AWS Terraform (prod) | `infra/terraform/accounts/prod/` |
| Snowflake Terraform (prod) | `infra/terraform/snowflake/accounts/prod/` |
| Docker / ECR publish scripts | `infra/scripts/` |

## Architecture

```
SEC EDGAR API
      |
      v
edgar-warehouse CLI  (edgar_warehouse/runtime.py)
      |
      v
S3 Parquet (bronze)
      |
      v
Snowflake EDGARTOOLS_SOURCE  <-- native S3 pull via bootstrap SQL
      |
      v
dbt (infra/snowflake/dbt/edgartools_gold/)
      |
      v
EDGARTOOLS_GOLD  (8 dynamic tables)
      |
      v
Streamlit dashboard  (infra/snowflake/streamlit/  OR  examples/dashboard/)
```

## Data Layer Definitions

| Layer | Location | Description |
|-------|----------|-------------|
| **Bronze** | S3 (`s3://<bucket>/`) | Raw Parquet files written by `edgar-warehouse`. One file per filing/entity, partitioned by form type and date. Never mutated. |
| **Source** | Snowflake `EDGARTOOLS_SOURCE` | External stage + tables auto-refreshed from S3 via Snowflake native S3 pull (bootstrap SQL). Read-only raw layer. |
| **Silver** | `edgar_warehouse/silver.py` | Cleaned, typed, deduplicated records. Applied in the warehouse runtime before S3 write; also used for ad-hoc re-processing. |
| **Gold** | `EDGARTOOLS_GOLD` (dbt dynamic tables) | Business-ready tables: `company`, `ownership_holdings`, `ownership_activity`, `filing_detail`, `filing_activity`, `adviser_disclosures`, `adviser_offices`, `private_funds`, `ticker_reference`, `edgartools_gold_status`. Refreshed on a Snowflake-managed schedule. |

## edgartools Dependency

The platform depends on the `edgartools` PyPI package (`edgartools>=5.29.0`). It is **not** a local path dependency — install from PyPI.

## SEC data idempotency

SEC filing artifacts are treated as additive and immutable after they have been
captured. Warehouse loaders must skip already loaded SEC files by default and
only re-fetch when an operator passes an explicit `--force` repair flag.

## Schema conventions

**Use BIGINT (DuckDB default `INTEGER`/`BIGINT` sizing), never SMALLINT, for
any integer column derived from counting real-world SEC/IAPD records** —
sequence/index columns (e.g. `owner_index`, `txn_index`, `fund_index`,
`office_index`, `event_index`) and any other count-derived value. SMALLINT's
32,767 ceiling is not a theoretical concern: `sec_adv_private_fund.fund_index`
(a per-filing sequence number) hit 22,277 for one real adviser's March-2026
ADV filing — a single large fund-administration platform reporting
thousands of Series-LLC funds under one CRD — 68% of the SMALLINT ceiling
from a single real-world record, on data that is additive/immutable once
captured (see "SEC data idempotency" below), so a future overflow can't be
patched by reprocessing old rows differently. SMALLINT/TINYINT remain fine
for genuinely bounded small values with a real domain ceiling (e.g.
`source_quarter` 1-4, `source_year`), not for anything counting rows.

## Debugging discipline: 5-whys

When fixing **any** error (CLI failures, ECS task crashes, CI failures, data
bugs, infra errors), do a 5-whys root-cause pass before applying a fix:

1. State the observed symptom (error message, exit code, wrong output).
2. Ask "why" repeatedly (3-5 times) until you reach a root cause, not just
   the proximate trigger.
3. Apply the fix at the root cause, not just the symptom.
4. If the issue is non-trivial or likely to recur, document the chain
   (problem → whys → resolution) in this file or `TODOS.md` so future
   sessions don't re-debug it from scratch.

The "Long-load 5-whys (resolved)" section below is the template for this —
follow that format for new entries.

## Long-load 5-whys (resolved)

**Problem:** Loading 100 companies sequentially took 30–90 minutes.

1. `bootstrap-next` fetches all 100 CIKs sequentially — no parallelism at the CIK level.
2. Each CIK requires N SEC API calls (submissions.json + all pagination files). A well-filed
   company has 50+ pagination files × 200–500 ms = 10–25 s per company.
3. `bootstrap-batch` (Step Functions Distributed Map) was in `GOLD_AFFECTING_COMMANDS`, so
   every parallel batch task rebuilt gold tables and uploaded silver.duckdb — work that
   operates on the whole warehouse state and multiplies I/O by batch count.
4. The three phases (bronze, MDM, gold) were mixed into a single command, preventing the
   MDM entity resolution + graph sync (Snowflake-hosted Neo4j Graph Analytics Native App —
   see "Graph storage" note below) from running against the complete silver dataset.
5. There was no single Step Function that encoded the correct sequence: parallel bronze
   → MDM in bulk → gold once.

**Resolution:** `bootstrap-batch` removed from `GOLD_AFFECTING_COMMANDS`. New `gold-refresh`
command builds gold once. New `load_history` Step Function chains all four phases correctly.

## Artifact-throttle 5-whys (resolved 2026-07-12)

**Problem:** A 20-CIK `load_history` re-run spent ~20+ min (est. ~93 min floor) in
`filing_artifact_pipeline` over 5,583 accessions with flat ~416 MiB memory, looking like it
was re-loading immutable, already-captured SEC data.

1. Why iterate 5,583 accessions? Per-window `bootstrap-next` runs with the default
   `--artifact-policy all_attachments`; `_configured_parser_accessions` selects every
   ownership/ADV-form accession in the window (heavy insiders → 5,583 Form 3/4/5).
2. Why revisit immutable data? Idempotency lives at the **download** layer, not the
   **iteration** layer — `fetch_filing_artifacts` returns cached artifacts with no SEC call
   when `existing_rows and not force`, but the orchestrator loop still visits every accession
   to check the cache. No "universe already captured → skip the pass" short-circuit.
3. Why does checking cached accessions cost ~93 min? The loop ran
   `time.sleep(WAREHOUSE_ARTIFACT_REQUEST_DELAY)` (default **1.0s**) after **every**
   accession, **unconditionally, even on a pure cache hit**. 5,583 × 1s ≈ 93 min of no-op
   throttle. **Root cause:** the SEC rate-limit sleep was paid on the idempotent no-op path,
   not just on real network fetches.

**Resolution (root-cause fix, #1):** `fetch_filing_artifacts` now returns `network_fetches`
(count of real SEC round-trips: edgartools `get_filing` + each `download_bytes`); the
orchestrator loop throttles only when `network_fetches > 0`. Cache hits (immutable,
already-captured artifacts) return `network_fetches=0` and skip the sleep, so re-runs against
loaded bronze no longer pay the ~93-min dead-time throttle while new filings are still fully
rate-limited. Locked in by `tests/unit/test_loader_idempotency.py` (`network_fetches` = 0 on
cache hit, 1 on fetch).

**Additional mitigations:**
- **#2 — opt-in artifact skip:** `load_history`'s SM input now accepts an optional
  `artifact_policy` field (`ArtifactPolicyCheck`/`ArtifactPolicyDefault` states in
  `deploy-aws-application.sh`, mirroring `WindowSizeCheck`/`TotalCikLimitCheck`), threaded
  through to per-window `bootstrap-next --artifact-policy`. Default stays
  `all_attachments` — `load_history` is the canonical loader for **brand-new** company
  universes (see Phased Pipeline below), so it must keep fetching artifacts for genuinely
  new CIKs by default. Pass `{"artifact_policy": "skip"}` explicitly only when re-running
  over an already-loaded universe purely to skip fetch entirely; do not make this the
  default, or first-time loads would silently stop capturing ownership/ADV artifacts.
- **#3 — lower redundant throttle default:** `WAREHOUSE_ARTIFACT_REQUEST_DELAY` default
  lowered `1.0s → 0.2s`. `sec_client.py`'s `pyrate_limiter` bucket (9 req/sec, matching
  `EDGAR_RATE_LIMIT_PER_SEC`) already throttles every individual SEC request; the
  orchestrator's per-accession sleep is a second, more conservative layer on top of that,
  not the primary rate-limit safety net.

NOTE: fix #1 (code) and #3 (default) take effect only after a warehouse image rebuild +
deploy. Fix #2 (SM input plumbing) takes effect after the next `deploy-aws-application.sh`
run that re-registers the `load_history` state machine — no image rebuild required.

## Gold-build memory / daily_incremental OOM 5-whys (fixed and deployed, re-run pending, 2026-07-30)

**Problem:** `daily_incremental`'s first-ever prod execution
(`daily-incremental-1785336584`) OOM-killed (exit 137) 4 times in a row, identically,
exhausting `MaxAttempts:3` retries and failing the execution.

1. Symptom: CloudWatch shows all 4 attempts dying mid-`gold_table_started` for
   `sec_thirteenf_holding` (~6.8M rows), on a 4096MB `medium` Fargate task.
2. Why does one table's build kill the whole task? `build_gold()`
   (`edgar_warehouse/serving/gold_models.py`) returned a fully-realized
   `dict[str, pa.Table]` — every prior table stayed alive in memory while the next one
   built. By the time `sec_thirteenf_holding` started, ~7M rows across `dim_filing`
   (3.26M), `fact_filing_activity` (3.26M), `fact_adv_private_fund` (374K), and 13 smaller
   tables were still held in the dict — confirmed via the identical `gold_table_completed`
   row counts across all 4 attempts.
3. Why hold everything in memory? The caller (`warehouse_orchestrator.py`) then made two
   more full passes over that same dict — `write_gold_to_storage_manifest` and
   `write_gold_to_serving_export` — before `del gold_tables` freed anything. Peak memory was
   the sum of every gold table simultaneously, not the largest one.
4. Why did `gold-refresh`'s own prior OOM fix (commit `37c3171`, May 2026, moved it to the
   `large` task profile) not protect `daily_incremental`? `GOLD_AFFECTING_COMMANDS`
   (7 members, all calling this same `build_gold()` path) and `workflow_profile()`
   (`infra/scripts/deploy-aws-application.sh`, per-command task sizing) are two independent
   collections with no link between them — adding `daily_incremental` to the first didn't
   flag that it needed the second's `large` profile too. Separately, `large` and `medium`
   currently share the identical 4096MB ceiling (only CPU differs), so `37c3171`'s "move to
   `large`" fix may already be memory-ineffective today regardless.
5. **Root cause:** no caller in the memory-heavy `GOLD_AFFECTING_COMMANDS` path streamed
   gold-table construction — every one materialized the whole ~24-table gold layer before
   writing any of it, so the failure was only a matter of when one of them ran at
   sufficient scale to hit the ceiling.

**Resolution (structural fix, done 2026-07-30):** `build_gold()` split into a builder
registry (`_gold_table_builders`) plus a new generator, `iter_gold_tables()`, that yields
`(name, table)` pairs one at a time; `build_gold()` is now just
`dict(iter_gold_tables(db))`, kept for the one remaining caller
(`validate_data_quality.py`) that needs random access across the full gold layer.
`warehouse_orchestrator.py`'s `GOLD_AFFECTING_COMMANDS` caller now streams: build one
table, write it to storage, export it to Snowflake, `del table`, move to the next — instead
of three full passes over the whole gold layer held in memory at once. Confirmed via
source inspection (every `_build_*` function signature) that no builder depends on a
previously-built table (all take only a `conn` argument), so streaming changes lifetime, not
build order or output. Characterization
tests (`tests/unit/test_gold_models_streaming.py`) cover both the schema/table-name parity
between `build_gold()` and `iter_gold_tables()` and the generator's actual laziness (a later
builder, e.g. `sec_thirteenf_holding`, is provably not invoked until the generator reaches
it).

**Deployed 2026-07-30 (ticket 03):** `large`'s memory raised 4096 → 8192MB
(`register_task_definition large 2048 8192`); `daily_incremental`/`bootstrap`/`full_reconcile`/
`gold_refresh` all moved onto `large`. A critical finding changed the actual fix needed:
`workflow_profile()` is never called with `"daily_incremental"`/`"bootstrap"` at all (dead
code) — their real `RunWarehouseTask` step is built by `write_warehouse_mdm_gold_definition`'s
`run_wh`, which was still hardcoded to the medium ARN; that's what was actually rewired.
Warehouse image (digest `sha256:aca8078c658bc3f66ac40fa9e41923c4f29743f23ad5623756d94888728cbb30`,
confirmed via `docker run --entrypoint python ... -c "from edgar_warehouse.serving.gold_models
import iter_gold_tables"` to contain ticket 01's streaming fix) deployed to prod via
`deploy-aws-application.sh --env prod --enable-mdm`. A fresh `daily_incremental` execution was
started to confirm. **Re-run outcome still pending as of this entry** — see
`.scratch/gold-build-memory-reliability/issues/03-decide-task-memory-fix-to-unblock-daily-incremental.md`
for the execution ARN and result once known. **Confounding caveat:** both the streaming fix and
the memory bump are live together in this one deploy — a pass confirms the combination works,
not that either fix alone was sufficient; ticket 01's own "peak memory drops materially" step
remains formally unconfirmed in isolation. **Also note:** the failed execution
(`daily-incremental-1785336584`) ran an older state-machine shape that predates
`Stage0CompanyIdentity` (added by the Company Identity Pipeline map, never before run in
prod) — the re-run exercises ~70 sequential per-window tasks ahead of the actual
`RunWarehouseTask` step that OOM'd, so a Stage0 failure would be an unrelated, new issue, not
this fix failing. Full ticket detail: `.scratch/gold-build-memory-reliability/map.md`.

## AWS teardown 5-whys (resolved 2026-07-11)

`destroy-aws-complete.sh` is authored/tested for Linux/CI and failed three times on macOS
(Colima host, default bash 3.2, GNU-vs-BSD tool differences) during the `077127448006`
decommission. Fixes are in the script; re-record here if they regress.

**Problem 1 — `mktemp: mkstemp failed ... File exists`, aborted at the first S3 bucket.**
1. `mktemp "${TMP_DIR}/s3-versions-XXXXXX.json"` failed. 2. BSD/macOS `mktemp` only substitutes
*trailing* `X`s; the `.json` suffix after the X's makes the template literal. 3. Written for GNU
`mktemp` (substitutes X's anywhere). 4. `set -e` aborts the whole run. **Root cause:** GNU-vs-BSD
`mktemp`. **Fix:** drop the `.json` suffix so X's are trailing (portable; `aws … file://` ignores
the extension).

**Problem 2 — `DeleteObjects MalformedXML`, aborted emptying a small bucket.**
1. `delete-objects` rejected the payload on `snowflake-export` (only ~75 live objects). 2. A single
`list-object-versions --max-items 1000` page returned 537 Versions + 473 DeleteMarkers = **1010**
combined; the Python summed both into one request. 3. S3 `delete-objects` accepts at most **1000
keys** per call. **Root cause:** versioned buckets can return >1000 combined versions+markers per
page. **Fix:** cap each delete batch to `objects[:1000]`; the outer loop re-lists from the start and
converges.

**Problem 3 — `mapfile: command not found`, task-def cleanup silently no-op'd.**
1. Ad-hoc cleanup used `mapfile -t`. 2. macOS ships bash 3.2, which lacks `mapfile` (bash 4+).
**Root cause:** bash-3.2 host. **Fix:** build arrays with `while IFS= read -r … do ARR+=("$line"); done < <(cmd)`.

**Also:** prod `infra/terraform/accounts/prod/backend.hcl` pointed at the stale
`edgartools-dev-tfstate-077127448006/accounts/prod` state (6 resources: leftover notifications
module) instead of the real `edgartools-prod-tfstate/accounts/prod` (44 resources). A naive
`terraform destroy` would have orphaned the entire prod VPC/ECS/KMS stack. **Lesson:** verify a
teardown's backend resolves to the *current* state (`terraform state list` count) before trusting it.

## INSTITUTIONAL_HOLDS / EMPLOYED_BY 5-whys (fixed, not yet deployed, 2026-07-26)

**Problem:** `INSTITUTIONAL_HOLDS` was 0 in MDM after `derive-relationships` reported "OK." A
2026-07-13 finding (EDGE-11, `.planning/workstreams/fix-pipelines/REQUIREMENTS.md`) attributed
this to the bulk artifact-fetch pipeline never selecting 13F-HR forms. That finding was stale and
had already been overtaken by a later fix — re-trusting it without re-checking live state would
have pointed at the wrong problem.

1. Symptom: `INSTITUTIONAL_HOLDS` = 0 despite a derive step reporting success.
2. Why assume the fetch pipeline is broken? Because a 13-day-old doc said so. Checking live prod
   Snowflake instead: `EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SEC_THIRTEENF_HOLDING` has **6.8M rows**
   — the fetch/parse pipeline works and has run at scale. The cited root cause no longer applies.
3. Why is the relationship still 0 if the source data exists? CloudWatch on the actual derive
   task (`mdm-mdm-large/.../7fd06878e8254bcab9cbdb4263066ab8`, 2026-07-25T23:26:52Z) shows:
   `{"event": "mdm_relationship_skip", "rel_type": "INSTITUTIONAL_HOLDS", "reason":
   "missing_source_table", "source_table": "sec_thirteenf_filing"}`.
4. Why is `sec_thirteenf_filing` "missing" when it's created in the same schema and written by the
   same ingest loop as `sec_thirteenf_holding`? MDM's derive step reads silver through
   `ShardedSilverReader` (`edgar_warehouse/silver_support/sharded_reader.py`), which only exposes
   tables listed in its hardcoded `_TABLES` allowlist as cross-shard UNION ALL views.
   `sec_thirteenf_filing` was added to the schema in the same commit as `sec_thirteenf_holding`
   (d20cad8) but never added to `_TABLES` — a registration gap, not a data gap.
5. Why did this look like a clean "OK, zero rows" instead of an error? `_find_missing_source_table`
   deliberately catches any DuckDB "does not exist" error to gracefully skip relationship types
   with no source data yet (by design, so one missing type doesn't crash the whole `mdm run`). That
   same broad catch makes a **registration bug indistinguishable from a genuinely empty universe**
   — the derive step logs `mdm_relationship_skip` either way.

**Root cause:** `ShardedSilverReader._TABLES` omitted `sec_thirteenf_filing`. The same omission
also silently dropped `sec_employment_event` (the EDGE-09 sibling gap, Item 5.02 8-K path for
`EMPLOYED_BY`) — added in the same commit, same allowlist, same bug.

**Fix:** added both table names to `_TABLES`. Regression test added
(`tests/unit/test_sharding.py::test_sharded_silver_reader_exposes_thirteenf_filing_and_employment_event`)
that builds a real shard via `SilverDatabase`, writes one row to each table, and asserts
`ShardedSilverReader` can read it back — confirmed to fail with the exact prod `CatalogException`
before the fix and pass after. **No new SEC fetching is required** — the source data already
exists in the shards; this is a reader fix plus a `derive-relationships` re-run, not a bulk
reload. Not yet deployed/re-derived/graph-verified as of this entry — see
`.scratch/release-readiness/issues/06-define-full-chain-launch-gate.md` for the full write-up and
`.planning/workstreams/fix-pipelines/REQUIREMENTS.md` (EDGE-09/EDGE-11) for corrected status.

**Lesson:** a stale root-cause doc plus a deliberately-broad "missing table → skip" error handler
is a trap — always re-verify against live state (source row counts, actual skip-event logs) before
building on top of a prior investigation's conclusion, especially when a fails-closed gate (ticket
06) depends on the conclusion being right.

**Addendum (2026-07-26, second layer):** deploying the `_TABLES` fix and re-running
`mdm-backfill-relationships --relationship-type INSTITUTIONAL_HOLDS` in prod got past the
`missing_source_table` skip and hit a **second, previously-unreachable bug**: `_ensure_thirteenf_manager`
(`edgar_warehouse/mdm/pipeline.py`) queried `SELECT company_name FROM sec_company WHERE cik = ?`,
but `sec_company`'s real column is `entity_name` (`silver_store.py:41`) — `company_name` appears
nowhere else in the codebase. `duckdb.BinderException` in prod, task exit code 1. This code path
had **never executed** before today (always short-circuited by the `sec_thirteenf_filing`
registration bug), so the typo was invisible. Worse: the one existing unit test for this exact path
(`test_thirteenf_manager_outside_adv_universe_is_created`,
`tests/mdm/test_pipeline_relationships.py`) used a `StubSilver` fixture keyed
`"FROM sec_company WHERE cik": [{"company_name": ...}]` — the **same wrong column name** — so the
stub silently mirrored the bug instead of the real schema and the test passed regardless. Fixed
both (query → `entity_name`, stub fixture → `entity_name`) and added a third test,
`test_thirteenf_manager_resolves_name_against_real_silver_schema`, that runs the same code path
against a real `SilverDatabase`-backed DuckDB file instead of a hand-rolled stub — confirmed to
fail with the exact prod `BinderException` before the fix. **Lesson (compounding the one above):**
a hand-rolled stub that encodes a query's expected shape can silently drift from the real schema in
lockstep with a bug in the code under test, since nothing ever validates either side against the
other — for any code path that has *never actually run against real data*, prefer a schema-backed
fixture (real `SilverDatabase`/DuckDB) over a string-matched stub, or treat passing stub-only tests
for such paths as unproven, not verified.

## Manifest-pipeline ownership + cursor-syntax incident 5-whys (resolved 2026-07-27)

**Problem:** applying the ERDP-01/02/04 Snowflake bootstrap SQL fixes to prod (new
`GUIDANCE_FACTS`/`CONSENSUS_ESTIMATES`/`TRANSCRIPT_EVENTS` tables, updated `LOAD_EXPORTS_FOR_RUN`/
`REFRESH_AFTER_LOAD`/`PROCESS_RUN_MANIFEST_STREAM`) turned into a live `SNOWFLAKE_RUN_MANIFEST_TASK`
outage plus a second, self-inflicted access break, while migrating one pilot company (Apple,
320193) end-to-end.

1. Symptom: `SNOWFLAKE_RUN_MANIFEST_TASK` started `FAILED`-looping shortly after the bootstrap SQL
   was reapplied, instead of the expected `SUCCEEDED`/`SKIPPED`(idle) pattern.
2. Why fail? `REFRESH_AFTER_LOAD` (recreated under `EDGARTOOLS_PROD_DEPLOYER`) tried
   `ALTER DYNAMIC TABLE ... REFRESH` on tables it didn't own — `COMPANY` and most of the original 9
   gold tables were owned by `ACCOUNTADMIN` from early ad-hoc bootstrapping, `EARNINGS_CALENDAR`
   plus the 3 new Explore tables were owned by whichever role last ran `dbt run --full-refresh`
   against them. Snowflake requires the *direct owner* role for that `ALTER` (documented elsewhere
   in this file). Ownership had never been consistent across the 20 gold tables.
3. Why was ownership never consistent? No source-controlled bootstrap SQL provisioned a single role
   for these objects — each fix session used whatever role was convenient at the time
   (`ACCOUNTADMIN` for early manual bootstrapping, `EDGARTOOLS_PROD_DEPLOYER` for dbt runs), so
   ownership silently drifted table-by-table with every unrelated deploy.
4. Why did the interim fix (granting `ACCOUNTADMIN` ownership of `REFRESH_AFTER_LOAD` as a
   stopgap) get corrected mid-incident? Per explicit user instruction: ad-hoc `ACCOUNTADMIN`
   ownership is not an acceptable pattern for pipeline objects. **Root cause of the ownership
   churn:** fixed by creating a single dedicated `EDGARTOOLS_PROD_LOADER` role
   (`infra/snowflake/sql/bootstrap/08_loader_role.sql`) and transferring ownership of all 20 gold
   dynamic tables plus the 3 manifest procedures onto it in one operation, and pointing
   `profiles.yml`'s prod dbt target at that role by default (it previously defaulted to
   `EDGARTOOLS_PROD_DEPLOYER`, which would have silently re-flipped ownership on the next
   unparameterized `dbt run --target prod`).
5. **Compounding self-inflicted bug:** the ownership transfer used
   `GRANT OWNERSHIP ... REVOKE CURRENT GRANTS`, which revokes *all* outbound grants on an object,
   not just the previous owner's — this silently stripped `EDGARTOOLS_PROD_READER`'s (the
   Streamlit dashboard's role) `SELECT` on all 20 gold tables. Caught before being reported as
   fixed, via `SHOW GRANTS ON TABLE ... COMPANY` showing only the new `OWNERSHIP` row. Fixed with
   `GRANT SELECT ON ALL/FUTURE DYNAMIC TABLES ... TO ROLE EDGARTOOLS_PROD_READER`; `08_loader_role.sql`
   uses `COPY CURRENT GRANTS` instead so a future re-application of this fix cannot repeat it.

**Separate, genuine defect found and fixed along the way:** `PROCESS_RUN_MANIFEST_STREAM`'s
shorthand `FOR row IN (SELECT col1, col2 FROM ...) DO` cursor form (Snowflake Scripting's
row-iteration-over-a-query syntax) fails with `Unsupported: Scalar subquery with multi-column
SELECT clause` — independently reproduced live on 2026-07-27 with a trivial two-column literal
`SELECT 1, 2 UNION ALL SELECT 3, 4`, unrelated to any table in this repo. **This is not a
"never worked" case**: `TASK_HISTORY` shows the same procedure body succeeded as recently as
2026-07-26 16:53:53, less than a day before the failures started — so treat this as a real but
not fully understood intermittent defect in the multi-column form, not a permanently broken
construct. Do not use the shorthand `FOR row IN (SELECT col_a, col_b, ...) DO` form for 2+ columns
in this account; use the explicit form instead:
```sql
DECLARE
  cnt INTEGER;
  c1 CURSOR FOR (SELECT col_a, col_b FROM ...);
  v_a TYPE; v_b TYPE;
BEGIN
  cnt := (SELECT COUNT(*) FROM (SELECT col_a, col_b FROM ...));
  OPEN c1;
  FOR i IN 1 TO cnt DO
    FETCH c1 INTO v_a, v_b;
    ...
  END FOR;
  CLOSE c1;
END;
```
A naive "loop until `FETCH` stops returning rows" pattern (checking `SQLROWCOUNT`/`v_a IS NULL`)
hung indefinitely under this same account state and had to be killed with
`SELECT SYSTEM$CANCEL_QUERY('<query_id>')` — the bounded `FOR i IN 1 TO <precomputed COUNT(*)>`
form above is the one that worked. Live in `04_refresh_wrapper.sql`.

## Streamlit-in-Snowflake ownership 5-whys (resolved 2026-07-27)

**Problem:** GH-252's second dashboard (`MDM_GRAPH_DASHBOARD`) was deployed with a
dedicated, correctly-scoped reader role (`EDGARTOOLS_GRAPH_REVIEW_READER`, SELECT on
exactly 5 review views) — but that role's grants turned out not to control what the
*app itself* could see when opened.

1. Symptom: nothing wrong yet — worth checking *before* declaring "access limited to a
   dedicated read role" (GH-251 criterion 6) actually true for the new dashboard, not
   just for someone manually `USE ROLE`-ing into the reader role.
2. Why does the reader role's SELECT grants not settle it? Streamlit-in-Snowflake apps
   run with the app **owner's** privileges by default ("owner's rights"), not the
   viewer's. Restricted caller's rights exists only as a Preview feature for
   container-runtime apps — not what `CREATE STREAMLIT` (the module's resource type)
   produces (docs.snowflake.com/en/developer-guide/streamlit/object-management/owners-rights).
3. Why does that matter here specifically? `infra/terraform/snowflake/modules/dashboard`
   creates the `snowflake_streamlit` resource authenticated as whichever role ran
   `terraform apply` — in this repo, always `ACCOUNTADMIN`. `SHOW STREAMLITS` confirmed
   **both** dashboards (the original `EDGARTOOLS_DASHBOARD` and the new
   `MDM_GRAPH_DASHBOARD`) were owned by `ACCOUNTADMIN`. Any viewer with `USAGE` on the
   app queries with ACCOUNTADMIN's full privileges through it, not the reader role's.
4. Why not just `GRANT OWNERSHIP ... TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER`? Confirmed
   live: Snowflake rejects it outright — `Unsupported feature 'GRANT/REVOKE OWNERSHIP ON
   STREAMLIT'`. Ownership of a Streamlit object cannot be transferred after creation at
   all — the only way to change it is to create the object while running **as** the
   target role.
5. **Root cause:** the shared `dashboard` Terraform module always creates its
   `snowflake_streamlit` resource under the Terraform-authenticated admin role, with no
   mechanism (Terraform or otherwise) to create it under a minimal-privilege role instead.

**Resolution (GH-252's dashboard only, not the original — see "Still shared" below):**
`infra/snowflake/sql/graph_review/02_dashboard_reader_grants.sql` now: grants
`EDGARTOOLS_GRAPH_REVIEW_READER` `CREATE STREAMLIT` on its schema + `READ` on its stage,
`DROP`s the Terraform-created (ACCOUNTADMIN-owned) `MDM_GRAPH_DASHBOARD` object, and
recreates it identically while running `USE ROLE EDGARTOOLS_GRAPH_REVIEW_READER` —
confirmed via `SHOW STREAMLITS` that `owner` is now `EDGARTOOLS_GRAPH_REVIEW_READER`, and
via `terraform plan` that this produces **zero drift** (the `snowflake_streamlit` resource
schema doesn't track an owner/role attribute at all, so Terraform is blind to who owns it
— re-applying the module won't fight this, but it also means a future `-replace` or
destroy/recreate of this resource silently reverts ownership to ACCOUNTADMIN again; re-run
`02_dashboard_reader_grants.sql` afterward if that ever happens).

**Still shared / not fixed:** the original `EDGARTOOLS_DASHBOARD` has the identical
ACCOUNTADMIN-owner gap, already implicitly deferred by `deploy.sh`'s own header comment
since GH-247 ("*going forward: that dashboard-owner role once its grants are live*",
referring to the provisioned-but-unused `EDGARTOOLS_{ENV}_DASHBOARD_OWNER` role). Not
touched in this pass — GH-252 was in scope, the original dashboard's fix is its own
follow-up (same drop/recreate-as-target-role recipe would apply).

**Lesson:** a role's `SELECT`/`USAGE` grants prove it *can* be activated and *can* query
the right objects — neither proves what a Streamlit app built on top of it actually
executes as. For any Streamlit-in-Snowflake app whose access-control story matters, check
`SHOW STREAMLITS ... ` for the `owner` column before trusting a "dedicated read role"
claim; Terraform-created objects in this repo default to the admin role as owner unless
something has deliberately re-created them otherwise.

## Dev Terraform/Snowflake go-live blockers 5-whys (partially resolved 2026-07-27)

**Problem:** Resuming a paused live `terraform apply` for the dev Snowflake stack
(`infra/terraform/snowflake/accounts/dev` and
`infra/terraform/access/snowflake/accounts/dev`, the roots `go-live.sh`/
`deploy-snowflake-stack.sh --env dev` drive) hit `terraform init` failing on a
nonexistent S3 bucket, then a real Snowflake "free trial has ended" error, then a
plan that wanted to destroy the entire `native_pull` module (16 tables, storage
integration, export stage, manifest task), then an apply that silently would have
unscheduled the production manifest task, then a final grant failure. Five
distinct blockers, stacked.

1. **`terraform init` failed:** local (gitignored) `backend.hcl` files across 4 dev
   roots pointed at `edgartools-dev-tfstate-690839588395`, which was never
   provisioned (its `bootstrap-state` local state has `resources: []` — `init`'d,
   never `apply`'d). **Why did every local file have the same wrong bucket?**
   They're generated from the tracked `.example` templates — 2 of the 4
   `.example` files (`accounts/dev`, `access/aws/accounts/dev`) carried the wrong
   suffixed name while the other 2 correctly said `edgartools-dev-tfstate` (the
   real bucket, in use since 2026-07-02, holding all 4 roots' actual state).
   **Root cause:** a repo-level inconsistency in the tracked `.example` files,
   silently propagated into every local checkout. **Fix:** corrected both wrong
   `.example` files and the 4 local `backend.hcl` files to `edgartools-dev-tfstate`.
2. **After `init` succeeded, `terraform plan` failed with `390913 (08004): Your
   free trial has ended and all of your virtual warehouses have been suspended`.**
   This looked like a billing blocker but wasn't: dev's `terraform.tfvars` had
   `snowflake_organization_name = "EADPGLN"` / `account_name = "YG91578"` — a
   **different account** from the one this whole platform actually runs on
   (`XCPCLKF`/`KB19989`, confirmed via `SELECT CURRENT_ORGANIZATION_NAME(),
   CURRENT_ACCOUNT_NAME()` against the `snowconn`/`edgartools-prod` connections
   both dbt and this repo's other tooling already use). `EADPGLN-YG91578` never
   held any real EdgarTools infrastructure. **Fix:** corrected both dev
   `terraform.tfvars` files' account identifiers to `XCPCLKF`/`KB19989`, plus a
   third stale reference (`provisioning_state_bucket` pointing at the
   decommissioned `077127448006` account's bucket) in
   `access/snowflake/accounts/dev/terraform.tfvars`.
3. **With the right account, the plan showed `0 add, 0 change, 27 destroy`** —
   all of `module.native_pull` (every source/gold table Terraform tracks, the
   storage integration, export stage, Snowpipe, manifest task).
   `local.native_pull_enabled` in
   `infra/terraform/snowflake/accounts/dev/main.tf` requires 3 variables
   (`snowflake_storage_role_arn`, `snowflake_export_root_url`,
   `snowflake_manifest_sns_topic_arn`) that the local `terraform.tfvars` had
   simply never set, defaulting them to `null` and disabling the whole module.
   **Fix:** recovered the real values from the existing state (`terraform state
   pull`, not guessed) and added them to `terraform.tfvars`.
4. **With that fixed, the plan dropped to 4 changes, but one was a real,
   unrelated bug:** `snowflake_task.manifest_processor` in
   `infra/terraform/snowflake/modules/native_pull/main.tf` had never declared a
   `schedule` block in its entire git history, yet the live task
   (`SNOWFLAKE_RUN_MANIFEST_TASK`, applied 2026-07-06) has `schedule: 1 MINUTE`,
   `state: started`, `predecessors: []` (standalone) — set out-of-band at some
   point, never back-ported into the module. Applying as-is would have either
   failed (Snowflake generally rejects resuming a standalone task with no
   schedule) or stripped the schedule from a `started` task, stopping the
   `PROCESS_RUN_MANIFEST_STREAM` pipeline that refreshes `EDGARTOOLS_GOLD`.
   **Fix:** added an explicit `schedule { minutes = 1 }` block to the task
   resource (module is shared by dev and prod — prod almost certainly has the
   same latent gap, not yet verified/applied there). Confirmed via `SHOW TASKS`
   after apply that the schedule survived.
5. **Applying `access/snowflake/accounts/dev` (creates `EDGARTOOLS_DEV_LOADER`/
   `EDGARTOOLS_DEV_DASHBOARD_OWNER` roles + grants, retires
   `EDGARTOOLS_DEV_REFRESHER`) landed everything except 5 grants targeting the
   `EDGARTOOLS_DECISION` schema**, which does not exist in dev at all (`SHOW
   SCHEMAS IN DATABASE EDGARTOOLS_DEV` confirms). GH-247's PR (#294) added
   Terraform-managed reader grants for a Decision Contract schema that has, at
   most, only ever existed ad hoc in prod. **Not fixed** — creating it needs its
   own scoped decision about what belongs in it (see
   `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql`,
   still labeled a "sketch" as of GH-246's PR #292). Plan saved at
   `/tmp/dev-access-plan3.tfplan` (ephemeral, not committed) for whoever picks
   this up next.

**Root cause common to #1–#3:** nobody had ever run `terraform init`/`plan`/
`apply` against these two dev roots since the 2026-07-06 apply and the
`690839588395`/`XCPCLKF` account migration — local config silently drifted from
reality (wrong bucket, wrong account, incomplete vars) with nothing to catch it
until the next live-apply attempt.

**Verified safe before applying #5's role deletion:** `SHOW GRANTS TO ROLE
EDGARTOOLS_DEV_REFRESHER` showed only inbound USAGE/MONITOR/OPERATE grants, no
owned objects (dev's dynamic tables are owned by `EDGARTOOLS_DEV_DEPLOYER`) — so
dropping it did not repeat the ownership-orphaning pattern from the
manifest-pipeline incident above.

**Update (2026-07-27, same day):** #4 was confirmed live in prod, and it was
worse than "latent" — `SNOWFLAKE_RUN_MANIFEST_TASK` had already lost its
schedule (`schedule: None`) after an unrelated cursor-bug incident earlier that
morning (03:13–03:18) auto-suspended it; it had been resumed but never
rescheduled, so gold refresh was running only on occasional manual triggers,
not the intended 1-minute cadence. Applied the same module fix to
`snowflake/accounts/prod` and `access/snowflake/accounts/prod` (the latter
required `terraform import`-ing `EDGARTOOLS_PROD_LOADER`, which already existed
from the `08_loader_role.sql` bootstrap run during that same morning's
incident — Terraform didn't know about it). Verified live: schedule restored,
`EDGARTOOLS_PROD_DASHBOARD_OWNER`/`EDGARTOOLS_PROD_LOADER` roles and grants
landed, `EDGARTOOLS_PROD_REFRESHER` retired (confirmed it owned nothing first).
Also applied GH-251's `infra/snowflake/sql/graph_review/01_graph_review_contract.sql`
to prod (schema, 4 tables, 5 fail-closed views, `EDGARTOOLS_GRAPH_REVIEW_READER`
role) — unblocked there because prod already has the generation-scoped
`GRAPH_ACTIVE_POINTER`/`GRAPH_GENERATION` tables (from the residual-holds work
above); **dev does not** — dev's `NEO4J_GRAPH_MIGRATION` schema has only ever
had non-generation-scoped `sync-graph` runs, so the same SQL fails there
(`GRAPH_ACTIVE_POINTER does not exist`) after creating the schema + 4 empty
tables (harmless, `CREATE IF NOT EXISTS` — resumes cleanly once dev gets a
generation-scoped `sync-graph --generation-id ...` + `graph-activate` run).

**Update (2026-07-27, later same day):** applying the SQL contract to prod
wasn't sufficient on its own — the first `mdm verify-graph` run against it
(execution `gh251-populate-review-1785189032`) failed at the ECS task level
with all 4 review tables still at 0 rows and zero `graph_review`/`publish`
log lines. Root cause: prod's running `edgartools-prod-mdm` image (digest
tag `sha-6ea935cc32ed`, pushed 2026-07-26T19:26:11-04:00) predated GH-251's
merge (PR #293, 2026-07-27T19:25:36Z) by over a day, so it simply didn't
contain the `graph_review_publish` code path — a deploy/promotion gap (dev
auto-builds on every `main` push; prod never auto-promotes, see "Image
management" below), not a code bug. Rebuilt and pushed a fresh prod MDM
image from current `main` (digest `sha256:cc098d80...`, tags
`sha-2fa5fafb63a9`/`prod`) and redeployed via `deploy-aws-application.sh
--env prod --enable-mdm`. Re-ran `mdm verify-graph`
(`gh251-populate-review-retry-1785191328`): the ECS task still exits 1, but
that's a real, pre-existing graph parity mismatch (missing `person`/
`security` nodes, missing `COMPANY_HOLDS`/`HOLDS`/`IS_INSIDER` edges — 193,323
MDM-active vs. 193,063 graph nodes, 166,067 vs. 157,732 edges) unrelated to
GH-251 or this deploy. Confirmed the actual goal directly: all 4
`MDM_GRAPH_REVIEW` tables are populated (6 entity types, 11 relationship
types, 40 mismatch samples, 11 native-app checks) and
`V_GRAPH_REVIEW_ACTIVE_GENERATION` resolves to the real active generation
(`ticket20-strict-endpoint-seal-850ea34-20260725T130457Z`, 193,063 nodes /
157,732 edges — exact match to the verifier's own output). GH-251's contract
is genuinely live and correct in prod. **Lesson:** a SQL-contract "applied
successfully" is necessary but not sufficient evidence a publish path
works — always confirm the *code* that writes to it is actually running in
the target environment before trusting an empty-tables-after-first-run
result as diagnostic.

**Still open:** the `EDGARTOOLS_DECISION` schema gap (#5) — scoped further:
`infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql` is close
(builds from existing gold tables, but its "MDM active-company universe" join
is an explicit placeholder that just self-joins `COMPANY`, documented as
"compile checks only, not agent-grade"); `02_subject_bundle_read_issuer.sql`
has an actual bug, not just a placeholder — `BUNDLE_AUDITOR` references
`EDGARTOOLS_GOLD.SEC_AUDITOR_REPORT_EVIDENCE`, but that table only exists in
`EDGARTOOLS_SOURCE` (verified live), never `EDGARTOOLS_GOLD`. The real open
decision behind both: no Snowflake-side source has been chosen yet for "MDM
active company universe" — MDM's authoritative state is Postgres, not
Snowflake; the closest reflection is `NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES`
(entity_type=COMPANY), but nobody has decided if that's right, what "active"
means for it, or whether it should route through the generation-scoped
`GRAPH_ACTIVE_POINTER` pattern GH-251 established. Also still open: dev's
generation-scoped graph sync gap noted above (deprioritized for now, not
worked further).

## Phased Pipeline (use this for all bootstraps ≥10 companies)

`load_history` is the canonical way to load companies at scale. It runs in four
sequential stages, each optimised for its workload:

```
Stage 1 — Bronze + Silver (parallel, N×10 concurrent ECS tasks)
  seed-universe  →  bootstrap-batch ×N  (MaxConcurrency=10)
  • Each batch: fetch SEC submissions + pagination → S3 bronze, parse → silver DuckDB
  • NO gold build per batch (bootstrap-batch is NOT in GOLD_AFFECTING_COMMANDS)

Stage 2 — MDM entity resolution (sequential Step Functions)
  mdm-run  →  mdm-backfill-relationships  →  mdm-sync-graph  →  mdm-verify-graph
  • Runs after ALL batches complete so entity resolution sees the full silver dataset
  • Derives IS_INSIDER, MANAGES_FUND etc. and syncs to the graph (Snowflake, not external Neo4j)

Stage 3 — Gold refresh (single ECS task)
  gold-refresh
  • Reads complete silver DuckDB, builds all 9 gold tables, writes Snowflake export manifests
  • SNOWFLAKE_RUN_MANIFEST_TASK picks up the manifest and refreshes EDGARTOOLS_GOLD within 1 min
```

**Graph storage (read this before assuming "Neo4j" means an external service):**
As of the `neo4j-snowflake` workstream (v1.3, completed 2026-06-12), graph data lives
*inside* Snowflake — the Neo4j Graph Analytics Native App, installed in the same Snowflake
account as gold. There is no separate Neo4j database, no `NEO4J_URI`/`NEO4J_PASSWORD`
secret, and no external Bolt connection. `mdm sync-graph` materializes
`MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES` (plus per-label/per-type compatibility views) into a
Snowflake schema (e.g. `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`); `mdm verify-graph` runs a
strict SQL parity check plus Native App checks (compute pool, `GRAPH_INFO`, `BFS`, `WCC`)
against that same Snowflake target. One credential (the same `MDM_SNOWFLAKE_*`/
`DBT_SNOWFLAKE_*`/Snowflake CLI connection used everywhere else), one platform. Native App
grants: `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`. Full migration history:
`.planning/workstreams/neo4j-snowflake/`.

**MDM database (read this before assuming a separate AWS RDS instance):**
MDM's operational Postgres database was cut over from AWS RDS (private VPC) to Snowflake's
native Postgres service — provisioned and managed inside the same Snowflake account as
gold and the graph (`infra/scripts/bootstrap-prod-mdm.sh` provisions a "Snowflake Postgres
instance," e.g. `EDGARTOOLS_PROD_MDM`; connects via `snowflake_admin`). No AWS RDS module,
no VPC subnet group, no RDS security group remain for MDM — confirmed via repo-wide search,
zero `rds_mdm`/`mdm_database` Terraform files exist anymore (only `mdm_secret_moves.tf` in
the AWS accounts, handling the Secrets Manager migration). One platform (Snowflake) hosts
gold, the graph, and now MDM's operational store — eliminating the separate AWS RDS
network/credential surface. Note: this is still a distinct Postgres-wire-protocol DSN
(`MDM_DATABASE_URL`, port 5432) from the Snowflake SQL connection used for dbt/gold/graph
(`DBT_SNOWFLAKE_*`/`MDM_SNOWFLAKE_*`, HTTPS) — "one platform" means one Snowflake account
and governance boundary, not literally one shared connection string for both protocols.

**When to use what:**

| Scenario | Command / State Machine |
|----------|------------------------|
| Load 10+ companies (recommended) | `load_history` Step Function |
| Single company debug/resync | `targeted_resync` Step Function |
| Rebuild gold from existing silver | `gold_refresh` Step Function |
| Recent filings only (fast) | `bootstrap` Step Function |
| Daily incremental (ongoing) | `daily_incremental` Step Function |

**Running `load_history` via Step Functions:**

```bash
aws stepfunctions start-execution \
  --region us-east-1 \
  --state-machine-arn arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-dev-load-history \
  --name "load-history-$(date +%s)" \
  --input '{}'
# Runs ~15 min for 100 companies (vs 30-90 min sequential)
# Monitor: aws stepfunctions describe-execution --execution-arn <arn> --query status
```

**Do NOT run `bootstrap-next` locally for large batches** — it is sequential, so throughput
alone rules it out at scale. Reserve it for single-company ad-hoc loads with explicit
`--cik-list`. (Historical note: this guidance originally also cited "cannot reach MDM
Postgres, private VPC" — that no longer applies. MDM Postgres moved off AWS RDS onto
Snowflake's native Postgres service; see "MDM database" note below. Local reachability to
the current Snowflake-hosted instance has not been re-verified, so treat the sequential-
throughput reason as the one to rely on.)

**Key invariants (do not break):**
- `bootstrap-batch` must NOT be in `GOLD_AFFECTING_COMMANDS` — enforced in `warehouse_orchestrator.py:79`
- `gold-refresh` must be in `GOLD_AFFECTING_COMMANDS` — it is the sole gold builder in the phased pipeline
- `SNOWFLAKE_RUN_MANIFEST_TASK` must be STARTED in `EDGARTOOLS_GOLD` — verify with
  `snow sql --connection edgartools-dev -q "SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK'"`
- `silver_mdm_gold` map MUST pass `--artifact-policy skip` to `bootstrap-batch` — without it
  the pipeline makes thousands of SEC API calls (fetching ownership XMLs) even though the
  purpose of this pipeline is to reprocess already-loaded bronze with zero SEC calls.
  5-why root cause: the artifact pipeline is a separate SEC fetch pass; "no SEC calls" must
  be encoded as a flag, not assumed from the pipeline name.
- `BOOTSTRAP_BATCH_CONCURRENCY` recommended range: **2–5** concurrent ECS tasks. Current
  default is 3 (already within the recommended range). Values below 2 are not recommended
  for production — throughput is too low. Values above 5 risk triggering SEC rate limiting:
  at 5 tasks × ~9 req/sec theoretical max = ~45 req/sec, well above SEC's 10 req/sec per-IP
  limit without stagger mitigation. The in-process rate limiter in `sec_client.py` (9 req/sec
  per task) enforces per-task throttling but does not coordinate across ECS tasks.

Key import pattern (do not change without checking the edgartools changelog):

```python
# edgar_warehouse/parsers/ownership.py
from edgar.ownership import Ownership

parsed = Ownership.from_xml(content)
```

Other edgartools surfaces used:
- `edgar.filing` — filing metadata and document fetching in `runtime.py`
- `edgar.entity` — company/entity resolution
- `edgar.xbrl` — financial statement parsing in batch scripts

When the `edgartools` version is bumped, run the batch scripts in `scripts/batch/` to smoke-test parsing.

## Development Commands

> **Tooling:** always use `uv` for Python dependency management and Python CLI
> execution in this repo. The lockfile is `uv.lock`; never invoke bare `pip` or
> bare `dbt` from repo workflows. Use `uv sync` for project deps, `uv pip
> install` for deliberate one-off installs, and `uv run --with <package>` when a
> deploy needs a transient tool such as `dbt-snowflake`.
>
> **Docker runtime:** on macOS use Colima as the local Docker daemon. On Windows
> use Docker Desktop. The default macOS fast-feedback path is Colima plus plain
> `docker build`/`docker push`; `docker buildx` is supported when it is
> measurably faster or when using Linux/Windows CI registry cache. Do not
> introduce another container build/runtime stack.
>
> **One-time Colima setup (macOS):** Docker 29+ in Colima defaults to the
> containerd image-store snapshotter, which the legacy `docker build` path
> cannot use. Run this once per workstation (and after any Colima/Docker
> upgrade) to disable the snapshotter and provision adequate CPU/RAM/disk:
> ```bash
> bash infra/scripts/setup-colima.sh           # apply + restart Colima
> bash infra/scripts/setup-colima.sh --verify  # check current state
> ```
> `publish-warehouse-image.sh` fails fast with a pointer to this script if
> the daemon is misconfigured.

```bash
# Required env vars before any warehouse command
export EDGAR_IDENTITY="EdgarTools Platform thepaulananth@gmail.com"   # SEC User-Agent; must contain email
export WAREHOUSE_RUNTIME_MODE="bronze_capture"
export WAREHOUSE_BRONZE_ROOT="s3://edgartools-dev-bronze/warehouse/bronze"
export WAREHOUSE_STORAGE_ROOT="s3://edgartools-dev-warehouse/warehouse"
export SERVING_EXPORT_ROOT="s3://edgartools-dev-snowflake-export/warehouse/artifacts/snowflake_exports/"
export MDM_DATABASE_URL="postgresql://postgres:test@localhost:5432/mdm"  # local Colima postgres
export AWS_DEFAULT_REGION=us-east-1  # infra is us-east-1, not the default us-east-2

# Install project deps (uses uv.lock)
uv sync --extra s3 --extra snowflake

# Warehouse CLI
edgar-warehouse --help
edgar-warehouse bootstrap --tracking-status-filter active

# dbt (from dbt project root)
cd infra/snowflake/dbt/edgartools_gold
uv run --with dbt-snowflake dbt compile  # validate models without executing
uv run --with dbt-snowflake dbt run      # create/refresh gold dynamic tables in Snowflake
uv run --with dbt-snowflake dbt test     # run data quality tests

# Terraform — AWS infra
cd infra/terraform/accounts/prod
terraform plan
terraform apply

# Terraform — Snowflake infra
cd infra/terraform/snowflake/accounts/prod
terraform plan
terraform apply

# AWS-only Snowflake native-pull deploy (dev)
# Requires a SnowCLI connection (configured in ~/.snowflake/config.toml) and keeps
# Snowflake secrets out of repo files.
bash infra/scripts/deploy-snowflake-stack.sh \
  --env dev \
  --snow-connection snowconn \
  --run-validation \
  --run-dbt

# Docker image publish (Linux / CI with buildx registry cache)
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region <region> \
  --ecr-repository edgartools-dev-warehouse \
  --role warehouse \
  --image-tag $(git rev-parse HEAD) \
  --mode buildx \
  --cache-tag buildcache \
  --also-tag dev

# Docker image publish (macOS Colima — see "Manual AWS build and deploy" below for the full recipe)
colima start
export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    690839588395.dkr.ecr.us-east-1.amazonaws.com
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-warehouse \
  --role warehouse \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# Standalone dashboard (local)
cd examples/dashboard
uv pip install -r requirements.txt
streamlit run edgar_universe_dashboard.py
```

## dbt gold model SQL changes — smoke test convention

When a gold model's SQL body changes (not just its config), `dbt run`
**will not** detect the change for `materialized='dynamic_table'` models —
dbt-snowflake's dynamic-table materialization only diffs *configuration*
(target_lag, warehouse, refresh_mode, etc.), not the SQL body. An unchanged
config means `dbt run` is a silent no-op even though the deployed dynamic
table still runs the old SQL.

To force redeploy of a changed dynamic table, use:

```bash
uv run --with dbt-snowflake dbt run --select <model_name> --full-refresh
```

This issues `CREATE OR REPLACE DYNAMIC TABLE ... initialize = ON_CREATE`,
which triggers an immediate INITIAL refresh.

**Known gap blocking `--full-refresh` (dev, as of 2026-06-13):** the
`EDGARTOOLS_DEV_DEPLOYER` role lacks a direct `SELECT` grant on
`EDGARTOOLS_SOURCE` tables. Ad-hoc queries succeed (via the
`ACCOUNTADMIN`/`ORGADMIN` secondary roles), but Snowflake's dynamic-table
INITIAL refresh checks the table owner role's *direct* grants only —
`CREATE OR REPLACE DYNAMIC TABLE` makes `EDGARTOOLS_DEV_DEPLOYER` the new
owner, so the refresh fails with "not authorized ... (Note: the primary role
is the owner role of the dynamic table)". This affects **any**
`EDGARTOOLS_GOLD` dynamic table's `--full-refresh`, not just one model. See
`TODOS.md` ("EDGARTOOLS_DEV_DEPLOYER lacks direct SELECT on
EDGARTOOLS_SOURCE") for the fix and status.

Required env vars for `dbt run`/`dbt compile` against Snowflake (none have
defaults except role/database/warehouse, which fall back to the dev target's
values in `profiles.yml`):

```bash
export DBT_SNOWFLAKE_ACCOUNT=<account_locator.region.cloud>
export DBT_SNOWFLAKE_USER=<user>
export DBT_SNOWFLAKE_PASSWORD=<password>
export DBT_SNOWFLAKE_WAREHOUSE=EDGARTOOLS_DEV_REFRESH_WH
```

**SnowCLI connection naming.** No literal Snowflake account locator is ever committed to
this repo (always a placeholder like `<account_locator.region.cloud>` above) — the only
project-level convention is the **connection name**, resolved from
`~/.snowflake/config.toml`. `infra/scripts/go-live.sh`'s `default_snow_connection_for_env()`
defines: **`snowconn`** for dev, **`edgartools-prod`** for prod. `go-live.sh` is the
current orchestration entry point and always passes `--snow-connection` explicitly to
`deploy-snowflake-stack.sh`, so its own internal fallback default
(`edgartools-${ENVIRONMENT}`, i.e. `edgartools-dev` for dev) only matters if you invoke
`deploy-snowflake-stack.sh` directly without `--snow-connection` — prefer passing
`--snow-connection snowconn` explicitly for dev rather than relying on either script's
default, since the two scripts disagree.

## Image management

Use AWS ECR only for deployable images. Do not add non-AWS registry targets,
SDKs, ODBC drivers, or deployment steps back into this repo unless the platform
architecture changes explicitly.

| Image | Dockerfile | Installs | Runs |
|-------|------------|----------|------|
| `edgartools-dev-warehouse-deps` | `Dockerfile.warehouse-deps` | locked `.[s3]` deps via `uv` | dependency base image |
| `edgartools-dev-warehouse` | `Dockerfile` | source copy on warehouse deps | warehouse ECS tasks |
| `edgartools-dev-mdm-deps` | `Dockerfile.mdm-deps` | locked `.[s3,mdm-runtime]` deps via `uv`; no API/admin packages | MDM Step Functions dependency base image |
| `edgartools-dev-mdm` | `Dockerfile.mdm-neo4j` | source copy on MDM deps | MDM ECS tasks/API |

**Tagging strategy**

| Tag | Meaning |
|-----|---------|
| `:dev` | Mutable latest dev image |
| `:sha-<hash>` | Immutable rollback/audit image |
| `:prod` | Manually promoted production image |

**Manual AWS build and deploy — complete recipe (macOS Colima)**

CI (GitHub Actions `deploy.yml`, the "Deploy" workflow — `build-images.yml`
no longer exists) builds and pushes the DEV images automatically on every push
to `main` in ~30-45s via buildx registry cache, retagging `:dev` each time.
It does NOT promote to the prod ECR repos or register task definitions — prod
promotion (docker tag/push to `edgartools-prod-*` + `deploy-aws-application.sh`)
is still manual. Use the steps below for prod promotion, ad-hoc builds, or when
CI is unavailable; for a dev image of current `main`, prefer CI's digest
(`gh run list --workflow deploy.yml`) over rebuilding locally.

```bash
# 1. Start Colima and point Docker CLI at it (do once per terminal session).
colima start
export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock

# 2. Authenticate to ECR (token valid for 12 h).
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    690839588395.dkr.ecr.us-east-1.amazonaws.com

# NOTE: ECR repositories must have MUTABLE tags for :dev to be overwritten.
# If you see "tag is immutable" on push, run once per affected repo:
#   aws ecr put-image-tag-mutability --region us-east-1 \
#     --repository-name edgartools-dev-warehouse --image-tag-mutability MUTABLE
#   aws ecr put-image-tag-mutability --region us-east-1 \
#     --repository-name edgartools-dev-mdm --image-tag-mutability MUTABLE

# 3a. Build and push the warehouse image.
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-warehouse \
  --role warehouse \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# 3b. Build and push the MDM image (when edgar_warehouse/mdm/** changed).
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-mdm \
  --role mdm \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# 4. Capture the digest refs that step 3 printed (used for deploy).
WAREHOUSE_REF=$(aws ecr describe-images \
  --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageDigest" \
  --output text | xargs -I{} echo "690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-warehouse@{}")
MDM_REF=$(aws ecr describe-images \
  --region us-east-1 \
  --repository-name edgartools-dev-mdm \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageDigest" \
  --output text | xargs -I{} echo "690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-mdm@{}")

# 5. Deploy ECS task definitions and Step Functions state machines.
bash infra/scripts/deploy-aws-application.sh \
  --env dev \
  --skip-build \
  --image-ref "$WAREHOUSE_REF" \
  --mdm-image-ref "$MDM_REF" \
  --enable-mdm
```

**If publish-warehouse-image.sh fails with a cache layer error (Colima cache corruption)**

```bash
# Look up current deps tags from ECR (avoids stale hardcoded values)
WH_DEPS=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-warehouse-deps \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]" --output text)
MDM_DEPS=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-mdm-deps \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]" --output text)

ECR="690839588395.dkr.ecr.us-east-1.amazonaws.com"
SHA_TAG="sha-$(git rev-parse --short=12 HEAD)"

# Rebuild warehouse directly
docker pull "${ECR}/edgartools-dev-warehouse-deps:${WH_DEPS}"
docker build --platform linux/amd64 \
  --build-arg "DEPENDENCY_IMAGE=${ECR}/edgartools-dev-warehouse-deps:${WH_DEPS}" \
  -f Dockerfile -t "${ECR}/edgartools-dev-warehouse:${SHA_TAG}" -t "${ECR}/edgartools-dev-warehouse:dev" .
docker push "${ECR}/edgartools-dev-warehouse:${SHA_TAG}"
docker push "${ECR}/edgartools-dev-warehouse:dev"

# Rebuild MDM directly
docker pull "${ECR}/edgartools-dev-mdm-deps:${MDM_DEPS}"
docker build --platform linux/amd64 \
  --build-arg "DEPENDENCY_IMAGE=${ECR}/edgartools-dev-mdm-deps:${MDM_DEPS}" \
  -f Dockerfile.mdm-neo4j -t "${ECR}/edgartools-dev-mdm:${SHA_TAG}" -t "${ECR}/edgartools-dev-mdm:dev" .
docker push "${ECR}/edgartools-dev-mdm:${SHA_TAG}"
docker push "${ECR}/edgartools-dev-mdm:dev"
```

**When to rebuild which image**

| Changed paths | Rebuild |
|---------------|---------|
| `edgar_warehouse/**` (excluding `edgar_warehouse/mdm/`) | warehouse only |
| `edgar_warehouse/mdm/**` | MDM only |
| Both (e.g. `orchestrator.py` + `mdm/cli.py`) | both |
| `Dockerfile` / `Dockerfile.warehouse-deps` | warehouse (+ deps if lock changed) |
| `Dockerfile.mdm-neo4j` / `Dockerfile.mdm-deps` | MDM (+ deps if lock changed) |
| `uv.lock` | deps images for both — run without `--skip-build` |

**Clean up local images before a build (run this first every time)**

Colima accumulates stale images fast — old SHA tags, debug tags, superseded deps layers. Clean before building to avoid cache confusion and reclaim disk.

```bash
export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock

# 1. Show what's on disk
docker system df
docker images --format "{{.Repository}}:{{.Tag}}\t{{.Size}}"

# 2. Remove dangling (untagged) images and unused build cache
docker image prune -f
docker builder prune -f

# 3. Remove old named images — keep only :dev and the latest :sha-* per repo.
#    List old tags from the output above and delete explicitly:
ECR="690839588395.dkr.ecr.us-east-1.amazonaws.com"
docker rmi \
  "${ECR}/edgartools-dev-warehouse:sha-<old>" \
  "${ECR}/edgartools-dev-mdm:sha-<old>" \
  "${ECR}/edgartools-dev-warehouse-deps:deps-<old>" \
  # ... add any debug/ad-hoc tags (routerfix-*, hydratefix-*, etc.)

# 4. Nuclear option — wipe everything (forces full re-pull of base + deps on next build)
docker system prune -af   # WARNING: removes ALL local images, not just ours
```

**What to keep:**
- `:dev` tag for each repo — used as build cache source (`--cache-from-tag dev`)
- Latest `:sha-<hash>` per repo — rollback anchor
- `:deps-<hash>` for warehouse-deps and mdm-deps — slow to rebuild; only remove if `uv.lock` changed
- `public.ecr.aws/docker/library/python:3.12-slim-bookworm` — base layer cache

**Rollback to a previous SHA**

```bash
ECR=<account>.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-warehouse
SHA=sha-abc1234
docker pull $ECR:$SHA
docker tag  $ECR:$SHA $ECR:dev
docker push $ECR:dev
```

## Key Large Files (Read in Chunks)

These files exceed 30 KB. When modifying them, read section by section rather than all at once:

| File | Size | Contents |
|------|------|----------|
| `edgar_warehouse/runtime.py` | ~92 KB | Core ETL loop, form dispatch, S3 writes |
| `edgar_warehouse/silver.py` | ~78 KB | Record cleaning and transformation logic |
| `edgar_warehouse/gold.py` | ~39 KB | Python-side gold aggregations |

## Setup

See `docs/runbook.md` for end-to-end environment setup including AWS credentials, Snowflake keypair auth, S3 bucket provisioning, dbt profiles configuration, and first-run bootstrap.

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools directly.

Available gstack skills:

| Skill | Purpose |
|-------|---------|
| `/office-hours` | Async Q&A and coaching sessions |
| `/plan-ceo-review` | CEO-lens plan review |
| `/plan-eng-review` | Engineering-lens plan review |
| `/plan-design-review` | Design-lens plan review |
| `/design-consultation` | Design consultation session |
| `/design-shotgun` | Rapid parallel design exploration |
| `/design-html` | Generate HTML design artifacts |
| `/review` | Code review |
| `/ship` | Ship a change end-to-end |
| `/land-and-deploy` | Land PR and deploy |
| `/canary` | Canary deploy workflow |
| `/benchmark` | Run benchmarks |
| `/browse` | Web browsing (use this for all browsing) |
| `/connect-chrome` | Connect to Chrome for browser automation |
| `/qa` | Full QA pass |
| `/qa-only` | QA without implementation |
| `/design-review` | Design review pass |
| `/setup-browser-cookies` | Configure browser cookies |
| `/setup-deploy` | Configure deploy settings |
| `/setup-gbrain` | Configure gbrain |
| `/retro` | Retrospective |
| `/investigate` | Investigate an issue |
| `/document-release` | Document a release |
| `/document-generate` | Generate documentation |
| `/codex` | Codex integration |
| `/cso` | CSO workflow |
| `/autoplan` | Automated planning |
| `/plan-devex-review` | Developer experience plan review |
| `/devex-review` | Developer experience review |
| `/careful` | Extra-careful execution mode |
| `/freeze` | Freeze a dependency or config |
| `/guard` | Guard a file or section |
| `/unfreeze` | Unfreeze a dependency or config |
| `/gstack-upgrade` | Upgrade gstack |
| `/learn` | Learn about a topic or codebase |

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec

## Agent skills

### Issue tracker

Issues and Wayfinder maps are tracked as local Markdown under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The default five-role triage vocabulary is used. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository using root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.
