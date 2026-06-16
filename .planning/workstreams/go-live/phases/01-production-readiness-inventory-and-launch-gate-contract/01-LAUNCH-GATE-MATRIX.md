# Launch Gate Matrix - Phase 1 Production Readiness

Date: 2026-06-14 UTC
Environment: production required; dev rows are precedent only and require separate production proof.

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, Terraform state, full task logs, raw connector traces, raw Native App job logs, and full generated deployment JSON.

## Gate Matrix

| Gate | Owner/Source | Required Fix | Required Rerun Proof | Status |
|---|---|---|---|---|
| AWS passive infrastructure outputs | AWS operator | Pattern 1 read-only `terraform plan` for `infra/terraform/accounts/prod/` validated the resource-add count and the 22 output names from `outputs.tf` (see [evidence/aws.md](evidence/aws.md)); a real `terraform apply` against a real S3 backend is still required to produce live output values. Also fix the `versions.tf` `~>` version-constraint bug (`required_version = "~> 1.14.7"`, currently only worked around via a temporary, reverted edit per Pattern 1) before any real `apply`. | Non-secret output summary in [evidence/aws.md](evidence/aws.md): output names present (22/22, plan-validated), environment label, and account label only. | BLOCKED |
| Production bronze data reuse from dev bronze | AWS operator | After prod passive storage exists, run the documented S3-to-S3 bronze sync from `s3://edgartools-dev-bronze-077127448006/warehouse/bronze/` to the prod bronze root resolved from `terraform -chdir=infra/terraform/accounts/prod output -raw bronze_bucket_name`; copy bronze only, do not use `--delete`, and keep loader defaults idempotent (`--force` only for explicit repair). See [runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md) section 3. | [evidence/aws.md](evidence/aws.md) records dry-run/final sync command, source/destination prefixes, object count, and total size only; no full key listing or copied object body is pasted. | BLOCKED |
| Production AWS application manifest (`infra/aws-prod-application.json`) | AWS operator | Live discovery or successful production deploy must create or replace the production app summary. | Non-secret summary in [evidence/aws.md](evidence/aws.md): file presence, top-level keys, state-machine names, and digest-vs-tag image-ref format only. | BLOCKED |
| AWS active application deploy (`infra/scripts/deploy-aws-application.sh`) | AWS operator | Run production deploy through the existing script with explicit image refs, MDM enabled when required, Snowflake Postgres source, and no Terraform-owned runtime commands. Exact command, flag resolution order, and the full list of identifiers the script hard-fails on until prod passive infra (row above) is applied are documented in [runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md). | [evidence/aws.md](evidence/aws.md) records exact command, env label, pass/fail, and sanitized state-machine/image-ref summary. | BLOCKED |
| Stale `edgar-identity` secret ARN mitigation | AWS operator | Go-live runbook/checklist must require `--edgar-identity-secret-arn` with a freshly looked-up ARN before every deploy after secret recreation or rotation. Documented command (`aws secretsmanager describe-secret --secret-id edgartools-prod-edgar-identity --query ARN --output text`, resolved fresh immediately before deploy) is in [runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md) section 2. | [evidence/aws.md](evidence/aws.md) records a non-secret deploy-preflight summary proving the explicit flag was supplied; no ARN value is pasted. | BLOCKED |
| ECR cleanup deleting in-flight image digest mitigation | AWS operator | Go-live runbook/checklist must require re-resolving warehouse and MDM image digests immediately before deploy after any cleanup step. Documented ordering requirement (re-resolve digests AFTER `cleanup-ecr-images.sh --apply` runs, in the same session, immediately before deploy) is in [runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md) section 4. | [evidence/aws.md](evidence/aws.md) records command ordering and digest format only; no full ECR JSON body is pasted. | BLOCKED |
| Snowflake native S3 pull stack (`infra/scripts/deploy-snowflake-stack.sh`) | Snowflake operator | Create the 3 missing prod `backend.hcl` files (`infra/terraform/{access/aws,snowflake,access/snowflake}/accounts/prod/backend.hcl`, from `.example` templates) plus real `terraform.tfvars` with production Snowflake account/org identifiers and a real S3 tfstate backend — all require a production Snowflake account to exist (D-01). The proven structural blocker (script `die`s at the `backend.hcl` existence check before any apply/validation/dbt/dashboard step) and the `native_pull` target-state resource list (1 storage integration, 2 file formats, 1 external stage, source mirror tables, 1 pipe, 1 stream, 3 stored procedures, 1 task) are documented in [runbook/snowflake-native-pull.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/snowflake-native-pull.md). | [evidence/snowflake.md](evidence/snowflake.md) records the structural-blocker smoke-test result (`rc=1`, `backend.hcl` message, no Terraform apply/Snowflake SQL/dbt/dashboard action reached). | BLOCKED |
| Snowflake deployer direct grants for gold dynamic tables | Snowflake operator | Run `SHOW GRANTS TO ROLE EDGARTOOLS_PROD_DEPLOYER;` (or live discovery) against a production Snowflake account to confirm direct `SELECT` on `EDGARTOOLS_SOURCE` tables needed by dynamic-table refresh, analogous to the resolved dev `EDGARTOOLS_DEV_DEPLOYER` grant gap (see CLAUDE.md / `TODOS.md`). | [evidence/snowflake.md](evidence/snowflake.md) "Known Grant Gap" section records the required-fix grant check and dbt dynamic-table refresh readiness summary. | BLOCKED |
| dbt compile/run/test for production target | Snowflake operator | Run `dbt deps`, `dbt run --target prod`, `dbt test --target prod` with production `DBT_SNOWFLAKE_*` credentials (`EDGARTOOLS_PROD_DEPLOYER` / `EDGARTOOLS_PROD` / `EDGARTOOLS_PROD_REFRESH_WH`) supplied outside git. Note: even `dbt compile --target prod` opens a live Snowflake connection and fails with a login-request error without real credentials (Pitfall 4) — there is no placeholder-only compile check. Exact placeholder commands and the dev-target precedent gate (Task 02-02-02, BLOCKED on missing dev credentials) are documented in [runbook/dbt-gold.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md). | [evidence/snowflake.md](evidence/snowflake.md) records exact dbt commands, target, pass/fail, model/test counts, and no compiled SQL containing secrets. | BLOCKED |
| `EDGARTOOLS_GOLD_STATUS` and dynamic-table freshness | Snowflake operator | After the native-pull and dbt gates pass, run `SELECT * FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS LIMIT 10;` (or `snow sql --connection edgartools-prod -q ...`), documented with the full `EDGARTOOLS_GOLD_STATUS` column list in [runbook/dbt-gold.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md). | [evidence/snowflake.md](evidence/snowflake.md) records table/view status, last refresh, and freshness summary using the existing summary-table shape; no full query dumps. | BLOCKED |
| MDM Snowflake Postgres secret container and connectivity | MDM operator | Populate `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake` using the steps in [runbook/mdm-secrets.md](../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md) (sections 1 and 2 for `put-secret-value`; section 5 for `describe-secret` presence check). Then re-run `check-connectivity`, `migrate`, and `counts` with the prod `MDM_DATABASE_URL`. | [evidence/mdm-hosted-graph.md](evidence/mdm-hosted-graph.md): dev re-verification is in `### Dev MDM Postgres Re-Verification (D-03)` and dev DSN shape is in `### Dev postgres_dsn Shape Reference (D-07 — for plan 03-02)` (dev precedent only — prod proof required separately). | BLOCKED |
| `edgar-warehouse mdm sync-graph` hosted graph materialization | MDM operator | Run bounded production sync with explicit graph limit and target scope after MDM connectivity and production identifiers pass. | [evidence/mdm-hosted-graph.md](evidence/mdm-hosted-graph.md): dev rehearsal result (including `mdm_sync_graph` stage) in `### Dev Rehearsal — Full E2E (D-09/D-10)` (dev precedent only — prod proof required separately). | BLOCKED |
| Strict `edgar-warehouse mdm verify-graph` | MDM operator | Run local strict hosted graph verification with production Snowflake connection/database and explicit Native App compute-pool selector before AWS E2E. | [evidence/mdm-hosted-graph.md](evidence/mdm-hosted-graph.md): dev preflight pass and `mdm_verify_graph` stage in `### Dev Rehearsal — Full E2E (D-09/D-10)`, plus cited `03-LIVE-DEV-RUN.md` precedent in `### GRAPH-01/GRAPH-02 Dev Precedent Citation (D-04)` (dev precedent only — prod proof required separately). | BLOCKED |
| AWS MDM hosted graph E2E | AWS operator | Run `infra/scripts/run-aws-mdm-e2e.sh` for production only after `infra/aws-prod-application.json` exists (populated by a successful production deploy), local strict verify-graph preflight passes, and explicit limits/stop conditions are set. | [evidence/mdm-hosted-graph.md](evidence/mdm-hosted-graph.md): dev rehearsal (all 6 stages SUCCEEDED) in `### Dev Rehearsal — Full E2E (D-09/D-10)`; prod blocker proof (exit 1 on missing `infra/aws-prod-application.json`) in `### Prod --status-only Structural-Blocker Reproduction (D-02)` (dev rehearsal precedent only — prod proof required separately). | BLOCKED |
| Dashboard operator inspection views | dashboard reviewer | Launch dashboard with production or production-like read-only config after CLI/dbt/Native App gates are available; record text UAT notes for launch-critical views. | [evidence/dashboard-security.md](evidence/dashboard-security.md) records overview, MDM, hosted graph, mismatch diagnostics, refresh timestamp, and bounded-sample UAT notes. | BLOCKED |
| Dashboard README `NEO4J_*` cleanup (neo4j-snowflake Phase 4 `04-03-PLAN.md` closeout) | dashboard reviewer / release owner | Complete upstream dashboard docs/final evidence closeout so active setup no longer instructs external `NEO4J_*`, Bolt, Aura, or `check-connectivity --neo4j` paths. | [evidence/dashboard-security.md](evidence/dashboard-security.md) records README recheck and links the upstream closeout evidence. | BLOCKED |
| Evidence secret-safety scrub | release owner | Run final scan over the launch matrix and evidence files after all Phase 1 evidence templates exist. | Non-secret grep summary confirms no credential DSNs, passwords, tokens, Terraform state, raw logs, raw connector traces, or full generated JSON are committed. | PASS |

