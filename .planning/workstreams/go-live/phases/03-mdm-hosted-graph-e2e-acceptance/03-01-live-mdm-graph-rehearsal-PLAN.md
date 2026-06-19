---
phase: 03
plan: 03-01-live-mdm-graph-rehearsal
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md
autonomous: true
requirements: [MDM-01, GRAPH-01, GRAPH-02, LIVE-03]

must_haves:
  truths:
    - "A full dev rehearsal of run-aws-mdm-e2e.sh --env dev completed: local strict verify-graph preflight passed and gated a 6-stage Step Functions chain (mdm_migrate, mdm_run, mdm_backfill_relationships, mdm_sync_graph, mdm_verify_graph, mdm_counts) to SUCCEEDED."
    - "The prod blocker is reproduced read-only: run-aws-mdm-e2e.sh --env prod --status-only exits 1 on the infra/aws-prod-application.json existence check with zero AWS API calls."
    - "Dev MDM Postgres connectivity, idempotent migration, and counts were re-verified live with the DSN masked before any output reached evidence."
    - "The cited dev hosted-graph precedent (03-LIVE-DEV-RUN.md: 15 nodes / 4 edges, all parity ok, Native App graph_info/bfs/wcc ok, compute pool CPU_X64_XS, phase3_acceptance true) is referenced for GRAPH-01/GRAPH-02 without a standalone re-run."
    - "The masked dev postgres_dsn shape (structure only, no values) is captured in a stable, referenceable form for plan 03-02 (D-07)."
  artifacts:
    - path: ".planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md"
      provides: "Appended '## Phase 3 Live Checks Actually Run' section with dev rehearsal, prod --status-only reproduction, dev Postgres re-verify, and masked DSN shape reference."
      contains: "## Phase 3 Live Checks Actually Run"
  key_links:
    - from: "evidence/mdm-hosted-graph.md (Phase 3 section)"
      to: "03-LIVE-DEV-RUN.md"
      via: "citation for GRAPH-01/GRAPH-02 (D-04)"
      pattern: "03-LIVE-DEV-RUN"
    - from: "evidence/mdm-hosted-graph.md (masked DSN shape)"
      to: "plan 03-02 prod postgres_dsn runbook (D-07)"
      via: "non-secret connection-string structure reference"
      pattern: "postgresql://<user>:<password>@<host>.snowflake.app"
---

<objective>
Run the four live acceptance activities for Phase 3 and append all evidence to the
EXISTING Phase 1 evidence file
`.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md`
(append in place — mirroring how Phase 2 appended a new dated section to
`evidence/aws.md`/`evidence/snowflake.md`; do NOT create a new Phase 3 evidence file).

The four activities:
(a) Full dev rehearsal of `run-aws-mdm-e2e.sh --env dev` — default local `verify-graph`
    preflight gating the 6-stage Step Functions chain to SUCCEEDED (LIVE-03 / GRAPH-02; D-09/D-10).
(b) Read-only prod blocker reproduction: `run-aws-mdm-e2e.sh --env prod --status-only` must
    exit 1 on the `infra/aws-prod-application.json` existence check, zero AWS calls (LIVE-03; D-02).
(c) Live dev MDM Postgres re-verification: `mdm check-connectivity` / `mdm migrate` / `mdm counts`
    against dev `MDM_DATABASE_URL`, DSN masked before any output (MDM-01; D-03/D-07).
(d) Cite the existing dev hosted-graph precedent `03-LIVE-DEV-RUN.md` as-is for GRAPH-01/GRAPH-02
    (D-04) — no standalone `verify-graph` re-run.

Purpose: Produce fresh live acceptance evidence for the MDM + hosted-graph path and the masked
dev DSN shape that plan 03-02 (secrets runbook + matrix) will consume.

Output: Appended `## Phase 3 Live Checks Actually Run` section in the Phase 1 evidence file.

SCOPE EXCLUSIONS (handled by plan 03-02, NOT here):
- Do NOT create `runbook/mdm-secrets.md` (secret-population runbook — D-05/D-06/D-08 is 03-02).
- Do NOT edit `01-LAUNCH-GATE-MATRIX.md` (BLOCKED-row / Required-Identifiers updates is 03-02).
- Do NOT run `aws secretsmanager describe-secret` / `put-secret-value` against prod here.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-CONTEXT.md
@.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-RESEARCH.md
@.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-PATTERNS.md
@.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-VALIDATION.md

