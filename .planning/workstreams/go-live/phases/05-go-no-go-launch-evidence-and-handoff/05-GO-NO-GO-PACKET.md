# Go/No-Go Launch Decision Packet — v1.5 Go-Live

- This packet contains non-secret evidence only. No DSNs, passwords, tokens,
  ARNs, raw connector exceptions, Terraform state, or full generated
  deployment JSON appear anywhere below. Secret NAMES (for example
  `edgartools-prod/mdm/postgres_dsn`) are allowed; secret VALUES are never
  allowed.

## Launch Decision: NO-GO — Conditional

**Date:** 2026-06-16 UTC

This is the current, explicit launch decision for the v1.5 go-live milestone.
It is **NO-GO — Conditional**: production launch is blocked on exactly five
items (below), each of which has a documented remediation step. None of the
work in this milestone constitutes a production launch — it is launch-gate
proof, evidence capture, and operator handoff. This packet lists exactly what
must be satisfied to flip the decision to GO. No part of this document should
be read as authorizing a production deploy, a production data load, or any
write action against production AWS, Snowflake, or MDM systems.

The authoritative per-gate detail (25 BLOCKED rows, 6 PASS rows, owners, exact
required-fix and required-rerun-proof text) lives in the launch gate matrix:

- [`01-LAUNCH-GATE-MATRIX.md`](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md)

This packet synthesizes that matrix into a readable decision. It does **not**
duplicate individual gate rows — read the matrix directly for row-level
required-fix text, exact commands, and evidence-file pointers.

## Dev Precedent Summary

### Milestone progress