## Blocker Classification Rules

- D-01: Missing production proof, unsafe deploy hazards, incomplete acceptance docs, or launch-affecting incomplete workstream closeout are blockers until fixed.
- D-02: Incomplete upstream workstream items that affect launch evidence, dashboard docs, acceptance gates, or operator runbooks block go-live until merged and rechecked.
- D-03: Known deploy hazards with documented workarounds are blockers until the go-live runbook has explicit required mitigations and the checklist enforces them before deploy.
- D-04: Missing production artifacts or live proof are blockers until discovered live or replaced by explicit operator-provided evidence.
- D-05: Warning-only status is allowed only for cleanup that does not affect operator commands, acceptance gates, security, or evidence.
- D-06: Launch blockers must be fixed; this matrix does not support a waiver status.
- D-07: Secret-safety failures in evidence or runbooks are hard blockers until scrubbed and rechecked.
- D-08: A blocker is fixed only after rerunning the relevant check and recording a non-secret pass summary in the Phase 1 inventory.

## Dev Vs Prod Distinction

The dev hosted-graph proof from `03-LIVE-DEV-RUN.md` is precedent only. Any gate that references that proof must say "dev precedent only — prod proof required separately" and must stay production-blocked until the same proof is captured against the production AWS profile/account, Snowflake connection/database, MDM secret names, and Native App app/compute-pool selector.

