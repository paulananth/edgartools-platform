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

Claude, Codex, and Grok may work on this repository independently, but they
must not share an uncoordinated edit surface.

- **HARD RULE: no two runtimes may ever commit to the same branch.** Each
  runtime works on its own dedicated branch. If you find yourself about to
  commit and `git log -1` shows a commit authored by another runtime's
  current work that you did not expect, STOP — do not commit — and ask the
  user how to proceed (e.g. branch off, rebase onto a new branch, or hand
  off).
- **HARD RULE: use a dedicated git worktree per active runtime session,
  not a bare checkout in one shared working directory, whenever more than
  one runtime (or more than one session of the same runtime) may be
  active at the same time.** A bare shared checkout only has *one*
  branch checked out at once — a second session switching that checkout
  disrupts a first session's in-progress work even when nothing is
  actually lost (git preserves the underlying commits/stashes either
  way). Confirmed live 2026-08-21: two concurrent sessions repeatedly
  switched a shared working directory's checked-out branch out from
  under a third, in-progress session — once stashing its uncommitted
  changes, once mid-rebase. Each runtime session should create its own
  worktree (Claude Code: the `EnterWorktree` tool, or plain
  `git worktree add ../<repo>-<topic> <branch>`) and work there instead.
  If you notice your working directory's checked-out branch changed
  unexpectedly mid-session, do not assume anything was lost — check
  `git branch --show-current`, `git reflog`, and that your own
  commits/stash still resolve by name (`git rev-parse <branch>`,
  `git stash list`) before taking any recovery action, and push your own
  branch to `origin` as soon as it's in a good state so it no longer
  depends on the shared working directory's state.
- Branch naming convention: prefix branches with the owning runtime, e.g.
  `claude/<topic>`, `codex/<topic>`, or `grok/<topic>`. Before starting
  work or committing, run `git branch --show-current` — if the current
  branch is prefixed for a *different* runtime (or is a shared branch
  like `main`/`codex/main-sync` that another runtime is actively using),
  create/check out your own branch (in your own worktree) before making
  any commits.
- **HARD RULE: never commit directly to `main`, for any reason, including a
  quick fix or a single-file doc change.** The moment you pick up a ticket or
  issue — before writing any code, before the first edit — create your own
  `<runtime>/<topic>` branch (in your own worktree per the rule above) and
  commit there. Confirmed live 2026-08-28: a Codex session started and
  finished real implementation work for ecs-cost-sizing Ticket 08 (rollback
  registry, CLI, deploy script, tests) as a local, unpushed commit sitting
  directly on `main` in the shared working directory — no branch at all,
  not even a wrongly-prefixed one. It was only caught because a Claude
  session happened to notice local `main` was one commit ahead of
  `origin/main` before pushing anything; had that push happened first, it
  would have put unreviewed work straight on `main` with no branch, no PR,
  and no review gate. Recovered by branching off that commit
  (`codex/ecs-cost-sizing-revision-retirement-gates`), pushing it, then
  hard-resetting local `main` back to `origin/main`. If you ever find
  yourself with uncommitted or committed changes on `main` for ticket/issue
  work, stop, branch off `HEAD` immediately, and reset `main` back to
  `origin/main` before doing anything else.
- Treat current Codex or Grok work as protected unless the user explicitly hands it off.
- Use separate GSD workstream directories under `.planning/workstreams/<name>/`; do not edit another runtime's active workstream files.
- Before editing, run `git status --short` and `git log -1` and inspect
  `.planning/active-workstream` when present.
- Avoid overlapping source files, Terraform roots, generated application JSON, and planning artifacts across runtimes unless the user assigns the same task to both.
- If overlap is unavoidable, stop and ask for an ownership decision instead of merging assumptions.
- Do not overwrite, revert, stage, or commit changes created by another runtime unless explicitly instructed.

## Git/GitHub commit and PR text with backticks

**Never build a `git commit -m`/`gh pr create --body`/`gh pr edit --body` string via an
inline bash heredoc (`"$(cat <<'EOF' ... EOF)"`) when the text contains backticks or code
spans.** Write the message to a scratch file first (e.g. with a file-write tool), then pass
it with `git commit -F <file>` or `gh pr create --body-file <file>` /
`gh pr edit --body-file <file>`.

**Why:** backtick-quoted spans inside the heredoc body (e.g. `` `EDGARTOOLS_PROD.MDM` ``)
have been observed to get interpreted as command substitution in this environment even
with a quoted heredoc delimiter (`<<'EOF'`), which should disable that. The stray commands
mostly fail harmlessly, but their empty output gets silently spliced into the message and
the heredoc terminator itself can leak into the final text — producing a mangled commit
message or PR body that looks fine at a glance. This happened twice in one session (a
commit message, then a PR body) before being caught. File-based input sidesteps the
problem entirely.

## Quick Navigation

| Need | Location |
|------|----------|
| ETL runtime (form parsing, S3 writes) | `edgar_warehouse/application/warehouse_orchestrator.py` (`edgar_warehouse/runtime.py` and `edgar_warehouse/application/command_router.py` are compatibility shims re-exporting from here, not separate implementations) |
| Silver-layer transformations | `edgar_warehouse/silver_store.py` (`edgar_warehouse/silver.py` is a compatibility shim re-exporting `SilverDatabase`, not a second implementation) |
| Source-layer dimensional export (feeds `EDGARTOOLS_SOURCE`, not `EDGARTOOLS_GOLD` — see single-path-per-layer map Ticket 01, which is why this module was renamed off its old "gold_models.py" name) | `edgar_warehouse/serving/source_dimensional_export.py` (`edgar_warehouse/gold.py` is a thin compatibility shim re-exporting it, not a second implementation) |
| Ownership / Form 3-4-5 parser | `edgar_warehouse/parsers/ownership.py` |
| ADV parser (investment advisers) | `edgar_warehouse/parsers/adv.py` |
| CLI entry point | `edgar_warehouse/cli.py` |
| Batch scripts per form type | `scripts/batch/` |
| dbt gold models (23 dynamic tables — the actual gold layer) | `infra/snowflake/dbt/edgartools_gold/models/gold/` |
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
edgar-warehouse CLI  (edgar_warehouse/cli.py -> edgar_warehouse/application/warehouse_orchestrator.py)
      |
      v
S3 Parquet (bronze)
      |
      v
Snowflake EDGARTOOLS_SOURCE  <-- native S3 pull via bootstrap SQL
      |                          (+ a Python-populated dimensional export from
      |                           edgar_warehouse/serving/source_dimensional_export.py, merged
      |                           in here too -- see Quick Navigation above)
      v
Snowflake EDGARTOOLS_SILVER  <-- landing zone + dbt-native collapse
      |                          (silver-snowflake-migration map, in progress:
      |                           real ingestion live in prod; DuckDB/
      |                           silver_store.py is still canonical for most
      |                           consumers until each one's cutover ticket
      |                           lands -- do not assume this is fully cut
      |                           over without checking that map's Decisions
      |                           so far)
      |
      +-------------------------------------------------+
      |                                                  |
      v                                                  v
dbt (infra/snowflake/dbt/edgartools_gold/)      MDM Postgres (Snowflake-hosted, NOT AWS
      |                                          RDS -- see "MDM database" note below)
      v                                          entity resolution: edgar_warehouse/mdm/
EDGARTOOLS_GOLD  (23 dynamic tables)              ("mdm run", 6 entity types)
      |                                                  |
      v                                       +----------+-----------+
Streamlit dashboard                            |                      |
(infra/snowflake/streamlit/                    v                      v
 OR examples/dashboard/)              Snowflake                Snowflake
                                       NEO4J_GRAPH_MIGRATION    MDM mirror schema
                                       schema -- Neo4j Graph    ("mdm export",
                                       Analytics Native App,    edgar_warehouse/
                                       NOT an external Neo4j    mdm/export.py)
                                       ("mdm sync-graph" /
                                       "mdm verify-graph" --
                                       see "Graph storage"
                                       note below)
                                             |
                                             v
                                       Operator MDM/graph review
                                       dashboard
                                       (examples/mdm_graph_dashboard/)
```

MDM reads from silver (today: mostly DuckDB `silver_store.py`; migrating to
`EDGARTOOLS_SILVER`, same in-progress caveat as above) and resolves entities
independently of the gold/dbt path — the two branches above run in parallel,
not in sequence. See "Graph storage" and "MDM database" notes further below
for what each Snowflake-hosted piece actually is, since both names ("Neo4j",
"Postgres mirror") suggest external services that don't exist here.

## ECS cost-sizing conclusions (Ticket 28, resolved 2026-08-30)

Treat ECS sizing as validated-output economics, not a utilization-only
exercise. Low memory, an exit code of zero, or a Step Functions `SUCCEEDED`
status does not prove that a cheaper profile produced the same complete,
recoverable, idempotent result.

Ticket 28 ran three current-image `mdm.residual_security` candidates on
`mdm-medium:203` and a current-image control on `mdm-large:137`. The candidate
runs each passed their execution-local correctness and identity-parity checks,
with worst memory p95 ranging from 9.34% to 9.84%. That apparent headroom did
**not** justify promotion:

- Every sequential rerun added the same 65 active `IS_INSIDER` and 1,349
  active `HOLDS` relationships. Cross-run idempotency therefore failed.
- The candidate runs progressively filled the shared 100,000-row
  `COMPANY_HOLDS` target, while the later control found it full and inserted
  zero rows. Candidate and control did not process the same record funnel, so
  their end-to-end duration and cost were not comparable.
- On the independently equal-work `MdmSecurities` stage, candidate p95 was
  3,307.583 seconds versus 2,825.220 seconds on large: 17.07% slower.
- Mean candidate cost looked 10.92% lower, but median and p95 improvements were
  only 2.86% and 1.78%; none can approve a downgrade after the idempotency and
  funnel failures. Recovery parity also remained unproven because no
  qualifying run failed or retried.

The fail-closed decision is to keep `mdm-large` as the residual-security
operational profile. Do not change production references, retire the large
definition, start a sizing bake window, or infer that `mdm-small` is safe from
this cohort. A future reconsideration needs isolated or restorable input plus
the Ticket 30 run-bound relationship ledger so the candidate and control see
the same input envelope.

Separately, the current-image unbounded `sync-graph` canary on `mdm-large`
passed its execution-local gates: 226,197 nodes, 621,201 edges, 32.190 seconds
of command time, and about $0.00285 of estimated on-demand compute. That result
accepts the unbounded large-profile sync route; it does not approve the
residual-security downgrade.

Required promotion gates remain: repeated current-image candidates, a matched
control, exact correctness/completeness/identity parity, recovery and cross-run
idempotency, candidate p95 no more than 5% slower, and at least 10% lower cost
per successful validated output. Candidate and control must not execute in
parallel against the same mutable MDM state. The separate
`.scratch/ecs-parallel-runs/` map permits residual-pipeline parallelism only in
two bounded dependency-safe waves, with a disposable success/failure canary
before implementation or production rollout.

Canonical analysis and immutable evidence:

- `.scratch/ecs-cost-sizing/issues/28-run-mdm-residual-security-medium-canaries-and-unbounded-graph-sync-canary.md`
- `.scratch/ecs-cost-sizing/evidence/ticket28/`
- `.scratch/ecs-parallel-runs/map.md`

## Data Layer Definitions

| Layer | Location | Description |
|-------|----------|-------------|
| **Bronze** | S3 (`s3://<bucket>/`) | Raw Parquet files written by `edgar-warehouse`. One file per filing/entity, partitioned by form type and date. Never mutated. |
| **Source** | Snowflake `EDGARTOOLS_SOURCE` | External stage + tables auto-refreshed from S3 via Snowflake native S3 pull (bootstrap SQL), plus a Python-built dimensional export (`edgar_warehouse/serving/source_dimensional_export.py`) merged in via `LOAD_EXPORTS_FOR_RUN`. Read-only raw layer. |
| **Silver** | `edgar_warehouse/silver_store.py` (local DuckDB, canonical today for most consumers) migrating to Snowflake `EDGARTOOLS_SILVER` (landing zone + dbt collapse, real ingestion already live) | Cleaned, typed, deduplicated records. Mid-migration as of this writing — see `.scratch/silver-snowflake-migration/map.md` for exactly which consumers have cut over vs. still read DuckDB; do not assume either store is authoritative without checking there first. |
| **Gold** | `EDGARTOOLS_GOLD` (23 dbt dynamic tables) | Business-ready tables, e.g. `company`, `ownership_holdings`, `ownership_activity`, `filing_detail`, `filing_activity`, `adviser_disclosures`, `adviser_offices`, `private_funds`, `ticker_reference`, `edgartools_gold_status`, plus 13 more added since this table was first written (`accounting_flags`, `adv_fund_count_reconciliation`, `consensus_estimates`, `earnings_calendar`, `earnings_releases`, `executive_records`, `financial_derived`, `financial_factors`, `financial_facts`, `guidance_facts`, `institutional_holdings`, `mdm_company`, `transcript_events`) — see `infra/snowflake/dbt/edgartools_gold/models/gold/` for the current, authoritative list rather than trusting this count to stay accurate. Refreshed on a Snowflake-managed schedule. |

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

## Daily accession-expansion 5-whys (resolved in code 2026-07-31; RC run pending)

**Problem:** A recurring daily run expanded 3,082 index-impacted CIKs into 148,524
historical artifact candidates, ran for 13h20m, opened its circuit, and still reported
the warehouse task as successful after abandoning candidates.

1. Daily-index discovery retained impacted CIKs but discarded the exact accession union.
2. Refreshing each impacted CIK's submissions metadata returned years of `recent` and
   pagination accessions, not only filings from the daily window.
3. Configured-form selection consumed that historical set, so a bounded CIK input did
   not imply a bounded artifact input.
4. The artifact loop had no assertion tying selected candidates back to the daily index.
5. Exhausted retries and an opened circuit were treated as partial metrics rather than
   command failures, allowing silver publication and downstream work to continue.

**Resolution:** Recurring `daily-incremental` defaults to a seven-calendar-day boundary,
revalidates those small SEC index catalogs, carries their exact accession union and digest
through submissions refresh, intersects configured-form selection with that union, and
fails closed on expansion, retry exhaustion, or an opened circuit. This scheduled index
revalidation is a narrow freshness operation, not an artifact-repair override: immutable
bronze conflict handling remains enforced, while filing artifacts still skip captured
objects unless an operator explicitly supplies `--force`. Historical discovery remains
unchanged for explicit `--start-date`/`--end-date` ranges and can also be selected with
`--recurring-index-lookback-days 0`. An immutable-RC production run must still prove the
full chain completes inside the six-hour bound.