# Evidence destination — APPEND a new section below existing content, do not rewrite:
@.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md

# Dev hosted-graph precedent cited as-is for GRAPH-01/GRAPH-02 (D-04):
@.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md

# The E2E driver under test (read in full):
@infra/scripts/run-aws-mdm-e2e.sh

<interfaces>
<!-- Two completely separate connection surfaces under the `mdm` CLI. NEVER conflate
     their env-var setup across tasks (RESEARCH.md Pattern 1 / Anti-Patterns). -->

MDM Postgres surface (Task 3 only) — uses MDM_DATABASE_URL:
  edgar-warehouse mdm check-connectivity   # read-only (SELECT 1 + table introspection)
  edgar-warehouse mdm migrate              # idempotent WRITE (CREATE TABLE IF NOT EXISTS + seed)
  edgar-warehouse mdm counts               # read-only (SELECT COUNT(*) per table)
  # get_engine() does: url = os.environ["MDM_DATABASE_URL"]  -> KeyError if unset.

Snowflake graph surface (Task 1 only) — via SNOW_CONNECTION/SNOWFLAKE_CONNECTION or
  MDM_SNOWFLAKE_* / DBT_SNOWFLAKE_* or ~/.snowflake/connections.toml. NEVER reads
  MDM_DATABASE_URL:
  edgar-warehouse mdm sync-graph / verify-graph   # driven by run-aws-mdm-e2e.sh preflight + stages

run-aws-mdm-e2e.sh control flow (lines 75-77, 203-229):
  - line 77:  [[ -f infra/aws-<env>-application.json ]] || fail   # runs BEFORE RUN_E2E branch
  - line 203: if RUN_E2E != true -> print_state_machine_status; exit 0   (the --status-only path)
  - line 213: run_hosted_graph_preflight   (local strict `mdm verify-graph` — the LIVE-03 gate)
  - lines 224-229: start_and_wait x6: mdm_migrate -> mdm_run -> mdm_backfill_relationships ->
                   mdm_sync_graph -> mdm_verify_graph -> mdm_counts
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Dev rehearsal full E2E (preflight-gated) + cite GRAPH precedent</name>
  <files>.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md</files>
  <action>
This is the Snowflake-graph surface — set ONLY the Snowflake connection (do NOT export
MDM_DATABASE_URL in this task).

Demonstrates D-09 (fresh full E2E for LIVE-03/GRAPH-02) and D-10 (preflight gates the chain).

1. Pitfall 1 precondition check: the script's default local preflight runs `mdm verify-graph`,
   which can fail at the Native App `compute_pool` check (no rows from
   `show_available_compute_pools()`) even when SQL parity is ok. If the rehearsal's preflight
   fails with `native_app.compute_pool` failed, apply the documented grant remediation cited in
   `03-LIVE-DEV-RUN.md` (`infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` plus the two
   account-level `GRANT CREATE COMPUTE POOL ON ACCOUNT` / `GRANT CREATE WAREHOUSE ON ACCOUNT`
   statements on `Neo4j_Graph_Analytics`, and activate compute pool `CPU_X64_XS`), then re-run.
   Record the remediation step (command names only, no secret output) in evidence if it was hit.

2. Run the canonical full rehearsal (RESEARCH.md verbatim; NO --status-only, NO --skip-preflight
   per D-09/D-10/D-11):
   `bash infra/scripts/run-aws-mdm-e2e.sh --env dev --aws-profile sec_platform_deployer
    --snow-connection snowconn --snowflake-database EDGARTOOLS_DEV`
   (defaults: --mdm-run-limit 5, --graph-limit 100). Wait for the 6-stage chain to complete.

