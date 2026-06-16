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

## Phase 3 Live Checks Actually Run

Date: 2026-06-15 UTC
Environment: dev (rehearsal); prod --status-only (blocker reproduction).
This section records the live acceptance evidence from Phase 3 plan 03-01-live-mdm-graph-rehearsal.

### Prod --status-only Structural-Blocker Reproduction (D-02)

```bash
bash infra/scripts/run-aws-mdm-e2e.sh --env prod --status-only
```

Result: failed (exit 1).

Failed at the `infra/aws-prod-application.json` existence check (line 77 of `run-aws-mdm-e2e.sh`) with zero AWS API calls — no `==> Step Functions` output was produced. The error text:

```
ERROR: deployment summary not found: <repo-root>/infra/aws-prod-application.json
```

BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `AWS MDM hosted graph E2E`.

dev precedent only — prod proof required separately

Production still requires: `infra/aws-prod-application.json` (populated by a successful production deploy) before `run-aws-mdm-e2e.sh --env prod` can proceed past the preflight existence check.

### Dev MDM Postgres Re-Verification (D-03)

DSN loaded from AWS Secrets Manager (`edgartools-dev/mdm/postgres_dsn`) without printing. Mask-check confirmed dev `.snowflake.app` target before running `mdm migrate`.

```bash
uv run --extra mdm-runtime edgar-warehouse mdm check-connectivity
uv run --extra mdm-runtime edgar-warehouse mdm migrate
uv run --extra mdm-runtime edgar-warehouse mdm counts
```

Result: succeeded (exit 0 for all three commands).

**check-connectivity** — `{"connected": true, "dialect": "postgresql", "missing_tables": []}` — 20 tables introspected, SELECT 1 returned 1 row.

**migrate** (idempotent re-apply) — `{"dialect": "postgresql", "seeded": true}` — 19 tables present; non-zero row counts: mdm_entity=8083, mdm_company=5500, mdm_person=2251, mdm_security=322, mdm_source_ref=68249, mdm_change_log=69435, mdm_entity_attribute_stage=223637, mdm_relationship_instance=62061, mdm_relationship_type=11, mdm_relationship_property_def=46, mdm_relationship_source_mapping=11, mdm_entity_type_definition=6, mdm_field_survivorship=11, mdm_match_threshold=5, mdm_normalization_rule=31, mdm_source_priority=4.

**counts** — 19 tables queried; relationship totals: IS_INSIDER=25647 active, HOLDS=35846 active, ISSUED_BY=322 active, COMPANY_HOLDS=246 active (all with pending_graph_sync matching active — graph sync due on next E2E run).

`MDM_DATABASE_URL` unset after all three commands.

dev precedent only — prod proof required separately

Production still requires: `edgartools-prod/mdm/postgres_dsn` secret populated (see `runbook/mdm-secrets.md`) and `edgartools-prod/mdm/snowflake` secret populated before any of these commands can target prod MDM Postgres.

### Dev postgres_dsn Shape Reference (D-07 — for plan 03-02)

The prod `postgres_dsn` secret must satisfy the same connection-string structure as the dev DSN (values replaced with placeholders):

```
postgresql://<user>:<password>@<host>.snowflake.app:<port>/<database>?sslmode=require
```

Invariants enforced by `audit-mdm-snowflake-postgres-cutover.py`'s `validate_snowflake_postgres_dsn()`:
- Host must end in `.snowflake.app`
- Database must be `mdm`
- `sslmode=require` must be present

This heading is the stable format reference consumed by plan 03-02 (D-07).