## Bronze-recovery-with-no-DB-row 5-whys (resolved 2026-08-10)

**Problem:** Ticket 42's full-universe `load_history` backfill (task 35, `retry4`), window 1/53,
was live-observed re-fetching full document bytes from SEC for accessions whose bronze content
was already durably in S3 from **2026-08-06** — 4 days before the task started. Confirmed
systemic (sampled 4 accessions, all re-fetched despite unchanged S3 `LastModified`), not a
one-off.

1. Symptom: `sec_pull_completed` events with real byte payloads for documents whose bronze S3
   object timestamp never changed across the fetch (write layer correctly deduped the write;
   the wasteful part was the read).
2. Why re-fetch content that's already in bronze? `fetch_filing_artifacts`
   (`edgar_warehouse/bronze_filing_artifacts.py`) only treated an accession/document as
   "already loaded" if the **silver DuckDB** already had a `sec_filing_attachment`/
   `sec_raw_object` row for it — never by checking bronze S3 existence directly.
3. Why did silver lack rows for content bronze already had? This task's local silver.duckdb was
   freshly re-hydrated from canonical S3 at task start; canonical had no rows for these
   accessions.
4. Why would bronze have the file but canonical silver not have the row? Bronze S3 writes are
   durable and immediate per-document; silver DB rows only become part of canonical once a run
   reaches its merge/publish step. These Aug-6 bronze objects were almost certainly written by
   an earlier attempt (of this same `load_history` execution, or another command) that captured
   bronze but never got its silver mutations merged back before crashing (OOM) or exiting.
5. **Root cause:** the idempotency check was keyed on silver-row state, not bronze-object state,
   so it couldn't distinguish "genuinely never fetched" from "fetched and stored, but the
   bookkeeping that would prove it never survived a crash." This is the mirror image of the
   already-known [ticket 88](.scratch/release-readiness/issues/88-missing-s3-object-for-cached-accession-text-extraction.md)
   gap (DB row present, S3 object missing) — this is the reverse case (S3 object present, DB row
   missing), previously unhandled. Every retry re-paid the full SEC network cost for any
   accession caught in this gap, directly contradicting this file's own "SEC data idempotency"
   policy above.

**Fix:** `fetch_filing_artifacts`'s per-accession bronze-key `find_existing` LIST (ticket 88's
existing mechanism) now always runs when not `force` (previously gated on `existing_rows`, which
is exactly the state that's missing in this bug). The per-document loop checks this LIST (via the
existing `_raw_object_still_present` helper, reused as-is) before dispatching a document to the
real-fetch pool; a match routes to a new `_recover_from_bronze` worker that reads the object back
from S3 (cheap, no SEC rate limit) instead of calling `download_bytes`, and still writes the
`sec_raw_object`/`sec_filing_attachment` DB rows so the retry's own bookkeeping gap is closed
going forward. Gated on a non-empty `existing_bronze_keys` before the check runs at all, so a
genuinely cold accession (nothing under its prefix) doesn't pay the `object_exists` HEAD fallback
— preserving the original gate's cost-avoidance intent for the common case.

**Deliberate behavior change, not just an optimization (weighed with a second-opinion review
before shipping):** in production, `write_immutable_bytes` is the *only* writer to a canonical
bronze document key and enforces content-identity atomically at write time (S3 conditional PUT
with `IfNoneMatch: *`), so "content exists at this key" already implies "this is the one accepted
payload for it." The only way stored content could legitimately differ from what SEC would serve
now is out-of-band SEC-side drift (already characterized as benign and already tolerated
elsewhere in this same pipeline — see "INSTITUTIONAL_HOLDS" ticket 87/93 above: single
trailing-newline drift, isolated per-document, never fatal). This fix means that specific,
already-tolerated drift class is no longer independently re-detected via the no-DB-row path — it
now surfaces as an `artifact_bronze_recovered` event instead of a raised conflict. Two tests were
rewritten (not deleted) to reflect this: `test_partial_failure_immutable_conflict_no_partial_merge`
now runs under `force=True` (bronze-recovery is deliberately gated on `not force`, so an operator
repair run still exercises the genuine `write_immutable_bytes` conflict), and a new
`test_stale_object_with_no_db_row_is_bronze_recovered_not_flagged` documents the new
`force=False` contract explicitly. New coverage:
`tests/unit/test_bronze_recovery_no_db_row.py`. Full suite green: 1474 passed, 4 skipped.
Path-format equality between `StorageLocation.join()` and `find_existing()` (the fix depends on
both producing byte-identical strings) verified live against the real prod bronze bucket before
deploying, not just local tempdir tests.

**Not yet deployed as of this entry** — see task 35's own status for the redeploy + `retry5`
restart this fix was written to unblock.

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

## MDM Snowflake mirror schema lost on cutover 5-whys (resolved 2026-08-09)

**Problem:** Stage 14's `bronze_seed_silver_gold` execution (started 2026-08-08, ran
company/security/person resolution + all 11 relationship types successfully over ~16h)
failed at the `MdmExport` state: `snowflake.connector.errors.ProgrammingError: 002003
(42S02): SQL compilation error: Object 'EDGARTOOLS_PROD.MDM.MDM_ENTITY' does not exist or
not authorized.`

1. Symptom: `mdm export`'s mirror write (`_build_snowflake_mirror_writer`, targets schema
   `MDM` deliberately, distinct from the `EDGARTOOLS_GOLD` golden-record target — see
   `edgar_warehouse/mdm/export.py`'s docstring) failed on its very first MERGE statement.
2. Why? `SHOW SCHEMAS LIKE 'MDM' IN DATABASE EDGARTOOLS_PROD` showed the schema exists but
   was created **2026-08-07**, owned by `ACCOUNTADMIN`, with **zero tables** —
   `docs/prod-mdm-snowflake-graph-first-load.md` documents a first-time load of 19 tables
   completed 2026-06-22, but that load is gone.
3. Why is it gone? That 2026-06-22 first-time load was a one-off, uncommitted manual shell
   session (per the runbook's own "non-printing shell process" language) — it had no
   script. When the platform's Snowflake account was rebuilt for this go-live cutover
   (Stages 1–13, all Terraform/scripted), every other piece re-provisioned automatically,
   but this step had nothing to re-run.
4. Why did the role even matter? A second, independent gap: `EDGARTOOLS_PROD_LOADER` (the
   role `mdm export`'s mirror writer actually authenticates as, per the
   `MDM_SNOWFLAKE_SECRET_JSON` secret's `ROLE` field) had **zero grants** on the MDM schema
   even before checking table existence — `docs/prod-mdm-snowflake-graph-first-load.md`'s
   "Required Production Objects" grants were only ever written for
   `EDGARTOOLS_PROD_DEPLOYER`, and nothing carried them over when the export path was
   standardized onto `EDGARTOOLS_PROD_LOADER` (see the manifest-pipeline-ownership incident
   above for that same standardization).
5. **Root cause:** the MDM Snowflake mirror bootstrap (schema + 19 tables + grants to the
   correct role) was documented in prose but never captured as a committed, re-runnable
   script — so it silently did not survive the account cutover, unlike every Terraform- or
   bootstrap-SQL-backed piece of the same cutover.

**Resolution:** wrote `infra/scripts/generate_mdm_mirror_ddl.py`, which reflects the schema
straight from `edgar_warehouse.mdm.database`'s SQLAlchemy models (the same models the
Postgres MDM instance is built from) for exactly the 19 tables in
`edgar_warehouse.mdm.migrations.runtime.MDM_TABLES`, and emits `CREATE TABLE IF NOT EXISTS`
DDL (`NOW()` defaults rewritten to `CURRENT_TIMESTAMP()` — Snowflake rejects `NOW()` in a
column `DEFAULT` clause specifically, "Unknown functions NOW, NOW, NOW", even though `NOW()`
works fine as an ordinary function call) plus additive grants
(`GRANT SELECT, INSERT, UPDATE, DELETE ON ALL/FUTURE TABLES ... TO ROLE EDGARTOOLS_PROD_LOADER`
— deliberately not `GRANT OWNERSHIP ... REVOKE CURRENT GRANTS`, see the
manifest-pipeline-ownership incident for why that pattern silently strips unrelated grants).
Output committed as `infra/snowflake/sql/bootstrap/09_mdm_mirror_schema.sql`. Applied live
2026-08-09: 19 tables created, `EDGARTOOLS_PROD_LOADER` granted schema USAGE +
current/future SELECT/INSERT/UPDATE/DELETE; a manual one-off `mdm export` ECS task confirmed
the fix. `docs/prod-mdm-snowflake-graph-first-load.md` updated to point at the script instead
of a lost manual session, and to correct the stale `EDGARTOOLS_PROD_DEPLOYER` role reference.

**Lesson:** any provisioning step that isn't Terraform or a committed script does not
survive an account rebuild, however carefully it was documented in prose — "run this once"
in a runbook needs a script next to it, not just a description of what an operator did.

**Follow-up (2026-08-09, same day):** completing Stage 14 past this fix hit an identical
failure one step later — `mdm sync-graph` against `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`
(the graph destination schema, also never re-provisioned after the cutover), same root
cause, same missing-script pattern. Two distinct grants were needed for
`EDGARTOOLS_PROD_LOADER`, not one: schema-level USAGE/CREATE TABLE/CREATE VIEW/DML (same
shape as the MDM fix above) *and* `CREATE SCHEMA` on the parent `EDGARTOOLS_PROD` database
itself — a real Snowflake gotcha: `CREATE SCHEMA IF NOT EXISTS` evaluates the `CREATE
SCHEMA` privilege *before* checking whether the schema already exists, so pre-creating the
schema as `ACCOUNTADMIN` doesn't let a role without that database-level grant skip the
check. Also corrected a second doc inaccuracy: `mdm sync-graph`/`mdm verify-graph` were
documented as running under `EDGARTOOLS_PROD_DEPLOYER` — they don't; both read the exact
same `MDM_SNOWFLAKE_SECRET_JSON` secret as `mdm export`, so all three commands share one
runtime role (`EDGARTOOLS_PROD_LOADER`), not a split pair. Fixed the same way: committed
`infra/snowflake/sql/bootstrap/10_graph_schema.sql` (idempotent, same shape as
`09_mdm_mirror_schema.sql`) and re-applied the already-idempotent
`infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`. **Sharper lesson:** when one
stage's provisioning turns out to have been an uncommitted manual step, assume every later
stage in the same pipeline family is too until proven otherwise — check the whole chain
before declaring victory on the first fix.

**Follow-up (2026-08-19): a third, still-different failure at the same `MdmExport`
state**, ten days later — a fresh `bronze_seed_silver_gold` execution reached `MdmExport`
successfully this time (both fixes above held) and failed with
`ProgrammingError: Object 'EDGARTOOLS_PROD.MDM.MDM_COMPANY_ENTITY' does not exist or not
authorized` — a *third* distinct object, not one of the 19 mirror tables or the graph
schema fixed above.

1. Symptom: `mdm export`'s **default** writer (`_build_snowflake_writer()` in
   `edgar_warehouse/mdm/cli.py`, meant to target `EDGARTOOLS_GOLD` — see `export.py`'s
   `DOMAIN_TO_TABLE`, which lists the 5 golden-record export targets `MDM_COMPANY_ENTITY`/
   `MDM_ADVISER`/`MDM_PERSON`/`MDM_SECURITY`/`MDM_FUND`) tried to write into schema `MDM`
   instead — confirmed live: all 5 tables exist and are correctly defined in
   `EDGARTOOLS_GOLD` (`07_mdm_export_targets.sql` was applied; 0 rows each, since export has
   never once succeeded past this point).
2. Why did the default writer resolve to schema `MDM`? `SnowflakeConnectionSettings.from_env()`
   defaults schema to `"EDGARTOOLS_GOLD"` only when the secret's `MDM_SNOWFLAKE_SCHEMA` key is
   absent/empty — the live secret (`edgartools-prod/mdm/snowflake`) had it explicitly set to
   `"MDM"`, overriding the default for every consumer of that secret, including the default
   writer.
3. Why was it set to `MDM`? `mdm export`'s **separate** mirror writer
   (`_build_snowflake_mirror_writer()`) deliberately hardcodes `schema="MDM"` in Python — it
   does *not* read `MDM_SNOWFLAKE_SCHEMA` from the secret at all. `mdm sync-graph`/
   `verify-graph` (`snowflake_graph.py`) also don't read it — they fully-qualify every
   reference via their own `DEFAULT_TARGET_SCHEMA`/`DEFAULT_MDM_SCHEMA` constants, never
   relying on the connection's default schema. So **nothing in the codebase actually needs**
   `MDM_SNOWFLAKE_SCHEMA=MDM` — the only real consumer of that secret field is the default
   writer, which needs it to be `EDGARTOOLS_GOLD`.
4. Why did the secret have the wrong value then? `bootstrap-prod-mdm.sh` (the script that
   provisions this secret) correctly sets it to `$GOLD_SCHEMA` (default `"EDGARTOOLS_GOLD"`,
   line ~341) — the live value had drifted from what the script would produce, almost
   certainly overwritten by a manual `put-secret-value` during the 2026-08-09 incident above
   (the two "MDM"-schema fixes that day likely prompted someone to point the whole secret at
   `MDM` without noticing the default writer shares it).
5. **Root cause:** one secret field (`MDM_SNOWFLAKE_SCHEMA`) is a de facto shared default for
   two writers with genuinely different target schemas, and only one of the two
   (`_build_snowflake_mirror_writer`) protects itself with its own hardcoded override — the
   other silently inherits whatever the secret says. A manual secret edit made for one
   consumer's benefit silently broke the other, with no test or grant check to catch it
   (this writer only ever runs against real Snowflake, so nothing in the test suite exercises
   its schema resolution).

**Fix:** corrected the live secret's `MDM_SNOWFLAKE_SCHEMA` back to `EDGARTOOLS_GOLD` via
`put-secret-value` (preserving every other field byte-for-byte), matching what
`bootstrap-prod-mdm.sh` already produces — a config fix, not a code or DDL change. No
image rebuild needed for this specific fix (ECS injects secrets at task launch), though a
`bronze_seed_silver_gold` re-run is still needed to confirm live. **Not yet re-verified**
as of this entry.

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

## Shard-publish promotion-race 5-whys (fixed, not yet deployed, 2026-08-19)

**Problem:** three separate `bronze_seed_silver_gold` prod executions failed
on an identical `PromotionConflictError` for `shard-0.duckdb`, the third of
which aborted a `ToleratedFailurePercentage: 0` release outright on one lost
race.