Counting `*-SUMMARY.md` files under each go-live phase directory at execution
time: Phase 1 has 3, Phase 2 has 2, Phase 3 has 2, Phase 4 has 3 — 10 plan
summaries total across Phases 1-4. `STATE.md` frontmatter confirms
`completed_phases: 4`, `completed_plans: 10`, `total_plans: 12`. The honest
framing is: **Phases 1-4 complete (10 plans); Phase 5 in progress** (this
packet and its companion runbook are two of Phase 5's plans). This is dev
rehearsal and evidence-capture progress, not production launch progress —
production launch readiness is the subject of the NO-GO blockers below.

### Per-system rehearsal evidence

Every line below cites dev rehearsal evidence only. **dev precedent only —
prod proof required separately** applies to each one individually; none of
these citations may be read as production proof.

- **AWS:** Phase 1 ran a read-only `terraform plan` for
  `infra/terraform/accounts/prod/` and validated the resource-add count and
  all 22 `outputs.tf` output names — see
  [evidence/aws.md](../01-production-readiness-inventory-and-launch-gate-contract/evidence/aws.md)
  (dev precedent only — prod proof required separately). No real apply
  action has been run against a real S3 backend.
- **Snowflake/dbt:** Phase 1 captured a structural-blocker smoke test
  (`infra/scripts/deploy-snowflake-stack.sh` exits before any apply because
  the 3 prod `backend.hcl` files do not exist) — see
  [evidence/snowflake.md](../01-production-readiness-inventory-and-launch-gate-contract/evidence/snowflake.md)
  (dev precedent only — prod proof required separately). No prod-target dbt
  run has been executed.
- **MDM / hosted graph:** Phase 3 ran a full dev rehearsal E2E with all 6
  pipeline stages (including `mdm_sync_graph` and `mdm_verify_graph`)
  reported SUCCEEDED against dev Snowflake Postgres and the dev Native App
  compute pool — see
  [evidence/mdm-hosted-graph.md](../01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md)
  (dev precedent only — prod proof required separately). No prod MDM secret
  population or prod AWS MDM E2E has been run.
- **Dashboard:** Phase 1/4 recorded text UAT notes with pass/fail for all 5
  launch-critical dashboard views against dev/dev-like data, dated 2026-06-16
  UTC — see
  [evidence/dashboard-security.md](../01-production-readiness-inventory-and-launch-gate-contract/evidence/dashboard-security.md)
  (dev precedent only — prod proof required separately). No production or
  production-like UAT pass has been recorded.

## NO-GO Blockers

This packet enumerates exactly the 5 NO-GO blockers. Each blocker names the
launch gate matrix row(s) it blocks (by gate name — see the matrix for the
full required-fix and required-rerun-proof text) and the remediation step
that flips it from BLOCKED to PASS. All 5 must flip to PASS before a GO
decision is possible; partial completion keeps the decision at NO-GO.

### Blocker 1: Prod AWS infrastructure not yet applied

Maps to the matrix rows "AWS passive infrastructure outputs", "Production
bronze data reuse from dev bronze", "Production AWS application manifest
(`infra/aws-prod-application.json`)", and "AWS active application deploy" in
[01-LAUNCH-GATE-MATRIX.md](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md).
`infra/aws-prod-application.json` is absent because no real Terraform apply
action has run against a real S3 backend for `infra/terraform/accounts/prod/`, and
`infra/scripts/deploy-aws-application.sh` has not been run for production.
**Remediation:** an AWS operator applies the prod Terraform stack against a
real backend, fixes the documented `versions.tf` constraint issue first, then
runs the production deploy script through
[runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md)
with explicit image digests and the freshly resolved `edgar-identity` secret
ARN, and records non-secret evidence in `evidence/aws.md`.

### Blocker 2: Prod MDM Secrets Manager secrets not yet populated

Maps to the matrix row "MDM Snowflake Postgres secret container and
connectivity" in
[01-LAUNCH-GATE-MATRIX.md](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md).
The secret containers `edgartools-prod/mdm/postgres_dsn` and
`edgartools-prod/mdm/snowflake` (names only — no values recorded anywhere) do
not yet hold production values. **Remediation:** an MDM operator follows
[runbook/mdm-secrets.md](../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md)
sections 1-2 to populate both secrets with real production values, then
re-runs `check-connectivity`, `migrate`, and `counts` against the prod
`MDM_DATABASE_URL` and records a non-secret pass summary in
`evidence/mdm-hosted-graph.md`.

### Blocker 3: Prod Snowflake dbt not yet deployed

Maps to the matrix rows "Snowflake native S3 pull stack", "Snowflake
deployer direct grants for gold dynamic tables", "dbt compile/run/test for
production target", and "`EDGARTOOLS_GOLD_STATUS` and dynamic-table
freshness" in
[01-LAUNCH-GATE-MATRIX.md](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md).
The 3 prod `backend.hcl` files and a real `terraform.tfvars` with production
Snowflake identifiers do not exist, which blocks every downstream Snowflake
step. **Remediation:** a Snowflake operator creates the missing backend
configs once a production Snowflake account exists, runs
[runbook/snowflake-native-pull.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/snowflake-native-pull.md),
confirms `EDGARTOOLS_PROD_DEPLOYER` direct `SELECT` grants on
`EDGARTOOLS_SOURCE`, then runs `dbt run --target prod` and
`dbt test --target prod` per
[runbook/dbt-gold.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md)
and records pass/fail and freshness summaries in `evidence/snowflake.md`.

### Blocker 4: Prod hosted graph E2E not yet verified

Maps to the matrix rows "`edgar-warehouse mdm sync-graph` hosted graph
materialization", "Strict `edgar-warehouse mdm verify-graph`", and "AWS MDM
hosted graph E2E" in
[01-LAUNCH-GATE-MATRIX.md](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md).
The dev rehearsal succeeded end-to-end, but no run has been made against
production Snowflake connection/database, production MDM secrets, or the
production Native App compute-pool selector. **Remediation:** after Blockers
2 and 3 flip to PASS, an MDM operator runs bounded `mdm sync-graph`, then
strict local `mdm verify-graph` against the production Snowflake
connection, then `infra/scripts/run-aws-mdm-e2e.sh` for production with
explicit limits and stop conditions once `infra/aws-prod-application.json`
exists, recording non-secret stage results in `evidence/mdm-hosted-graph.md`.

### Blocker 5: Prod dashboard UAT not yet run

Maps to the matrix row "Dashboard operator inspection views" in
[01-LAUNCH-GATE-MATRIX.md](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md).
Dev-run UAT notes exist for all 5 views, but no UAT pass has been recorded
against a production or production-like read-only configuration.
**Remediation:** after Blockers 1-4 flip to PASS, a dashboard reviewer
launches the dashboard against a production-like read-only configuration
(after the CLI/dbt/Native App gates are available) and records text UAT
notes for all 5 launch-critical views in `evidence/dashboard-security.md`.

## Prod Launch Sequence

When all five blockers above are PASS, the production launch sequence runs
in this order. Each step links to its existing runbook rather than
re-pasting commands here:

1. **AWS deploy** — apply prod Terraform, then run the production deploy
   script. See
   [runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md).
2. **Snowflake native pull** — create the native-pull stack (storage
   integration, file formats, external stage, source mirror tables, pipe,
   stream, stored procedures, task). See
   [runbook/snowflake-native-pull.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/snowflake-native-pull.md).
3. **dbt** — run and test the gold dynamic tables against the production
   target. See
   [runbook/dbt-gold.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md).
4. **MDM secrets population** — populate the two production MDM secrets. See
   [runbook/mdm-secrets.md](../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md).
5. **MDM E2E** — run bounded production MDM sync and the AWS MDM hosted
   graph E2E with explicit limits and stop conditions. See
   [evidence/mdm-hosted-graph.md](../01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md)
   for the dev-rehearsal stage list this run must reproduce in production.
6. **verify-graph** — run strict `edgar-warehouse mdm verify-graph` against
   the production Snowflake connection and Native App compute pool.
7. **Dashboard UAT** — launch the dashboard against the production-like
   read-only configuration and record UAT notes for all 5 views.

No step in this sequence runs before its predecessor's gate is recorded as
PASS in the launch gate matrix.

## Required Approvals

Each sequence step requires sign-off from the owner shown in the launch gate
matrix Owner/Source column before it runs, and the prior step's gate must
already be PASS:

| Sequence step | Required approver |
|---|---|
| AWS deploy | AWS operator |
| Snowflake native pull, dbt | Snowflake operator |
| MDM secrets population, MDM E2E, verify-graph | MDM operator |
| Dashboard UAT | Dashboard reviewer |
| Final GO/NO-GO decision flip | Release owner |

No sequence step runs before its named owner approves it, and no step runs
out of order relative to the sequence above.

## Evidence Capture Rules

Evidence capture for the production launch sequence follows the same SEC-01
non-secret rules established in Phase 1. Every evidence entry records: the
exact command run, an environment label (`prod`), pass/fail result, key
counts or statuses, and sanitized links to detail files.

- Never paste DSNs, passwords, tokens, Terraform state, raw connector
  traces or exceptions, full task logs, raw Native App job logs, or full
  generated deployment JSON.
- Generated JSON such as `infra/aws-prod-application.json` is summarized
  only as file presence, top-level keys, state-machine name list, and
  image-ref format — the JSON body is never pasted.
- Secrets may be loaded into runtime environment variables at execution
  time, but the value must never be printed, logged, or committed.

See the full Secret-Safety Rules section in
[01-LAUNCH-GATE-MATRIX.md](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md)
for the complete rule set rather than restating it here.

## Post-Launch Follow-Up

These items are go-live-specific follow-up that future operators need
milestone-local context for. They are tracked authoritatively in the repo
`TODOS.md` (added in plan 05-02) — this section provides milestone-local
context only and does not duplicate the `TODOS.md` entries:

- **Production dashboard UAT** — deferred until prod MDM secrets and prod
  Snowflake connection exist (deferred from Phase 4 D-08/D-09). Once
  Blockers 1-4 flip to PASS, a dashboard reviewer must run the prod UAT pass
  described in Blocker 5 above.
- **Production MDM secrets population runbook execution** — the runbook at
  [runbook/mdm-secrets.md](../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md)
  is written and dev-verified; it has not yet been executed against the
  real production secret names `edgartools-prod/mdm/postgres_dsn` and
  `edgartools-prod/mdm/snowflake`.
- **`EDGARTOOLS_PROD_DEPLOYER` direct SELECT grants** — analogous to the
  resolved dev `EDGARTOOLS_DEV_DEPLOYER` grant gap documented in
  `CLAUDE.md`/`TODOS.md`; must be confirmed against the real production
  Snowflake account before any `dbt run --target prod --full-refresh`.
- **External Neo4j runtime remnant deprecation** — formal removal or
  deprecation of any remaining external Neo4j runtime paths, deferred per
  the go-live `REQUIREMENTS.md` "Future Requirements" section.

## References

- [01-LAUNCH-GATE-MATRIX.md](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md)
- [evidence/aws.md](../01-production-readiness-inventory-and-launch-gate-contract/evidence/aws.md)
- [evidence/snowflake.md](../01-production-readiness-inventory-and-launch-gate-contract/evidence/snowflake.md)
- [evidence/mdm-hosted-graph.md](../01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md)
- [evidence/dashboard-security.md](../01-production-readiness-inventory-and-launch-gate-contract/evidence/dashboard-security.md)
- [runbook/launch-ops.md](runbook/launch-ops.md) — companion stop/rollback runbook for the production launch sequence above.