## Secret-Safety Rules

No evidence file or runbook may include DSNs, passwords, tokens, Terraform state, raw connector traces or exceptions, sensitive generated deployment values, raw Native App job logs, full task logs, or full generated application JSON.

Evidence entries must include the exact command, environment label, pass/fail result, key counts or statuses, and sanitized evidence links. Full logs are not pasted.

Generated JSON such as `infra/aws-*-application.json` is summarized only as file presence, top-level keys, state-machine name list, and image-ref format. The JSON body is never pasted.

Evidence files contain only commands actually run or verified. Planned commands that cannot run yet belong as `BLOCKED` matrix rows, not as evidence entries.

Dashboard screenshots are optional if secret-safe. Text UAT notes are sufficient for Phase 1.

Secrets may be loaded into runtime environment variables with `aws secretsmanager get-secret-value ... --query SecretString --output text`, but the value must never be printed, pasted, logged, or committed.

Local/static readiness checks, production identifier validation, secret-safety scan, live discovery, and strict hosted-graph preflight must pass before paid or state-changing execution. Pure read-only status and metadata checks, such as `--status-only`, are allowed before all gates are green only when they start no workloads and reveal no secret values.

`--skip-preflight` runs are emergency/debug only. They cannot satisfy Phase 3 acceptance or go-live gates.

Bounded production runs require explicit limits, target scope, and stop conditions before execution.

## Required Production Identifiers

These inputs are required before Phase 2 execution planning:

- [x] Production AWS profile and AWS account label. Per D-05: `aws-admin-dev` and `aws-admin-prod` both resolve to account `077127448006`, IAM user `cli-access` — prod is same-account, prefix-distinguished (not a separate account).
- [ ] Production bronze reuse source and destination prefixes:
  - [x] Dev bronze source root: `s3://edgartools-dev-bronze-077127448006/warehouse/bronze/`.
  - [ ] Prod bronze destination root resolved from `terraform output -raw bronze_bucket_name` plus `/warehouse/bronze/`.
