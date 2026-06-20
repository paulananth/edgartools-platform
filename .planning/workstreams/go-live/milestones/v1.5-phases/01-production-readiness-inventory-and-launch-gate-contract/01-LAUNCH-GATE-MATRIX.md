# Launch Gate Matrix - Phase 1 Production Readiness

Date: 2026-06-14 UTC
Environment: production required; dev rows are precedent only and require separate production proof.

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, Terraform state, full task logs, raw connector traces, raw Native App job logs, and full generated deployment JSON.

## Gate Matrix

| Gate | Owner/Source | Required Fix | Required Rerun Proof | Status |
|---|---|---|---|---|
| AWS passive infrastructure outputs | AWS operator | Real `terraform apply` against the bootstrapped `edgartools-prod-tfstate` S3 backend completed (Phase 6 plan 06-01): `Apply complete! Resources: 42 added, 0 changed, 0 destroyed.` `versions.tf` `~>` constraint bug fixed permanently (`required_version = ">= 1.14.7"`, committed). | Non-secret output summary in [evidence/aws.md](evidence/aws.md) "Phase 6 Production Apply" section: 22/22 output names captured live (no values), resource-add count, region/account labels. | PASS |
| Production bronze data reuse from dev bronze | AWS operator | After prod passive storage exists, run the documented S3-to-S3 bronze sync from `s3://edgartools-dev-bronze-077127448006/warehouse/bronze/` to the prod bronze root resolved from `terraform -chdir=infra/terraform/accounts/prod output -raw bronze_bucket_name`; copy bronze only, do not use `--delete`, and keep loader defaults idempotent (`--force` only for explicit repair). See [runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md) section 3. Prerequisite update (Phase 6): the prod bronze bucket (`edgartools-prod-bronze-077127448006`) now exists per the live `terraform output`, but the sync itself has not been run — out of Phase 6 scope. | [evidence/aws.md](evidence/aws.md) records dry-run/final sync command, source/destination prefixes, object count, and total size only; no full key listing or copied object body is pasted. | BLOCKED |
| Production AWS application manifest (`infra/aws-prod-application.json`) | AWS operator | Successful production deploy (Phase 6 plan 06-02, `deploy-aws-application.sh --env prod`, exit code 0) created the production app summary at repo root. | Non-secret summary in [evidence/aws.md](evidence/aws.md) "Phase 6 Plan 02" section: file presence confirmed, 18/18 top-level keys listed, 22 state-machine names listed, `image_ref`/`mdm_image_ref` confirmed in `@sha256:` digest form (no values pasted). | PASS |
| AWS active application deploy (`infra/scripts/deploy-aws-application.sh`) | AWS operator | Production deploy ran via the existing script (Phase 6 plan 06-02) with explicit `--image-ref`/`--mdm-image-ref` digest refs, `--enable-mdm`, `--skip-build`, and a freshly resolved `--edgar-identity-secret-arn`; exit code 0; 22 Step Functions state machines + 5 ECS task definitions created (all-create, 0 updates/destroys). Exact command, flag resolution order, and identifiers documented in [runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md). | [evidence/aws.md](evidence/aws.md) "Phase 6 Plan 02" section records exact command, env label, exit code 0, and sanitized state-machine/image-ref summary. | PASS |
| Stale `edgar-identity` secret ARN mitigation | AWS operator | Go-live runbook required `--edgar-identity-secret-arn` with a freshly looked-up ARN before deploy; the real Phase 6 plan 06-02 deploy followed this exactly — `describe-secret` was run in the same shell session immediately before the deploy invocation, not a cached/manifest value (no `infra/aws-prod-application.json` existed yet at the time of resolution). Documented command in [runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md) section 2. | [evidence/aws.md](evidence/aws.md) "Phase 6 Plan 02" section records that the ARN was freshly resolved in-session before the real deploy; no ARN value is pasted. | PASS |
| ECR cleanup deleting in-flight image digest mitigation | AWS operator | Go-live runbook required re-resolving warehouse and MDM image digests immediately before deploy after any cleanup step; the real Phase 6 plan 06-02 deploy followed this exactly — digests were re-resolved in-session immediately before the deploy call, and the script's internal `cleanup-ecr-images.sh --env prod --apply` step (which ran as part of the same deploy invocation) reported "0 images deleted, 0 MB freed" with no `ManifestNotFoundException`. Documented ordering requirement in [runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md) section 4. | [evidence/aws.md](evidence/aws.md) "Phase 6 Plan 02" section records command ordering, cleanup result (0 deleted), and digest format only; no full ECR JSON body or digest value is pasted. | PASS |
| Snowflake native S3 pull stack (`infra/scripts/deploy-snowflake-stack.sh`) | Snowflake operator | An operator supplied production Snowflake ACCOUNTADMIN access; the six local Terraform input files were created (gitignored) and the wrapper was run with explicit operator approval. Required fixing 6 pessimistic `versions.tf` constraints, one bad `terraform.tfvars.example` default, importing 3 pre-existing shared IAM roles into prod state, namespacing 3 inline IAM policies to avoid overwriting dev's secret grants, switching from `externalbrowser` to password auth (account has no SAML IdP), and resolving a dashboard-object creation ordering race. All three Terraform roots applied with zero destroys. | [Phase 7 native-pull evidence](../07-production-snowflake-native-pull-and-gold/evidence/native-pull.md) "Phase 7 Plan 07-01 Retry" section records every root-cause fix and the structural verification (`native_pull_ready = true`, all native-pull objects created, manifest task confirmed `started`). No secret/ARN/account-identifier value is pasted. | PASS |
| Snowflake deployer direct grants for gold dynamic tables | Snowflake operator | A production service user `EDGARTOOLS_PROD_DEPLOYER` was created, granted exactly the `EDGARTOOLS_PROD_DEPLOYER` role, and verified end-to-end: connected using only credentials read back from AWS Secrets Manager, confirmed `CURRENT_ROLE()`/`CURRENT_WAREHOUSE()`/`CURRENT_DATABASE()`, and confirmed live `SELECT` access against the source schema's tables. | [Phase 7 native-pull evidence](../07-production-snowflake-native-pull-and-gold/evidence/native-pull.md) "Result" subsection and [Phase 7 dbt-gold evidence](../07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md) "Dependency Update" section record the verification steps and the new `edgartools-prod/dbt/snowflake` secret (deliberately separate from the Phase-8/MDM-02-owned `edgartools-prod/mdm/snowflake`). | PASS |
| dbt compile/run/test for production target | Snowflake operator | Ran `dbt deps`, `dbt run --target prod`, `dbt test --target prod` with production `DBT_SNOWFLAKE_*` credentials sourced live from `edgartools-prod/dbt/snowflake`. 15 of 16 models passed on the first attempt; `FINANCIAL_FACTS` failed on a genuine pre-existing schema-drift bug (live `SEC_FINANCIAL_FACT` table missing `PERIOD_START`, also present in dev), fixed via a non-destructive 3-step `ALTER TABLE` migration against prod only (5-whys in `TODOS.md`). Retry: 16/16 models built, `dbt test --target prod` reported `PASS=47 ERROR=0` (36 data tests + 11 unit tests). | [evidence/snowflake.md](evidence/snowflake.md) "SNOW-04 dbt/gold — PASS" section and [Phase 7 dbt-gold evidence](../07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md) record exact commands, target, pass/fail, model/test counts, the schema-drift bug and fix, and no compiled SQL/secrets. | PASS |
| `EDGARTOOLS_GOLD_STATUS` and dynamic-table freshness | Snowflake operator | After the native-pull and dbt gates passed, ran `SELECT * FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS` (no rows — expected, dbt's direct build path doesn't populate the manifest-refresh status view) and `SHOW DYNAMIC TABLES IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_GOLD` (all 15 dynamic tables `scheduling_state = ACTIVE`, `target_lag = DOWNSTREAM`, never suspended). | [evidence/snowflake.md](evidence/snowflake.md) "SNOW-04 dbt/gold — PASS" section and [Phase 7 dbt-gold evidence](../07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md) record table/view status and freshness summary using the existing summary-table shape; no full query dumps. | PASS |
| MDM Snowflake Postgres secret container and connectivity | MDM operator | Populate `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake` using the steps in [runbook/mdm-secrets.md](../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md) (sections 1 and 2 for `put-secret-value`; section 5 for `describe-secret` presence check). Then re-run `check-connectivity`, `migrate`, and `counts` with the prod `MDM_DATABASE_URL`. | [evidence/mdm-hosted-graph.md](evidence/mdm-hosted-graph.md): dev re-verification is in `### Dev MDM Postgres Re-Verification (D-03)` and dev DSN shape is in `### Dev postgres_dsn Shape Reference (D-07 — for plan 03-02)` (dev precedent only — prod proof required separately). | BLOCKED |
| `edgar-warehouse mdm sync-graph` hosted graph materialization | MDM operator | Run bounded production sync with explicit graph limit and target scope after MDM connectivity and production identifiers pass. | [evidence/mdm-hosted-graph.md](evidence/mdm-hosted-graph.md): dev rehearsal result (including `mdm_sync_graph` stage) in `### Dev Rehearsal — Full E2E (D-09/D-10)` (dev precedent only — prod proof required separately). | BLOCKED |
| Strict `edgar-warehouse mdm verify-graph` | MDM operator | Run local strict hosted graph verification with production Snowflake connection/database and explicit Native App compute-pool selector before AWS E2E. | [evidence/mdm-hosted-graph.md](evidence/mdm-hosted-graph.md): dev preflight pass and `mdm_verify_graph` stage in `### Dev Rehearsal — Full E2E (D-09/D-10)`, plus cited `03-LIVE-DEV-RUN.md` precedent in `### GRAPH-01/GRAPH-02 Dev Precedent Citation (D-04)` (dev precedent only — prod proof required separately). | BLOCKED |
| AWS MDM hosted graph E2E | AWS operator | Run `infra/scripts/run-aws-mdm-e2e.sh` for production only after `infra/aws-prod-application.json` exists (populated by a successful production deploy), local strict verify-graph preflight passes, and explicit limits/stop conditions are set. | [evidence/mdm-hosted-graph.md](evidence/mdm-hosted-graph.md): dev rehearsal (all 6 stages SUCCEEDED) in `### Dev Rehearsal — Full E2E (D-09/D-10)`; prod blocker proof (exit 1 on missing `infra/aws-prod-application.json`) in `### Prod --status-only Structural-Blocker Reproduction (D-02)` (dev rehearsal precedent only — prod proof required separately). | BLOCKED |
| Dashboard operator inspection views | dashboard reviewer | Launch dashboard with production or production-like read-only config after CLI/dbt/Native App gates are available; record text UAT notes for launch-critical views. | [evidence/dashboard-security.md](evidence/dashboard-security.md) Phase 1 UAT Notes section filled with dev-run pass/fail for all 5 views (2026-06-16 UTC) — dev precedent only — prod proof required separately. | BLOCKED |
| Dashboard README `NEO4J_*` cleanup (neo4j-snowflake Phase 4 `04-03-PLAN.md` closeout) | dashboard reviewer / release owner | Complete upstream dashboard docs/final evidence closeout so active setup no longer instructs external `NEO4J_*`, Bolt, Aura, or `check-connectivity --neo4j` paths. | [evidence/dashboard-security.md](evidence/dashboard-security.md) README Cleanup section: cleanup completed in go-live Phase 4 plan 04-01 (commit e5865ba); arch test `test_dashboard_foundation_boundaries.py` enforces new contract (24 passed). Documentation gate satisfied; no prod dependency. | PASS |
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
| dbt/gold | Gold models fail, stale, or disagree with MDM/source data | Snowflake native pull, dbt model SQL, dynamic-table grants, freshness | dbt compile/run/test, `EDGARTOOLS_GOLD_STATUS`, dynamic table refresh/freshness | Snowflake operator | PASS | dbt run/test passed 16/16 models, 47/47 tests against prod (2026-06-20); see [evidence/snowflake.md](evidence/snowflake.md) "SNOW-04 dbt/gold — PASS". |
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
