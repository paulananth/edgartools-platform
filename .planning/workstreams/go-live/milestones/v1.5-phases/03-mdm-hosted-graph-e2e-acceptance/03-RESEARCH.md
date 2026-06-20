# Phase 3: MDM Hosted Graph E2E Acceptance - Research

**Researched:** 2026-06-15
**Domain:** Operational acceptance (live CLI/script runs + evidence/runbook docs) — no new code, no new packages
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Phase 3 Scope Given Prod AWS Blocker
- **D-01:** Phase 3 scope is a **dev rehearsal run + documentation** —
  not Phase 2's D-01 "document-and-validate-only" pattern. The dev rehearsal
  is a full E2E run (see D-09).
- **D-02:** Live-reproduce `run-aws-mdm-e2e.sh --env prod --status-only`
  (read-only) as concrete BLOCKED-row proof of the missing
  `infra/aws-prod-application.json`, mirroring Phase 2's SNOW-01
  `backend.hcl` rc=1 reproduction.
- **D-03:** For MDM-01, since prod MDM Postgres secrets don't exist yet,
  Phase 3 **re-verifies dev MDM Postgres connectivity/migration/counts live**
  as a dev-precedent refresh, in addition to documenting the prod commands
  as a BLOCKED required-fix.
- **D-04:** For GRAPH-01/GRAPH-02, the existing
  `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md`
  is cited as-is as dev precedent — **no new live `verify-graph` run** is
  performed for this requirement pair.

#### MDM Secret Population Runbook (MDM-01)
- **D-05:** Document **full `aws secretsmanager put-secret-value` commands
  with placeholders** (not just names/JSON shape) for the BLOCKED "MDM
  Snowflake Postgres secret container and connectivity" row.
- **D-06:** Population-runbook entries are scoped to exactly two of the four
  `edgartools-prod/mdm/*` secrets:
  - `postgres_dsn` — runbook entry required.
  - `snowflake` — runbook entry required.
  - `neo4j` — **not required**, documented as legacy/N/A under the
    Snowflake-hosted graph (per Phase 2 framing). No population entry.
  - `api_keys` — **deferred**, purpose unclear. No population entry this
    phase.
- **D-07:** The runbook uses the **dev MDM Postgres connection** (re-verified
  live per D-03) as a non-secret "shape reference" for what the prod
  `postgres_dsn` value should contain — connection-string **structure only,
  no values**. The prod runbook is otherwise independent.
- **D-08:** Evidence for the "secret exists but not populated" vs "populated"
  distinction on the BLOCKED row is an
  `aws secretsmanager describe-secret` **presence check only** (non-secret
  metadata) — no new value-dumping commands.

#### Acceptance-vs-Debug Framing (`--status-only` / `--skip-preflight`)
- **D-09:** The "dev rehearsal run" (D-01) is a **full E2E run** of
  `run-aws-mdm-e2e.sh --env dev` (`RUN_E2E=true`, the default — i.e. no
  `--status-only`). This generates fresh acceptance evidence for
  LIVE-03/GRAPH-02 chain steps (`mdm_migrate`, `mdm_run`,
  `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`,
  `mdm_counts`), **supplementing** — not replacing — the cited
  `03-LIVE-DEV-RUN.md` precedent used for GRAPH-01/GRAPH-02 (D-04).
- **D-10:** LIVE-03's "stop before expensive AWS execution when local
  acceptance gates cannot pass" requirement is demonstrated **live**: the dev
  rehearsal run uses the script's **default local `verify-graph` preflight**
  (no `--skip-preflight`), and the preflight pass is captured as the gate
  that allows the full E2E run to proceed. This pass/gate evidence is part of
  the Phase 3 deliverable.
- **D-11:** `--skip-preflight` is **not used, demonstrated, or documented**
  anywhere in Phase 3 deliverables — omitted entirely. The script's own help
  text and inline warning ("This cannot satisfy Phase 3 acceptance") are
  sufficient; Phase 3 does not duplicate or reinforce that warning.
- **D-12:** Prod-targeted commands in Phase 3 are limited strictly to the
  `--status-only` structural-blocker reproduction (D-02).
  `--skip-preflight` is **never invoked against prod** in this phase.

### Claude's Discretion
None recorded in CONTEXT.md beyond the locked decisions above.

### Deferred Ideas (OUT OF SCOPE)
- `edgartools-prod/mdm/api_keys` secret — purpose unclear; no population
  runbook entry in Phase 3. Revisit when its consumer is identified.
- `edgartools-prod/mdm/neo4j` secret — documented as not required / legacy
  graph container under the Snowflake-hosted graph path (per Phase 2
  framing). No action needed unless the legacy Neo4j path is formally
  deprecated (tracked as a Future Requirement in REQUIREMENTS.md).
- Reproducing the `--skip-preflight` warning against prod — explicitly not
  done (D-11/D-12); prod evidence stays limited to `--status-only`.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MDM-01 | Production MDM Snowflake Postgres configuration is populated through AWS Secrets Manager, and MDM connectivity, migration, and counts checks pass with secret-safe output. | Section "MDM Postgres CLI Commands" (env vars, exact commands for `check-connectivity`/`migrate`/`counts`); "Dev MDM Postgres Re-Verification (D-03)" (live re-run procedure + reachability caveat); "MDM Secret Population Runbook (D-05–D-08)" (full `put-secret-value` placeholders for `postgres_dsn`+`snowflake`, `describe-secret` presence-check commands, dev DSN shape reference). |
