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
not limited to: the `snowconn` SnowCLI connection convention,
`EDGARTOOLS_DEV_LOADER`/`EDGARTOOLS_DEV_DEPLOYER` role references, `dbt run --target dev` (the default target), and the
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
| ETL runtime (form parsing, S3 writes) | `edgar_warehouse/application/warehouse_orchestrator.py` (`edgar_warehouse/runtime.py` is a pure re-export shim onto `edgar_warehouse/application/command_router.py`, which is real but thin: its own `run_command`/`run_seed_universe_command` route through `LEGACY_COMMAND_REGISTRY`/`execute_standard_command`, ultimately calling `warehouse_orchestrator._execute_warehouse` -- confirmed live 2026-09-02 while tracing `bootstrap`'s full call chain for its retirement, correcting this table's prior "both are compatibility shims re-exporting from here" claim) |
| Silver write path (landing-only writers, in-run lookup) | `edgar_warehouse/silver_landing_store.py` (`SilverLandingStore`; the local DuckDB engine, `silver_store.py`/`silver_protection.py`/the `silver.py` shim, was deleted by silver-merge-engine-migration Ticket 17, 2026-09-15 — there is no local silver store any more). Schema snapshot: `edgar_warehouse/silver_schema.py`, held equal to `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql` by `tests/unit/test_silver_schema_snapshot.py` |
| Source-layer dimensional export (feeds `EDGARTOOLS_SOURCE`, not `EDGARTOOLS_GOLD` — see single-path-per-layer map Ticket 01, which is why this module was renamed off its old "gold_models.py" name) | `edgar_warehouse/serving/source_dimensional_export.py` (its `edgar_warehouse/gold.py` compatibility shim was deleted in PR #550, 2026-09-06 — zero importers repo-wide; the module's own DuckDB-materialized builders were retired the same commit since every dbt gold model now `ref()`s dbt silver directly) |
| Ownership / Form 3-4-5 parser | `edgar_warehouse/parsers/ownership.py` |
| ADV parser (investment advisers) | `edgar_warehouse/parsers/adv.py` |
| CLI entry point | `edgar_warehouse/cli.py` |
| Batch scripts per form type | `scripts/batch/` |
| dbt gold models (23 dynamic tables — the actual gold layer) | `infra/snowflake/dbt/edgartools_gold/models/gold/` |
| Snowflake bootstrap SQL | `infra/snowflake/sql/bootstrap/` |
| MDM graph (Snowflake-hosted, NOT external Neo4j) | `edgar_warehouse/mdm/graph_readonly.py`, `mdm publish-relationships`/`mdm reconcile` CLI, `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` |
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
      |                          (the only silver store: every writer records
      |                           to the landing zone via
      |                           edgar_warehouse/silver_landing_store.py and
      |                           the dbt silver models collapse it; the local
      |                           DuckDB engine was deleted 2026-09-15,
      |                           silver-merge-engine-migration Ticket 17)
      |
      +-------------------------------------------------+
      |                                                  |
      v                                                  v
dbt (infra/snowflake/dbt/edgartools_gold/)      MDM Postgres (Snowflake-hosted, NOT AWS
      |                                          RDS -- see "MDM database" note below)
      v                                          entity resolution: edgar_warehouse/mdm/
EDGARTOOLS_GOLD  (23 dynamic tables)              ("mdm mastering", 6 entity types)
      |                                                  |
      v                                       +----------+-----------+
Streamlit dashboard                            |                      |
(infra/snowflake/streamlit/                    v                      v
 OR examples/dashboard/)              Snowflake                Snowflake
                                       NEO4J_GRAPH_MIGRATION    MDM mirror schema
                                       schema -- Neo4j Graph    ("mdm publish",
                                       Analytics Native App,    edgar_warehouse/
                                       NOT an external Neo4j    mdm/export.py)
                                       ("mdm publish-relationships" /
                                       "mdm reconcile" --
                                       see "Graph storage"
                                       note below)
                                             |
                                             v
                                       Operator MDM/graph review
                                       dashboard
                                       (examples/mdm_graph_dashboard/)
```

MDM's own silver reader is **always** Snowflake `EDGARTOOLS_SILVER` via
`SnowflakeSilverReader` (`edgar_warehouse/mdm/cli.py`'s `_silver_reader()`
docstring is explicit: "Always EDGARTOOLS_SILVER via SnowflakeSilverReader")
— cut over live-verified 2026-09-06 (duckdb-retirement-cutover Ticket 05).
The DuckDB-vs-Snowflake parity commands (`mdm verify-silver-parity`,
`mdm verify-resolver-input-parity`) and their DuckDB reader path were
deleted by silver-merge-engine-migration Ticket 08; DuckDB's
`ShardedSilverReader` and the one-time `backfill-silver-landing-historical`
command were deleted by that map's Ticket 15 (2026-09-15), and the DuckDB
engine itself (`silver_store.py`, `silver_protection.py`, the `duckdb`
dependency) by Ticket 17 the same day — no production module imports DuckDB,
and once the images are rebuilt from that change neither image installs it (it survives in `uv.lock` only as `splink`'s
transitive dependency under the `mdm` extra, which no image installs). MDM
resolves entities independently of the gold/dbt path — the two branches
above run in parallel, not in sequence. See "Graph storage" and "MDM
database" notes further below for what each Snowflake-hosted piece
actually is, since both names ("Neo4j", "Postgres mirror") suggest
external services that don't exist here.

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
| **Silver** | Snowflake `EDGARTOOLS_SILVER` (landing zone `EDGARTOOLS_SILVER_LANDING` + dbt collapse). Writers: `edgar_warehouse/silver_landing_store.py`. | Cleaned, typed, deduplicated records. The local DuckDB store that used to be canonical is gone (silver-merge-engine-migration, finished with Ticket 17 on 2026-09-15). |
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
4. If the issue is non-trivial or likely to recur, document only the final
   conclusion in this file or `TODOS.md` so future sessions don't re-debug
   it from scratch — the numbered why-by-why walkthrough is scaffolding for
   *finding* the root cause, not something a future reader needs preserved.
   Write: **Problem** (1 sentence), **Root cause** (1 sentence), **Fix**
   (1 sentence — the actual code/infra change), **Lesson** (1-2 sentences —
   the reusable insight, especially if it names a pattern repeated
   elsewhere in this file), plus any ticket/file links. 4-8 lines total,
   not a full incident narrative.

## Hard-won operational rules

Distilled from ~40 resolved incidents whose full write-ups were pruned from this file on 2026-09-17 —
the reusable constraint is kept, the narrative is not. Ticket detail lives under `.scratch/` and in git
history (`git log -S '<symbol>' -- CLAUDE.md`).

**Snowflake — SQL, objects, cost**

- Do not use the shorthand multi-column `FOR row IN (SELECT a, b, ...) DO` cursor form in this account —
  it fails with `Unsupported: Scalar subquery with multi-column SELECT clause`. Use an explicit
  `DECLARE ... CURSOR ... OPEN ... FOR i IN 1 TO <precomputed COUNT(*)> DO FETCH ... END FOR` (a "loop
  until FETCH returns nothing" pattern hangs and needs `SYSTEM$CANCEL_QUERY`). Live in
  `04_refresh_wrapper.sql`.
- `GRANT OWNERSHIP ... REVOKE CURRENT GRANTS` strips *all* outbound grants, not just the previous
  owner's — it once silently dropped the dashboard reader role's `SELECT` on all 20 gold tables. Use
  `COPY CURRENT GRANTS`, or additive `GRANT ... ON ALL/FUTURE TABLES`.
- `NOW()` is rejected in a column `DEFAULT` clause specifically (it works fine as an ordinary function
  call) — use `CURRENT_TIMESTAMP()`.
- `CREATE SCHEMA IF NOT EXISTS` evaluates the `CREATE SCHEMA` privilege *before* checking whether the
  schema already exists, so pre-creating it as `ACCOUNTADMIN` does not let an under-privileged role skip
  the check.
- Streamlit-in-Snowflake apps run with the app **owner's** privileges, and
  `GRANT/REVOKE OWNERSHIP ON STREAMLIT` is unsupported — ownership is fixed at creation. The only way to
  change it is to create the object while running *as* the target role. Terraform tracks no owner
  attribute, so any `-replace`/destroy-recreate silently reverts ownership to the admin role and
  `infra/snowflake/sql/graph_review/02_dashboard_reader_grants.sql` must be re-run. Check
  `SHOW STREAMLITS`' `owner` column before trusting any "access limited to a dedicated read role" claim.
- Before adding any new Snowflake `TASK`: a fixed-interval poll task pays a per-resume warehouse charge
  close to every tick unless the interval is wide enough for a real suspend in between. Size it against an
  explicit credit budget up front, or gate it (`WHEN SYSTEM$STREAM_HAS_DATA(...)`) — never ship a "tune
  later" cadence. `LOAD_SILVER_LANDING_TASK` ran at 5 MIN (~9 credits/day) until this was caught; it is
  now 180 MIN.
- Loading Parquet with `USE_LOGICAL_TYPE = false` reads a UTC timestamp as zone-less clock time and labels
  it with the session `TIMEZONE`, defaulting to `America/Los_Angeles`. Pin `TIMEZONE = 'UTC'` on every
  loading session, including owner's-rights procedures, which run with the *caller's* timezone. Guarded by
  `tests/unit/test_loader_task_timezone_sql.py`.
- `snowflake-connector-python` reads the module-global `paramstyle` once, at `connect()` time, and caches
  it on the connection — mutating the global afterward has no effect. Use the shared
  `connect_with_qmark_paramstyle()` for `?`-style placeholders.
- `EDGARTOOLS_PROD_LOADER` is the single runtime role for `mdm export`, `mdm sync-graph` and
  `mdm verify-graph` (all three read the same `MDM_SNOWFLAKE_SECRET_JSON`), and it also owns the gold
  objects `REFRESH_AFTER_LOAD` refreshes, so it needs `OPERATE` + `SELECT` on everything a gold model
  references, `EDGARTOOLS_SILVER` included. That secret's `MDM_SNOWFLAKE_SCHEMA` must stay
  `EDGARTOOLS_GOLD`: the mirror writer hardcodes its own `MDM` schema and the graph commands fully
  qualify, so the default golden-record writer is the field's only real consumer.

**Postgres / MDM**

- `mdm migrate` does not run automatically on deploy. Treat any prod deploy carrying new migration files
  as incomplete until it has been re-run explicitly — "the image is current" and "the migration was
  applied" are separate facts.
- Test every migration against a genuinely **populated** table. An empty-table-only suite is unproven for
  exactly what migrations exist to do, and has shipped real breakage here more than once.
- Postgres cannot defer a **partial** unique index (only a full-table `UNIQUE`/`PRIMARY KEY` backed by a
  non-partial index can be `DEFERRABLE`), so it is checked at every row-level UPDATE — order and flush
  multi-row status transitions explicitly instead of trusting SQLAlchemy's unit-of-work ordering.
- Guard each privileged `GRANT` in a migration with an "already satisfied" check, or a rerun by a role
  that holds the membership without ADMIN OPTION is rejected outright.
- Snowflake-hosted Postgres re-grants `snowflake_write`'s baseline DML as a platform side effect of
  `ALTER POSTGRES INSTANCE ... RESET ACCESS FOR '<role>'` for *either* role, so `bootstrap-prod-mdm.sh`
  runs `mdm migrate` as its true last database-mutating step. `mdm check-fence`
  (`edgar_warehouse/mdm/fence_monitor.py`) discovers the fenced table set live and verifies no leak.
- SQLAlchemy's `Session` never auto-commits, and a logged "succeeded" is not evidence of a durable write.
  Commit only once the work a checkpoint claims is itself durable, and roll staged state back on failure.
- Memoize invariant lookups per batch, and bulk-prefetch/bulk-flush per-row round trips. This N+1 shape
  has been found and fixed at least five separate times in this codebase — assume any newly-added batch
  path has it until a real run at scale says otherwise. SQLite-backed unit tests never surface it.
- MDM chain runtime is ~60-70 min end to end; `Reconcile` (~21 min) and `Publish` (~19 min) are ~65% of it
  and are Snowflake-side work. Relationship derivation (~15 min, bounded by
  `MDM_RELATIONSHIP_CONCURRENCY`, default 4) is no longer the bottleneck — optimise the Snowflake stages,
  not derivation.

**Pipeline / runtime**

- A bounded CIK input does not imply a bounded artifact input — carry the daily index's exact accession
  union through submissions refresh, intersect form selection against it, and fail closed on expansion,
  retry exhaustion or an opened circuit.
- Key idempotency on the durable artifact (the bronze S3 object), not on bookkeeping a crash can discard.
  `write_immutable_bytes` is the only writer to a canonical bronze key and enforces content-identity
  atomically at write time (conditional PUT, `IfNoneMatch: *`).
- Recurring runs abort only on `unresolved_errors`: oversized responses
  (`WAREHOUSE_SEC_MAX_RESPONSE_BYTES`, now 150MB) and immutable-object conflicts are isolated,
  individually-recoverable skips. Any *unclassified* error still fails the run closed.
- Any "same calendar day" check needs an explicit timezone, and the right one is the business
  process's — `America/New_York` via `pytz` (`zoneinfo` needs a tz database these images don't install).
- A one-time backfill CLI's `--dry-run` needs a `--limit` from the start: proving the logic on real data
  needs tens of rows; only estimating full-run cost needs the whole table.
- Before hand-orchestrating a multi-step prod workflow with raw `aws ecs run-task`, check
  `aws stepfunctions list-state-machines` — a purpose-built, already-proven machine for the task can exist
  without being referenced in this file.
- Provisioning that isn't Terraform or a committed script does not survive an account rebuild, however
  carefully a runbook describes it. And when one stage turns out to have been an uncommitted manual step,
  assume every later stage in the same family is too.
- A check that can silently run against stale, superseded infrastructure makes a false positive and a
  false negative look identical to success. Confirm the *code* under test is what is actually running
  before treating a clean result as evidence — a SQL contract "applied successfully" says nothing about
  the image that writes to it.
- A pre-code `/gof-refactor-reviewer` consult can bless an architecture while the concrete diff still gets
  a load-bearing detail wrong. The mandatory post-diff 3-axis `/code-review` is what catches those.

**Security — handling credentials**

- Never pipe `snow sql ... RESET ACCESS` or `aws secretsmanager get-secret-value` output to
  `head`/`tail`/`cat`/a bare variable capture, for any reason including debugging a downstream parsing
  error — pipe straight into the credential-consuming script and put debug output (`type(pw)`, length,
  key presence) *inside* that script. This leaked a live plaintext password into a transcript twice in one
  session.

**Test baseline**

- The 8 `tests/integration/test_acquisition_ledger_postgres.py`/`test_conflict_postgres.py` Postgres
  schema-drift failures against the local test-Postgres instance, and the `fastapi` import-collection
  errors in `tests/mdm/test_api.py`, `test_temporal_graph_queries.py` and `test_runtime_ops.py`, are
  pre-existing and unrelated to any current change. "Green except these" is the normal baseline.

## Known open items

Deploy status below is as last recorded on each item's own date — re-check against the running image
before trusting it.

- **Two graph-generation activation paths are out of sync.** `mdm publish-relationships` →
  `mdm reconcile --generation-id` → `mdm graph-activate` flips Snowflake's `GRAPH_ACTIVE_POINTER` with no
  Postgres record; the `edgartools-prod-generation-build` Step Function tracks every step in
  `mdm_graph_generation`/`mdm_graph_partition`. Both write the same Snowflake tables. Snowflake's pointer
  correctly shows `db802e24-...`, but Postgres still shows `9bc1d71d-...` as `activated` with no row for
  the live generation — so the next Step Function run would plan off a stale baseline, and anything
  reading Postgres for "what's active" reports the wrong one. Fix by re-running
  `edgartools-prod-generation-build` or backfilling the Postgres row.
- **The `EDGARTOOLS_DECISION` schema does not exist**, leaving 5 Terraform-managed grants unapplied.
  `infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql`'s "MDM active-company universe"
  join is an explicit placeholder that self-joins `COMPANY`, and
  `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql`'s `BUNDLE_AUDITOR` references
  `EDGARTOOLS_GOLD.SEC_AUDITOR_REPORT_EVIDENCE`, which exists only in `EDGARTOOLS_SOURCE`. The real
  blocker behind both: no Snowflake-side source has been chosen for "MDM active company universe" (MDM's
  authority is Postgres; the closest reflection is `NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES`).
- **Orphaned bootstrap SQL:** `infra/snowflake/sql/bootstrap/16_silver_landing_deployer_read.sql` and
  `17_mdm_export_deployer_read.sql` are committed, real fixes referenced by neither `install.sh` nor
  `deploy-snowflake-stack.sh`.
- **The original `EDGARTOOLS_DASHBOARD` Streamlit app is still ACCOUNTADMIN-owned** — the same gap already
  fixed for `MDM_GRAPH_DASHBOARD`, with the same drop/recreate-as-target-role recipe.
- **Release-readiness Ticket 74, items 1-2:** repairing the two known stale accessions, and a proactive
  scan for other pre-2026-07-31 stale bronze objects.
- **Ticket 101:** automated `sec_filing_text` capture is unimplemented (0 rows in prod). Its iXBRL
  hidden-content extraction fix (`_strip_hidden_ixbrl_content`,
  `edgar_warehouse/filing_text_projection.py`) is in source but was undeployed when written.
- **Migration 022** (`edgar_warehouse/mdm/migrations/022_relationship_derivation_checkpoint_cursor.sql`,
  the resumable relationship-derivation cursor) had never been run against real Postgres when written —
  confirm it applied before relying on `INSTITUTIONAL_HOLDS`/`MANAGES_FUND` making forward progress past a
  capped run. Related open fog on the
  [mdm-relationship-versioning-gap map](.scratch/mdm-relationship-versioning-gap/map.md):
  `reconciliation_pass` still restarts its own scan from the beginning on every call.
- **Written as "not yet deployed":** the `mdm_change_log` write-side diff (which otherwise regenerates
  `mdm publish`'s backlog unboundedly) and the oversized-SEC-document recurring-run fix. Confirm both are
  in the running image.

## Phased Pipeline (use this for all bootstraps ≥10 companies)

`load_history` is the canonical way to load companies at scale. Its live
`edgartools-prod-load-history` definition (re-verified via
`describe-state-machine`, not copied from an older architecture doc) runs:

```
Stage 0 — Company identity seeding (single steps, no windowing)
  SeedUniverse → MdmSeedUniverse
  • Seeds the CIK universe and MDM's own tracking state. Company entity
    *resolution* (IS_INSIDER, MANAGES_FUND, etc.) happens later, in Stage 2
    (Mastering, renamed from MdmRun by mdm-stage-renaming ticket 01) -- there
    is no separate identity-resolution state here; an
    earlier load_history shape had one (stage0-stage1-consolidation map),
    removed when Stage0CompanyIdentity/ReduceIdentityRefresh were deleted.

Stage 1 — Bronze + Silver bootstrap (windowed, MaxConcurrency=1)
  IngestBronzeAndSilver/WindowedBootstrap
  • Each window: bootstrap-next --silver-only over a CIK slice → S3 bronze, parse → Snowflake silver landing zone
  • MaxConcurrency=1 by design (concurrent writers promoting the same shared
    silver object raced and lost writes) -- windows run one at
    a time, not in parallel, regardless of BOOTSTRAP_BATCH_CONCURRENCY (see
    "Key invariants" below -- that env var does not control this Map)
  • Within each window, artifact fetching (ownership/ADV/13F documents) uses
    bounded intra-task concurrency (ThreadPoolExecutor, WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY,
    default 5) -- this is real parallelism, just not CIK-batch-level parallelism

Stage 1B — Fundamentals (windowed, MaxConcurrency=1 each, run after Stage 1)
  FetchEntityFacts → FetchPerFilingFundamentals → FetchThirteenFHoldings
  • XBRL company facts, 8-K/DEF 14A per-filing data, and 13F holdings respectively

Stage 1C — ADV bulk + Firm Roster (lenient, run after Stage 1B, not in earlier
versions of this doc -- confirmed live via describe-state-machine 2026-09-10)
  FetchAdvBulk → IngestAdvBulkSources → FetchFirmRoster → IngestFirmRosterSources
  • fetch-adv-bulk + ingest-relationship-sources (adv-fetch-pipeline-wiring spec),
    then fetch-firm-roster + ingest-relationship-sources (adv-firm-roster-crosscheck
    spec, ticket 02) -- so MDM sees fresh ADV silver and the Firm Roster completeness
    cross-check stays current in this same execution
  • All 4 states have a Catch, same leniency as Stage 1B (AD-13) -- a failure here
    doesn't abort the run, it just proceeds without fresh ADV/roster data

Stage 2 — MDM entity resolution (nested Step Functions execution, not inline states)
  RunMdmChain invokes the separate `edgartools-prod-mdm` state machine
  (startExecution.sync:2), which runs: Mastering → BackpropagateIdsToSilver →
  "Infer Relationships" → Publish → "Publish Relationships" → Reconcile
  (Reconcile has a non-fatal Catch, ReconcileFailedNonFatal -- a reconcile
  failure doesn't abort the outer `load_history` run)
  • Runs after Stage 1/1B/1C complete so entity resolution sees the full silver dataset
  • Derives IS_INSIDER, MANAGES_FUND etc. and syncs to the graph (Snowflake, not external Neo4j)
  • BackpropagateIdsToSilver (between Mastering and Infer Relationships) writes
    resolved mdm_entity_ids back to silver so relationship derivation can join
    against them -- not previously documented in this section

Stage 3 — Gold refresh (single ECS task, live state name `FactPublishtoGold`)
  gold-refresh
  • Writes Snowflake export manifests for source-layer serving exports (not the gold layer)
  • EDGARTOOLS_GOLD is 23 Snowflake dynamic tables (see Data Layer Definitions
    above for the current authoritative list -- this line previously said 21,
    stale against that same table). Live prod 2026-08-29: every
    table had TARGET_LAG=DOWNSTREAM but DYNAMIC_TABLE_REFRESH_HISTORY showed
    REFRESH_TRIGGER=MANUAL only (REFRESH_AFTER_LOAD after a run manifest).
    DOWNSTREAM does not refresh gold leaves. gold_model_config() now uses
    target_lag='6 hours' (same as silver). SNOWFLAKE_RUN_MANIFEST_TASK still
    runs LOAD_EXPORTS_FOR_RUN then REFRESH_AFTER_LOAD as an extra explicit
    trigger. The Ticket 39 completion barrier fail-closes on a stale
    data_timestamp regardless of either clock.
```

(Elsewhere in this repo, `daily_incremental`'s own Company Identity
capture stage -- a different, sibling state named `CaptureCompanyIdentityBatches`
(renamed from `ResolveCompanyIdentityBounded` for a business-readable name)
in `write_warehouse_mdm_gold_definition` -- is unrelated to `load_history`'s
Stage 0 above; it runs *before* bronze/silver capture in that pipeline,
not as a seeding step. `bootstrap` shared this same state until
state-machine-consolidation ticket 06 retired the workflow entirely.)

**`edgartools-prod-bootstrap-batched` (formerly a separate, standalone state
machine running CIK batches with real parallelism via a `BatchBootstrap`
Map, `MaxConcurrency=3`) was deleted (state-machine-consolidation wayfinder
map, ticket 03)** — it was never part of `load_history`'s call graph, had
**zero executions ever** in prod, and was architecturally superseded by
`load_history`'s sequential-windowed design, which was built specifically
to fix a `silver.duckdb` consistency race inherent to
`bootstrap_batched`'s concurrent-writer/`cik_batches.jsonl` architecture.

`edgartools-prod-silver-mdm-gold` (the standalone re-process-already-loaded-
bronze machine, `BatchSilver` Map at `MaxConcurrency=3` via
`BOOTSTRAP_BATCH_CONCURRENCY`) was retired outright (state-machine-
consolidation wayfinder map, ticket 09, 2026-09-05: zero executions ever) —
both code and the live AWS object are gone; see the "Key invariants" section
below for the full retirement note. The genuinely-parallel batch pipelines
remaining in prod are `one_click_data_refresh`'s own two `bootstrap-batch`
Maps (hardcoded `MaxConcurrency` of 20 and 2, not env-controlled) — see that
machine's own entry further below. Both reprocess already-loaded bronze (no
new SEC submissions fetched) and are unrelated to `load_history`'s own
bootstrap Stage.

`edgartools-prod-full-reconcile` (SEC-drift detection against live SEC
submissions truth) was likewise decommissioned end-to-end on 2026-09-04 on the
same evidence -- zero executions ever, no EventBridge schedule. The state
machine, the `edgar-warehouse full-reconcile` CLI command,
`application/commands/full_reconcile.py`,
`application/workflows/silver_reconcile_pipeline.py`, `edgar_warehouse/reconcile.py`
and the Postgres `SecReconcileFinding` model are all gone; `BOOKKEEPING_TABLES`
is now 10 tables, not 11. The shared `stage_*_loader` functions in
`edgar_warehouse/loaders.py` were NOT part of it and are untouched.

**Graph storage (read this before assuming "Neo4j" means an external service):**
As of the `neo4j-snowflake` workstream (v1.3, completed 2026-06-12), graph data lives
*inside* Snowflake — the Neo4j Graph Analytics Native App, installed in the same Snowflake
account as gold. There is no separate Neo4j database, no `NEO4J_URI`/`NEO4J_PASSWORD`
secret, and no external Bolt connection. `mdm publish-relationships` materializes
`MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES` (plus per-label/per-type compatibility views) into a
Snowflake schema (e.g. `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`); `mdm reconcile` runs a
strict SQL parity check plus Native App checks (compute pool, `GRAPH_INFO`, `BFS`, `WCC`)
against that same Snowflake target. One credential (the same `MDM_SNOWFLAKE_*`/
`DBT_SNOWFLAKE_*`/Snowflake CLI connection used everywhere else), one platform. Native App
grants: `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`.

**Publishing is generation-scoped, not a direct overwrite** (`edgar_warehouse/mdm/
snowflake_graph.py`): `mdm publish-relationships` always materializes into a
**new** `GRAPH_GENERATION` row, `STATUS` defaulting to `'building'`
(`GENERATION_STATUSES = ("building", "verified", "activated", "retired",
"failed")`) — pass `--generation-id` to target a specific one, otherwise a
fresh UUID is minted; publishing alone never makes it live. `mdm reconcile
--generation-id <id>` verifies that specific generation and, on pass,
promotes it `'building' → 'verified'` (the only status `graph-activate`
accepts); on fail, demotes it to `'failed'`. `mdm graph-activate
--generation-id <id>` is the final step: atomically flips
`GRAPH_ACTIVE_POINTER` to the target generation, retires whichever
generation was previously `'activated'`, and promotes the target to
`'activated'` — all inside one `BEGIN`/`COMMIT` so a crash mid-flip can't
leave the pointer referencing a generation whose own status wasn't updated
to match. `mdm reconcile` with no `--generation-id` instead verifies
whatever generation the pointer currently targets.

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
`edgar_warehouse/mdm/graph_review_publish.py` persists `mdm reconcile`'s
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
| Daily incremental (ongoing) | `daily_incremental` Step Function |

(`bootstrap` -- recent-N-filings-per-active-company, formerly listed here as
"Recent filings only (fast)" -- was retired by state-machine-consolidation
ticket 06: zero EventBridge schedule, exactly one execution ever, and it
shared `daily_incremental`'s exact Step Functions shape via the same
`write_warehouse_mdm_gold_definition` builder, differing only in company
selection logic -- recency-capped per company vs. `daily_incremental`'s
SEC-daily-index-driven discovery. `daily_incremental` is the sole remaining
Warehouse Pipeline Machine and structurally supersedes it for ongoing use;
`bootstrap-full`/`bootstrap-next` remain for full-history loads.)

**Running `load_history` via Step Functions:**

```bash
aws stepfunctions start-execution \
  --region us-east-1 \
  --state-machine-arn arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-prod-load-history \
  --name "load-history-$(date +%s)" \
  --input '{}'
# NOTE: the dev ARN this example previously used (edgartools-dev-load-history)
# no longer exists -- AWS-side dev was decommissioned (see the account map at
# the top of this file); confirmed live 2026-09-10 via list-state-machines,
# zero edgartools-dev-* state machines remain. prod is the only live target.
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
backoff on `WindowedBootstrap`), correct Stage 0/1/1B/1C/2/3 sequencing (identity before
ownership/ADV, MDM after silver is complete, gold last), and the cross-command
`sec_fetch_active` lease that prevents it from racing a concurrently-running
`daily_incremental`/`bootstrap`/etc. Reserve `bootstrap-next` for single-company ad-hoc
loads with explicit `--cik-list`. (Historical note: this guidance originally also cited
"cannot reach MDM Postgres, private VPC" — that no longer applies. MDM Postgres moved off
AWS RDS onto Snowflake's native Postgres service; see "MDM database" note below. Local
reachability to the current Snowflake-hosted instance has not been re-verified.)

**Key invariants (do not break):**

`silver_mdm_gold` (the standalone re-process-already-loaded-bronze machine
this section used to document, `BatchSilver` Map at `MaxConcurrency=3` via
`BOOTSTRAP_BATCH_CONCURRENCY`) was retired outright (state-machine-
consolidation wayfinder map, ticket 09, 2026-09-05: zero executions ever) —
deleted, not modified. `BOOTSTRAP_BATCH_CONCURRENCY` had exactly one real
consumer (that machine's `BatchSilver` Map); the other two `bootstrap-batch`
callers inside `write_one_click_data_refresh_definition` received the env
var but never read it (their `MaxConcurrency` was always hardcoded — 20 for
the "first-load recovery" Map, 2 for the Ticket 20 strict candidate-manifest
Map, since deleted with release mode by silver-merge-engine-migration Ticket 11).
With its one real consumer gone, the env var/CLI flag were removed
entirely from `deploy-aws-application.sh`, not left as dead plumbing.

Neither `one_click_data_refresh`'s `bootstrap-batch` Map(s) nor
`load_history` (which runs `bootstrap-next`, a different command, per
window at `MaxConcurrency=1`) were ever controlled by this env var — their
`MaxConcurrency` values are unaffected by its removal. The old standalone
`edgartools-prod-bootstrap-batched` machine (also ran `bootstrap-batch`) was
separately deleted earlier (zero executions ever; superseded by
`load_history`'s sequential-windowed design — see the "Phased Pipeline"
note above and state-machine-consolidation wayfinder map ticket 03).

- `bootstrap-batch` must NOT be in `SOURCE_EXPORT_COMMANDS` (renamed from `GOLD_AFFECTING_COMMANDS`, single-path-per-layer map — the commands it gates build a source-layer export, not gold) — enforced in `warehouse_orchestrator.py:85`
- `gold-refresh` must be in `SOURCE_EXPORT_COMMANDS` — it is the sole gold builder in the phased pipeline
- `SNOWFLAKE_RUN_MANIFEST_TASK` must be STARTED in `EDGARTOOLS_GOLD` — verify with
  `snow sql --connection edgartools-dev -q "SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK'"`
- `one_click_data_refresh`'s `bootstrap-batch` Map must keep passing `--artifact-policy skip`
  where documented above — without it the pipeline makes thousands of SEC API calls (fetching
  ownership XMLs) even though the purpose of that path is to reprocess already-loaded bronze
  with zero SEC calls. 5-why root cause: the artifact pipeline is a separate SEC fetch pass;
  "no SEC calls" must be encoded as a flag, not assumed from the pipeline name.
- **Do not manually kick off `one_click_data_refresh`'s default path
  (`{"batch_size": 100}`) while `daily_incremental` is
  running.** Confirmed live 2026-09-06: a manual run
  (`one-click-data-refresh-verify-1788697757`, 08:29-10:41 ET) overlapped
  almost exactly with that day's scheduled `daily_incremental` run
  (`edgartools-prod-daily-incremental-refresh`, `cron(0 12 ? * MON-SAT *)` =
  8am ET, ran 08:00-10:44 ET) and failed with
  `States.ExceedToleratedFailureThreshold` — both failed Map items crashed
  with `s3fs.utils.FileExpired` on the canonical `silver.duckdb` object,
  meaning some writer replaced it mid-download of another reader's hydrate
  step. This mitigation is **partial, not a full fix**: a 7-day CloudWatch
  log sweep found the same `FileExpired` signature recurring across ~38
  distinct ECS tasks within that one run alone, a rate at least as
  consistent with `one_click_data_refresh`'s own 20 concurrent
  `bootstrap-batch` workers racing each other's hydrate/publish cycles as
  with `daily_incremental`'s overlap — the two weren't distinguished by this
  investigation. Avoiding the overlap removes one contributing writer but
  may not eliminate the race. See
  `.scratch/state-machine-consolidation/issues/11-decide-bronze-seed-silver-gold-default-path-fate.md`
  and `.scratch/state-machine-consolidation/issues/14-fix-monolith-silver-hydrate-fileexpired-race.md`
  for the full evidence and open follow-up.

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
| `edgar_warehouse/application/warehouse_orchestrator.py` | ~290 KB | Core ETL loop, form dispatch, S3 writes, landing-export flush. `edgar_warehouse/runtime.py` is a pure re-export shim; `edgar_warehouse/application/command_router.py` is a real (if thin) routing facade that ultimately delegates here (see Quick Navigation above for the exact chain) — this table previously pointed at both as pure shims with stale sizes copied from an earlier version of this file. |
| `edgar_warehouse/serving/source_dimensional_export.py` | ~63 KB | Builds a source-layer dimensional export consumed by dbt — not the gold layer itself (see Quick Navigation above and `.scratch/single-path-per-layer/issues/01-enumerate-layer-transitions.md`; renamed off "gold_models.py" for exactly this reason). |

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