3. Append a `## Phase 3 Live Checks Actually Run` section (new top-level section below existing
   Phase 1 content — analogous to Phase 2's `## Phase 2 Read-Only Checks Actually Run` append to
   evidence/aws.md). Under it add a `### Dev Rehearsal — Full E2E (D-09/D-10)` subsection with:
   the command block; `Result: succeeded.`; a Step Functions table with columns
   `Workflow | Latest status | Latest execution name | Started` for all 6 stages (fresh
   `aws-mdm-e2e-<epoch>-*` execution names from THIS run); an explicit note that the local strict
   `verify-graph` preflight PASSED and that this pass is the gate that allowed the AWS executions
   to proceed (LIVE-03 / D-10). Add a `D-09 rehearsal verify-graph payload (incidental to
   GRAPH-01/GRAPH-02, not a re-proof)` payload-summary block (Overall status / nodes / edges /
   node parity / relationship parity / Native App status / compute pool / graph_info / bfs / wcc)
   with THIS run's fresh values. Restate env (`dev`), connection (`snowconn`), database
   (`EDGARTOOLS_DEV`), and AWS profile inline. End the block with the verbatim boilerplate line
   `dev precedent only — prod proof required separately` followed by a "Production still requires:"
   sentence.

4. Add a `### GRAPH-01/GRAPH-02 Dev Precedent Citation (D-04)` subsection that cites
   `03-LIVE-DEV-RUN.md` AS-IS (15 nodes / 4 edges, node+relationship parity ok, Native App
   graph_info/bfs/wcc ok, compute pool CPU_X64_XS, phase3_acceptance true). Explicitly state no
   standalone verify-graph re-run was performed for this citation (D-04) — the rehearsal's
   preflight + mdm_verify_graph stage are incidental byproducts. Do not duplicate or restate the
   `--skip-preflight` warning text (D-11) — link to the script `--help` instead.

Use `Result: succeeded/failed` + structured summary; never paste raw task logs (SEC-01).
  </action>
  <verify>
    <manual>run-aws-mdm-e2e.sh --env dev exited 0; the local verify-graph preflight payload showed status: "ok" and gated the run; all 6 Step Functions stages (mdm_migrate, mdm_run, mdm_backfill_relationships, mdm_sync_graph, mdm_verify_graph, mdm_counts) reached SUCCEEDED. (03-VALIDATION.md Manual-Only rows: GRAPH-01, GRAPH-02, LIVE-03.)</manual>
  </verify>
  <done>
Evidence file has a new `## Phase 3 Live Checks Actually Run` section with `### Dev Rehearsal —
Full E2E (D-09/D-10)` (command + `Result: succeeded.` + 6-stage SUCCEEDED table with fresh
execution names + preflight-gate note + fresh payload summary) and `### GRAPH-01/GRAPH-02 Dev
Precedent Citation (D-04)` citing 03-LIVE-DEV-RUN.md as-is. If Pitfall 1 was hit, the grant
remediation step is recorded. `dev precedent only — prod proof required separately` boilerplate
present. No raw logs, no DSNs, no `--skip-preflight` usage.
  </done>
</task>

<task type="auto">
  <name>Task 2: Prod --status-only structural-blocker reproduction (read-only)</name>
  <files>.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md</files>
  <action>
Demonstrates D-02 (BLOCKED-row proof for LIVE-03). No credentials are exercised — the script
fails at line 77's `[[ -f "$APPLICATION_FILE" ]] || fail` BEFORE the RUN_E2E branch (Pitfall 4),
so zero AWS API calls are made.

1. Run: `bash infra/scripts/run-aws-mdm-e2e.sh --env prod --status-only`
   Expected: exit code 1, stderr `ERROR: deployment summary not found:
   <repo-root>/infra/aws-prod-application.json`, and NO `==> Step Functions in ...` output (if
   any Step Functions output appears, the wrong env/premise is in play — stop and re-check D-02).

2. Append a `### Prod --status-only Structural-Blocker Reproduction (D-02)` subsection under the
   Phase 3 section: the command block; `Result: failed (exit 1).`; a one-line summary that it
   failed on the `infra/aws-prod-application.json` existence check with zero AWS API calls; and a
   `BLOCKED - see 01-LAUNCH-GATE-MATRIX.md row 'AWS MDM hosted graph E2E'.` cross-reference line
   (exact matrix row name). Do NOT add `--skip-preflight`, do NOT remove `--status-only`, and do
   NOT modify the script to bypass the existence check (Tampering threat T-03-02).

Capture the stderr line as evidence text (it contains a repo path only, no secrets) — never paste
raw stack traces.
  </action>
  <verify>
    <manual>run-aws-mdm-e2e.sh --env prod --status-only exited 1 on the infra/aws-prod-application.json existence check with zero AWS API calls (no `==> Step Functions` output). (03-VALIDATION.md Manual-Only row: LIVE-03.)</manual>
  </verify>
  <done>
