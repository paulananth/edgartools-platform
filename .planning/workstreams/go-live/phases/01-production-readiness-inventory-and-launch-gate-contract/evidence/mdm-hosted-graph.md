# MDM + Hosted Graph Evidence - Phase 1 Production Readiness

Date: 2026-06-14 UTC
Environment: production required; dev rows are precedent only and require separate production proof.
Snowflake connection: production connection required.
Snowflake database: production database required.
AWS profile: production profile required.

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, full task logs, and raw Native App job logs.

## Preflight Gate Note

Before any AWS MDM E2E starts, Phase 1 requires the local `edgar-warehouse mdm verify-graph` gate to be runnable against the target Snowflake connection, target Snowflake database, and Native App compute pool. The strict full-acceptance production run and any `phase3_acceptance: true` summary are Phase 3 work.

For Phase 1, that strict production run is not recorded as a pass. It remains a matrix blocker:

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Strict edgar-warehouse mdm verify-graph`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `AWS MDM hosted graph E2E`.

## Phase 1 Read-Only Checks Actually Run

```bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --status-only
```

Result: succeeded.

Relevant non-secret dev Step Functions status:

| Workflow | Latest status | Latest execution name |
| --- | --- | --- |
| `mdm_migrate` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-migrate` |
| `mdm_run` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-run` |
| `mdm_backfill_relationships` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-backfill` |
| `mdm_sync_graph` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-sync` |
| `mdm_verify_graph` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-verify` |
| `mdm_counts` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-counts` |

This was a dev `--status-only` check. It started no workloads and is not production proof.

`--skip-preflight` is emergency/debug — non-acceptance. A run using `--skip-preflight` cannot satisfy Phase 3 acceptance or any go-live gate unless separate strict preflight proof is captured.

## Verify-Graph Non-Secret Payload Summary Template

To be filled by Phase 3 production run only:

- Overall status: pending production proof
- Snowflake graph nodes: pending production proof
- Snowflake graph edges: pending production proof
- Node parity status: pending production proof
- Relationship parity status: pending production proof
- Missing/extra node diagnostics: pending production proof
- Missing/extra edge diagnostics: pending production proof
- Missing edge endpoint diagnostics: pending production proof
- Native App status: pending production proof
- Native App compute pool: pending production proof
- Native App checks:
  - `app_installation`: pending production proof
  - `app_user_role_grant`: pending production proof
  - `app_admin_role_grant`: pending production proof
  - `database_role_to_application`: pending production proof
  - `database_role_privileges`: pending production proof
  - `compute_pool`: pending production proof
  - `graph_schema_sample`: pending production proof
  - `graph_info`: pending production proof
  - `bfs`: pending production proof
  - `wcc`: pending production proof
- `phase3_acceptance`: pending production proof

Relationship parity table shape:

| Relationship type | MDM active | Snowflake graph | Delta |
| --- | ---: | ---: | ---: |
| pending production proof | pending production proof | pending production proof | pending production proof |

## Dev Precedent Reconciliation

dev precedent only — prod proof required separately

The dev hosted graph evidence from `03-LIVE-DEV-RUN.md` shows:

- strict local `edgar-warehouse mdm verify-graph` eventually succeeded in dev,
- Snowflake graph nodes: `15`,
- Snowflake graph edges: `4`,
- node parity status: `ok`,
- relationship parity status: `ok`,
- Native App status: `ok`,
- Native App compute pool: `CPU_X64_XS`,
- Native App `GRAPH_INFO`, `BFS`, and `WCC` checks: `ok`,
- dev `phase3_acceptance`: `true`,
- latest dev AWS MDM hosted graph E2E reached `mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`, and `mdm_counts` with `SUCCEEDED` status.

Production still requires production Snowflake connection/database, production Native App app and compute-pool selector, production strict verify-graph proof, and production AWS MDM E2E proof.

## Not-Yet-Runnable Production Steps

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `MDM Snowflake Postgres secret container and connectivity`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `edgar-warehouse mdm sync-graph hosted graph materialization`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Strict edgar-warehouse mdm verify-graph`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `AWS MDM hosted graph E2E`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake native S3 pull stack (infra/scripts/deploy-snowflake-stack.sh)`.

These planned production commands are not evidence entries because they were not run during Phase 1.