1. Symptom: `_publish_shard_if_remote` (`edgar_warehouse/application/
   warehouse_orchestrator.py`) raised `PromotionConflictError` from
   `stage_and_promote`, and nothing caught it — the whole `BatchSilver`
   batch failed.
2. Why does a concurrent writer land on the same shard? `BatchSilver`
   (the Distributed Map driving this stage) runs `MaxConcurrency: 20`
   against only **4** shards total — multiple concurrent batches routinely
   hash to the same shard index, so "concurrent writer" isn't an edge case,
   it's the common case at this concurrency ratio.
3. Why did the function not handle that? It assumed, undocumented, "each
   shard is owned by exactly one writer" and both blindly overwrote the
   remote object (no merge) and never retried on conflict — the same false
   assumption the monolith `silver.duckdb` path already had and already
   fixed once, in PR #222 (commit `a1f5d37b`), for the identical reason.
4. Why wasn't the shard path fixed at the same time as the monolith path?
   No evidence found of a deliberate decision — the shard-publish function
   was added later and the monolith's fix was never ported over, so the
   same bug shipped a second time on a structurally identical write path.
5. **Root cause:** the shard-publish path silently diverged from its own
   sibling's already-proven concurrency-safety pattern, and nothing
   (test, lint, or doc) enforced that the two stay in sync.

