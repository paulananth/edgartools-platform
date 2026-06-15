# Dashboard UAT + Security Evidence - Phase 1 Production Readiness

Date: 2026-06-14 UTC
Environment: production-like read-only configuration required; dev UAT rows are precedent only and require separate production proof.

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, Terraform state, raw connector traces, raw connector exceptions, stack traces, full task logs, and unbounded exports.

## What This File Must NOT Include

Do not include:

- DSNs, passwords, tokens, or account-secret values,
- raw connector exceptions or stack traces,
- full logs,
- mutation controls or instructions,
- unbounded exports,
- full generated deployment JSON,
- raw Native App job logs.

Bounded samples are diagnostics, not exhaustive exports. Dashboard screenshots are optional if secret-safe; text UAT notes are sufficient for Phase 1.

## Read-Only / Inspection-Only Guarantee

The dashboard is inspection only. It does not run sync, repair, migrate, load, derive, grant, activate, deploy, or write actions. `Refresh metrics` only rereads cached read-only helper payloads.

The dashboard is used after CLI, dbt, and Native App gates to explain issues. It does not define acceptance. Acceptance remains with CLI verification, dbt checks, strict `edgar-warehouse mdm verify-graph`, and AWS hosted graph E2E evidence.

## Routing Policy

Operators start with CLI verification and dbt tests, then inspect the dashboard for explanation:

1. Run the relevant CLI/dbt/Native App gate and capture pass/fail evidence.
2. Use the dashboard to inspect MDM overview, hosted graph overview, mismatch diagnostics, bounded samples, and refresh timestamps.
3. Treat dashboard-only warnings as launch-blocking only when they point to a failed gate or launch-impacting data gap.

## Secret-Safe Loading Convention

Operators may load `MDM_DATABASE_URL` from AWS Secrets Manager into an environment variable using `aws secretsmanager get-secret-value ... --query SecretString --output text`, but the value must not be printed or pasted. The dashboard runtime receives the value through the environment only.

This is the only sanctioned path for the MDM DSN to enter the dashboard runtime during local/operator testing.

## Phase 1 UAT Notes Template

To be filled only after production or production-like read-only dashboard testing actually runs:

| View | Evidence to inspect | Result | Notes |
| --- | --- | --- | --- |
| MDM overview | Entity counts, relationship counts, setup guidance | pending production proof | no credentials or raw exceptions |
| Hosted graph overview | Snowflake graph node/edge counts and Native App failure-only detail | pending production proof | no raw Native App logs |
| Mismatch diagnostics | Missing/extra node and edge samples with bounded row limit | pending production proof | bounded samples only |
| Manual refresh | Refresh timestamp and cached read-only payload behavior | pending production proof | no write controls |
| Bounded samples | Row limit behavior and no unbounded export path | pending production proof | diagnostics only |

dev precedent only — prod proof required separately

Known dev precedent from go-live state: the dashboard passed local UAT after loading MDM configuration from AWS Secrets Manager without printing the DSN. That does not satisfy production dashboard UAT.

## Known Cleanup Item - Classify, Do Not Inherit

The current `examples/mdm_graph_dashboard/README.md` still documents `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `NEO4J_SECRET_JSON`, and `check-connectivity --neo4j` as active setup/check paths.

Per the upstream `neo4j-snowflake` Phase 4 `04-03-PLAN.md`, that dashboard documentation closeout is incomplete and blocks go-live dashboard docs until merged and rechecked:

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Dashboard README NEO4J_* cleanup (neo4j-snowflake Phase 4 04-03-PLAN.md closeout)`.

This cleanup item is not a dashboard pass.

## Not-Yet-Runnable Production Steps

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Dashboard operator inspection views`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Dashboard README NEO4J_* cleanup (neo4j-snowflake Phase 4 04-03-PLAN.md closeout)`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Evidence secret-safety scrub` for final all-evidence scan before launch handoff.
