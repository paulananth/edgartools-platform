# Phase 7: Production Snowflake Native Pull And Gold - Context

**Gathered:** 2026-06-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 7 executes the production Snowflake native-pull and dbt gold launch
gates after Claude-completed Phase 6. Phase 6 is treated as complete and its
verification is carried forward; Phase 7 does not rerun Phase 6 actions.

This phase has two execution plans:

1. **07-01: Production native-pull deploy and validation** - run the
   Snowflake deploy wrapper for production native pull, capture deep
   Snowflake validation proof, and produce a sanitized committed validation
   artifact.
2. **07-02: Production dbt gold run/test and audit** - run standalone dbt
   commands against the production target, perform grant and freshness/status
   audits, and update launch evidence.

Phase 7 does not populate MDM secrets, run MDM or hosted graph write paths,
perform dashboard UAT/upload, rerun AWS deploy, or broaden the AWS/Snowflake
architecture. Generated application JSON and raw validation artifacts are
operator-local inputs only unless explicitly sanitized under the rules below.

</domain>

<decisions>
## Implementation Decisions

### Phase 6 Dependency Boundary
- **D-01:** Phase 7 is based on Claude's completed Phase 6 handoff on
  `claude/go-live-v1.6-phase6`. Phase 6 production AWS infrastructure,
  application deploy, and verification are treated as completed inputs.
- **D-02:** Phase 7 may use `infra/aws-prod-application.json`,
  Terraform/live outputs, and Phase 6 summaries as operator-local inputs.
  The generated JSON remains untracked and must never be committed or pasted
  into evidence.
- **D-03:** If generated manifest, Terraform outputs, and live AWS discovery
  disagree on a value required by Snowflake deployment, Phase 7 stops and
  records the non-secret mismatch shape. If only `infra/aws-prod-application.json`
  is stale while live AWS/Terraform outputs agree, execution may proceed with
  the live outputs and evidence must mark the manifest stale.
- **D-04:** Phase 7 trusts Phase 6 verification docs for baseline readiness.
  It does not rerun Phase 6 actions or perform broad Phase 6 rediscovery. Any
  local/live reads are Phase 7 input gathering, not Phase 6 re-verification.

### Native-Pull Proof Standard
- **D-05:** SNOW-03 requires deep Snowflake proof, not wrapper success alone:
  wrapper success plus storage integration metadata, stage/list evidence,
  copy-history evidence, task state, and native-pull readiness.
- **D-06:** Plan 07-01 invokes the wrapper as:
  `bash infra/scripts/deploy-snowflake-stack.sh --env prod --snow-connection edgartools-prod --run-validation`.
  dbt is intentionally not run by this wrapper call; dbt belongs to Plan 07-02.
- **D-07:** The raw `infra/snowflake/sql/prod_native_pull_handshake.json`
  may be generated locally, but Phase 7 commits only a sanitized validation
  artifact.
- **D-08:** The sanitized native-pull artifact includes Snowflake resource
  names, object categories, booleans, safe counts, and PASS/BLOCKED status.
  It omits ARNs, external IDs, S3 URLs, manifest file names, account
  identifiers, raw connector errors, and raw Snowflake result rows.
- **D-09:** If native-pull deploy succeeds but a deep validation check fails,
  the executor may immediately rerun validation once. If it still fails,
  SNOW-03 remains BLOCKED with partial-pass evidence showing what deployed
  and which validation check failed.

### dbt Gold Evidence Shape
- **D-10:** Plan 07-02 runs dbt standalone after native-pull passes:
  `uv run --with dbt-snowflake dbt deps`, `dbt run --target prod`, and
  `dbt test --target prod` from `infra/snowflake/dbt/edgartools_gold/`.
  The plan may derive or confirm `DBT_SNOWFLAKE_DATABASE`,
  `DBT_SNOWFLAKE_WAREHOUSE`, and `DBT_SNOWFLAKE_ROLE` from Snowflake outputs
  before running dbt.
- **D-11:** dbt evidence may include selected sanitized console output with
  model names and timings. It must not include compiled SQL, raw adapter
  traces, account locators, passwords, tokens, or secrets.
- **D-12:** After dbt succeeds, Phase 7 captures a broad Snowflake audit:
  `EDGARTOOLS_GOLD_STATUS`, dynamic table details/freshness, task history,
  source table row counts, and grant checks. The audit is summarized without
  raw row dumps or sensitive values.
- **D-13:** `EDGARTOOLS_PROD_DEPLOYER` direct grants are checked before
  `dbt run`. If required direct grants are missing, execution stops early
  with actionable evidence instead of running dbt into a predictable failure.
- **D-14:** If `dbt run` passes but `dbt test` fails, SNOW-04 remains
  BLOCKED. Evidence records the passing run, failed test names, likely
  owner/remediation, and does not treat deployed tables as a launch pass.