Evidence file Phase 3 section has a `### Prod --status-only Structural-Blocker Reproduction (D-02)`
subsection with command, `Result: failed (exit 1).`, the zero-AWS-calls note, and the exact
`BLOCKED - see 01-LAUNCH-GATE-MATRIX.md row 'AWS MDM hosted graph E2E'.` cross-reference. No
`--skip-preflight`, no script modification.
  </done>
</task>

<task type="auto">
  <name>Task 3: Dev MDM Postgres re-verify (masked DSN + shape reference for 03-02)</name>
  <files>.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md</files>
  <action>
This is the MDM Postgres surface — uses ONLY `MDM_DATABASE_URL` (do NOT set any Snowflake graph
env vars in this task). Demonstrates D-03 (MDM-01 dev-precedent refresh) and D-07 (masked DSN
shape reference for plan 03-02). Scoped to DEV only.

1. Load the dev DSN into the environment WITHOUT printing it (Secret-Safety Rules):
   `export MDM_DATABASE_URL="$(aws secretsmanager get-secret-value
    --secret-id edgartools-dev/mdm/postgres_dsn --query SecretString --output text)"`
   Mask-check before any further action (Tampering threat T-03-03 — verify the target is dev):
   `echo "$MDM_DATABASE_URL" | sed 's/:[^:@]*@/:***@/'` and confirm host ends in `.snowflake.app`.
   NEVER paste raw `get-secret-value` output anywhere.

2. Primary path (Pitfall 2 / A1 — dev Postgres reachability not pre-confirmed):
   - `uv run --extra s3 --extra snowflake edgar-warehouse mdm check-connectivity`  (read-only)
   - `uv run --extra s3 --extra snowflake edgar-warehouse mdm migrate`  (idempotent WRITE — Pitfall
     3; expect a no-op `{"dialect":...,"seeded":true,"tables":{...}}` payload; label it
     "idempotent migration re-apply", not "read-only check")
   - `uv run --extra s3 --extra snowflake edgar-warehouse mdm counts`  (read-only)
   If the local connection fails (DNS/timeout — `psycopg2.OperationalError`), fall back to the
   documented `aws ecs run-task` pattern against cluster `edgartools-dev-warehouse` with
   `containerOverrides command:["mdm","check-connectivity"]` (and `migrate`/`counts`) per
   `docs/aws-mdm-snowflake-postgres-cutover.md`. Do NOT use the `edgartools-dev-mdm-check-connectivity`
   Step Functions state machine (documented permanently broken). Record whichever path worked.

3. Append a `### Dev MDM Postgres Re-Verification (D-03)` subsection: the three commands (or the
   ECS-fallback command if used); `Result: succeeded.`; for each — masked output only
   (connectivity result, migrate payload table-count summary, counts per table). Run `mdm migrate`
   ONLY after the mask-check in step 1 confirms a dev DSN. End with the verbatim
   `dev precedent only — prod proof required separately` boilerplate + a "Production still requires:"
   sentence.

4. Add a `### Dev postgres_dsn Shape Reference (D-07 — for plan 03-02)` subsection presenting the
   DSN in placeholder form ONLY (structure, no values):
   `postgresql://<user>:<password>@<host>.snowflake.app:<port>/<database>?sslmode=require`
   with a one-line note that the prod `postgres_dsn` secret must satisfy the same
   `<host>.snowflake.app` / `database=mdm` / `sslmode=require` invariants enforced by
   `audit-mdm-snowflake-postgres-cutover.py`'s `validate_snowflake_postgres_dsn()`. This stable
   heading is the format reference plan 03-02 consumes — do not bury it.

5. `unset MDM_DATABASE_URL` afterward.
  </action>
  <verify>
    <manual>`mdm check-connectivity` and `mdm counts` returned success and `mdm migrate` returned its idempotent `seeded`/`tables` payload, all with the DSN masked via `sed 's/:[^:@]*@/:***@/'` before any output was recorded. (03-VALIDATION.md Manual-Only row: MDM-01.)</manual>
  </verify>
  <done>
