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
- Another runtime's open PR or worktree is not edited directly; build on it once it merges.
- Use separate GSD workstream directories under `.planning/workstreams/<name>/`; do not edit another runtime's active workstream files.
- Before editing, run `git status --short` and `git log -1` and inspect
  `.planning/active-workstream` when present.
- Avoid overlapping source files, Terraform roots, generated application JSON, and planning artifacts across runtimes unless the user assigns the same task to both.
- If overlap is unavoidable, stop and ask for an ownership decision instead of merging assumptions.
- Do not overwrite, revert, stage, or commit changes created by another runtime unless explicitly instructed.

## Shared local data (operator, 2026-10-16)

For recurring loads, delivery readiness, file changes, resource sizing and run
recovery, use [data-operations](skills/data-operations/SKILL.md).

- Initial and daily runs enumerate the entire available source delivery
  (operator: "always load everything from source"). The Change Journal skips
  files already processed with the same source, key, content hash and processing
  identity. Changed rules or relevant shared inputs also require reprocessing.
  Leave `--all` off for normal runs; use it only for an explicit forced replay.
  Read [the load sequence](docs/initial-and-daily-source-load.md) before SEC,
  GLEIF or OpenFIGI loads. Provider access retains its existing authorization.
- Use one permanent local PostgreSQL 16 server shared by all agents. Initialize
  MDM, RDM, Rules, Bookkeeping and Change Journal by default; retain existing
  silver without initializing or migrating it.
  All agents look up the same Company identities in the shared MDM.
  The server runs on the Docker context already configured on the machine
  (operator, 2026-10-17). Start, inspect, back up and copy it with
  `infra/scripts/local-test-stores.py`. The procedure is
  [Initialize shared local PostgreSQL](docs/local-agent-testing.md).
  Source its private `worker.env` before work and `verifier.env` before verification.
- Separate Git worktrees isolate code edits; routine lookups and development
  use the existing shared server, without creating a server per agent.
  Use its private runtime connection file outside Git; never print its values.
- Master data changes go through the Merge Stage. Other writes use each
  store's normal application code and restricted roles. Coordinate changes
  to shared schemas, rules and records so agents do not overwrite each other.
- Use a separate test environment only when a test could disrupt shared data,
  such as deleting records, testing recovery or applying experimental migrations.
- Coordinate shared-server maintenance with its current users. Keep lifecycle
  commands with the creating worktree; client access from other worktrees is
  allowed. Never stop, restore or replace shared data while others use it.
- This shared-server default supersedes the per-agent-copy default in local
  testing guides and skills. Their backup and copy procedures remain available
  for isolated tests. Local testing does not qualify a Snowflake deployment.

## Path ownership (operator, 2026-10-16)

Nothing is owned by Codex (operator, 2026-10-16: "nothing is owned by codex";
it replaces the 2026-10-04 table that split paths between Claude and Codex).
Any runtime edits any path. Run the guard before every commit and push:
`bash scripts/dev/overlap_guard.sh` (exit 0 = no overlap; exit 1 lists each
file an open PR or worktree of another runtime also touches). On an overlap,
build on that work once it merges, or rebase onto it; never edit beside it.
Run it on its own, never piped (`guard | tail -1 && git commit` takes `tail`'s
exit status, so a STOP lets the commit and push run; it did, 2026-10-22).

## Task checklists (MUST, every ticket, every runtime)

**HARD RULE: every ticket keeps its parts as a Markdown checklist in the
ticket file itself, and keeps it current until the ticket closes, including
while completing it.** No exception for small tickets or "last step" work.
Operator rule, 2026-09-24.

- List every part before starting: `- [ ] <part>`. Add parts that surface
  mid-work (a decision the user took, a finding, a follow-up) as they appear.
- Tick a part only when it is done and verified: `- [x] <part>`, naming how it
  was verified (test, PR, live check) on the same line.
- A part that is skipped, deferred or moved to another ticket stays on the
  list, marked `- [ ] ~~<part>~~ deferred to <ticket>: <why>`. Never delete it.
- Before reporting a ticket complete, re-read its checklist. Any unchecked part
  means the report says "incomplete" and names it.

**Time matters.** Stamp each checked part with its completion time in local
ET (`2026-09-24 14:05 ET`), never UTC. Say up front when a part will take long
(a full scan, a large test suite, a deploy), and report the elapsed time of any
step over ten minutes, so the operator can see where the time went.