| GRAPH-01 | `edgar-warehouse mdm sync-graph` and strict `edgar-warehouse mdm verify-graph` pass in the target environment with SQL parity, Native App grants, compute pool availability, `GRAPH_INFO`, `BFS`, and `WCC` proof. | Section "Snowflake Graph CLI Commands" (env vars, `sync-graph`/`verify-graph` args, strict-check breakdown); "Dev Hosted-Graph Precedent (03-LIVE-DEV-RUN.md)" (cites existing `phase3_acceptance: true` proof per D-04 — no new run). |
| GRAPH-02 | AWS MDM E2E reaches `mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`, and `mdm_counts` through the Snowflake-hosted graph path without requiring external `NEO4J_*` credentials. | Section "run-aws-mdm-e2e.sh Full Walkthrough" (stage-by-stage breakdown of the 6 Step Functions, `warn_lingering_neo4j_references`); "Dev Rehearsal Run (D-09/D-10)" (canonical full-run command + preflight gate). |
| LIVE-03 | Operator can run bounded production status and E2E checks, distinguish known blockers from launch failures, and stop before expensive AWS execution when local acceptance gates cannot pass. | Section "Prod `--status-only` Structural-Blocker Reproduction (D-02)" (exact failure point, exit code, zero AWS calls); "Dev Rehearsal Run (D-09/D-10)" (preflight-gates-E2E evidence); "Acceptance vs Debug Framing" (where `--status-only`/`--skip-preflight` warnings already live — D-11 says cite, don't restate). |
</phase_requirements>

## Summary

Phase 3 is a pure operational-acceptance phase: every command the planner will
schedule already exists in the repo (`infra/scripts/run-aws-mdm-e2e.sh`,
`edgar_warehouse/mdm/cli.py` subcommands, `infra/scripts/bootstrap-aws-mdm-secrets.sh`).
No new code, no new packages, no new architecture. The planner's job is to
sequence five categories of work: (1) a live dev rehearsal run of the full
AWS MDM E2E chain gated by a local strict `verify-graph` preflight (D-09/D-10),
(2) a live read-only reproduction of the prod `--status-only` structural
blocker (D-02), (3) a live re-verification of dev MDM Postgres
connectivity/migration/counts (D-03), (4) citation of existing dev
hosted-graph evidence for GRAPH-01/GRAPH-02 without re-running it (D-04), and
(5) a documentation-only secret-population runbook for exactly two prod MDM
secrets (`postgres_dsn`, `snowflake`) with full placeholder commands (D-05–D-08).

The most important structural fact for planning: **two completely separate
connection surfaces exist under the `mdm` CLI**, and conflating their env vars
is the single most likely planning error. `check-connectivity` / `migrate` /
`counts` / `run` / `backfill-relationships` talk to **MDM Postgres** via
`MDM_DATABASE_URL` only (`edgar_warehouse/mdm/database.py:get_engine()`).
`sync-graph` / `verify-graph` talk to **Snowflake** via
`SnowflakeConnectionSettings.from_env()` (`MDM_SNOWFLAKE_*` / `DBT_SNOWFLAKE_*`
env vars or `~/.snowflake/connections.toml`), and never touch
`MDM_DATABASE_URL`. `run-aws-mdm-e2e.sh`'s local preflight only exercises the
second surface (`mdm verify-graph`); D-03's dev Postgres re-verification
exercises the first surface and is a **separate** set of commands the planner
must schedule independently.

**Primary recommendation:** Sequence Phase 3 as five independent task groups
(dev rehearsal E2E, prod `--status-only` reproduction, dev Postgres
re-verification, GRAPH dev-precedent citation, secret-population runbook
docs), each producing one `evidence/*.md` entry or `runbook/*.md` section,
following the Phase 2 `evidence/*.md` + `runbook/*.md` pairing convention.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| AWS MDM E2E orchestration (`run-aws-mdm-e2e.sh`) | API / Backend (Step Functions) | — | Driver script starts/polls AWS Step Functions executions; all actual work runs in ECS tasks. |
| Local strict hosted-graph preflight (`mdm verify-graph`) | API / Backend (CLI) | Database / Storage (Snowflake) | CLI process connects directly to Snowflake to run SQL parity + Native App checks before AWS executions start. |
| MDM Postgres connectivity/migration/counts (`mdm check-connectivity`/`migrate`/`counts`) | Database / Storage | API / Backend (CLI) | CLI process connects directly to Snowflake-hosted Postgres via `MDM_DATABASE_URL`; schema/seed/count operations are DB-tier responsibilities exposed through a thin CLI. |
| Hosted graph materialization (`mdm sync-graph`) | Database / Storage (Snowflake) | API / Backend (CLI) | Writes graph-ready node/edge tables directly into Snowflake target schema from MDM source tables — a DB-tier transformation invoked via CLI. |
| Prod secret population (`put-secret-value`) | API / Backend (AWS Secrets Manager) | — | Pure AWS control-plane operation; no application code involved. |
| Launch gate matrix / evidence docs | — (documentation) | — | Not a runtime tier — planning artifact updates only. |

## Standard Stack

**N/A** — this phase installs no packages and introduces no new libraries.
All commands invoke the existing `edgar-warehouse` CLI (already installed via
`uv sync --extra s3 --extra snowflake`) and existing shell scripts under
`infra/scripts/`. See "Package Legitimacy Audit" below for the formal
no-new-packages confirmation.

## Package Legitimacy Audit

**Not applicable.** Phase 3 installs zero new external packages. All tooling
(`edgar-warehouse` CLI, `uv`, `aws` CLI, `snow` CLI) is already present in the
repo's `pyproject.toml`/`uv.lock` and documented in `CLAUDE.md`. No
`slopcheck`/registry verification is required.

**Packages removed due to slopcheck verdict:** none (N/A — no packages evaluated).
**Packages flagged as suspicious:** none (N/A — no packages evaluated).

## Architecture Patterns

### System Architecture Diagram

```
Operator (local shell, AWS profile + Snowflake connection configured)
  |
  |--[1]--> run-aws-mdm-e2e.sh --env dev
  |           |
  |           |--> local preflight: `edgar-warehouse mdm verify-graph`
  |           |       (direct Snowflake connection: SQL parity + Native App
  |           |        GRAPH_INFO/BFS/WCC + compute pool checks)
  |           |       PASS --> continue   FAIL --> exit 1, no AWS calls
  |           |
  |           |--> print_state_machine_status (AWS Step Functions list-executions,
  |           |       read-only, from infra/aws-dev-application.json)
  |           |
  |           |--> warn_lingering_neo4j_references (grep on JSON + deploy script,
  |           |       warning-only, never blocks)
  |           |
  |           `--> start_and_wait x6 (sequential, ~20s poll):
  |                  mdm_migrate -> mdm_run -> mdm_backfill_relationships ->
  |                  mdm_sync_graph -> mdm_verify_graph -> mdm_counts
  |                  (each a real AWS Step Functions execution -> ECS task
  |                   running `edgar-warehouse mdm <subcommand>`)
  |
  |--[2]--> run-aws-mdm-e2e.sh --env prod --status-only
  |           |
  |           `--> [[ -f infra/aws-prod-application.json ]] || fail
  |                 (FILE DOES NOT EXIST -> immediate exit 1, ZERO AWS calls,
  |                  --status-only branch at line 203 never reached)
  |
  |--[3]--> Dev MDM Postgres re-verification (D-03)
  |           |
  |           |--> aws secretsmanager get-secret-value --secret-id
  |           |       edgartools-dev/mdm/postgres_dsn  (export MDM_DATABASE_URL,
  |           |       never printed)
  |           |
  |           `--> edgar-warehouse mdm check-connectivity / migrate / counts
  |                 (direct Postgres connection to Snowflake-hosted Postgres,
  |                  *.snowflake.app host, sslmode=require)
  |
  `--[4]--> Secret population runbook (D-05-D-08, documentation only)
              |
              |--> aws secretsmanager put-secret-value --secret-id
              |       edgartools-prod/mdm/postgres_dsn  (placeholder DSN)
              |--> aws secretsmanager put-secret-value --secret-id
              |       edgartools-prod/mdm/snowflake     (placeholder JSON)
              `--> aws secretsmanager describe-secret (presence check, both)
```

### Recommended Evidence/Runbook Structure (mirrors Phase 2)

```
.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/
├── 03-CONTEXT.md            # already exists
├── 03-RESEARCH.md           # this file
├── 03-0N-PLAN.md            # planner output
├── evidence/
│   └── mdm-hosted-graph.md  # dev rehearsal + prod --status-only + dev Postgres
│                             # re-verify evidence (mirrors Phase 1's template
│                             # at ../01-.../evidence/mdm-hosted-graph.md)
└── runbook/
    └── mdm-secrets.md        # postgres_dsn + snowflake population runbook
                               # (mirrors ../02-.../runbook/aws-deploy.md style)
```

### Pattern 1: Two-Surface Env Var Separation

**What:** `edgar-warehouse mdm <subcommand>` reads from one of two completely
independent connection configs depending on subcommand.

**When to use:** Every task in this phase that invokes the `mdm` CLI must
declare which surface it needs.

| Subcommand | Connection surface | Required env vars | Read/Write |
|---|---|---|---|
| `mdm check-connectivity` | MDM Postgres | `MDM_DATABASE_URL` | read-only (`SELECT 1` + table introspection) |
| `mdm migrate` | MDM Postgres | `MDM_DATABASE_URL` | **write** (applies schema SQL + seeds reference data unless `--no-seed`) |
| `mdm counts` | MDM Postgres | `MDM_DATABASE_URL` | read-only (`SELECT COUNT(*)` per table) |
| `mdm run` | MDM Postgres + silver DuckDB | `MDM_DATABASE_URL`, `MDM_SILVER_DUCKDB` or `WAREHOUSE_STORAGE_ROOT` | write |
| `mdm backfill-relationships` | MDM Postgres + silver DuckDB | `MDM_DATABASE_URL`, silver source | write |
| `mdm sync-graph` | Snowflake (graph target) | `SNOW_CONNECTION`/`SNOWFLAKE_CONNECTION` or `MDM_SNOWFLAKE_*`/`DBT_SNOWFLAKE_*` (`ACCOUNT`,`USER`,`PASSWORD`,`DATABASE`,`WAREHOUSE`; `SCHEMA` defaults to `EDGARTOOLS_GOLD`) | write (materializes `NEO4J_GRAPH_MIGRATION` tables) |
| `mdm verify-graph` | Snowflake (graph target + Native App) | same as `sync-graph`, plus optional `--native-app-*` flags | read-only |

**Example — `_session()` chain for Postgres commands:**
```python
# Source: edgar_warehouse/mdm/cli.py, edgar_warehouse/mdm/database.py
def get_engine(url: str | None = None) -> Engine:
    url = url or os.environ["MDM_DATABASE_URL"]   # KeyError if unset — hard requirement
```

**Example — Snowflake settings resolution order for `sync-graph`/`verify-graph`:**
```python
# Source: edgar_warehouse/mdm/export.py:_snowflake_setting (lines 181-189)
# For key="ACCOUNT": checks in order —
#   1. env MDM_SNOWFLAKE_ACCOUNT
#   2. env DBT_SNOWFLAKE_ACCOUNT
#   3. secret["MDM_SNOWFLAKE_ACCOUNT"]   (from MDM_SNOWFLAKE_SECRET_JSON / DBT_SNOWFLAKE_SECRET_JSON)
#   4. secret["DBT_SNOWFLAKE_ACCOUNT"]
#   5. secret["snowflake_account"]
#   6. secret["account"]
# Falls back to ~/.snowflake/connections.toml (SNOWFLAKE_CONNECTION-named profile)
# if none of MDM_SNOWFLAKE_SECRET_JSON/DBT_SNOWFLAKE_SECRET_JSON env vars are set.
```

### Pattern 2: `run-aws-mdm-e2e.sh` Preflight-Gates-E2E (LIVE-03 demonstration)

**What:** The script runs `mdm verify-graph` locally BEFORE starting any AWS
Step Functions execution, and a failure here makes ZERO AWS API calls beyond
`print_state_machine_status` (which itself is read-only `list-executions`).

**When to use:** This IS the live demonstration of LIVE-03's "stop before
expensive AWS execution when local acceptance gates cannot pass" requirement
(D-10). Capture the preflight PASS output as part of the dev rehearsal
evidence.

```bash
# Source: infra/scripts/run-aws-mdm-e2e.sh, lines 203-217
if [[ "$RUN_E2E" != "true" ]]; then
  print_state_machine_status
  warn_lingering_neo4j_references
  exit 0
fi

if [[ "$SKIP_PREFLIGHT" == "true" ]]; then
  echo "WARNING: --skip-preflight bypasses local strict verify-graph." >&2
  echo "WARNING: this run cannot satisfy Phase 3 acceptance unless preflight proof is captured separately." >&2
else
  run_hosted_graph_preflight   # uv run --extra snowflake edgar-warehouse mdm verify-graph
fi

print_state_machine_status
warn_lingering_neo4j_references
# ... only past this point do start_and_wait x6 begin (real Step Functions executions)
```

### Anti-Patterns to Avoid

- **Conflating `MDM_DATABASE_URL` with Snowflake graph env vars:** Setting
  only `MDM_DATABASE_URL` and expecting `sync-graph`/`verify-graph` to work
  (or vice versa) will fail with `RuntimeError: Missing Snowflake export
  setting(s): ...` or `KeyError: 'MDM_DATABASE_URL'` respectively. Document
  per-task which env vars are needed.
- **Treating `mdm-check-connectivity` Step Functions state machine as usable:**
  `docs/aws-mdm-snowflake-postgres-cutover.md` documents this state machine as
  permanently broken (hardcodes removed `--neo4j` flag). Do not schedule any
  Phase 3 task that invokes it. Use direct CLI `mdm check-connectivity` (local,
  if MDM Postgres is reachable) or `ecs run-task` with
  `command:["mdm","check-connectivity"]` as the documented fallback.
- **Re-running `verify-graph` for GRAPH-01/GRAPH-02 "just to be safe":** D-04
  explicitly forbids this — cite `03-LIVE-DEV-RUN.md` as-is. A new run is only
  in scope as part of the D-09 full dev rehearsal (which exercises
  `verify-graph` as the AWS `mdm_verify_graph` Step Functions stage AND as the
  local preflight — both are part of the rehearsal, not a separate
  GRAPH-01/GRAPH-02 re-proof).
- **Using `get-secret-value` anywhere in evidence:** D-08 restricts evidence to
  `describe-secret` (presence/metadata only). `get-secret-value` is permitted
  only as a runtime step to populate `MDM_DATABASE_URL` for the dev
  re-verification (D-03) — never paste its output, and never put it in an
  evidence file.

## Don't Hand-Roll

**N/A.** Every operation in this phase already has a first-class CLI
subcommand or existing shell script. There is no "deceptively complex problem"
to solve — the work is execution + evidence capture, not implementation.

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| AWS MDM E2E orchestration | A new orchestration script | `infra/scripts/run-aws-mdm-e2e.sh` (existing, handles preflight + 6-stage chain + Neo4j-reference warnings) | Already implements D-09/D-10's exact required sequencing. |
| Hosted graph SQL parity / Native App checks | New verification SQL | `edgar-warehouse mdm verify-graph` (existing, `SnowflakeGraphVerifier`) | Already implements node/edge parity, diagnostics, and Native App `GRAPH_INFO`/`BFS`/`WCC`/compute-pool checks. |
| Secret population | A new secret-writing script | `infra/scripts/bootstrap-aws-mdm-secrets.sh` for `postgres_dsn` (validates DSN shape); raw `aws secretsmanager put-secret-value` for `snowflake` (no equivalent helper exists — see Open Questions) | The Postgres DSN helper enforces host-suffix/database/`sslmode=require` invariants matching `audit-mdm-snowflake-postgres-cutover.py`'s validator. |

**Key insight:** The planner should resist any temptation to write new
scripts or wrapper tooling for this phase — the entire success criteria set
(1-5) maps onto existing commands. New artifacts should be limited to
`evidence/*.md` and `runbook/*.md` documentation files.

## Common Pitfalls

### Pitfall 1: Native App compute pool not active blocks the dev rehearsal preflight
**What goes wrong:** `run_hosted_graph_preflight` (`mdm verify-graph`) can fail
at the `compute_pool` check with status `failed` even though SQL parity is
`ok`, blocking the entire dev rehearsal before any Step Functions execution
starts.
**Why it happens:** Per `03-LIVE-DEV-RUN.md`, this exact failure occurred in
the prior dev run: `Neo4j_Graph_Analytics.graph.show_available_compute_pools()`
returned no rows until `GRANT CREATE COMPUTE POOL ON ACCOUNT` /
`GRANT CREATE WAREHOUSE ON ACCOUNT` were applied to the Native App and the
compute pool `CPU_X64_XS` was activated. The Native App's compute pool state
is **not** guaranteed to persist as "active" between sessions/runs.
**How to avoid:** Before scheduling the D-09 full rehearsal, the planner
should include a check step: re-run `mdm verify-graph` locally first (which
IS the preflight anyway) and inspect the `native_app.compute_pool` status. If
it fails, the remediation is the same Snowflake grant SQL cited in
`03-LIVE-DEV-RUN.md` (`infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`
plus the two account-level `GRANT CREATE COMPUTE POOL`/`GRANT CREATE WAREHOUSE`
statements) — this remediation step itself is **not** new Phase 3 scope, it's
a precondition the rehearsal task should be prepared to hit and resolve using
already-documented SQL.
**Warning signs:** `verify-graph` payload shows `"native_app": {"status":
"failed", ...}` with `compute_pool` check failed, even when
`node_parity`/`relationship_parity` are `ok`.

### Pitfall 2: Dev MDM Postgres reachability is unconfirmed from this environment
**What goes wrong:** D-03's "re-verify dev MDM Postgres connectivity/migration/counts
live" assumes local CLI commands (`edgar-warehouse mdm check-connectivity` etc.)
can reach the Snowflake-hosted Postgres instance. This has NOT been confirmed
live in this research session.
**Why it happens:** CLAUDE.md documents that the *original* RDS-backed MDM
Postgres was in a "private VPC" unreachable from local/non-ECS contexts
(`bootstrap-next` caveat). The MDM database has since been migrated to
Snowflake Postgres (`docs/aws-mdm-snowflake-postgres-cutover.md`), whose host
ends in `.snowflake.app` with `sslmode=require` — this is typically a
publicly-routable Snowflake-managed endpoint, but this has not been verified
live in this session and must not be assumed.
**How to avoid:** The planner should sequence D-03 as: (1) attempt local
`MDM_DATABASE_URL` export + `mdm check-connectivity` first; (2) if connection
times out / DNS fails, fall back to the `ecs run-task` pattern documented in
`docs/aws-mdm-snowflake-postgres-cutover.md` (lines 298-307) — `command:
["mdm","check-connectivity"]` (and similarly for `migrate`/`counts`) via
`aws ecs run-task` against the `edgartools-dev-warehouse` cluster, which is
guaranteed to have network access. Document whichever path actually worked as
the evidence.
**Warning signs:** `psycopg2.OperationalError: could not translate host name`
or connection timeout when running `mdm check-connectivity` locally.

### Pitfall 3: `mdm migrate` is a write operation, not read-only
**What goes wrong:** Treating `mdm migrate` as a safe "check" command similar
to `check-connectivity`/`counts`.
**Why it happens:** `_handle_migrate` calls `migrate(get_engine(), seed=args.seed)`
which applies `001_initial_schema.sql`, `003_tracking_status_index.sql`,
`004_company_ticker_parent.sql`, `005_fundamentals_relationships.sql`, and (if
`seed=True`, the default) calls `seed_defaults()`. These are idempotent
(`CREATE TABLE IF NOT EXISTS` / `INSERT ... ON CONFLICT`-style) but DO write to
the database.
**How to avoid:** This is expected and safe for D-03 — the dev MDM Postgres
schema/seed migration is already applied and idempotent, so re-running
`mdm migrate` against dev should be a no-op write (verify via the returned
`{"dialect": ..., "seeded": true, "tables": {...}}` payload showing existing
table counts unchanged). Document the command as "idempotent migration
re-apply", not "read-only check", in evidence.
**Warning signs:** N/A for dev (idempotent); would matter more for a
hypothetical first-time prod migration (out of scope — prod secrets don't
exist yet per D-03's framing).

### Pitfall 4: `infra/aws-prod-application.json` check happens BEFORE `--status-only` branches
**What goes wrong:** Assuming `--status-only --env prod` will print a status
report (possibly an empty/error one) and then fail.
**Why it happens:** The file-existence check (`[[ -f "$APPLICATION_FILE" ]] ||
fail`, line 77) runs unconditionally during argument-resolution setup —
**before** the `RUN_E2E` true/false branch at line 203 is ever reached. Since
`infra/aws-prod-application.json` does not exist, the script calls `fail
"deployment summary not found: ${REPO_ROOT}/infra/aws-prod-application.json"`
and exits 1 immediately via `set -euo pipefail`.
**How to avoid:** Document the reproduction precisely: `bash
infra/scripts/run-aws-mdm-e2e.sh --env prod --status-only` (with any AWS
profile/region flags — they don't matter, since `aws_cli` is never invoked)
exits 1 with stderr `ERROR: deployment summary not found:
<repo>/infra/aws-prod-application.json`, having made **zero AWS API calls**.
This is the cleanest possible BLOCKED-row proof — no credentials are even
exercised.
**Warning signs:** If the evidence shows ANY AWS API call output (e.g.
`==> Step Functions in ...`) for the prod `--status-only` run, something is
wrong — either `infra/aws-prod-application.json` was created (re-check D-02's
premise) or the command was run against `--env dev` by mistake.

## Code Examples

### `mdm verify-graph` — strict checks invoked (Success Criterion 3)

```python
# Source: edgar_warehouse/mdm/snowflake_graph.py, SnowflakeGraphVerifier.verify()
# Strict verification (default; --skip-native-app NOT passed) performs:
#   1. node_parity: MDM_ACTIVE_COUNT vs SNOWFLAKE_GRAPH_NODE_COUNT per entity type
#   2. relationship_parity: same, per relationship type
#   3. diagnostics: missing_graph_nodes, extra_graph_nodes, missing_graph_edges,
#      extra_graph_edges, missing_graph_edge_endpoints (all must be empty)
#   4. native_app checks (config.verify_native_app=True by default):
#      - app_installation, app_user_role_grant, app_admin_role_grant
#      - database_role_to_application, database_role_privileges
#      - compute_pool (must list the configured selector, default CPU_X64_XS)
#      - graph_schema_sample
#      - graph_info   (Neo4j_Graph_Analytics.GRAPH.GRAPH_INFO)
#      - bfs          (Native App BFS proof)
#      - wcc          (Native App WCC proof)
# Overall `passed` = node_parity ok AND relationship_parity ok AND
#                     diagnostics_clean AND native_app_ok
# Defaults (overridable via --native-app-* flags):
#   DEFAULT_TARGET_SCHEMA = "NEO4J_GRAPH_MIGRATION"
#   DEFAULT_MDM_SCHEMA = "MDM"
#   DEFAULT_NATIVE_APP_NAME = "Neo4j_Graph_Analytics"
#   DEFAULT_NATIVE_APP_DATABASE_ROLE = "NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE"
#   DEFAULT_NATIVE_APP_COMPUTE_POOL = "CPU_X64_XS"
```

### Dev rehearsal full E2E — canonical command (D-09)

```bash
# Source: .planning/workstreams/neo4j-snowflake/phases/03-.../03-LIVE-DEV-RUN.md
# (regression command, end of file) — this is the D-09 full-run invocation.
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --snow-connection snowconn \
  --snowflake-database EDGARTOOLS_DEV
# Defaults applied: --mdm-run-limit 5, --graph-limit 100
# No --status-only, no --skip-preflight (per D-09/D-10/D-11).
```

### Prod `--status-only` structural-blocker reproduction (D-02)

```bash
# Source: infra/scripts/run-aws-mdm-e2e.sh, lines 75-77
bash infra/scripts/run-aws-mdm-e2e.sh --env prod --status-only
# Expected output (stderr), exit code 1:
#   ERROR: deployment summary not found: <repo-root>/infra/aws-prod-application.json
# Zero AWS API calls made (fails before any aws_cli invocation).
```

### Dev MDM Postgres re-verification (D-03) — primary path

```bash
# Step 1: load the dev MDM Postgres DSN into MDM_DATABASE_URL without printing it.
export MDM_DATABASE_URL="$(aws secretsmanager get-secret-value \
  --secret-id edgartools-dev/mdm/postgres_dsn \
  --query SecretString --output text)"

# Step 2: connectivity (read-only)
uv run --extra s3 --extra snowflake edgar-warehouse mdm check-connectivity

# Step 3: migration (idempotent write — see Pitfall 3)
uv run --extra s3 --extra snowflake edgar-warehouse mdm migrate

# Step 4: counts (read-only)
uv run --extra s3 --extra snowflake edgar-warehouse mdm counts

# unset afterward
unset MDM_DATABASE_URL
```

### Dev MDM Postgres re-verification (D-03) — ECS fallback (if local connect fails)

```bash
# Source: docs/aws-mdm-snowflake-postgres-cutover.md, lines 298-307
# (adapted per-subcommand: substitute "check-connectivity" with "migrate" or "counts")
aws ecs run-task \
  --region us-east-1 \
  --cluster edgartools-dev-warehouse \
  --task-definition edgartools-dev-mdm-medium:<latest-revision> \
  --launch-type FARGATE \
  --network-configuration '{"awsvpcConfiguration":{"subnets":["<subnet-id>"],"securityGroups":["<sg-id>"],"assignPublicIp":"ENABLED"}}' \
  --overrides '{"containerOverrides":[{"name":"edgar-warehouse","command":["mdm","check-connectivity"]}]}'
# Do NOT use the edgartools-dev-mdm-check-connectivity Step Functions state
# machine — it hardcodes a removed --neo4j flag and always fails (documented
# known issue).
```

### MDM Secret Population Runbook (D-05–D-08)

**`postgres_dsn` — full command with placeholders (uses existing validated helper):**

```bash
# Validates DSN scheme/host-suffix/database/sslmode before writing
# (host suffix default: .snowflake.app; database default: mdm)
printf '%s' "postgresql://<APPLICATION_ROLE_USER>:<APPLICATION_ROLE_PASSWORD>@<PROD_SNOWFLAKE_POSTGRES_HOST>.snowflake.app:5432/mdm?sslmode=require" | \
  bash infra/scripts/bootstrap-aws-mdm-secrets.sh \
    --env prod \
    --aws-profile aws-admin-prod \
    --aws-region us-east-1 \
    --dsn-stdin
# Writes to: edgartools-prod/mdm/postgres_dsn
# --dry-run flag available to validate without writing.
```

**`postgres_dsn` shape reference (D-07, structure only — no values):**

```
postgresql://<user>:<password>@<host>.snowflake.app:<port>/<database>?sslmode=require
```
- `<host>` must end with `.snowflake.app` (enforced by `bootstrap-aws-mdm-secrets.sh`
  `--expected-host-suffix`, default `.snowflake.app`)
- `<database>` must equal `mdm` (default; `--database` overridable)
- query string must include `sslmode=require`
- This is the exact shape `audit-mdm-snowflake-postgres-cutover.py`'s
  `validate_snowflake_postgres_dsn()` enforces for the dev secret — the prod
  secret must satisfy the same structural invariants against a (different,
  prod) Snowflake Postgres instance.

**`snowflake` secret — full command with placeholders (no existing helper; raw `put-secret-value`):**

```bash
# JSON keys consumed by _snowflake_setting() via secret.get("MDM_SNOWFLAKE_<KEY>")
# or secret.get("DBT_SNOWFLAKE_<KEY>") (uppercase keys checked first).
aws secretsmanager put-secret-value \
  --profile aws-admin-prod \
  --region us-east-1 \
  --secret-id edgartools-prod/mdm/snowflake \
  --secret-string '{
    "MDM_SNOWFLAKE_ACCOUNT": "<ORGNAME-ACCOUNTNAME>",
    "MDM_SNOWFLAKE_USER": "<PROD_MDM_SNOWFLAKE_USER>",
    "MDM_SNOWFLAKE_PASSWORD": "<PROD_MDM_SNOWFLAKE_PASSWORD>",
    "MDM_SNOWFLAKE_DATABASE": "<EDGARTOOLS_PROD>",
    "MDM_SNOWFLAKE_WAREHOUSE": "<EDGARTOOLS_PROD_REFRESH_WH>",
    "MDM_SNOWFLAKE_SCHEMA": "EDGARTOOLS_GOLD",
    "MDM_SNOWFLAKE_ROLE": "<EDGARTOOLS_PROD_DEPLOYER>"
  }'
# Output text only (no --output text needed; put-secret-value returns ARN/VersionId
# metadata to stdout by default — do NOT paste this output into evidence, it
# contains the secret ARN. Redirect to /dev/null or capture+discard if running live.)
```

**Presence-check evidence for both secrets (D-08 — non-secret metadata only):**

```bash
aws secretsmanager describe-secret \
  --profile aws-admin-prod --region us-east-1 \
  --secret-id edgartools-prod/mdm/postgres_dsn \
  --query '{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate,VersionIdsToStages:VersionIdsToStages}'

aws secretsmanager describe-secret \
  --profile aws-admin-prod --region us-east-1 \
  --secret-id edgartools-prod/mdm/snowflake \
  --query '{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate,VersionIdsToStages:VersionIdsToStages}'
# A populated secret has a "VersionIdsToStages" entry with stage "AWSCURRENT"
# pointing at a version created by put-secret-value above (i.e., LastChangedDate
# advances and VersionIdsToStages is non-empty). An empty/never-populated
# container (Terraform-created) has no AWSCURRENT version with a written value.
```

## Dev Hosted-Graph Precedent (cited per D-04, GRAPH-01/GRAPH-02)

`.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md`
contains, as of 2026-06-12 (dev, `EDGARTOOLS_DEV`, connection `snowconn`,
profile `sec_platform_deployer`):

- Native App grants SQL (`infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`)
  applied successfully, plus two account-level grants
  (`CREATE COMPUTE POOL`, `CREATE WAREHOUSE` on `Neo4j_Graph_Analytics`).
- An initial strict `mdm verify-graph` run that **failed** only on
  `compute_pool` (no rows from `show_available_compute_pools()`), with SQL
  parity already `ok` (15 nodes / 4 edges, no diagnostics).
- A post-remediation strict `mdm verify-graph` run that **passed** fully:
  `status: ok`, `native_app.status: ok`, compute pool `CPU_X64_XS` available
  (7 rows), `graph_info`/`bfs`/`wcc` all `ok`, and `phase3_acceptance: true`.
- An AWS `run-aws-mdm-e2e.sh --env dev --status-only` run showing all 6 stages
  (`mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`, `mdm_sync_graph`,
  `mdm_verify_graph`, `mdm_counts`) at `SUCCEEDED` from a prior live full run
  (`aws-mdm-e2e-1781277675-*` execution names).
- Relationship parity table for 11 relationship types (all deltas = 0).

**What's new in Phase 3 vs. this precedent:**
- Phase 3 D-09 runs a **fresh** full E2E (`run-aws-mdm-e2e.sh --env dev`,
  no `--status-only`) — new Step Functions executions, new evidence, but the
  same chain/preflight pattern already proven above.
- Phase 3 does NOT re-run `verify-graph` as a standalone GRAPH-01/GRAPH-02
  proof — that requirement pair is satisfied by citing the above as-is. The
  D-09 rehearsal's preflight + `mdm_verify_graph` stage are incidental
  byproducts of the rehearsal, not a separate GRAPH proof.
- Phase 3 adds the dev MDM Postgres re-verification (D-03) and prod
  `--status-only`/secret-runbook work, neither of which exists in the cited
  precedent.

## Launch Gate Matrix Integration

`01-LAUNCH-GATE-MATRIX.md` rows that Phase 3 evidence must update (all
currently `BLOCKED`):

| Matrix row | Phase 3 evidence that updates it |
|---|---|
| "MDM Snowflake Postgres secret container and connectivity" | Dev re-verification (D-03) results as **dev precedent refresh**; prod remains BLOCKED pending D-05/D-06 secret population — but the runbook commands (this doc's "MDM Secret Population Runbook") give the exact required-fix commands. |
| "`edgar-warehouse mdm sync-graph` hosted graph materialization" | Cited via `03-LIVE-DEV-RUN.md` (D-04) — dev precedent only; row stays BLOCKED for prod per "Dev Vs Prod Distinction" rule. |
| "Strict `edgar-warehouse mdm verify-graph`" | Same — cited dev precedent (`phase3_acceptance: true`), prod proof still required separately; row stays BLOCKED. |
| "AWS MDM hosted graph E2E" | D-09 fresh dev rehearsal evidence supplements the cited precedent; prod row stays BLOCKED — D-02's `--status-only` reproduction documents WHY (missing `infra/aws-prod-application.json`). |

`01-LAUNCH-GATE-MATRIX.md` "## Required Production Identifiers" — Phase 3
should update the checkbox list with:
- `[ ]` → still unchecked for `edgartools-prod/mdm/postgres_dsn` and
  `edgartools-prod/mdm/snowflake` (population runbook documented, not yet
  executed against real prod values — D-05/D-06 produce the runbook, not the
  population itself, since prod Terraform hasn't applied these secret
  containers yet).
- `edgartools-prod/mdm/neo4j` — annotate as "not required / legacy" per D-06.
- `edgartools-prod/mdm/api_keys` — annotate as "deferred, consumer unclear"
  per D-06.

`evidence/mdm-hosted-graph.md` (Phase 1 template, this phase's destination)
currently has placeholder sections "Verify-Graph Non-Secret Payload Summary
Template" and "Dev Precedent Reconciliation" — Phase 3 should populate the
"Dev Precedent Reconciliation" section's already-correct dev numbers (15
nodes / 4 edges / `phase3_acceptance: true`) are already filled in; Phase 3
adds a NEW section for the D-09 fresh dev rehearsal run (with its own
Step-Functions execution names/timestamps) and a NEW section for the D-02
prod `--status-only` reproduction and D-03 dev Postgres re-verification.

## Acceptance vs Debug Framing (D-11/D-12)

Per D-11, Phase 3 does **not** restate the `--skip-preflight` warning. For
citation purposes only, the existing warning text lives at:

- `infra/scripts/run-aws-mdm-e2e.sh` lines 31-32 (`--help` text):
  `"--skip-preflight   Skip local verify-graph preflight before AWS executions. This cannot satisfy Phase 3 acceptance."`
- `infra/scripts/run-aws-mdm-e2e.sh` lines 209-211 (inline runtime warning when
  `--skip-preflight` is actually passed).
- `01-LAUNCH-GATE-MATRIX.md` line ~61 ("Secret-Safety Rules" section):
  `"--skip-preflight runs are emergency/debug only. They cannot satisfy Phase 3 acceptance or go-live gates."`

Phase 3 deliverables should link to these locations (e.g. "see script
`--help` / `01-LAUNCH-GATE-MATRIX.md`") rather than reproduce the warning text.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Dev MDM Postgres (Snowflake-hosted, `*.snowflake.app`) is reachable from this execution environment's local shell once `MDM_DATABASE_URL` is exported from Secrets Manager — i.e., it is NOT behind the same "private VPC" restriction CLAUDE.md documents for the original RDS instance. | "Dev MDM Postgres Re-Verification (D-03)" / Pitfall 2 | If wrong, D-03's primary-path commands fail and the planner must schedule the ECS `run-task` fallback as the primary (not backup) path — adds AWS task-definition-revision lookup as a prerequisite step. |
| A2 | The `edgartools-prod/mdm/snowflake` secret's expected JSON key shape (uppercase `MDM_SNOWFLAKE_*`/`DBT_SNOWFLAKE_*` keys, e.g. `MDM_SNOWFLAKE_ACCOUNT`, `MDM_SNOWFLAKE_SCHEMA` defaulting to `EDGARTOOLS_GOLD`) for prod should mirror the same key names `_snowflake_setting()` checks for dev — no prod-specific secret JSON shape documentation was found, so this is inferred directly from `edgar_warehouse/mdm/export.py`. | "MDM Secret Population Runbook (D-05–D-08)" — `snowflake` secret command | If the prod runtime expects different key casing or additional keys (e.g. a `ROLE` requirement enforced only in prod), the placeholder command in the runbook would need correction before real population — but since D-05/D-06 only require the RUNBOOK (not actual population) this phase, the risk is limited to "runbook needs a follow-up edit," not a live failure. |
| A3 | `infra/scripts/bootstrap-aws-mdm-secrets.sh --env prod` will resolve `NAME_PREFIX=edgartools-prod` and `SECRET_ID=edgartools-prod/mdm/postgres_dsn` correctly even though the secret container itself may not yet exist (Terraform for prod MDM secrets not yet applied per STATE.md blockers). | "MDM Secret Population Runbook (D-05–D-08)" — `postgres_dsn` command | If the `edgartools-prod/mdm/postgres_dsn` secret container doesn't exist yet, `put-secret-value` will fail with `ResourceNotFoundException` — this is EXPECTED and should be documented as the BLOCKED-row state (consistent with D-05's framing: "document... commands... for the BLOCKED row", not "execute against real prod"). |

## Open Questions

1. **Is there a `bootstrap-aws-mdm-secrets.sh`-equivalent helper for the `snowflake` secret?**
   - What we know: `bootstrap-aws-mdm-secrets.sh` only handles `postgres_dsn`
     (validates DSN shape per `audit-mdm-snowflake-postgres-cutover.py`'s
     `validate_snowflake_postgres_dsn`). No equivalent script for
     `edgartools-prod/mdm/snowflake` was found in `infra/scripts/`.
   - What's unclear: Whether a raw `put-secret-value` with a hand-built JSON
     payload (as documented above) is the intended population method, or
     whether one should exist but hasn't been written yet.
   - Recommendation: Document the raw `put-secret-value` command (done above)
     as the D-05 runbook entry; this is consistent with "document full
     commands with placeholders" (D-05) regardless of whether a future helper
     script is added. No blocker for Phase 3 planning.

2. **Exact dev MDM Postgres reachability (A1) — confirm at execute time.**
   - What we know: original RDS was VPC-private (CLAUDE.md); migrated target
     is Snowflake Postgres (`*.snowflake.app`, `sslmode=require`), which is
     typically publicly routable for Snowflake-managed Postgres.
   - What's unclear: No live connection was attempted in this research
     session (research-only constraint).
   - Recommendation: planner should make the first D-03 task attempt the
     local path and have the ECS `run-task` fallback (documented above) ready
     as an alternate task branch if the local path fails with a DNS/connection
     error.

## Validation Architecture

This phase produces no application code and no automated test suite changes —
deliverables are live command runs captured as evidence/runbook Markdown.
`workflow.nyquist_validation` is not explicitly disabled in `.planning/config.json`,
but the standard Test Framework / Phase Requirements → Test Map sections are
not applicable to an operational-acceptance phase with zero new source files.

### Sampling Rate
- **Per task:** Manual verification — exit codes and JSON payload `status`/`passed`
  fields from each live command (e.g. `mdm verify-graph` payload `status: "ok"`,
  `run-aws-mdm-e2e.sh` exit 0 for dev rehearsal / exit 1 for prod `--status-only`
  reproduction).
- **Phase gate:** All five evidence categories (dev rehearsal, prod
  `--status-only` reproduction, dev Postgres re-verify, GRAPH precedent
  citation, secret runbook) present in `evidence/mdm-hosted-graph.md` and
  `runbook/mdm-secrets.md` before `/gsd:verify-work`.

### Wave 0 Gaps
None — no test infrastructure changes needed for this phase.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — phase uses existing AWS IAM profile / Snowflake connection auth, no new auth code. |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A — no new access-control code; existing IAM/Snowflake role grants unchanged. |
| V5 Input Validation | no | N/A — no new code paths accept untrusted input. |
| V6 Cryptography | no | N/A — secrets remain in AWS Secrets Manager / Snowflake; no custom crypto. |

### Known Threat Patterns for {stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret value leakage into evidence/runbook Markdown (DSNs, ARNs, full `put-secret-value` output) | Information Disclosure | D-08's `describe-secret`-presence-check-only rule; `mask_dsn()` pattern from `audit-mdm-snowflake-postgres-cutover.py`; never `get-secret-value --query SecretString` output pasted into committed files (SEC-01). |
| Accidental prod state mutation while reproducing the `--status-only` blocker (D-02) | Tampering | The reproduction fails before any AWS API call (Pitfall 4) — inherently safe; planner should NOT add `--skip-preflight` or remove the `--status-only` flag when reproducing D-02. |
| `mdm migrate` run against the wrong `MDM_DATABASE_URL` (e.g. accidentally targeting prod once secrets exist) | Tampering | Always `echo $MDM_DATABASE_URL | sed 's/:[^:@]*@/:***@/'`-style mask-check (never raw echo) the masked host before running `mdm migrate`; D-03 is scoped to dev only this phase. |

## Sources

### Primary (HIGH confidence — read in full this session)
- `infra/scripts/run-aws-mdm-e2e.sh` — full file read (233 lines): flag parsing, `state_machine_arn`/`print_state_machine_status`, `warn_lingering_neo4j_references`, `run_hosted_graph_preflight`, `start_and_wait`, full 6-stage chain.
- `edgar_warehouse/mdm/cli.py` — argparse registration (lines 1-200) and handlers for `migrate`, `counts`, `check-connectivity`, `sync-graph`, `verify-graph`, `backfill-relationships` (lines 650-940).
- `edgar_warehouse/mdm/database.py` — `get_engine()` / `MDM_DATABASE_URL` (lines 73-74).
- `edgar_warehouse/mdm/migrations/runtime.py` — `MDM_TABLES`, `migrate`, `check_connectivity`, `count_tables`.
- `edgar_warehouse/mdm/export.py` — `SnowflakeConnectionSettings.from_env()`, `_snowflake_setting()`, `_snowflake_secret_payload()`.
- `edgar_warehouse/mdm/snowflake_graph.py` — `SnowflakeGraphVerifier.verify()`, Native App check defaults and `_verify_native_app`.
- `infra/scripts/bootstrap-aws-mdm-secrets.sh` — full file read: DSN construction/validation, `put-secret-value` invocation.
- `infra/scripts/audit-mdm-snowflake-postgres-cutover.py` — `validate_snowflake_postgres_dsn`, `extract_dsn`, `mask_dsn` (DSN shape invariants).
- `infra/terraform/modules/warehouse_runtime/main.tf` — `aws_secretsmanager_secret.mdm_postgres_dsn`/`mdm_neo4j`/`mdm_api_keys`/`mdm_snowflake` resource definitions confirming `${name_prefix}/mdm/<name>` naming.
- `infra/aws-dev-application.json` — confirms `mdm.secrets.*` ARN shape and that `infra/aws-prod-application.json` does not exist.
- `docs/aws-mdm-snowflake-postgres-cutover.md` — Snowflake Postgres cutover runbook, `mdm-check-connectivity` Step Functions broken-state-machine known issue + `ecs run-task` fallback.
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` — full dev hosted-graph E2E evidence (cited per D-04).
- `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md` — Phase 2 runbook format precedent.
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md` — BLOCKED rows + Required Production Identifiers.
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md` — evidence template structure.
- `.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-CONTEXT.md` — locked Phase 3 decisions D-01..D-12.
- `CLAUDE.md` / `AGENTS.md` — MDM secret naming convention, "private VPC" caveat for original RDS, `MDM_DATABASE_URL` local dev value.

### Secondary (MEDIUM confidence)
None — all claims verified against primary sources read this session.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: N/A — no new packages/libraries.
- Architecture: HIGH — every command/script/handler read in full from source.
- Pitfalls: HIGH for Pitfalls 1, 3, 4 (directly sourced from script/precedent/code); MEDIUM for Pitfall 2 (A1 — dev Postgres reachability not live-tested this session, flagged as Open Question).

**Research date:** 2026-06-15
**Valid until:** 14 days (operational/CLI surface is stable, but AWS Step Functions executions and Native App compute-pool activation state are time-sensitive — re-check compute pool status immediately before D-09 rehearsal regardless of this research's age).