Evidence file Phase 3 section has `### Dev MDM Postgres Re-Verification (D-03)` (3 commands or ECS
fallback, `Result: succeeded.`, masked outputs, migrate labeled idempotent re-apply, boilerplate)
and `### Dev postgres_dsn Shape Reference (D-07 — for plan 03-02)` with the placeholder-only DSN
shape + invariants note. No raw DSN anywhere; MDM_DATABASE_URL was loaded without printing and
unset afterward.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Secrets Manager / Snowflake Postgres → evidence Markdown (committed) | Secret values (DSN, password, ARNs) must never cross into committed evidence. |
| Local operator shell → prod AWS control plane | `--status-only` prod reproduction must not mutate or even reach prod state. |
| `MDM_DATABASE_URL` selection → `mdm migrate` (a write) | A write command must only ever target the intended dev database. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-01 | Information Disclosure | DSN / connection-string leakage into evidence Markdown (Tasks 1 & 3) | mitigate | Mask every DSN with `sed 's/:[^:@]*@/:***@/'` BEFORE any output is recorded; load `MDM_DATABASE_URL` via `get-secret-value` without printing it; present the postgres_dsn shape in placeholder form only (D-07); never paste `get-secret-value` output or raw Native App / task logs (SEC-01, D-08). |
| T-03-02 | Tampering | Accidental prod state mutation during the `--status-only` reproduction (Task 2) | mitigate | The reproduction fails at the `infra/aws-prod-application.json` existence check (line 77) before any AWS API call (Pitfall 4); do NOT add `--skip-preflight`, do NOT remove `--status-only`, do NOT modify the script to bypass the check. Any `==> Step Functions` output is a stop-and-recheck signal. |
| T-03-03 | Tampering | `mdm migrate` run against the wrong `MDM_DATABASE_URL` (Task 3) | mitigate | Mask-check the host with `sed 's/:[^:@]*@/:***@/'` and confirm a dev `.snowflake.app` target BEFORE running `mdm migrate`; phase scoped to dev only; `unset MDM_DATABASE_URL` afterward. |
| T-03-SC | Tampering | Supply-chain (npm/pip/cargo installs) | accept | No package installs in this phase — all tooling (`edgar-warehouse`, `aws`, `uv`, `snow`) already present (RESEARCH.md Package Legitimacy Audit: N/A). No slopcheck/legitimacy checkpoint required. |
</threat_model>

<verification>
Phase 3 (this plan) is complete when the Phase 1 evidence file
`01-.../evidence/mdm-hosted-graph.md` contains an appended `## Phase 3 Live Checks Actually Run`
section with all four subsections:
- `### Dev Rehearsal — Full E2E (D-09/D-10)` — exit 0, 6 stages SUCCEEDED, preflight-gate note.
- `### GRAPH-01/GRAPH-02 Dev Precedent Citation (D-04)` — cites 03-LIVE-DEV-RUN.md as-is.
- `### Prod --status-only Structural-Blocker Reproduction (D-02)` — exit 1, zero AWS calls.
- `### Dev MDM Postgres Re-Verification (D-03)` + `### Dev postgres_dsn Shape Reference (D-07)`.

Every command block uses `Result: succeeded/failed`, masked output only, no raw logs/DSNs.
No `--skip-preflight` anywhere. No runbook/matrix edits (those are plan 03-02).
</verification>

<success_criteria>
- (a) Dev rehearsal: `run-aws-mdm-e2e.sh --env dev` exited 0 with local preflight pass gating the
  6-stage SUCCEEDED chain; fresh evidence recorded. (LIVE-03, GRAPH-02 — D-09/D-10)
- (b) Prod blocker: `run-aws-mdm-e2e.sh --env prod --status-only` exited 1 on the missing-file
  check with zero AWS calls; BLOCKED cross-reference recorded. (LIVE-03 — D-02)
- (c) Dev MDM Postgres: connectivity/idempotent-migrate/counts re-verified with masked DSN;
  placeholder DSN shape captured for plan 03-02. (MDM-01 — D-03/D-07)
- (d) GRAPH precedent cited as-is, no standalone re-run. (GRAPH-01/GRAPH-02 — D-04)
- Evidence appended to the EXISTING Phase 1 file; no new evidence file, no runbook, no matrix edit.
- All three threat-model mitigations honored; no secret values committed.
</success_criteria>

<output>
Append the `## Phase 3 Live Checks Actually Run` section to
`.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md`,
then create
`.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-01-live-mdm-graph-rehearsal-SUMMARY.md`
when done.
</output>