### Evidence Writeback
- **D-15:** Phase 7 writes evidence in both places: detailed Phase 7-local
  evidence/artifacts and concise pass/block citations in Phase 1 launch
  evidence and matrix files.
- **D-16:** Phase 7-local evidence files are:
  `.planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold/evidence/native-pull.md`,
  `.planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md`,
  and `.planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold/evidence/native-pull-validation-sanitized.json`.
- **D-17:** Launch gate matrix rows update plan-by-plan only after proof:
  Plan 07-01 updates SNOW-03/native-pull rows after native-pull proof, and
  Plan 07-02 updates SNOW-04/dbt-gold rows after dbt/audit proof.
- **D-18:** Mixed status is allowed. Passed rows flip to PASS; blocked rows
  remain BLOCKED with precise evidence, owner, and remediation.
- **D-19:** Safe blocked evidence should be committed when a live operation
  blocks, so the blocker is reproducible and actionable. Raw sensitive
  output is still excluded.

### the agent's Discretion
- The user delegated the dbt invocation choice to the agent. The locked
  decision is standalone dbt (D-10), chosen because it separates SNOW-03
  and SNOW-04 evidence and avoids rerunning the deploy wrapper for dbt only.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream Contracts
- `.planning/workstreams/go-live/PROJECT.md` - v1.6 production-launch goal,
  AWS/Snowflake boundaries, and secret-safety contract.
- `.planning/workstreams/go-live/REQUIREMENTS.md` - SNOW-03 and SNOW-04
  requirement definitions and traceability.
- `.planning/workstreams/go-live/ROADMAP.md` - Phase 7 goal, dependencies,
  plans, and success criteria.
- `.planning/workstreams/go-live/STATE.md` - workstream state and current
  blocker list.

### Phase 6 Handoff
- `.planning/workstreams/go-live/phases/06-production-aws-infrastructure-and-application-deploy/06-CONTEXT.md`
  - decisions and boundaries from the completed Phase 6 production AWS work.
- `.planning/workstreams/go-live/phases/06-production-aws-infrastructure-and-application-deploy/06-01-SUMMARY.md`
  - passive infrastructure apply summary and outputs available to later
  phases.
- `.planning/workstreams/go-live/phases/06-production-aws-infrastructure-and-application-deploy/06-02-SUMMARY.md`
  - active application deploy summary and generated manifest handling.