- **Read the clock before every stamp:** `TZ=America/New_York date`. A
  guessed time is wrong more often than not.
- **The last part of every ticket is `Learning → skill`.** Name the skill
  line the ticket changed with what it learned, or write "none". A rule,
  practice or how-to learned here belongs in a skill (data work, MDM
  engineering) or in this file (how to work in this repo), never only in a
  ticket or in one runtime's private memory. A skill issue found while
  working is fixed in the skill, on its own branch and PR.

## How to work in this repo (every runtime)

Learned the hard way; each is a standing operator rule.

**Tests and CI**
- Run only the tests a change can affect ("Test baseline", below). No local
  test run may take more than five minutes; CI runs everything.
- Merge when every CI check is green and the PR is ready, without asking:
  merging is automatic (operator, 2026-10-17: "auto merge and not ask for
  approval"). Watch CI, merge on green, and report the merge.
- Green means green on today's `main`: a PR whose base moved since its CI ran is
  updated (`gh pr update-branch`) and waits for CI again before it merges; two
  PRs each green alone broke `main` together (2026-10-18).
- A test states its expected answer; it never compares with a frozen copy of
  retired code. To retire such an oracle, write its answers into the test (or an
  answer file written once while the two still agree), change each answer once
  to see the test fail, and compute any value that follows the clock (ticket 88).
- A conclusion reached by reading code is not proof of behaviour: test each
  case the claim covers (one test per kind, per source), since the untested
  case is where a gap hides.
- Every background watcher (CI, a long test, a proof) has a deadline and an
  exit for every outcome, including the PR merging or closing. Stop test
  containers when a run ends, however it ends. macOS has no `timeout`
  command (a watcher wrapped in it exits at once and does nothing); give the
  deadline with a background `sleep N; kill <pid>` instead.
- Choose the cheapest proof that proves the change (the `mdm-engineering`
  skill, "Choose the cheapest proof"); say the time of any step over ten
  minutes before starting it.

**Commits, PRs and secrets**
- One branch per ticket, cut fresh off `origin/main` in its own worktree;
  never continue a ticket on a used or merged branch (PRs are squash-merged).
- Work only in this repository. Never commit, push or open a PR in another
  repository, even for a task that spans repositories.
- Commit and PR text from a file ("Git/GitHub commit and PR text with
  backticks", below).
- Never print a secret, a password, a token or a database address, and never
  ask the operator to type one into the chat. Read them from environment
  variables; if one is missing, ask the operator to set it in their own
  terminal. Redact by key name (any key containing `password`, `secret`,
  `token`, `key`, `dsn` or `url`), never by an exact list, and never pipe a
  secrets fetch to `head`, `cat` or a variable you print.
- This repository is public: counts and invented examples only, never a
  value from the data (a name, an identifier, a record).
- No request to a data provider (its site, API or documentation) without the
  operator's permission for that request.

**Talking with the operator**
- Every time shown to the operator is local ET, including times read from
  AWS, Postgres or CI, which report UTC.
- Report findings with their numbers and what they mean, not the steps you
  are about to take.
- Use the business words of `CONTEXT.md`; translate engine terms first (a
  "matching rule", not a "binding rule").
- Do not ask for approval (operator, 2026-10-17: "auto merge and not ask for
  approval"). Where a step or a skill needs an approval, record it as given
  under this rule, with these words and the ET time, and say in plain words
  what was approved, what it changes and on what evidence. A digest, hash or
  version number goes beside the explanation, never instead of it. A rule
  version has a descriptive name.
- Decide what follows from a ruling already given, say so, and go on. Stop
  only for a switch-on or a new kind of decision, and then ask one question
  at a time with your recommendation.

**Stores**
- Writes into Snowflake's SQL layer go through dbt. MDM's own Postgres store
  is written by its own code (SQLAlchemy), not dbt.

**Debugging**
- Root cause first ("Debugging discipline: 5-whys", below); write a recurring
  lesson where it belongs: a skill, or this file.

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

The rebuild replaced the old pipeline (its orchestrator, parsers, DuckDB silver,
graph writers and Step Function builders are deleted; check with
`python3 scripts/dev/stale_paths.py`). The skills hold the how-to; this table
only points.

| Need | Location |
|------|----------|
| Source engine (reading and combining files; Rust behind a Python facade) | `crates/source-contract/`, `edgar_warehouse/rules/source_engine.py`; skill `data-platform` (READING.md, COMBINING.md) |
| Rules: source extracts, Dataset Contracts, quality, merge rules, identifier types | `rules/` (YAML people edit, reviewed in PRs), read by `edgar_warehouse/rules/files.py` |
| Workers and Bookkeeping (each step a worker with its verifier) | `edgar_warehouse/workers/`, `edgar_warehouse/bookkeeping/`; skill `bookkeeping` |
| MDM store and the Merge Stage | `edgar_warehouse/mdm/clean/` (`merge.py`, `binding.py`, `store.py`), migrations in `edgar_warehouse/mdm/migrations/`; skill `mdm-engineering` |
| RDM (reference data) | `edgar_warehouse/rdm/` |
| Silver writer (a PostgreSQL 16 `silver` schema through one sink) | `edgar_warehouse/silver_writer/` |
| Agent context (`edgar-warehouse context`) | `edgar_warehouse/context.py` |
| CLI entry point | `edgar_warehouse/cli.py` |
| Onboard a new feed or domain / refine live rules | `skills/data-onboarding/SKILL.md` (+ `REFERENCE.md`, `APPROVE.md`) and `skills/refining-rules/SKILL.md`; logs under `.scratch/onboarding/<source>/` |
| Silver schema snapshot (Snowflake landing) | `edgar_warehouse/silver_schema.py`, held equal to `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql` by `tests/unit/test_silver_schema_snapshot.py` |
| dbt gold models | `infra/snowflake/dbt/edgartools_gold/models/gold/` |
| Snowflake bootstrap SQL | `infra/snowflake/sql/bootstrap/` |
| MDM graph tables (Snowflake `NEO4J_GRAPH_MIGRATION`, still read by the live dashboard; their writers were retired, platform validation 2a/2b, 2026-09-30) | `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`, `infra/scripts/install-neo4j-graph-app.sh` |
| Streamlit-in-Snowflake dashboard | `infra/snowflake/streamlit/streamlit_app.py` |
| Standalone Streamlit dashboard | `examples/dashboard/edgar_universe_dashboard.py` |
| Batch scripts per form type (edgartools smoke tests) | `scripts/batch/` |
| AWS Terraform (prod) | `infra/terraform/accounts/prod/` |
| Snowflake Terraform (prod) | `infra/terraform/snowflake/accounts/prod/` |
| Docker / ECR publish scripts | `infra/scripts/` |
| Shared local PostgreSQL (MDM, RDM, Rules, Bookkeeping, Change Journal) | `docs/local-agent-testing.md`, `infra/scripts/local-test-stores.py` |

## Architecture

```
captured provider files (bronze; SEC, GLEIF, Form ADV, N-PORT, OpenFIGI, ...)
      |
      v
source engine: source extracts and combines   (rules/sources/<source>/*.yaml)
      |
      v
Dataset Contracts -> MDM (PostgreSQL; the Merge Stage, merge rules in rules/merge/)
      |                     |
      v                     v
silver writer          edgar-warehouse context (read-only views for agents)
(transaction parts)
```

Every step runs as a Bookkeeping worker with its verifier. MDM's store is
PostgreSQL 16; the hosted target is Snowflake Postgres or Databricks Lakebase, and today's provisioned
instance is Snowflake Postgres (below).
Snowflake stays the target platform for silver and gold (operator,
2026-10-14: "Snowflake is still the target platform"): the Snowflake layers
below, the dbt gold models and their rules in this file are live. The old
pipeline that fed them (the warehouse orchestrator, its parsers, the old MDM
chain and the AWS Step Function builders) is deleted from this repository.

## ECS cost sizing (old pipeline)

The ECS sizing study (Ticket 28, 2026-08-30) measured MDM commands of the old
pipeline, since deleted; its method stays valid for a future worker runtime:
judge a cheaper profile on validated output (correctness, completeness,
idempotency across reruns, a matched control on the same input), never on
memory use or an exit code. Evidence:
`.scratch/ecs-cost-sizing/issues/28-run-mdm-residual-security-medium-canaries-and-unbounded-graph-sync-canary.md`,
`.scratch/ecs-cost-sizing/evidence/ticket28/`.

## Data Layer Definitions

| Layer | Location | Description |
|-------|----------|-------------|
| **Bronze** | S3 (`s3://<bucket>/`) and local captures | Provider files as captured, one receipt per file. Never mutated. |
| **Source** | Snowflake `EDGARTOOLS_SOURCE` | External stage + tables auto-refreshed from S3 via Snowflake native S3 pull (bootstrap SQL). Read-only raw layer. |
| **Silver** | Snowflake `EDGARTOOLS_SILVER` (landing zone `EDGARTOOLS_SILVER_LANDING` + dbt collapse); the rebuild's writer is `edgar_warehouse/silver_writer/` (PostgreSQL 16 today; a Snowflake sink is its own ticket) | Cleaned, typed, deduplicated records. The old landing writer and the local DuckDB store are deleted. |
| **Gold** | `EDGARTOOLS_GOLD` (23 dbt dynamic tables) | Business-ready tables, e.g. `company`, `ownership_holdings`, `ownership_activity`, `filing_detail`, `filing_activity`, `adviser_disclosures`, `adviser_offices`, `private_funds`, `ticker_reference`, `edgartools_gold_status`, plus 13 more added since this table was first written (`accounting_flags`, `adv_fund_count_reconciliation`, `consensus_estimates`, `earnings_calendar`, `earnings_releases`, `executive_records`, `financial_derived`, `financial_factors`, `financial_facts`, `guidance_facts`, `institutional_holdings`, `mdm_company`, `transcript_events`) — see `infra/snowflake/dbt/edgartools_gold/models/gold/` for the current, authoritative list rather than trusting this count to stay accurate. Refreshed on a Snowflake-managed schedule. |

## edgartools Dependency

The platform depends on the `edgartools` PyPI package (`edgartools>=5.29.0`). It is **not** a local path dependency — install from PyPI.
When the `edgartools` version is bumped, run the batch scripts in `scripts/batch/` to smoke-test it.

## SEC data idempotency

SEC filing artifacts are treated as additive and immutable after they have been
captured. Processing follows the source-coverage and Change Journal policy under "Shared local data"
and preserves idempotency. Reprocessing retained bytes is separate from a
provider re-fetch, which requires its existing authorization.

## Schema conventions

Follow the [integer-width rule in AGENTS.md](AGENTS.md#how-to-work-in-this-repo-every-runtime).
It applies to every integer field, including bounded years and quarters;
the former exception for narrow types is retired.

## Debugging discipline: 5-whys

When fixing **any** error (CLI failures, ECS task crashes, CI failures, data
bugs, infra errors), do a 5-whys root-cause pass before applying a fix:

1. State the observed symptom (error message, exit code, wrong output).
2. Ask "why" repeatedly (3-5 times) until you reach a root cause, not just
   the proximate trigger.
3. Apply the fix at the root cause, not just the symptom.
4. If the issue is non-trivial or likely to recur, document only the final
   conclusion in a skill, this file or `TODOS.md` so future sessions don't re-debug
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
  it on the connection — mutating the global afterward has no effect. Set it before `connect()` for `?`-style placeholders.
- `EDGARTOOLS_PROD_LOADER` owns the gold objects `REFRESH_AFTER_LOAD` refreshes, so it needs `OPERATE` +
  `SELECT` on everything a gold model references, `EDGARTOOLS_SILVER` included. Its secret
  (`MDM_SNOWFLAKE_SECRET_JSON`) keeps `MDM_SNOWFLAKE_SCHEMA` at `EDGARTOOLS_GOLD`.

**Postgres / MDM**
- **The MDM store's engineering rules live in the `mdm-engineering` skill**, the one source for them:
  key-list lookups (join the keys, GIN one key at a time, `plan_cache_mode`), no table scans, set-based
  reads and writes, migrations on populated tables, partial unique indexes, guarded `GRANT`s, commits only
  when durable, the Merge Stage record by record, and the cheapest proof. The rules below are about this
  deployment.
- `mdm migrate` does not run automatically on deploy. Treat any prod deploy carrying new migration files
  as incomplete until it has been re-run explicitly — "the image is current" and "the migration was
  applied" are separate facts.
- Snowflake-hosted Postgres re-grants `snowflake_write`'s baseline DML as a platform side effect of
  `ALTER POSTGRES INSTANCE ... RESET ACCESS FOR '<role>'` for *either* role, so `bootstrap-prod-mdm.sh`
  runs `mdm migrate` as its true last database-mutating step.

**Pipeline / runtime**

- Bounded work and idempotent output are the `bookkeeping` skill's (DESIGN: a bounded, validated
  child-work manifest; immutable output by conditional creation, `IfNoneMatch: *`), the one source for them.
- Any "same calendar day" check needs an explicit timezone, and the right one is the business
  process's — `America/New_York` via `pytz` (`zoneinfo` needs a tz database these images don't install).
- A one-time backfill CLI's `--dry-run` needs a `--limit` from the start: proving the logic on real data
  needs tens of rows; only estimating full-run cost needs the whole table.
- Before running a multi-step workflow step by step by hand, look for the one already built (a
  Bookkeeping run, a committed script). The old AWS Step Functions are leftovers, never that workflow.
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

- No test is expected to fail: CI is green on `main`. Locally, the install wizard tests
  (`tests/architecture/test_install_wizard.py`) run `infra/scripts/install.sh`, which needs a `python3` of
  3.11 or later and `jq` on `PATH`. macOS's own `/usr/bin/python3` is 3.9, so put a newer one first.
- **Locally, run the tests a change can affect; CI runs everything** (operator, 2026-09-29, after a
  16-minute integration run). `pytest-testmon` records which code each test executes and re-runs only
  the tests touching changed Python: `TESTMON_DATAFILE=~/.cache/edgartools/testmondata uv run pytest
  --testmon <folders>` (one shared record for every worktree; a test never recorded always runs; it needs pytest's cache,
  so never add `-p no:cacheprovider`).
  It cannot see non-Python inputs: after a change to a migration `.sql`, a rules `.yaml` or another
  data file, also run that area's test files by name. The full suite runs in CI on every PR, and
  nothing merges until it is green.

## Known open items

Deploy status below is as last recorded on each item's own date — re-check against the running image
before trusting it.

- **The `EDGARTOOLS_DECISION` schema does not exist**, leaving 5 Terraform-managed grants unapplied.
  `infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql`'s "MDM active-company universe"
  join is an explicit placeholder that self-joins `COMPANY`, and
  `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql`'s `BUNDLE_AUDITOR` references
  `EDGARTOOLS_GOLD.SEC_AUDITOR_REPORT_EVIDENCE`, which exists only in `EDGARTOOLS_SOURCE`. The real
  blocker behind both: no Snowflake-side source has been chosen for "MDM active company universe" (MDM's
  authority is Postgres; the closest reflection is `NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES`).
- **The original `EDGARTOOLS_DASHBOARD` Streamlit app is still ACCOUNTADMIN-owned** — the same gap already
  fixed for `MDM_GRAPH_DASHBOARD`, with the same drop/recreate-as-target-role recipe.
- **Release-readiness Ticket 74, items 1-2:** repairing the two known stale accessions, and a proactive
  scan for other pre-2026-07-31 stale bronze objects.

## Snowflake-side facts from the old pipeline (still live)

The old AWS pipeline (`load_history`, `daily_incremental`, `targeted_resync`,
`gold_refresh`, `one_click_data_refresh` and their ECS commands) is deleted
from this repository: its Step Function builders and commands are gone, so
anything of it still deployed in AWS is a leftover, never something to run.
What it left in Snowflake is live:

- **Gold refresh.** `EDGARTOOLS_GOLD`'s dynamic tables use `target_lag = '6 hours'`
  (`gold_model_config()`); `TARGET_LAG = DOWNSTREAM` never refreshes a gold
  leaf. `SNOWFLAKE_RUN_MANIFEST_TASK` must be STARTED in `EDGARTOOLS_GOLD`: it
  runs `LOAD_EXPORTS_FOR_RUN`, then `REFRESH_AFTER_LOAD`, as an explicit trigger.
- **Graph storage is inside Snowflake**, not an external Neo4j: the Neo4j
  Graph Analytics Native App in the same account, tables in
  `NEO4J_GRAPH_MIGRATION`, the live generation named by
  `GRAPH_ACTIVE_POINTER`. There is no `NEO4J_URI` and no Bolt connection.
  Grants: `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`.
- **MDM's hosted store is Snowflake Postgres**, not AWS RDS
  (`infra/scripts/bootstrap-prod-mdm.sh` provisions the instance; it connects
  as `snowflake_admin`). It is a PostgreSQL-protocol address
  (`MDM_DATABASE_URL`, port 5432), separate from the Snowflake SQL connection
  used for dbt and gold: one account and governance boundary, two protocols.

## Development Commands

> **Tooling:** always use `uv` for Python dependency management and Python CLI
> execution in this repo. The lockfile is `uv.lock`; never invoke bare `pip` or
> bare `dbt` from repo workflows. Use `uv sync` for project deps, `uv pip
> install` for deliberate one-off installs, and `uv run --with <package>` when a
> deploy needs a transient tool such as `dbt-snowflake`.
>
> **Docker runtime:** use the Docker context already configured on the machine.
> Leave `DOCKER_HOST` unset. Publish images with `docker build` and
> `docker push` through `infra/scripts/publish-warehouse-image.sh --mode docker`.
> Local PostgreSQL 16 for agents is the shared server in
> [Initialize shared local PostgreSQL](docs/local-agent-testing.md).

```bash
# SEC User-Agent for a provider capture (provider_capture); must contain an email
export EDGAR_IDENTITY="EdgarTools Platform <email>"
export AWS_DEFAULT_REGION=us-east-1  # infra is us-east-1, not the default us-east-2
# (deploy-snowflake-stack.sh still reads WAREHOUSE_*_ROOT and SERVING_EXPORT_ROOT for its stage)

# Install project deps (uses uv.lock)
uv sync --extra s3 --extra snowflake

# CLI: start with doctor (the data-platform skill, Setup)
edgar-warehouse --help
edgar-warehouse doctor

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

# Snowflake native-pull deploy (prod; dev is decommissioned, above)
# Requires a SnowCLI connection (configured in ~/.snowflake/config.toml) and keeps
# Snowflake secrets out of repo files. A prod change needs the operator's word.
bash infra/scripts/deploy-snowflake-stack.sh \
  --env-name prod \
  --snow-connection edgartools-prod \
  --run-validation \
  --run-dbt

# Docker image publish (configured Docker context; full recipe below)
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

A `--full-refresh` makes the deploying role the dynamic table's owner, and the
INITIAL refresh checks that role's *direct* grants only (secondary roles do not
count): give it direct `SELECT` on every table the model reads first.

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
The AWS-side scripts that took `--env` (`deploy-aws-application.sh`, `run-aws-mdm-e2e.sh`)
were retired (platform validation 2b, 2026-09-30).

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

**Manual AWS build and deploy — configured Docker context**

Publish with `docker build` and `docker push` through
`infra/scripts/publish-warehouse-image.sh --mode docker`.
Prod promotion (build/push under `edgartools-prod-images`) is manual; the AWS
pipeline deploy script was retired (platform validation 2b, 2026-09-30).
Use the steps below for prod promotion and ad-hoc builds.

```bash
# 1. Confirm the configured Docker context answers (`docker info`).

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
```

**If publish-warehouse-image.sh fails with a cache layer error**

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
| `rules/**` or `edgar_warehouse/rules/**` | MDM (MDM loads its mappings and merge rules from `rules/`); both images copy `rules/`, so rebuild both to keep them equal |
| Both (e.g. `orchestrator.py` + `mdm/cli.py`) | both |
| `Dockerfile` / `Dockerfile.warehouse-deps` | warehouse (+ deps if lock changed) |
| `Dockerfile.mdm-neo4j` / `Dockerfile.mdm-deps` | MDM (+ deps if lock changed) |
| `uv.lock` | deps images for both — run without `--skip-build` |
| `crates/source-contract/**` (the source engine) | deps images for both: they build its wheel, and the deps tag hashes the crate |

**Clean up local images before a build (run this first every time)**

The local Docker daemon accumulates stale images: old SHA tags, debug tags, superseded deps layers. Clean before building to avoid cache confusion and reclaim disk.

```bash
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

Read these section by section rather than whole:

| File | Contents |
|------|----------|
| `edgar_warehouse/mdm/clean/merge.py` | The Merge Stage: a batch's closure, binding, survivorship and the save |
| `skills/data-platform/READING.md` | The source-extract language, every expression and limit |
| `skills/data-onboarding/SKILL.md` | Onboarding a feed or a domain, step by step |

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