**Fix:** `_publish_shard_if_remote` now merges the local candidate into
canonical via `merge_candidate_into_canonical` (same function the monolith
uses) instead of overwriting; a new `_publish_shard_if_remote_with_retry`
wrapper retries the whole read-merge-stage-promote cycle on
`PromotionConflictError`, mirroring `_publish_silver_database_with_retry`
exactly (same `WAREHOUSE_PUBLISH_CONFLICT_ATTEMPTS`/`_RETRY_BASE_SECONDS`/
`_RETRY_MAX_SECONDS` env vars, unbounded by default). The real call site
(`_execute_warehouse_bronze_capture`'s shard branch) now uses the retry
wrapper.

**Two risks surfaced by review, not fully closed:**
- The merge branch's extra read/write round trips add real memory pressure
  on top of a Fargate profile (`bootstrap-batch`'s `medium`, 4096MB) that
  live evidence from this same incident showed was *already* marginal —
  2 of the failed batch's 4 retry attempts were `OutOfMemoryError`
  (`ExitCode: 137`) against an 823MB shard, even under the old, simpler
  no-merge code. Mitigated (not eliminated) by porting the monolith's
  skip-if-unchanged fingerprint check (release-readiness ticket 79) to the
  shard path, so a shard provably unchanged since hydration skips the
  merge/S3 cycle entirely.
- The retry wrapper is unbounded by default and each retry re-runs the
  *full* merge branch — on a hot shard with real conflicting writes (not
  the skip-path's zero-write case), per-attempt memory/time cost
  multiplies by attempt count. This is the most plausible way the fix
  still reproduces the same `ExitCode: 137` even once deployed. Not
  addressed in this pass — logged as an explicit open risk in
  `.scratch/silver-snowflake-migration/issues/12-cutover-mdm-sharded-silver-reader-to-snowflake.md`
  for whoever verifies the real Stage 14 rerun.

Tests: 11 cases in `tests/unit/test_publish_shard_if_remote.py`, including a
real `SilverDatabase`-backed merge test and a two-concurrent-writers
regression test (injects a stale first baseline read to reproduce the
actual race a sequential test can't otherwise trigger). Full suite green.
**Not yet built, pushed, or deployed** as of this entry — see
`.scratch/silver-snowflake-migration/map.md` for status.

## EXCLUDED_OPERATIONAL_TABLES silently dropped on merge 5-whys (fixed, not yet deployed, 2026-08-24)

**Problem:** live during the change-propagation map's Ticket 29 prod dry run,
`load-daily-form-index-for-date 2026-08-21` ran clean at the ECS-task level
(3,719 daily-index rows staged, checkpoint written locally) but its own log
showed `"skipped": true, "tables_merged": []` for the silver-database publish
step. A follow-up `drive-filing-discovery-for-date` run against prod then
failed closed with `checkpoint status='missing'` — canonical genuinely never
received the seed.

1. Symptom: `sec_daily_index_checkpoint`/`stg_daily_index_filing` writes
   never reached canonical `silver.duckdb`, even though the seeding ECS task
   reported success.
2. Why "skipped"? `compute_silver_fingerprint`'s skip-if-unchanged
   optimization (release-readiness ticket 79) only fingerprints
   `PROTECTED_TABLE_REGISTRY` tables. `load-daily-form-index-for-date`'s
   entire write footprint is these two `EXCLUDED_OPERATIONAL_TABLES`
   members, so its fingerprint is *always* identical to hydration's —
   the publish is skipped unconditionally, every single run, forever.
3. Why does fixing the fingerprint alone not fix it? Found while
   implementing that fix: `merge_candidate_into_canonical`'s only
   content-copying loop (`for table_name, policy in
   PROTECTED_TABLE_REGISTRY.items(): ...`) also iterates
   `PROTECTED_TABLE_REGISTRY` exclusively — `EXCLUDED_OPERATIONAL_TABLES`
   tables are used only to satisfy the fail-closed unclassified-table
   check, never actually copied from candidate into the merged output.
4. Why was this never caught? Two independent bugs compounded so the first
   always masked the second — the fingerprint skip fired before the merge
   ever ran, so the merge loop's inability to copy these tables was never
   reached to be observed. `load-daily-form-index-for-date` has zero
   executions in prod prior to this attempt (confirmed via
   `list-executions`), so nothing had ever exercised this path before.
5. **Root cause:** `EXCLUDED_OPERATIONAL_TABLES` conflates two distinct
   concerns under one flag — "safe to skip conflict detection" (true for all
   members: checkpoints/staging have no `authority_column`/business-key
   semantics) and "changes here don't matter for publication" (only true for
   genuine bookkeeping like `pipeline_run`/`sec_sync_run`, false for tables
   like `sec_daily_index_checkpoint` whose content *is* the entire point of
   the command that wrote them). The merge's own documented intent for the
   whole set — "a candidate is always free to overwrite them" — was never
   actually implemented for any excluded table; only the fail-closed guard's
   exemption was.

**Resolution:** new `PUBLICATION_SIGNIFICANT_OPERATIONAL_TABLES` frozenset
(`silver_protection.py`), deliberately scoped to exactly the two tables with
live evidence — `sec_daily_index_checkpoint`, `stg_daily_index_filing` — not
every `EXCLUDED_OPERATIONAL_TABLES` member (widening on suspicion risks
forcing a real merge pass on commands that currently correctly skip one;
`sec_source_checkpoint` has 27,342 rows in prod today and has not been shown
to have the same bug — its live staleness is unaudited, logged as an open
follow-up in
[Ticket 31](.scratch/change-propagation/issues/31-excluded-operational-tables-never-reach-canonical-silver.md)
rather than assumed). `compute_silver_fingerprint` now fingerprints
`PROTECTED_TABLE_REGISTRY | PUBLICATION_SIGNIFICANT_OPERATIONAL_TABLES`.
`merge_candidate_into_canonical` gets a second, separate copying pass for
just these two tables: a blind `DELETE`+`INSERT` overwrite (no
authority-column conflict resolution — these tables have none, that's
*why* they were excluded from the protected loop, not a gap in it), using
explicit named column lists on both sides rather than `SELECT *` (candidate
and canonical could share the same columns in a different physical order;
`SELECT *` maps positionally and would silently write values into the
wrong columns instead of failing loud), and fails closed with a clear
`SilverPublicationError` on any column-set mismatch rather than a raw
DuckDB binder error or a silently dropped column.

Tests: `tests/unit/test_publication_significant_operational_tables.py` (7
cases) locks in both fixes at their own seams plus the inverse for genuine
bookkeeping (`pipeline_run` must stay excluded from both, proving the fix
doesn't over-widen); `test_skip_noop_silver_publish.py` gained one
end-to-end test through `_publish_silver_database_if_remote`. Full repo
suite green (2459 passed, 4 skipped). **Not yet deployed** as of this
entry — see
[Ticket 29](.scratch/change-propagation/issues/29-deploy-and-dry-run-gated-acquisition-path.md)
for the redeploy + re-run of `load-daily-form-index-for-date` /
`drive-filing-discovery-for-date` this fix was written to unblock.

## Relationship-derivation single-threaded tail (fixed, not yet deployed, 2026-08-19)

**Problem:** A live `mdm run --entity-type all` execution (`shard-fix-verify-1787134405`)
ran 5.6+ hours past company/security/person resolution with no sign of finishing.
CloudWatch overlap-counting (same technique used to prove `run_companies`' 16-way
concurrency was genuinely live) showed max concurrently-open SQL calls == 1 during this
tail — strictly sequential, unlike resolution's proven 16-way concurrency.

1. Symptom: the tail of `mdm run` (writing `mdm_relationship_instance` rows) ran
   single-threaded with no observable overlap in its Postgres calls.
2. Why single-threaded? `derive_relationships()`'s outer loop ran all 11
   `RELATIONSHIP_TYPES` sequentially on one shared session — no worker pool at all,
   unlike `run_companies`/`run_securities`/`run_persons` (mdm-run-throughput map, already
   fixed).
3. Why was each type itself slow, even alone? `GraphSyncEngine.ensure_relationship`
   pays one existing-version SELECT plus one `session.flush()` round trip **per
   relationship row** unless the caller primed the type first (`prime_relationship_type`
   + deferred flush) — only `_derive_manages_fund` did that; the other 10 types paid it
   per row.
4. Why per-row on top of that? Several types (`IS_INSIDER`, `HOLDS`,
   `HAS_PARENT_COMPANY`, `EMPLOYED_BY`, `AUDITED_BY`) also re-queried MdmPerson/MdmCompany
   fresh for every row via `_person_entity_id`/`_company_entity_id`, even though the same
   CIK repeats heavily (an issuer's CIK repeats across every one of its own insiders'
   rows; `INSTITUTIONAL_HOLDS`' `_ensure_thirteenf_manager` re-queried the same manager
   CIK on every one of its thousands of holding rows).
5. **Root cause:** the bulk-prefetch + deferred-flush pattern that fixed this exact
   shape for `MANAGES_FUND` and for `run_companies`/`run_securities`/`run_persons`
   (mdm-run-throughput map) was never ported to the other 10 relationship types or to
   the type-level loop itself — the same "sibling path silently diverged" shape as the
   shard-publish incident above, just in a different subsystem.

**Fix:** `_derive_relationship_type` now primes + defers flush for every type uniformly
(idempotent — `GraphSyncEngine.prime_relationship_type` is now a no-op on an
already-primed type, so this composes safely with `_derive_manages_fund`'s own internal
call). `_derive_is_insider`/`_derive_holds`/`_derive_has_parent_company`/
`_derive_employed_by`/`_derive_audited_by` now bulk-prefetch their per-row entity-ID
lookups once per batch instead of once per row (mirroring the bulk-prefetch pattern
`_derive_company_holds`/`_derive_manages_fund` already used). `_derive_institutional_holds`
memoizes `_ensure_thirteenf_manager` per unique CIK within a batch (safe: no per-call
side effect beyond the first) — deliberately did **not** memoize `_ensure_security_by_cusip`,
which opportunistically backfills `security_class` on every call, so a later row with a
non-NULL value can still backfill an earlier NULL one. `derive_relationships()` itself now
runs each relationship *type* on its own worker thread/session (bounded by
`MDM_RELATIONSHIP_CONCURRENCY`, default 4), mirroring `run_companies`' proven
per-row-worker-session pattern — falls back to 1 worker under SQLite (same StaticPool
guard `run_companies` already uses). Safe because every `_derive_*` method only ever
writes rows scoped to its own `rel_type_id` (`relationship_id` is a deterministic hash of
`(rel_type_id, source, target)` — no cross-type collision possible), and any stub entity
one type creates is read by another only as a best-effort, already-idempotent lookup that
quietly retries on the next `mdm run` if unresolved this run (the same fallback the old
strictly-sequential ordering already relied on).

**Second, independent bug found while implementing this** (not the original target, but a
correctness gap this fix would have newly exposed): `edgar_warehouse/silver_store.py`'s
`SilverDatabase.fetch()` and `edgar_warehouse/silver_support/sharded_reader.py`'s
`ShardedSilverReader.fetch()` both `execute()` then read back `self._conn.description` on
one shared DuckDB `Connection` — safe only because every existing caller was
single-threaded. `derive_relationships()`'s new worker threads call `.fetch()` on the
*same shared reader instance* concurrently, which would have raced two threads'
`execute()`/`description` reads against each other. Fixed with a `threading.Lock` around
each `fetch()` body (scoped to `.fetch()` only — the many other `SilverDatabase` write
methods are still only ever called from the single-threaded bronze/silver capture path,
so this adds no contention there). `SnowflakeSilverReader.fetch()` (the third
implementation of this duck-typed interface) was already safe — it opens a fresh cursor
per call.

Tests: `tests/mdm/test_pipeline_relationships.py`'s new
`TestRelationshipDeriveBoundedRoundTrips` (IS_INSIDER query-count stays flat as row count
grows, mirroring the existing `test_manages_fund_uses_bounded_database_round_trips`/
`test_company_holds_batches_entity_id_lookups_across_rows` precedents) and
`TestRelationshipTypesConcurrency` (two relationship types derived on genuinely concurrent
worker sessions against a real multi-connection SQLite engine — same direct-drive pattern
`test_run_companies_concurrency.py` uses to prove concurrency safety without going through
the dialect-gated entry point — plus an end-to-end sanity check that the SQLite-forced
single-worker path is still behaviorally identical to the old sequential loop). Full
repo suite green: 2225 passed, 4 skipped (same 2 pre-existing, unrelated failures as
every prior entry in this file). **Not yet deployed** as of this entry — no live
before/after timing has been captured; the CloudWatch overlap-counting method above is
the way to get one once this ships.

## MDM Postgres migration-011 schema drift blocking every mdm run (resolved 2026-08-20 — see correction below; the 2026-08-19 "resolved" claim was itself never actually verified)

**Problem:** the `relderiv-fix-verify-1787165186` execution (verifying the
relationship-derivation-concurrency fix above) failed at `MdmRun` — every
`mdm run --entity-type all` attempt exited 1 after exhausting retries.
Discovered while investigating a separate, adjacent symptom: the
mdm-ahead-of-silver backfill sweep (`backfill-mdm-entity-ids`) showed 0 of
5,752 `sec_company` rows resolved in `EDGARTOOLS_PROD.EDGARTOOLS_SILVER`
despite that feature (Phases A/B, `.scratch/mdm-ahead-of-silver/map.md`)
being fully implemented, tested, and wired into prod's `daily_incremental`/
`bootstrap` state machines for days.

1. Symptom: the ECS task's logs showed every query against `mdm_source_ref`
   failing with Postgres `UndefinedColumn` — 61 straight `mdm_sql_failed`
   events, same `statement_hash`, all selecting (among other columns)
   `mdm_source_ref.source_content_hash`.
2. Why is that column undefined? It doesn't exist on the live table, but the
   SQLAlchemy `MdmSourceRef` model declares it
   (`edgar_warehouse/mdm/database.py:216`) — `select()` on the mapped class
   pulls every mapped column, so any query touching this table fails
   outright, not just ones that need the new field.
3. Why does the model have a column the table doesn't? Commit `7ffda2d7`
   ("skip-if-unchanged fast path for run_companies", single-path-per-layer
   Ticket 03) added `source_content_hash` to the model **that same day**
   (2026-08-19 12:06 ET) — a few hours before this failure — along with a
   proper migration file, `edgar_warehouse/mdm/migrations/
   011_source_ref_content_hash.sql` (`ADD COLUMN IF NOT EXISTS`).
4. Why wasn't the migration applied? `migrate()`
   (`edgar_warehouse/mdm/migrations/runtime.py`) runs `011` as part of its
   sequence, but `migrate()` only executes via an explicit `mdm migrate`
   ECS/Step-Functions invocation (`edgartools-prod-mdm-migrate`) — nothing
   triggers it automatically on deploy or on `mdm run` startup. No `mdm
   migrate` execution had run against prod since `7ffda2d7` shipped.
5. **Root cause:** same class of gap as "MDM Snowflake mirror schema lost on
   cutover" above, just on the Postgres side this time — a schema migration
   can exist, be correct, and be committed, and still never reach the live
   database, because applying it is a separate manual step nothing enforces.
   The mdm-ahead-of-silver backfill sweep's "0 resolved" reading was a
   downstream symptom: `run_companies` couldn't write/read `mdm_source_ref`
   at all, so the sweep's `MdmSourceRef` lookup had nothing to match against
   — the backfill code itself was never the problem.

**Fix:** ran `edgartools-prod-mdm-migrate` (applies `011_source_ref_content_hash.sql`,
purely additive `ADD COLUMN IF NOT EXISTS`) — succeeded. Re-verified with a
scoped `mdm run --limit 25` (`edgartools-prod-mdm-run`, avoids a full-universe
run's cost) — succeeded, no more `UndefinedColumn` errors. Then ran
`backfill-mdm-entity-ids` as a standalone one-off ECS task (same task
definition/command the `BackfillMdmEntityIds` state in `daily_incremental`/
`bootstrap` already uses, per `deploy-aws-application.sh`) to close the loop
on the original adjacent symptom: resolved 5,752/5,752 pending `sec_company`
rows (`mdm_entity_backfill_completed`, `remaining_by_table.sec_company: 0`),
wrote them to the Snowflake landing export, and confirmed live —
`EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.SEC_COMPANY` shows 5,752 rows
with `mdm_entity_id` populated after `LOAD_SILVER_LANDING_TASK`'s next
5-minute cycle picked up the export. (The downstream collapsed
`EDGARTOOLS_SILVER.SEC_COMPANY` dynamic table has its own separate 6-hour
`target_lag`, pre-existing and unrelated to this fix, so it will reflect
these rows on its own schedule — not re-verified in this pass, and not
needed to confirm the mdm-ahead-of-silver pipeline itself works end-to-end.)

**Lesson:** a same-day ORM/migration-file change with no forcing function to
apply it in prod is a live landmine for every other consumer of that table —
even work (like the relationship-derivation concurrency fix, and the
mdm-ahead-of-silver feature, both unrelated to `7ffda2d7`) that was fully
correct on its own can look broken purely because a sibling change's
migration never ran. When `mdm run` (or any MDM Postgres consumer) fails
with `UndefinedColumn`/`UndefinedTable`, check for an unapplied migration
before assuming the failing code itself is at fault.

**CORRECTION (2026-08-20): the "Fix" above never actually fixed anything —
both of its verification steps were false signals.** Discovered while
investigating a Stage 14 (`bronze_seed_silver_gold`) full-universe rerun
that still failed at `MdmRun` with the identical `UndefinedColumn:
mdm_source_ref.source_content_hash` error, a full day after this section
was first marked resolved.

1. Symptom: `mdm run --entity-type all` still failed with the exact same
   error the original "Fix" claimed to have closed, reproduced twice more
   (once inside Stage 14's real execution, once via a standalone scoped
   `mdm run --limit 5` on the current `edgartools-prod-mdm-medium:178` task
   def) — including immediately after re-running the exact same "Fix"
   command and confirming it reported SUCCEEDED again.
2. Why would the same "successful" fix keep failing to fix anything? Both
   `edgartools-prod-mdm-migrate` (the "Fix" step) and
   `edgartools-prod-mdm-run` (the "Re-verified" step) are individually-named
   state machines that the state-machine-consolidation effort (ticket 02,
   2026-08-10, `.scratch/state-machine-consolidation/issues/
   02-decide-consolidation-mechanism-for-shared-mdm-tail.md`) had already
   superseded with one consolidated `edgartools-prod-mdm-utility` machine
   (`{"mode": "mdm_migrate"}` / `{"mode": "mdm_run"}`) nine days earlier —
   but left `ACTIVE`, un-deleted, called "orphaned but harmless" in that
   ticket's own text.
3. Why does invoking an "orphaned but harmless" machine matter? Both
   orphaned originals are frozen on task-def revisions from an image pushed
   **2026-08-09** (`edgartools-prod-mdm-{small,medium}:149`) — a full day
   *before* commit `7ffda2d7` even added `source_content_hash` to the
   `MdmSourceRef` model or wrote migration 011. `edgartools-prod-mdm-utility`
   was, by contrast, correctly re-registered onto the current `:178`
   revision by every deploy since (confirmed live: `edgartools-prod-mdm-
   small:178`/`edgartools-prod-mdm-medium:178` both resolve to the current
   prod image digest, an ancestor of `85ab9e65`).
4. Why did that make the original "Fix" a false positive? `mdm migrate`'s
   stale 2026-08-09 image doesn't contain `011_source_ref_content_hash.sql`
   in its migration sequence at all (that file didn't exist yet when the
   image was built) — so the orphaned `edgartools-prod-mdm-migrate` ran a
   shorter, older migration list, hit nothing new, and reported SUCCEEDED
   truthfully — for a version of the schema that was never the live problem.
   The real Postgres table was never touched.
5. **Root cause of the false negative too:** the orphaned
   `edgartools-prod-mdm-run`'s equally-stale image predates
   `source_content_hash` being added to the ORM model, so its `SELECT`
   against `mdm_source_ref` never asked for that column in the first place
   — "no `UndefinedColumn` error" was not evidence the migration worked, it
   was evidence the check never exercised the code path being tested. Two
   independent stale-code false signals, both pointing the same wrong
   direction, made the "resolved 2026-08-19" claim look doubly confirmed
   when neither confirmation ever touched current code.

**Real fix:** re-ran the migration via the actually-current
`edgartools-prod-mdm-utility` machine (`{"mode": "mdm_migrate"}`) —
confirmed via direct ECS log inspection that `mdm_source_ref.source_content_hash`
is now queried, updated, and read back successfully with zero
`UndefinedColumn` errors, on a scoped `mdm run --entity-type company --limit
5` task run directly against the current `edgartools-prod-mdm-medium:178`
task def (exit code 0). Migration 011 is now genuinely, durably applied.

**Lesson (sharper than the first pass above):** "the fix succeeded" and "the
verification found no error" are not equivalent to "the fix touched current
code" — when a check can silently run against stale, superseded
infrastructure and still report a clean result, a false positive and a
false negative can both look identical to success.

**Gap closed same-day (2026-08-20):** all 7 orphaned MDM Utility Machine
originals — not just the two that bit this incident — were deleted live in
prod (`.scratch/state-machine-consolidation/issues/
05-delete-orphaned-mdm-utility-machine-originals.md`, resolved): zero
running executions confirmed, fresh rollback snapshots captured, then
`edgartools-prod-mdm-run`/`-backfill-relationships`/`-sync-graph`/
`-verify-graph`/`-counts`/`-migrate`/`-check-connectivity` all deleted.
`edgartools-prod-mdm-utility` (the correct, current consolidated machine)
and every legitimate sibling confirmed untouched. This class of false
signal can no longer recur through these 7 names — there is nothing left
to accidentally invoke.

## SNOWFLAKE_RUN_MANIFEST_TASK / silver-loader OPERATE+SELECT gap 5-whys (resolved 2026-08-22)

**Problem:** After finally getting `bronze_seed_silver_gold`'s "Stage 14" and the standalone "Stage 15"
(`install.sh`'s two `gold-refresh`-adjacent stages) to a real `SUCCEEDED` state, `gold-verify-live`
still reported 19 of 19 checked `EDGARTOOLS_GOLD` tables empty — including `COMPANY`, which should
never be empty once `bronze_seed_silver_gold` has run.

1. Symptom: `gold-verify-live` failing repeatedly, `COMPANY` row count 0, no error surfaced by the
   Step Function or ECS task — everything upstream reported success.
2. Why empty despite success upstream? `SNOWFLAKE_RUN_MANIFEST_TASK`'s `TASK_HISTORY` (checked
   directly, not assumed) showed the task **firing exactly on its 360-minute schedule** but
   **failing every single scheduled run**, going back to at least 2026-08-18:
   `SQL compilation error: OPERATE privilege is required on all upstream Dynamic Tables of
   'EDGARTOOLS_PROD.EDGARTOOLS_GOLD.COMPANY' to perform a manual refresh.` The task's own `state`
   stayed `started` throughout — a "started, on-schedule, silently failing every tick" task gives
   no ambient signal that anything is wrong.
3. Why the OPERATE gap? `COMPANY`'s dbt model (the `dbt-gold-silver-rewiring` map) now reads
   directly from `EDGARTOOLS_SILVER.SEC_COMPANY` via `ref()`, not the old Python-populated
   `EDGARTOOLS_SOURCE` mirror. `08_loader_role.sql` (the "Manifest-pipeline ownership" fix, above)
   only ever granted `EDGARTOOLS_PROD_LOADER` — the role `REFRESH_AFTER_LOAD` runs
   `EXECUTE AS OWNER` under — privileges on `EDGARTOOLS_GOLD`. It was never extended to cover
   `EDGARTOOLS_SILVER`, so every one of `EDGARTOOLS_SILVER`'s 29 dynamic tables sat owned by
   `EDGARTOOLS_PROD_DEPLOYER` with no grant to loader at all.
4. Why did fixing OPERATE alone not fix it? A second, distinct gap surfaced immediately after:
   `SQL access control error: ... Your primary role EDGARTOOLS_PROD_LOADER must have SELECT
   granted on TABLE EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY.` A dynamic table's query runs
   as its *owner* — `OPERATE` lets the owner role refresh the object itself, but the owner role
   separately needs `SELECT` on every object the query text references. Both grants were missing,
   not just one.
5. **Root cause:** the silver-layer migration (dbt-gold-silver-rewiring) introduced a new upstream
   dependency for several gold models without anyone re-checking whether the loader role's existing
   grant surface (scoped to `EDGARTOOLS_GOLD` only, from the earlier ownership incident) still
   covered it — the same "fixed in one place, never ported to the newly-added dependency" shape as
   several other entries in this file (`ShardedSilverReader._TABLES`, the `SeedUniverse` task-profile
   hardcodes). Nothing enforced that a new cross-schema `ref()` edge also needed a matching grant.

**Compounding, unrelated finding along the way:** `install.sh`'s own Stage 15 retry loop
(20 attempts × 60s = ~20 minutes, built to ride out `REFRESH_AFTER_LOAD`'s per-table refresh time)
can **never succeed** as originally written, independent of the grant bug above: the
`ecs-cost-sizing` credit-consumption fix (see below) widened `SNOWFLAKE_RUN_MANIFEST_TASK`'s
schedule `1 min → 15 min → 6 hours` on 2026-08-14, after Stage 15's retry loop was written, and
nobody re-checked the two against each other. A purely passive 20-minute poll can only pass if it
happens to land within minutes of a 6-hourly tick — everywhere else, it always exhausts and fails,
even with zero underlying problem.

**Fix:**
- `infra/snowflake/sql/bootstrap/18_silver_loader_read_grants.sql` (new) grants
  `EDGARTOOLS_<ENV>_LOADER` `OPERATE` + `SELECT` on `ALL` + `FUTURE` dynamic tables in
  `EDGARTOOLS_SILVER` — additive only, no `REVOKE CURRENT GRANTS` (per the manifest-pipeline-
  ownership incident's own lesson). Wired into `install.sh` as a new "Snowflake: loader read
  grants on silver" stage, immediately after the existing loader-role-ownership stage and before
  any gold-refresh stage.
- `install.sh`'s Stage 15 retry loop now fires `EXECUTE TASK EDGARTOOLS_GOLD.SNOWFLAKE_RUN_MANIFEST_TASK`
  manually on every attempt (a call against an empty manifest stream just `SKIP`s harmlessly),
  decoupling this stage from the 6-hour schedule without changing the schedule itself — the
  credit-economy decision stays intact.
- Applied live to `PRJEDJU-QJB05385`: both grants applied, `REFRESH_AFTER_LOAD` re-run directly
  for the stuck `gold-refresh-stage15-1787432984` manifest (its `LOAD_EXPORTS_FOR_RUN` half had
  already succeeded and consumed the stream; only the refresh half was stuck) — all 20 gold tables
  refreshed successfully. `COMPANY` (5,752 rows), `FILING_ACTIVITY`/`FILING_DETAIL` (474,897 rows
  each), `OWNERSHIP_ACTIVITY`/`OWNERSHIP_HOLDINGS` (3 rows each) now populated and confirmed via a
  fresh `gold-verify-live`.

**Not fixed here, separately noted:** `gold-verify-live` still shows 14 tables empty after this
fix. Checked each: most (`FINANCIAL_FACTS`, `SEC_ADV_OFFICE`-derived tables, etc.) have genuinely
empty upstream silver data — the same, already-tracked "6 empty gold tables" gap from the
`snowflake-account-cutover` map's ticket 08 (awaiting task #35's full-universe fundamentals
backfill), just wider in scope than that ticket originally found. One new, real gap:
`TICKER_REFERENCE`'s dbt model was repointed (same `dbt-gold-silver-rewiring` migration) to read
from `EDGARTOOLS_SILVER.SEC_COMPANY_TICKER`, which has **zero rows** — even though the old,
now-orphaned `EDGARTOOLS_SOURCE.TICKER_REFERENCE` mirror still has 10,398 real rows. The silver
ingestion for company tickers appears to have never been wired up post-migration. Not investigated
further this session — needs its own ticket before fixing.

**Resolved 2026-08-22, as a side effect of the seed-universe-narrow-hydrate map's ticket 06** (a
publish/merge-side streaming-I/O fix, unrelated in purpose to this gap): the real root cause was
that `seed-universe` — the only writer of `sec_company_ticker` — had never successfully completed
against the rebuilt Snowflake account at all; every attempt OOM'd (see that map for the two-part
fix: table-scoped merges, then streaming file transfer). Once `seed-universe` finally ran clean,
`sec_company_ticker` populated (20,806 rows) and its Snowflake landing export wrote
`ticker_reference: 10403` for `LOAD_SILVER_LANDING_TASK`'s next cycle to pick up — the silver
ingestion path was correctly wired all along; it just never had a chance to run.

**Also still orphaned, found while wiring this fix (not fixed here):** `infra/snowflake/sql/bootstrap/
16_silver_landing_deployer_read.sql` and `17_mdm_export_deployer_read.sql` are committed, real,
non-dead fixes (each carries its own root-cause header) but are referenced by **neither**
`install.sh` nor `deploy-snowflake-stack.sh` — confirmed via a plain grep, zero hits for either
filename in either script. Both predate this fix and are unrelated to it; noted here so a future
session doesn't have to rediscover the gap from scratch.

## Ticket 20 Source Family Registry — Postgres-only activation/rerun bugs 5-whys (fixed, not yet deployed, 2026-08-24)

**Problem:** Ticket 20's Source Family Registry (`edgar_warehouse/acquisition/registry_ledger.py`,
migration `014_source_registry.sql`) shipped with 18 passing SQLite-backed unit tests and no
real-Postgres integration test. Writing the missing test (`tests/integration/
test_source_registry_postgres.py`, same shape as the existing 013/018/019 Postgres suite) found
two genuine bugs on first run against real Postgres, neither caught by SQLite.

**Bug 1 — `activate()`'s supersede-then-activate write hit the partial unique index it's supposed
to satisfy:**

1. Symptom: `SourceRegistryLedger.activate()`, activating a second version after a first was
   already active, raised `psycopg2.errors.UniqueViolation: duplicate key value violates unique
   constraint "uq_source_registry_version_single_active"` — from inside the ledger's own normal
   activation path, not a forged/bypass attempt.
2. Why? `activate()` set `previous.status = "superseded"` and `version.status = "active"` on two
   ORM objects, then called `session.flush()` once — leaving SQLAlchemy's unit-of-work free to
   emit the two resulting UPDATE statements in either order.
3. Why does statement order matter? `uq_source_registry_version_single_active` is a **partial
   unique index**, not a deferrable constraint — Postgres cannot defer a partial unique index
   (only a full-table `UNIQUE`/`PRIMARY KEY` constraint backed by a non-partial index can be
   declared `DEFERRABLE`), so it is checked immediately at each row-level UPDATE, not at commit.
4. Why did that make the flush fail? When SQLAlchemy happened to emit the new version's
   `status='active'` UPDATE before the previous version's `status='superseded'` UPDATE, both rows
   briefly held `status='active'` simultaneously at that statement boundary — an immediate
   violation.
5. **Root cause:** the code relied on `session.flush()`'s internal ordering to keep "at most one
   active row" true at every intermediate point, but nothing enforces that ordering — the two
   UPDATEs are independent objects in one unit of work with no declared dependency between them.

**Fix:** split the single flush into two — set `previous.status = "superseded"` and flush that
UPDATE first, *then* set `version.status = "active"` and flush again. Guarantees at most one
`'active'` row exists at any statement boundary, regardless of what SQLAlchemy would have chosen
unordered.

**Bug 2 — the migration's own DO block isn't idempotent for a rerun through `application`'s DSN:**

1. Symptom: calling `_apply_source_registry_migration` a second time via an engine connected as
   `application` (exactly how `mdm migrate` is documented to be safely re-runnable, per this
   file's "Self-managing Postgres migration pattern" note) raised
   `psycopg2.errors.InsufficientPrivilege: permission denied to grant role
   "edgartools_acquisition_registry_owner" ... Only roles with the ADMIN option ... may grant
   this role.`
2. Why does a rerun even reach privileged DDL? The rerun-gate checks
   `pg_has_role(current_user, 'edgartools_acquisition_registry_owner', 'MEMBER')` — analogous to
   013's `_apply_acquisition_ledger_migration` gate — and proceeds (`may_manage = True`) if the
   connecting role is a member.
3. Why is `application` a member here when it never is for 013? Ticket 20 deliberately uses **one**
   role for both governance (schema ownership) and operational access (what `application` SET
   ROLEs into to read/write) — unlike 013's split owner/coordinator/worker/etc. roles, where
   `application` is only ever granted the *operational* roles, never `edgartools_acquisition_owner`
   itself. 014's own DO block unconditionally grants the single owner role directly to
   `application`, so `pg_has_role` is `True` for `application` here, `may_manage` becomes `True`,
   and the rerun path — never exercised by 013's application DSN — executes for the first time.
4. Why did that DDL fail? The DO block's final statement,
   `GRANT edgartools_acquisition_registry_owner TO application`, ran unconditionally on every
   invocation. On a rerun, `application` already holds that membership but has no `ADMIN OPTION`
   on the role (`WITH INHERIT FALSE, SET TRUE` grants neither inherit-by-default nor
   admin-option), so re-issuing the same GRANT as `application` itself is rejected outright — not
   a no-op just because the membership already exists.
5. **Root cause:** the migration file was written assuming the "grant once, safe to reapply"
   idempotency 013 gets almost for free (because `application` never reaches the privileged branch
   for 013) — but 014's single-role design puts `application` on the privileged branch on every
   rerun, and none of the DO block's GRANT statements were individually guarded against "already
   satisfied, and the caller lacks rights to redundantly reassert it."

**Fix:** guarded each of the three privileged statements in `014_source_registry.sql`'s DO block
with an explicit "already satisfied" check before executing: the owner-role membership grant to
`current_user` now also checks `NOT pg_has_role(current_user, ...)`; the schema `USAGE, CREATE`
grant now checks `NOT (has_schema_privilege(...) AND has_schema_privilege(...))`; the membership
grant to `application` now also checks `NOT pg_has_role('application', ...)`. First install (run
by an admin principal, nothing yet satisfied) behaves identically; a rerun by `application` (or
anyone else already fully provisioned) now short-circuits every GRANT and reaches the idempotent
`CREATE TABLE IF NOT EXISTS`/`ALTER TABLE ... OWNER TO`/`REVOKE` statements in `statements[1:]`
cleanly, matching the rerun contract 013 established (and this file's "Self-managing Postgres
migration pattern" note) rather than diverging from it silently.

**Both fixes proven against real Postgres** (not just re-reading the SQL), via the new
`tests/integration/test_source_registry_postgres.py` — 4 tests, all reproduced the failure
against unfixed code first, then passed after: role/fencing proof mirroring the 013 suite's
"universal_login"/"forged_role" pattern, the open-draft/block/catch-up/activate round trip via
the real `SourceRegistryLedger` Python API, the supersede-then-activate proof plus a direct
attempt to force two active rows under the owning role (rejected by the partial index, as
designed), and the rerun proof for both the `application` and admin engines. SQLite-backed unit
tests (`tests/acquisition/test_registry_ledger.py`, 18 tests) still pass unchanged — neither bug
is reachable from SQLite, which has no equivalent immediate-partial-unique-index semantics and no
Postgres role/GRANT model to expose the rerun gap.

**Lesson:** a migration or ledger method whose only proof is SQLite-backed unit tests is unproven
for exactly the two things SQLite can't model — real constraint-timing semantics (deferrable vs.
immediate, partial index checks per-statement) and a real multi-role GRANT/`SET ROLE` privilege
graph. This is the same class of gap the "MDM Postgres migration-011 schema drift" and
"Manifest-pipeline ownership" incidents above already document for other subsystems — a real
role graph is not optional coverage for anything that fences a table by role.

**Deployed 2026-08-26** — migration `014_source_registry.sql` (this fix) applied live to prod via
`bootstrap-prod-mdm.sh`'s `snowflake_admin` path, alongside the Ticket 30 `snowflake_write`
REVOKE fix below, which found 014 had its own sibling gap of that same shape. See
"snowflake_write RESET ACCESS re-grant" 5-whys below for the full deploy story and a second,
more severe platform behavior it surfaced.

## snowflake_write RESET ACCESS re-grant 5-whys (fixed, deployed to prod 2026-08-26)

**Problem:** Deploying Ticket 30's `snowflake_write` REVOKE fix (change-propagation map — see
"Manifest-pipeline ownership" and the Ticket 20 entry above for the sibling incidents this one
continues) via `bootstrap-prod-mdm.sh` completed with `mdm migrate` reporting success and no
errors, but a live `has_table_privilege` sweep immediately after showed `application` and
`snowflake_write` **still** fully leaking DML access on all 11 fenced acquisition-ledger/registry
objects — contradicting an error-free migration run.

1. Symptom: `has_table_privilege('snowflake_write', 'source_fetch_decision', 'SELECT')` returned
   `true` right after a `mdm migrate` run whose own code path (confirmed by direct inspection and
   by calling `_apply_acquisition_ledger_migration` as a raw Python import) unconditionally issues
   `REVOKE ALL PRIVILEGES ... FROM snowflake_write` on that exact table when `may_manage` is true
   (confirmed true: `pg_has_role('snowflake_admin', 'edgartools_acquisition_owner', 'MEMBER')`).
2. Why does a successful REVOKE not show as revoked moments later? Calling
   `_apply_acquisition_ledger_migration(engine)` directly (bypassing the `mdm migrate` CLI
   entirely) revoked it immediately and the change held — proving the REVOKE mechanism itself is
   correct. The CLI path and the direct-call path use the identical source file and function; the
   only structural difference between the two test runs was how many
   `ALTER POSTGRES INSTANCE ... RESET ACCESS FOR '<role>'` calls happened around each one.
3. Why would RESET ACCESS matter? Isolated with a minimal repro: REVOKE, verify revoked (`false`),
   call `RESET ACCESS FOR 'snowflake_admin'` again with **zero other writes** in between, re-verify
   — the privilege came back (`true`). Repeated for `RESET ACCESS FOR 'application'` with the same
   result. **Root cause: Snowflake-hosted Postgres re-grants `snowflake_write`'s baseline DML
   access to these objects as a platform side effect of resetting *either* role's access** — a
   previously-undocumented behavior, distinct from and more severe than the standing
   `pg_default_acl` rule Ticket 30's original investigation already found (that rule explains why
   *new* tables get the grant; this explains why an *already-revoked* table's grant comes back).
4. Why did this make the fix ineffective in practice, not just in this one test? `bootstrap-prod-mdm.sh`'s
   normal run order is `mdm migrate` (applies the REVOKE) *then* `RESET ACCESS FOR 'application'`
   (part of the very same script, run on every single invocation) — so the script's own final step
   silently reopened the fence on every normal run, not just during ad hoc diagnostics.
5. **Root cause, restated:** the fix assumed "REVOKE persists once applied," which holds for plain
   Postgres but not for this platform's managed-role reconciliation, and nothing in the deploy
   script re-verified the end state after its own later steps ran.

**Compounding finding, same investigation:** migration 014 (`014_source_registry.sql`, Ticket 20)
had the identical original gap 013 once had — its own `application`-only REVOKE never got a
`snowflake_write` counterpart when it was written, so its two tables leaked via the same inherited-membership
path documented in Ticket 30's original writeup. Fixed the same way, mirroring 013's block.

**Fix:** `bootstrap-prod-mdm.sh` gained a new step — a fresh `snowflake_admin` rotation followed by
re-running `mdm migrate` (idempotent) — inserted after the `application` RESET ACCESS + secret
write and before the optional Snowflake-secret population, so it becomes the script's true last
database-mutating operation and both RESET ACCESS calls' side effects get corrected before the
script exits. `014_source_registry.sql` gained the same `snowflake_write` REVOKE block 013 has.
Live state after both fixes, verified via a full `has_table_privilege` sweep across all 11 objects
× both roles × SELECT/INSERT/UPDATE/DELETE: zero leaks.

**Open, unresolved risk:** this fix only protects runs that go through `bootstrap-prod-mdm.sh`
end-to-end. Any future credential rotation of either role — including one run outside this script,
e.g. manual incident response — reopens the fence until the next `mdm migrate` run, and nothing
currently monitors for that drift. A periodic live `has_table_privilege` check, alerting if either
role regains access, is the natural follow-up; not yet built. See
[Ticket 30](.scratch/change-propagation/issues/30-fence-application-from-acquisition-tables-under-snowflake-write.md)'s
"Bullet 4 resolved" section for full detail.

**Process note:** while diagnosing this live, a `RESET ACCESS FOR 'application'` command's raw
output was briefly piped through `tail` into visible output instead of straight into a
credential-consuming script, exposing the new plaintext password in that session's transcript.
Caught immediately; invalidated by rotating `application` again through the correct piped pattern
before any further action, with the AWS secret rewritten to match. A reminder that even a "just
checking it ran" command against this script's output needs the same discipline as every other
credential-handling step — there is no safe shortcut for a quick manual peek.

**Update (2026-08-26, Ticket 44): the monitoring follow-up this incident's own writeup deferred is
now built, live-verified, and already earned its keep.** `mdm check-fence`
(`edgar_warehouse/mdm/fence_monitor.py`) discovers the fenced-table set live from
`pg_class`/`pg_roles` rather than hardcoding the 11 objects known at the time — and that design
choice mattered immediately: a live run against prod found a **third** instance of this exact gap,
on `source_evidence_conflict` (migration 015, Ticket 25's evidence-conflict/repair table, owned by
`edgartools_acquisition_owner` same as 013's tables) — it had the identical missing
`snowflake_write` REVOKE block 013 had before this fix and 014 had before its own sibling fix,
never independently noticed until the monitor's live discovery surfaced it. Fixed the same way.
Confirmed live through the ordinary `application` DSN (piped directly from the existing
`edgartools-prod/mdm/postgres_dsn` secret, no elevated credential) that the check runs clean with
zero errors, closing this file's own "not yet confirmed" note on that exact question. Full
writeup: [Ticket 44](.scratch/change-propagation/issues/44-monitor-snowflake-write-privilege-drift.md).

**Second process note, same session, same mistake repeated:** verifying the point directly above
required reading the `application` DSN secret, and the very first attempt used a standalone
`aws secretsmanager get-secret-value ... | head -5` to debug a JSON-parsing failure — printing the
live plaintext password again, the identical failure mode as the note above, caught and fixed the
same way (immediate re-rotation through the safe piped pattern, secret rewritten). Two occurrences
of the exact same mistake in one session, both during ad hoc "let me just check this" commands
written outside the established safe pattern rather than through it — the lesson from the first
instance evidently wasn't sufficient on its own. **Concrete rule going forward, not just a
reminder:** never pipe a `snow sql ... RESET ACCESS` or `aws secretsmanager get-secret-value`
command's output to `head`/`tail`/`cat`/a bare variable capture for ANY reason, including debugging
a downstream parsing error — always pipe directly into the credential-consuming script and add
debug output (e.g. `type(pw)`, length, whether a key exists) *inside* that script instead, since
that's the only way to see what's needed without the credential ever passing through the
transcript.

## LOAD_SILVER_LANDING_TASK credit-burn 5-whys (resolved 2026-08-25, widened further 2026-08-26)

**Problem:** `EDGARTOOLS_PROD_REFRESH_WH` went from ~$0/day to ~9 credits/day, sustained every
day, starting 2026-08-18 — confirmed via `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`
and `METERING_DAILY_HISTORY` (this one warehouse is essentially all of the account's
`WAREHOUSE_METERING` cost on every affected day).

1. Symptom: `EDGARTOOLS_PROD_REFRESH_WH` (X-Small, `auto_suspend=60`) burns ~9 credits/day, every
   day, with no obvious backfill or manual work running.
2. Why? `QUERY_HISTORY` on that warehouse shows 58,971 `COPY INTO` statements and 1,908
   `CALL LOAD_SILVER_LANDING()` calls over 7 days — continuous, not bursty.
3. Why so many? `TASK_HISTORY` shows `LOAD_SILVER_LANDING_TASK` firing every 5 minutes, 288
   times/day, every day since it was created (2026-08-18 14:17), each firing running one
   `COPY INTO` per silver-landing table (~30 tables,
   `infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql`'s `LOAD_SILVER_LANDING()`
   procedure) regardless of whether new Parquet files actually landed since the last run.
4. Why does that cost real credits when each run only does ~20-30s of real work? Snowflake bills
   a per-resume minimum on top of actual compute time; with the warehouse suspending between
   5-minute ticks (idle time between runs exceeds `auto_suspend=60`), nearly every one of the 288
   daily firings pays that minimum on top of its real work, even on ticks with nothing new to
   load.
5. **Root cause:** `LOAD_SILVER_LANDING_TASK` was shipped with an explicitly-labeled "starting
   default... tune once real volume exists" 5-minute cadence (Ticket 07's own comment, silver-
   snowflake-migration map) and nobody circled back to tune it — the exact same
   poll-interval-too-tight-for-warehouse-resume-billing shape this file's own "ecs-cost-sizing"
   finding had already diagnosed and fixed for `SNOWFLAKE_RUN_MANIFEST_TASK` (1 MIN → 15 MIN →
   6 HOUR) three weeks earlier. That fix was never ported to this sibling task, created after it
   — the same "sibling path silently diverged" pattern this file documents repeatedly elsewhere
   (`ShardedSilverReader._TABLES`, shard-publish, relationship-derivation, the silver-loader
   OPERATE+SELECT gap above).

**Fix:** `LOAD_SILVER_LANDING_TASK`'s `SCHEDULE` widened `5 MINUTE → 60 MINUTE` in
`infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql` (24 resumes/day instead of 288),
applied live to prod (`SHOW TASKS` confirms `schedule: 60 MINUTE`, `state: started`). Sized to
land under an explicit **≤1 credit/day** ceiling for this task, extrapolated from the 5-minute
cadence's own observed ~9 credits/day at 288 resumes/day.

**Re-verified 2026-08-26 (Ticket 02) and widened further:** the 60-minute cadence's real cost was
independently measured against a full clean day of `WAREHOUSE_METERING_HISTORY` (the fix landed
mid-morning on 08-25, so that calendar day's raw total was a misleading transition-day mix of old
and new cadence) — a steady **0.031-0.042 credits/hour**, extrapolating to **~0.80 credits/day**,
comfortably confirming the ≤1 credit/day target. The operator then asked to bring cost down
further, into an explicit 0.3-0.5 credit/day band; presented with concrete options (120 MINUTE
≈0.40/day, 180 MINUTE ≈0.27/day, a stream-gated conditional task mirroring
`SNOWFLAKE_RUN_MANIFEST_TASK`'s own `WHEN SYSTEM$STREAM_HAS_DATA(...)` pattern, or a custom
interval), the operator chose **180 MINUTE** (8 resumes/day) — applied live to prod, `SHOW TASKS`
confirms `schedule: 180 MINUTE`, `state: started`. Extrapolated cost ~0.27 credits/day, not yet
independently re-measured at this cadence — see
[Ticket 02](.scratch/silver-landing-task-cost/issues/02-widen-load-silver-landing-task-to-0.3-0.5-credit-day.md)
for the full write-up and that open re-verification item.

`ALTER TASK ... SET SCHEDULE` against a `STARTED` root task fails closed (`"Unable to update
graph with root task ... since that root task is not suspended"`, confirmed live) — the script
now `SUSPEND`s before altering the schedule and `RESUME`s after, both idempotent no-ops if
already in that state, so a re-run is safe regardless of the task's current state. Nothing
downstream depends on landing's write latency (Ticket 07's own answer, unchanged by this fix) —
a multi-hour ceiling on data freshness here doesn't block any consumer, since every consumer
refreshes on its own `TARGET_LAG`, not on landing's write time.

**For future builds — read this before adding any new Snowflake `TASK`:** a fixed-interval poll
task pays a per-resume minimum charge close to every tick unless the interval is wide enough for
the warehouse to have been suspended for a meaningful stretch beforehand. Before shipping a new
scheduled task (or accepting a "5 MINUTE, tune later" placeholder default the way this one was
shipped), size the interval — or add a data-presence gate so idle ticks skip the resume
entirely (e.g. a stream-gated conditional task via `WHEN SYSTEM$STREAM_HAS_DATA(...)`, already
live for the sibling `SNOWFLAKE_RUN_MANIFEST_TASK` but still not built for this task, since a
fixed-interval widening met every credit target asked of it so far) — against an explicit credit
budget up front, the same way this fix had to retrofit one after the fact.
Full write-up: `.scratch/silver-landing-task-cost/issues/01-cap-load-silver-landing-task-credit-spend.md`,
`.scratch/silver-landing-task-cost/issues/02-widen-load-silver-landing-task-to-0.3-0.5-credit-day.md`.

## Migration 010 DuckDB commit-conflict 5-whys (resolved 2026-08-27)

**Problem:** A live-prod `daily-incremental` run (kicked off to verify the change-propagation
map's Ticket 46) crashed before any of Ticket 46's own code ran at all — the ECS task exited 1
while merely opening the local Silver DuckDB, hydrated fresh from prod's canonical
`silver.duckdb` (1.59GB). `_duckdb.TransactionException: TransactionContext Error: Failed to
commit: Attempting to modify table sec_financial_fact but another transaction has altered this
table`, raised from `_apply_schema_migration`'s own `self._conn.execute("COMMIT")`.

1. Symptom: the exception traces through `_ensure_schema_evolution` applying migration
   `010_company_facts_retirement_columns` (`_add_company_facts_retirement_columns`, Ticket 33's
   own migration adding `valid_from`/`valid_to`/`is_current` to `sec_financial_fact`/
   `sec_accounting_flag`) — not anything from this session's Ticket 46 work.
2. Why did the COMMIT fail claiming "another transaction" touched the table, when only one
   transaction (this process's own explicit `BEGIN TRANSACTION`) ever ran? Built a tight,
   deterministic repro (`SilverDatabase` opened against a hand-built pre-Ticket-33 store) and
   isolated it via direct pairwise testing of the migration's own ALTER statements: DuckDB
   1.5.2's `ALTER TABLE ... ADD COLUMN ... DEFAULT <expr>` against a table with **existing rows**
   triggers an internal row-backfill rewrite that bumps the table's version — confirmed via a
   1-row repro (crashes) vs. a 0-row repro (succeeds cleanly), deterministic either way.
3. Why does a version bump break the commit? A **second** `ALTER TABLE` statement against that
   same table, inside the **same explicit transaction**, then hits DuckDB's commit-time conflict
   check against that bump — reproduced directly: `valid_from DEFAULT NOW()` then `valid_to`
   (no default) on the same table, same transaction → crash; either statement alone → fine;
   without the explicit `BEGIN TRANSACTION` wrapper (autocommit per statement) → fine. Confirmed
   this isn't fixable by reordering: two default-bearing columns (`valid_from`, `is_current`)
   both need backfill, and only one statement can be last regardless of order — every ordering
   with 2+ default-bearing `ADD COLUMN`s on one table in one transaction crashes.
4. Why did migration 010 hit this specific shape? It issues exactly 3 `ADD COLUMN` statements per
   table (two default-bearing: `valid_from`, `is_current`), on two tables, inside
   `_apply_schema_migration`'s shared explicit-transaction wrapper — the same wrapper every other
   migration in `_schema_migrations()` also uses.
5. **Root cause:** no test ever exercised migration 010 against a **non-empty** pre-migration
   table — every existing test in `test_silver_store_schema_migration.py` either opens a fresh
   store (already has the columns via `_DDL`, migration no-ops) or predates Ticket 33 entirely
   (migration 010 not yet defined). And daily-incremental itself had not run successfully in prod
   in 3+ weeks (confirmed: last `SUCCEEDED` execution was 2026-08-04; zero active EventBridge
   rules for it at all) — so this Ticket 46 verification run was the **first real attempt** to
   apply migration 010 against prod's actual, populated `sec_financial_fact`. Checked all 6 other
   plain-ALTER migrations (003/004/005/006/008/009) for the same shape (2+ `ADD COLUMN`
   statements on one table, at least one with a `DEFAULT`, inside the shared transaction) — none
   of the others have it (005/006/009 loop over multiple tables/columns but never combine a
   default-bearing `ADD COLUMN` with a second statement on the *same* table); migration 010 is
   the only one affected among everything currently shipped.

**Resolution:** `_schema_migrations()`'s tuples gained a 4th field, `requires_transaction: bool`
(`True` for every existing migration, preserving current behavior exactly); migration 010 is the
one entry marked `False`. `_apply_schema_migration` now only wraps `migrate()` in
`BEGIN TRANSACTION`/`COMMIT`/`ROLLBACK` when `requires_transaction` is `True` — when `False`, each
statement `migrate()` issues autocommits on its own, and `_record_schema_migration` runs as its
own trivial autocommitted `INSERT`. Safe specifically for migration 010 because every statement it
issues is `ADD COLUMN IF NOT EXISTS` — already idempotent under interrupt-and-retry. **Not** applied
globally: `_backup_and_recreate_table`-based migrations (001/002/007) genuinely need the shared
transactional envelope — their `RENAME` → `CREATE TABLE IF NOT EXISTS` → `INSERT...SELECT`
sequence is not safely retriable without it (a crash mid-sequence would leave the renamed-away
backup table orphaned and the main table's own retry-detection query finding nothing to recreate,
since it checks the live table's current PK, and there's no live table to check).

New regression test, `test_migration_010_adds_retirement_columns_to_populated_tables`
(`tests/unit/test_silver_store_schema_migration.py`) — builds a pre-Ticket-33 store with ≥1
row in each affected table (the exact shape no prior test covered), confirmed to reproduce the
crash verbatim before the fix (reverted the fix locally, reran, watched it fail with the identical
`_duckdb.TransactionException`) and pass after. Full repo suite green after the fix.

**Lesson:** a schema migration's own unit tests can all pass while still never exercising the one
precondition (a genuinely populated table) that matters in production — an empty-table-only test
suite for a migration is unproven for exactly the thing migrations exist to do: evolve real data.
Same class of gap as the "MDM Postgres migration-011 schema drift" and "Ticket 20 Source Family
Registry" entries above (SQLite can't model Postgres's real GRANT/role semantics; here, an empty
DuckDB table can't model DuckDB's real ADD-COLUMN-with-DEFAULT row-rewrite semantics) — a real,
populated fixture is not optional coverage for anything that touches existing rows.

## sec_financial_fact retirement publish-conflict 5-whys (partially resolved 2026-08-27)

**Problem:** immediately after the migration 010 fix above unblocked local schema evolution, the
same Ticket 46 verification run's `daily-incremental` still failed (exit 2) — this time at the
final silver-publish step, with `SemanticMergeConflictError`:
`434805 ambiguous same-key conflict(s) block publication: sec_financial_fact{...}: ['valid_from',
'is_current']` for every one of the 434,805 pre-existing rows.

1. Symptom: `merge_candidate_into_canonical` (`silver_protection.py`) treats every pre-existing
   `sec_financial_fact` row as an unresolvable conflict on its first publish after Ticket 33.
2. Why? Built a direct repro against the real function (not just read the code): this table's
   `_comparable_columns` diff includes `valid_from`/`is_current` (no `provenance_columns`
   exemption for them existed), and the additive schema-reconciliation step — canonical learning
   about the 3 new columns for the first time — added them via a bare
   `ALTER TABLE ... ADD COLUMN IF NOT EXISTS {type}` with **no default**, leaving every
   pre-existing canonical row `NULL`. The candidate's own local schema migration
   (`_add_company_facts_retirement_columns`) had already backfilled real values. NULL-vs-real-value
   on a comparable column reads as a genuine conflict.
3. Why does that block the whole publish instead of resolving via the authority column? This
   table's `authority_column` is `ingested_at` — untouched by either side here (same original
   capture timestamp both places), so it ties, and `_resolve_conflict` returns `None`
   (ambiguous) on an exact tie, aborting the merge.
4. Why did this never surface before? `daily-incremental` hadn't successfully published to prod's
   real canonical silver in 3+ weeks (same root fact as the migration 010 entry above) — this was
   the first real publish attempt since Ticket 33 shipped its new columns at all.
5. **Root cause, part A (fixed):** the additive-column backfill had no notion of "what default did
   the candidate's own schema declare for this column" — it always left new columns NULL, which is
   only ever correct when the source schema itself declares no default either.
   **Root cause, part B (confirmed real, deliberately left open):** even after fixing A, a second,
   deeper repro proved a **genuine future retirement can never publish either** —
   `retire_financial_facts_not_in_snapshot` (`silver_store.py:4092`) sets `is_current`/`valid_to`
   but never touches `ingested_at` by design (it represents true capture time, not last-touched).
   So a real retirement always ties on the authority column too, and always hits the same
   ambiguous-conflict abort. Ticket 33's whole retirement feature has, as far as this investigation
   found, never actually been able to reach canonical silver — not a first-publish artifact, a
   standing gap.

**Resolution, part A only** (part B deliberately scoped out — see below): `merge_candidate_into_
canonical`'s additive `ADD COLUMN` step now reads the candidate's own declared `DEFAULT` (via a
new `_column_defaults` helper, `information_schema.columns.column_default`) and applies it to
canonical's newly-added column instead of leaving it NULL — matches the `is_current DEFAULT TRUE`
case exactly (both sides now agree). `valid_from DEFAULT NOW()` still needed a second, targeted
fix on top: `NOW()` evaluates to a genuinely different literal each time it runs, so no shared
default expression can ever make two independent backfills agree — `sec_financial_fact`'s (and
`sec_accounting_flag`'s) registry entries now declare `provenance_columns=frozenset({"valid_from"})`,
safe because `valid_from` is set once at first capture and never touched again by design (same
guarantee that already makes `mdm_entity_id`'s existing exemption safe elsewhere in this registry).
Deliberately did **not** add `valid_to`/`is_current` to `provenance_columns` — that would silently
stop retirement writes from ever reaching canonical at all (a worse, silent-data-loss bug), not
fix anything; those columns carry real business content that a genuine future candidate needs to
update, so blocking on a real conflict there is *currently correct*, just currently permanent
because of part B.

**Part B is an open design question, not fixed here** — user explicitly scoped it out mid-session
rather than have it decided unilaterally. Candidate resolution policies considered but not chosen:
bump `ingested_at` (or a new field) on retirement so the existing authority-column mechanism
naturally resolves it (changes `ingested_at`'s semantic meaning elsewhere); a dedicated
`valid_to`/`is_current` resolver mirroring the existing narrow `mdm_entity_id`-regression-guard
precedent (`silver_protection.py`'s "candidate wins on comparable columns but never drags
`mdm_entity_id` backward" special case); something else. Needs its own decision session before
retirement can actually publish to prod canonical silver.

Tests: 3 new (`tests/unit/test_silver_financial_fact_retirement_provenance.py`) — the first-publish
false-conflict regression (fails before the fix, passes after — verified both ways), a
valid_from-only-difference-does-not-block-or-get-copied case, and a **positive control** proving a
genuine retirement conflict still correctly blocks (i.e. confirming `is_current`/`valid_to` were
not accidentally exempted alongside `valid_from`). Full repo suite green.

## Phased Pipeline (use this for all bootstraps ≥10 companies)

`load_history` is the canonical way to load companies at scale. Its live
`edgartools-prod-load-history` definition (re-verified via
`describe-state-machine`, not copied from an older architecture doc) runs:

```
Stage 0 — Company identity seeding (single steps, no windowing)
  SeedUniverse → MdmSeedUniverse
  • Seeds the CIK universe and MDM's own tracking state. Company entity
    *resolution* (IS_INSIDER, MANAGES_FUND, etc.) happens later, in Stage 2
    (MdmRun) -- there is no separate identity-resolution state here; an
    earlier load_history shape had one (stage0-stage1-consolidation map),
    removed when Stage0CompanyIdentity/ReduceIdentityRefresh were deleted.

Stage 1 — Bronze + Silver bootstrap (windowed, MaxConcurrency=1)
  IngestBronzeAndSilver/WindowedBootstrap
  • Each window: bootstrap-next --silver-only over a CIK slice → S3 bronze, parse → silver DuckDB
  • MaxConcurrency=1 by design (same class of reason as the ticket-20 N-way
    silver-promotion-race finding elsewhere in this file) -- windows run one at
    a time, not in parallel, regardless of BOOTSTRAP_BATCH_CONCURRENCY (see
    "Key invariants" below -- that env var does not control this Map)
  • Within each window, artifact fetching (ownership/ADV/13F documents) uses
    bounded intra-task concurrency (ThreadPoolExecutor, WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY,
    default 5) -- this is real parallelism, just not CIK-batch-level parallelism

Stage 1B — Fundamentals (windowed, MaxConcurrency=1 each, run after Stage 1)
  FetchEntityFacts → FetchPerFilingFundamentals → FetchThirteenFHoldings
  • XBRL company facts, 8-K/DEF 14A per-filing data, and 13F holdings respectively

Stage 2 — MDM entity resolution (sequential Step Functions)
  mdm-run → mdm-backfill-relationships → mdm-export → mdm-sync-graph → mdm-verify-graph
  • Runs after Stage 1/1B complete so entity resolution sees the full silver dataset
  • Derives IS_INSIDER, MANAGES_FUND etc. and syncs to the graph (Snowflake, not external Neo4j)

Stage 3 — Gold refresh (single ECS task)
  gold-refresh
  • Writes Snowflake export manifests for source-layer serving exports (not the gold layer)
  • EDGARTOOLS_GOLD is 21 Snowflake dynamic tables. Live prod 2026-08-29: every
    table had TARGET_LAG=DOWNSTREAM but DYNAMIC_TABLE_REFRESH_HISTORY showed
    REFRESH_TRIGGER=MANUAL only (REFRESH_AFTER_LOAD after a run manifest).
    DOWNSTREAM does not refresh gold leaves. gold_model_config() now uses
    target_lag='6 hours' (same as silver). SNOWFLAKE_RUN_MANIFEST_TASK still
    runs LOAD_EXPORTS_FOR_RUN then REFRESH_AFTER_LOAD as an extra explicit
    trigger. The Ticket 39 completion barrier fail-closes on a stale
    data_timestamp regardless of either clock.
```

(Elsewhere in this repo, `bootstrap`/`daily_incremental`'s own Company Identity
capture stage -- a different, sibling state named `ResolveCompanyIdentityBounded`
in `write_warehouse_mdm_gold_definition` -- is unrelated to `load_history`'s
Stage 0 above; it runs *before* bronze/silver capture in those two pipelines,
not as a seeding step.)

**`edgartools-prod-bootstrap-batched` (formerly a separate, standalone state
machine running CIK batches with real parallelism via a `BatchBootstrap`
Map, `MaxConcurrency=3`) was deleted (state-machine-consolidation wayfinder
map, ticket 03)** — it was never part of `load_history`'s call graph, had
**zero executions ever** in prod, and was architecturally superseded by
`load_history`'s sequential-windowed design, which was built specifically
to fix a `silver.duckdb` consistency race inherent to
`bootstrap_batched`'s concurrent-writer/`cik_batches.jsonl` architecture.

There is a genuinely-parallel batch pipeline in prod:
`edgartools-prod-silver-mdm-gold` (`BatchSilver` Map, `MaxConcurrency=3`,
runs `bootstrap-batch --artifact-policy skip`) — this is what the
`BOOTSTRAP_BATCH_CONCURRENCY`/`bootstrap-batch` invariants below actually
govern. It reprocesses already-loaded bronze (no new SEC submissions
fetched) and is unrelated to `load_history`'s own bootstrap Stage.

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
grants: `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`.

**The write/sync path splits across two modules, not one** (investigated
2026-08-19, not previously written down here): `edgar_warehouse/mdm/graph.py`
prepares the Postgres-side mirror (writes `mdm_relationship_instance` rows —
its own docstring is explicit that "the Neo4j bolt driver and AuraDB are no
longer used"), then hands off to `edgar_warehouse/mdm/snowflake_graph.py`'s
`SnowflakeGraphSyncExecutor` (sync) and `SnowflakeGraphVerifier` (verify),
which generate and run the actual Snowflake SQL. Single path, not a
duplicate — `graph.py` never talks to Snowflake directly, `snowflake_graph.py`
never talks to Postgres directly.

**There are two separate read paths, not one, and they read different
stores on purpose:** `edgar_warehouse/mdm/api/routers/graph.py` (neighborhood/
traversal endpoints) reads live from the **Postgres mirror**
(`mdm_relationship_instance`) for speed — its own docstring: "Graph analytics
run via the Snowflake-hosted Neo4j Graph Analytics native app" (BFS/WCC etc.),
but simple lookups don't pay a Snowflake round trip. `edgar_warehouse/mdm/
graph_readonly.py` reads **Snowflake** graph metrics (parity/comparison,
Native App health) for the local MDM dashboard. Don't assume one is stale
duplication of the other — they're deliberately different stores for
different latency needs.

**A third, orthogonal piece governs *when* sync-graph work happens:**
`edgar_warehouse/mdm/publication.py` is a transactional MDM→graph publication
queue (07-03, RSYNC-01/03) — relationship-changing workflows call
`request_publication` atomically with their own MDM commit; a lease-based
coordinator claims and advances requests through `mdm_committed →
graph_pending → graph_building → graph_verified → graph_active`, with a
5-minute-warning/15-minute-hard-alert staleness SLO. This is queue mechanics
only — no Snowflake/Neo4j orchestration logic lives in this module, per its
own docstring.

**The generation-scoped operator review contract** (GH-251):
`edgar_warehouse/mdm/graph_review_publish.py` persists `mdm verify-graph`'s
payload into a bounded, read-only `MDM_GRAPH_REVIEW` schema that a managed
dashboard (`examples/mdm_graph_dashboard/`) can query through a plain
Snowpark session — no MDM Postgres DSN, no direct Neo4j credential needed by
that dashboard.

**Dead file, removed (2026-08-19):** `edgar_warehouse/serving/targets/
neo4j.py` was a 1-line, unimported placeholder ("Neo4j serving target
placeholder for future Gold publishing support") left over from a "publish
gold data out to an external Neo4j" concept that was superseded by the
current architecture (graph lives inside Snowflake; there is no external
Neo4j to publish to). Confirmed unreferenced anywhere in the codebase before
deletion. Noted here in case a future `git blame` on this line goes looking
for it.

Full migration history:
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
# Monitor: aws stepfunctions describe-execution --execution-arn <arn> --query status
# No verified timing figure for the current windowed/sequential shape as of this writing --
# do not rely on a "~15 min for 100 companies" style estimate carried over from an older,
# genuinely-parallel bootstrap-batch ×N architecture (see the Stage 1 diagram above).
```

**Do NOT run `bootstrap-next` locally for large batches.** This is no longer primarily a
throughput argument -- `load_history`'s own Stage 1 also processes CIK windows one at a
time (MaxConcurrency=1), so raw per-CIK throughput between the two isn't dramatically
different. Use `load_history` anyway because it provides what a bare local
`bootstrap-next` call doesn't: per-window resumability and retry (`MaxAttempts: 3` with
backoff on `WindowedBootstrap`), correct Stage 0/1/1B/2/3 sequencing (identity before
ownership/ADV, MDM after silver is complete, gold last), and the cross-command
`sec_fetch_active` lease that prevents it from racing a concurrently-running
`daily_incremental`/`bootstrap`/etc. Reserve `bootstrap-next` for single-company ad-hoc
loads with explicit `--cik-list`. (Historical note: this guidance originally also cited
"cannot reach MDM Postgres, private VPC" — that no longer applies. MDM Postgres moved off
AWS RDS onto Snowflake's native Postgres service; see "MDM database" note below. Local
reachability to the current Snowflake-hosted instance has not been re-verified.)

**Key invariants (do not break):**

The `bootstrap-batch`/`BOOTSTRAP_BATCH_CONCURRENCY` bullets below govern
`edgartools-prod-silver-mdm-gold` (`BatchSilver` Map, confirmed live at
`MaxConcurrency=3`, runs `bootstrap-batch --artifact-policy skip`) — the
standalone `edgartools-prod-bootstrap-batched` machine that used to also
run `bootstrap-batch` was deleted (zero executions ever; superseded by
`load_history`'s sequential-windowed design — see the "Phased Pipeline"
note above and state-machine-consolidation wayfinder map ticket 03).
Neither `silver_mdm_gold` nor `bootstrap-batch` is `load_history`, which
runs `bootstrap-next` (a different command) per window at
`MaxConcurrency=1` and is not controlled by `BOOTSTRAP_BATCH_CONCURRENCY`
at all.

- `bootstrap-batch` must NOT be in `SOURCE_EXPORT_COMMANDS` (renamed from `GOLD_AFFECTING_COMMANDS`, single-path-per-layer map — the commands it gates build a source-layer export, not gold) — enforced in `warehouse_orchestrator.py:85`
- `gold-refresh` must be in `SOURCE_EXPORT_COMMANDS` — it is the sole gold builder in the phased pipeline
- `SNOWFLAKE_RUN_MANIFEST_TASK` must be STARTED in `EDGARTOOLS_GOLD` — verify with
  `snow sql --connection edgartools-dev -q "SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK'"`
- `silver_mdm_gold` map MUST pass `--artifact-policy skip` to `bootstrap-batch` — without it
  the pipeline makes thousands of SEC API calls (fetching ownership XMLs) even though the
  purpose of this pipeline is to reprocess already-loaded bronze with zero SEC calls.
  5-why root cause: the artifact pipeline is a separate SEC fetch pass; "no SEC calls" must
  be encoded as a flag, not assumed from the pipeline name.
- `BOOTSTRAP_BATCH_CONCURRENCY` — verified via `deploy-aws-application.sh` that this env var
  is unpacked into, and its `MaxConcurrency` actually read by, only ONE of `bootstrap-batch`'s
  three ECS/Step-Functions callers: `write_silver_mdm_gold_definition`'s `BatchSilver` Map
  (`silver_mdm_gold`, `--artifact-policy skip`, confirmed live `MaxConcurrency=3`). The other
  two — both inside `write_bronze_seed_silver_gold_definition` — receive the same
  `$BOOTSTRAP_BATCH_CONCURRENCY` positional argument but never reference it; their
  `MaxConcurrency` is hardcoded in the JSON template instead: the "first-load recovery from
  cached bronze" Map (`--artifact-policy skip` too) at 20, and the Ticket 20 strict
  candidate-manifest Map (`--artifact-policy all_attachments`, real SEC fetches) at 2. Do not
  assume changing this env var affects either of those.

  **Recommended range for the one caller it does govern: keep it at or below the current
  default of 3** — do not raise it toward the old **2–5** guidance's upper end, and do not
  raise it toward Fargate's vCPU ceiling either (see below). DuckDB Retirement Cutover
  Ticket 06 retired `bootstrap-batch`'s CIK-sharded hydrate/publish mechanism
  (`open_silver_shard`/`_hydrate_shard_for_window`/`_publish_shard_if_remote_with_retry` —
  every writer now hydrates/opens/publishes the same monolith silver database, like every
  other command). The old **2–5** range's own documented rationale (SEC rate limiting) never
  actually applied to this specific caller — it always runs `--artifact-policy skip`, zero
  SEC calls — so retiring the shard mechanism doesn't free up that headroom because that
  headroom was never real for this caller in the first place. What retiring the shard
  mechanism *does* change, and makes strictly worse: every `BatchSilver` batch that finishes
  concurrently now merges into and publishes the exact same canonical `silver.duckdb` object
  via one ETag-guarded promote, instead of being spread across 4 separate shard files (each
  batch previously had roughly a 1-in-4 chance of colliding with another concurrent batch;
  now every batch collides with every other concurrent batch on the same object). This isn't
  theoretical — `write_bronze_seed_silver_gold_definition`'s own `strict_batch_map` (a
  *different* `bootstrap-batch` caller, but writing the identical monolith object via the
  identical `_publish_silver_database_with_retry`/ETag-promote mechanism) documents exactly
  this failure mode in production: "production hit this repeatedly at MaxConcurrency=4
  (PromotionConflictError aborting an otherwise-complete batch)," which is why it was lowered
  4→2 on 2026-07-22, still below `silver_mdm_gold`'s current default of 3. The retry wrapper
  (`_publish_silver_database_with_retry`) makes a lost race retryable rather than fatal, but
  each retry re-runs the full merge — not free, and evidence from a comparable monolith-write
  caller suggests conflicts start becoming *frequent*, not rare, right around where this
  caller's current default already sits.

  Separately, and only as an upper theoretical bound, **not** the actual binding constraint:
  this Map's task profile is `medium` (`register_task_definition medium 1024 4096` — 1024 CPU
  units = 1 vCPU/task), and the account's Fargate On-Demand vCPU quota is confirmed live
  (`aws service-quotas get-service-quota --service-code fargate --quota-code L-3032A538`,
  2026-08-31) at 30 vCPU, giving a hard ceiling of 30 concurrent `medium` tasks if this one Map
  had the entire account's Fargate quota to itself (it doesn't; other pipelines share it, and
  the "first-load recovery" Map above already runs at MaxConcurrency=20 on this same profile).
  Snowflake landing-zone ingestion throughput under many concurrent small Parquet writes has
  also not been measured. Neither number is the reason to hold the line at 3, though — the
  monolith promotion-conflict evidence above is. Raising this value is deferred
  implementation-time work for an operator, and should not be attempted without first either
  re-measuring monolith-object promotion-conflict frequency at higher concurrency directly, or
  reintroducing some form of writer partitioning for this specific Map.

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
  --env-name dev \
  --snow-connection snowconn \
  --run-validation \
  --run-dbt

# Docker image publish (Linux / CI with buildx registry cache)
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region <region> \
  --ecr-repository edgartools-dev-images \
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
  --ecr-repository edgartools-dev-images \
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
`~/.snowflake/config.toml`. **`--snow-connection` is required and never derived** from the
environment name — as of wayfinder ticket 03 (snowflake-env-provisioning map), both
`install.sh` (renamed from `go-live.sh` per the snowflake-account-cutover map's Ticket 05)
and `deploy-snowflake-stack.sh` fail closed without it. This replaced two
*disagreeing* derivations of the same default (`install.sh` mapped dev to `snowconn`,
while `deploy-snowflake-stack.sh` string-built `edgartools-${ENVIRONMENT}`, i.e.
`edgartools-dev`), which is why neither derives one now. Prod's connection is
`edgartools-prod`; pass it explicitly.

**Environment identifier.** The same ticket replaced `--env <dev|prod>` with
`--env-name <slug>` across `install.sh`, `deploy-snowflake-stack.sh`,
`bootstrap-prod-mdm.sh`, `bootstrap-aws-mdm-secrets.sh`, and `create-deployer.sh`
(positional). A slug is lowercase letters/digits in hyphen-separated words
(`prod`, `eu-prod`); hyphens map to underscores for Snowflake identifiers
(`eu-prod` → `EDGARTOOLS_EU_PROD`). There is **no `--env` back-compat alias** — the
rename was clean, since dev is decommissioned and prod was the only live caller.
The AWS-side scripts (`deploy-aws-application.sh`, `run-aws-mdm-e2e.sh`) deliberately
still take `--env`; `install.sh` threads one identifier to both flag names.

## Image management

Use AWS ECR only for deployable images. Do not add non-AWS registry targets,
SDKs, ODBC drivers, or deployment steps back into this repo unless the platform
architecture changes explicitly.

**One shared ECR repository per environment** (`edgartools-<env>-images`)
holds all four image kinds. Role and build stage are encoded entirely in the
**tag prefix** (`warehouse-*` / `mdm-*` / `warehouse-deps-*` / `mdm-deps-*`),
not the repository name — `publish-warehouse-image.sh` applies this prefix
automatically based on `--role`, so callers keep passing plain tags
(`sha-<hash>`, `dev`, `deps-<hash>`) and only `--ecr-repository` changes.
(Superseded, pre-consolidation repos — `edgartools-<env>-warehouse`,
`-mdm`, `-warehouse-deps`, `-mdm-deps` — are left in place as a read-only
rollback archive; nothing pushes to them anymore.)

| Image kind | Tag prefix | Dockerfile | Installs | Runs |
|------------|------------|------------|----------|------|
| warehouse deps | `warehouse-deps-*` | `Dockerfile.warehouse-deps` | locked `.[s3]` deps via `uv` | dependency base image |
| warehouse final | `warehouse-*` | `Dockerfile` | source copy on warehouse deps | warehouse ECS tasks |
| mdm deps | `mdm-deps-*` | `Dockerfile.mdm-deps` | locked `.[s3,mdm-runtime]` deps via `uv`; no API/admin packages | MDM Step Functions dependency base image |
| mdm final | `mdm-*` | `Dockerfile.mdm-neo4j` | source copy on MDM deps | MDM ECS tasks/API |

**Tagging strategy**

| Tag | Meaning |
|-----|---------|
| `warehouse-dev` / `mdm-dev` | Mutable latest dev image, per role |
| `warehouse-sha-<hash>` / `mdm-sha-<hash>` | Immutable rollback/audit image, per role |
| `warehouse-prod` / `mdm-prod` | Manually promoted production image, per role |
| `warehouse-deps-<hash>` / `mdm-deps-<hash>` | Dependency base image, keyed by lockfile hash |

**Manual AWS build and deploy — complete recipe (macOS Colima)**

CI (GitHub Actions `deploy.yml`, the "Deploy" workflow — `build-images.yml`
no longer exists) builds and pushes the DEV images automatically on every push
to `main` in ~30-45s via buildx registry cache, retagging `warehouse-dev`/
`mdm-dev` each time. It does NOT promote to prod or register task
definitions — prod promotion (build/push under `edgartools-prod-images` +
`deploy-aws-application.sh`) is still manual. Use the steps below for prod
promotion, ad-hoc builds, or when CI is unavailable; for a dev image of
current `main`, prefer CI's digest (`gh run list --workflow deploy.yml`) over
rebuilding locally.

```bash
# 1. Start Colima and point Docker CLI at it (do once per terminal session).
colima start
export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock

# 2. Authenticate to ECR (token valid for 12 h).
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    690839588395.dkr.ecr.us-east-1.amazonaws.com

# NOTE: the ECR repository must have MUTABLE tags for warehouse-dev/mdm-dev
# to be overwritten. If you see "tag is immutable" on push, run once:
#   aws ecr put-image-tag-mutability --region us-east-1 \
#     --repository-name edgartools-dev-images --image-tag-mutability MUTABLE

# 3a. Build and push the warehouse image (tags as warehouse-sha-<hash>, warehouse-dev).
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-images \
  --role warehouse \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# 3b. Build and push the MDM image (tags as mdm-sha-<hash>, mdm-dev; when edgar_warehouse/mdm/** changed).
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-images \
  --role mdm \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# 4. Capture the digest refs that step 3 printed (used for deploy). Query by
#    tag prefix since the repo now holds both roles.
WAREHOUSE_REF=$(aws ecr describe-images \
  --region us-east-1 \
  --repository-name edgartools-dev-images \
  --query "sort_by(imageDetails[?contains(imageTags[0], 'warehouse-sha-')],&imagePushedAt)[-1].imageDigest" \
  --output text | xargs -I{} echo "690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-images@{}")
MDM_REF=$(aws ecr describe-images \
  --region us-east-1 \
  --repository-name edgartools-dev-images \
  --query "sort_by(imageDetails[?contains(imageTags[0], 'mdm-sha-')],&imagePushedAt)[-1].imageDigest" \
  --output text | xargs -I{} echo "690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-images@{}")

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
  --repository-name edgartools-dev-images \
  --query "sort_by(imageDetails[?contains(imageTags[0], 'warehouse-deps-')],&imagePushedAt)[-1].imageTags[0]" --output text)
MDM_DEPS=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-images \
  --query "sort_by(imageDetails[?contains(imageTags[0], 'mdm-deps-')],&imagePushedAt)[-1].imageTags[0]" --output text)

ECR="690839588395.dkr.ecr.us-east-1.amazonaws.com"
SHA_TAG="sha-$(git rev-parse --short=12 HEAD)"
REPO="edgartools-dev-images"

# Rebuild warehouse directly
docker pull "${ECR}/${REPO}:${WH_DEPS}"
docker build --platform linux/amd64 \
  --build-arg "DEPENDENCY_IMAGE=${ECR}/${REPO}:${WH_DEPS}" \
  -f Dockerfile -t "${ECR}/${REPO}:warehouse-${SHA_TAG}" -t "${ECR}/${REPO}:warehouse-dev" .
docker push "${ECR}/${REPO}:warehouse-${SHA_TAG}"
docker push "${ECR}/${REPO}:warehouse-dev"

# Rebuild MDM directly
docker pull "${ECR}/${REPO}:${MDM_DEPS}"
docker build --platform linux/amd64 \
  --build-arg "DEPENDENCY_IMAGE=${ECR}/${REPO}:${MDM_DEPS}" \
  -f Dockerfile.mdm-neo4j -t "${ECR}/${REPO}:mdm-${SHA_TAG}" -t "${ECR}/${REPO}:mdm-dev" .
docker push "${ECR}/${REPO}:mdm-${SHA_TAG}"
docker push "${ECR}/${REPO}:mdm-dev"
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

# 3. Remove old named images — keep only warehouse-dev/mdm-dev and each
#    role's latest sha-* tag. List old tags from the output above and delete
#    explicitly:
ECR="690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-images"
docker rmi \
  "${ECR}:warehouse-sha-<old>" \
  "${ECR}:mdm-sha-<old>" \
  "${ECR}:warehouse-deps-<old>" \
  # ... add any debug/ad-hoc tags (routerfix-*, hydratefix-*, etc.)

# 4. Nuclear option — wipe everything (forces full re-pull of base + deps on next build)
docker system prune -af   # WARNING: removes ALL local images, not just ours
```

**What to keep:**
- `warehouse-dev` / `mdm-dev` — used as build cache source (`--cache-from-tag dev`, per role)
- Latest `warehouse-sha-<hash>` / `mdm-sha-<hash>` — rollback anchor, per role
- Latest `warehouse-deps-<hash>` / `mdm-deps-<hash>` — slow to rebuild; only remove if `uv.lock` changed
- `public.ecr.aws/docker/library/python:3.12-slim-bookworm` — base layer cache

**Rollback to a previous SHA**

```bash
ECR=<account>.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-images
SHA=warehouse-sha-abc1234   # or mdm-sha-abc1234 for the mdm role
docker pull $ECR:$SHA
docker tag  $ECR:$SHA $ECR:warehouse-dev
docker push $ECR:warehouse-dev
```

## Key Large Files (Read in Chunks)

These files exceed 30 KB. When modifying them, read section by section rather than all at once:

| File | Size | Contents |
|------|------|----------|
| `edgar_warehouse/application/warehouse_orchestrator.py` | ~292 KB | Core ETL loop, form dispatch, S3 writes, bronze/silver publish paths. `edgar_warehouse/runtime.py` and `edgar_warehouse/application/command_router.py` are now thin compatibility shims that re-export from here, not separate implementations — this table previously pointed at those shims with stale sizes copied from an earlier version of this file. |
| `edgar_warehouse/silver_store.py` | ~190 KB | Record cleaning and transformation logic. `edgar_warehouse/silver.py` is a compatibility shim re-exporting `SilverDatabase` from here. |
| `edgar_warehouse/serving/source_dimensional_export.py` | ~63 KB | Builds a source-layer dimensional export consumed by dbt — not the gold layer itself (see Quick Navigation above and `.scratch/single-path-per-layer/issues/01-enumerate-layer-transitions.md`; renamed off "gold_models.py" for exactly this reason). `edgar_warehouse/gold.py` is a compatibility shim re-exporting from here. |

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

**HARD RULE — no exceptions for "small" tickets: before writing or editing
any production code file, consult `/gof-refactor-reviewer`** on the code
area you're about to touch — it flags pattern-shaped structural problems
(repeated-change axes, duplicated conditionals, etc.) worth knowing about
before adding to them, per its own Rule 0 (default verdict is "leave it" —
only real, evidenced findings block anything, so this consult costs seconds
on a small change and comes back clean). "This ticket is tiny/mechanical" is
not a reason to skip it — that's exactly the judgement call Rule 0 already
makes for you. This is in addition to, not instead of, the code-review pass
below.

**HARD RULE — `/code-review` always runs three axes, not two: Standards,
Spec, and GoF.** The `/code-review` skill file's own template (Step 4) only
lists two sub-agent calls (Standards, Spec) — that template does NOT
override this rule; add a third `general-purpose` sub-agent call in the same
parallel batch, briefed with the `/gof-refactor-reviewer` skill's own
instructions run against the same diff/changed files. Aggregate its findings
under their own `## GoF` heading in step 5, reported the same way as the
other axes (evidenced, adjudicated, capped at 3 findings per its own
format) — never silently merged into Standards, and never skipped because
the skill file you loaded didn't mention it. Confirmed live 2026-08-28: a
Claude session ran `/code-review` with only the two axes the skill file
lists, missing this CLAUDE.md rule entirely until the user asked "what
happened to the GoF review" after the fact — the skill file's own steps are
not a complete checklist for this repo without this rule layered on top,
every time, not just when remembered.

## Agent skills

### Issue tracker

Issues and Wayfinder maps are tracked as local Markdown under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The default five-role triage vocabulary is used. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository using root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.