- `.planning/workstreams/go-live/phases/06-production-aws-infrastructure-and-application-deploy/06-VERIFICATION.md`
  - passed Phase 6 verification; baseline readiness trusted by Phase 7.
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/aws.md`
  - Phase 6 production AWS evidence summary and generated JSON summary rule.

### Launch Evidence Targets
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`
  - rows for Snowflake native S3 pull stack, deployer grants, dbt run/test,
  and `EDGARTOOLS_GOLD_STATUS`/freshness.
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/snowflake.md`
  - concise launch evidence target updated by Phase 7.
- `.planning/workstreams/go-live/phases/05-go-no-go-launch-evidence-and-handoff/05-GO-NO-GO-PACKET.md`
  - Blocker 3 remediation language for Snowflake native pull and dbt gold.

### Native-Pull Implementation And Runbooks
- `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/snowflake-native-pull.md`
  - prior runbook for native-pull deployment order, structural blocker, and
  target-state object list.
- `infra/scripts/deploy-snowflake-stack.sh` - wrapper Phase 7 invokes with
  `--env prod --snow-connection edgartools-prod --run-validation`.
- `infra/snowflake/sql/bootstrap_native_pull.py` - validation helper that
  emits the raw handshake artifact and validates integration/stage/copy
  history.
- `infra/snowflake/sql/README.md` - native-pull validation helper scope and
  execution-order reference.
- `infra/terraform/snowflake/modules/native_pull/main.tf` - Terraform object
  graph for storage integration, file formats, stage, source mirror tables,
  pipe, stream, procedures, and task.
- `infra/terraform/snowflake/accounts/prod/outputs.tf` - production
  Snowflake outputs used for safe status/resource-name summaries.
- `infra/terraform/snowflake/README.md` - Snowflake Terraform ownership and
  preferred build order.

### dbt Gold Implementation And Runbooks
- `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md`
  - prior dbt runbook, credential requirements, status query, and known
  grant-gap context.
- `infra/snowflake/dbt/edgartools_gold/README.md` - dbt project ownership,
  current gold objects, and dynamic-table/status-view notes.
- `infra/snowflake/dbt/edgartools_gold/dbt_project.yml` - dbt project config.
- `infra/snowflake/dbt/edgartools_gold/profiles.yml.example` - environment-
  backed dbt profile shape.
- `infra/snowflake/dbt/edgartools_gold/models/gold/edgartools_gold_status.sql`
  - `EDGARTOOLS_GOLD_STATUS` view definition.
- `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` - gold model
  metadata and tests.
- `docs/runbook.md` - production Snowflake/dbt operator commands and dynamic
  table caveats.

### Operator-Local Inputs
- `infra/aws-prod-application.json` - generated local application manifest if
  present. It may inform Phase 7 input discovery but must remain untracked
  and must not be pasted into evidence.
- `infra/snowflake/sql/prod_native_pull_handshake.json` - raw validation
  output if generated. It is local/raw; commit only the sanitized Phase
  7-local artifact from D-16.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `infra/scripts/deploy-snowflake-stack.sh` already orchestrates AWS access
  bootstrap/reconcile, Snowflake Terraform, Snowflake access grants, stream
  processor task deployment, optional native-pull validation, optional dbt,
  and optional dashboard upload. Phase 7 uses the validation path in 07-01
  and deliberately does not use the dbt flag.
- `infra/snowflake/sql/bootstrap_native_pull.py` can emit a structured
  native-pull handshake and validate stage/list plus manifest copy history.
  Its raw output must be sanitized before commit.
- `infra/terraform/snowflake/modules/native_pull/main.tf` already encodes the
  native-pull object graph: storage integration, file formats, stage, source
  mirror tables, pipe, stream, stored procedures, and task.
- `infra/snowflake/dbt/edgartools_gold/` is the dbt project for gold dynamic
  tables and `EDGARTOOLS_GOLD_STATUS`.

### Established Patterns
- Phase 1 launch evidence and matrix files are the cross-phase launch gate
  tracker. Phase 7 updates them with concise citations, while storing detail
  under the Phase 7 directory.
- Generated JSON summary rule from Phase 6 applies here: generated artifacts
  may be used locally, but committed evidence contains only sanitized
  summaries.
- Production evidence is not interchangeable with dev precedent. Phase 7
  must record production pass/block proof.
- Use `uv run --with dbt-snowflake dbt ...` for dbt commands, not bare `dbt`.
- Secret safety remains strict: no DSNs, passwords, tokens, raw connector
  traces, Terraform state, raw Native App logs, raw generated JSON, full row
  dumps, ARNs, external IDs, S3 URLs, or account identifiers in committed
  evidence.

### Integration Points
- Plan 07-01 writes `evidence/native-pull.md`,
  `evidence/native-pull-validation-sanitized.json`, then updates Phase 1
  `evidence/snowflake.md` and native-pull matrix rows.
- Plan 07-02 writes `evidence/dbt-gold.md`, then updates Phase 1
  `evidence/snowflake.md` and dbt/gold matrix rows.
- Phase 8 depends on Phase 7 Snowflake/dbt readiness but still owns MDM
  secret values and MDM connectivity.

</code_context>

<specifics>
## Specific Ideas

- Native-pull deploy command:
  `bash infra/scripts/deploy-snowflake-stack.sh --env prod --snow-connection edgartools-prod --run-validation`
- Native-pull deep validation should summarize:
  `DESC INTEGRATION`, stage/list access, manifest `COPY_HISTORY`, manifest
  processor task state/history, Terraform output `native_pull_ready`, object
  category counts, and safe resource names.
- Sanitized native-pull JSON should include fields such as environment,
  generated_at, status, database/schema names, storage integration name,
  stage/task names, native_pull_ready, validation check statuses, safe counts,
  retry_count, and blocked_reason_category when applicable.
- Sanitized native-pull JSON must omit ARNs, external IDs, S3 URLs, manifest
  file names, Snowflake account identifiers, raw SQL result rows, and raw
  error text.
- dbt commands:
  ```bash
  cd infra/snowflake/dbt/edgartools_gold
  uv run --with dbt-snowflake dbt deps
  uv run --with dbt-snowflake dbt run --target prod
  uv run --with dbt-snowflake dbt test --target prod
  ```
- Grant preflight should confirm `EDGARTOOLS_PROD_DEPLOYER` has the direct
  grants needed for dynamic-table refresh before `dbt run`.
- dbt/gold audit should summarize `EDGARTOOLS_GOLD_STATUS`, dynamic table
  freshness/details, task history, source row counts, and grant checks without
  dumping raw query results.

</specifics>

<deferred>
## Deferred Ideas

- MDM secret value population remains Phase 8 / MDM-02.
- Hosted graph sync/verification remains Phase 9 / GRAPH-03 and GRAPH-04.
- Dashboard UAT and dashboard upload remain outside Phase 7 unless a later
  phase explicitly scopes them.
- No reviewed todos were folded or deferred; `todo.match-phase 7` returned
  zero matches.

</deferred>

---

*Phase: 7-production-snowflake-native-pull-and-gold*
*Context gathered: 2026-06-19*