- [ ] Production Snowflake connection.
- [ ] Production Snowflake database.
- [ ] Deploy image references for warehouse and MDM images in digest form.
- [ ] Generated app summary path: `infra/aws-prod-application.json`.
- [ ] MDM Secrets Manager secret names for Postgres DSN, API keys, Snowflake settings, and any legacy/empty graph containers by name only:
  - [ ] `edgartools-prod/mdm/postgres_dsn` — population runbook documented in [../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md](../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md) (section 1), not yet executed against real prod values.
  - [ ] `edgartools-prod/mdm/neo4j` — not required / legacy (Snowflake-hosted graph path does not use this secret; D-06).
  - [ ] `edgartools-prod/mdm/api_keys` — deferred, consumer unclear (D-06).
  - [ ] `edgartools-prod/mdm/snowflake` — population runbook documented in [../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md](../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md) (section 2), not yet executed against real prod values.
- [ ] Native App application name and compute-pool selector.

The production app summary is currently a blocked gate until live discovery or a successful production deploy supplies it.

## Data-Issue Triage Table

Operators start with CLI verification and dbt tests, then inspect the dashboard. The dashboard is inspection only after CLI/dbt/Native App gates; it explains issues but does not define acceptance. Failed CLI/dbt/Native App gates are launch-blocking. Dashboard-only warnings block only when they point to a failed gate or a launch-impacting data gap.

| Layer | Symptom | Likely source | Evidence to check | Owner | Blocker status | Next action |
|---|---|---|---|---|---|---|
| ingestion | Missing or stale filing/entity input | SEC API capture, Step Functions bootstrap/daily runs, S3 bronze roots | AWS Step Functions status, CloudWatch task result summary, bronze S3 path presence | AWS operator | BLOCKED | Rerun bounded capture or document missing production proof in [evidence/aws.md](evidence/aws.md). |
| bronze/silver | Captured files exist but silver outputs or DuckDB shards are missing/stale | Warehouse transforms, object-storage publish, shard hydration | S3 warehouse paths, silver command summary, relevant loader counts | AWS operator | BLOCKED | Re-run bounded silver/gold preparation after source evidence is present. |
| MDM | Entity or relationship counts missing, low, or inconsistent | Snowflake Postgres DSN, MDM migration, MDM run, source-to-MDM prerequisites | `mdm migrate`, `mdm run`, `mdm counts`, and secret-container metadata without secret values | MDM operator | BLOCKED | Fix MDM runtime configuration or rerun bounded MDM commands. |
| hosted graph | MDM counts exist but hosted graph nodes/edges or parity are missing | `mdm sync-graph`, graph-ready Snowflake tables, verifier inputs | `mdm sync-graph`, strict `mdm verify-graph`, relationship parity table | MDM operator | BLOCKED | Run local strict verify-graph before AWS E2E; capture non-secret parity summary. |
| dbt/gold | Gold models fail, stale, or disagree with MDM/source data | Snowflake native pull, dbt model SQL, dynamic-table grants, freshness | dbt compile/run/test, `EDGARTOOLS_GOLD_STATUS`, dynamic table refresh/freshness | Snowflake operator | BLOCKED | Fix grants/model issue, rerun dbt/gold checks, and update [evidence/snowflake.md](evidence/snowflake.md). |
| Native App | `verify-graph` fails compute pool, `GRAPH_INFO`, `BFS`, or `WCC` | Native App install/grants/compute pool availability | Native App check section from strict `mdm verify-graph` | Snowflake operator | BLOCKED | Activate/repair Native App prerequisites outside Terraform, then rerun strict verify-graph. |
| dashboard | Dashboard view shows stale counts, missing diagnostics, or confusing copy | Read-only dashboard helper payloads, cached data, docs closeout | Text UAT notes, bounded samples, refresh timestamp, README recheck | dashboard reviewer | WARNING | Use dashboard to explain issue after CLI/dbt gates; escalate to `BLOCKED` if it points to a failed acceptance gate. |
| permissions | Command works as admin but fails as deployer/runtime role | IAM, Snowflake grants, Native App roles, direct dynamic-table owner grants | IAM role summaries, Snowflake grant summaries, dbt/verify-graph role-specific errors without raw traces | Snowflake operator | BLOCKED | Add or correct least-privilege grants in the proper provisioning surface and rerun the failing gate. |

## Requirement Traceability

| Requirement | Satisfied by | Status |
|---|---|---|
| LIVE-01 | Gate matrix, production identifier checklist, AWS/Snowflake/MDM preflight evidence links, and read-only-before-green spend boundary. | PASS |
| SEC-01 | Secret-safety rules, generated-JSON summary rule, secret-safe loading convention, and final scrub gate. | PASS |
| ISO-01 | All Phase 1 artifacts live under `.planning/workstreams/go-live/`. | PASS |
| ISO-02 | Matrix preserves AWS/Snowflake path and mentions external Neo4j only as stale cleanup to remove, not as an active launch dependency. | PASS |
