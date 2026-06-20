# Phase 7: Production Snowflake Native Pull And Gold - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-06-19
**Phase:** 7-production-snowflake-native-pull-and-gold
**Areas discussed:** Phase 6 Dependency Boundary, Native-Pull Proof Standard, dbt Gold Evidence Shape, Evidence Writeback Location

---

## Phase 6 Dependency Boundary

### Phase 6 Completion

| Option | Description | Selected |
|--------|-------------|----------|
| Gate then run | Require Phase 6 outputs before live mutation, but record precise BLOCKED evidence if they are missing. | |
| Blocked first | Start Phase 7 by proving the missing-output blocker, then stop until Phase 6 completes. | |
| Snowflake first | Proceed with any Snowflake-only steps possible, accepting more operator judgment and retry risk. | |

**User's choice:** Phase 6 is complete; it was completed by Claude.
**Notes:** Phase 7 is based on `claude/go-live-v1.6-phase6` and carries Phase 6 evidence forward.

### Phase 6 Output Source

| Option | Description | Selected |
|--------|-------------|----------|
| Terraform/live outputs only | Use live Terraform/Snowflake wrapper outputs and Phase 6 summaries; do not depend on generated `infra/aws-prod-application.json`. | |
| Phase 6 evidence docs | Use committed evidence summaries as the planning source, then have execution rediscover live values. | |
| Manifest plus outputs | Allow `infra/aws-prod-application.json` as an operator-local input, but never commit or paste sensitive values. | yes |

**User's choice:** Manifest plus outputs.
**Notes:** Generated JSON stays untracked and secret-safe.

### Mismatch Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Stop and reconcile | Treat mismatch as blocking, record non-secret mismatch shape, and require operator reconciliation before Snowflake deploy. | yes |
| Prefer live AWS/Terraform | Continue using live outputs if they are internally consistent, and note the manifest as stale. | yes |
| Operator override | Allow explicit operator-provided values to continue, as long as they are not committed. | |

**User's choice:** Hybrid of options 1 and 2.
**Notes:** Required-input mismatches block. Stale manifest alone does not block if live AWS/Terraform agree.

### Rechecking Phase 6

| Option | Description | Selected |
|--------|-------------|----------|
| Read-only preflight | Reconfirm required AWS/Terraform outputs and manifest shape only; no rerun of Phase 6 actions. | |
| Evidence-only trust | Trust Phase 6 verification docs and proceed directly to Snowflake steps. | yes |
| Full rediscovery | Re-run broader AWS discovery checks for buckets, SNS, IAM, ECS, and Step Functions before Snowflake. | |

**User's choice:** Evidence-only trust.
**Notes:** Local/live reads may support Phase 7 inputs, but are not a Phase 6 re-verification pass.

---

## Native-Pull Proof Standard

### Minimum SNOW-03 Proof

| Option | Description | Selected |
|--------|-------------|----------|
| Wrapper plus validation | Wrapper exits 0, validation artifact exists locally, and evidence summarizes safe validation fields. | |
| Terraform/wrapper only | Wrapper exits 0 and Terraform outputs show native-pull objects exist; skip extra validation. | |
| Deep Snowflake proof | Wrapper exits 0 plus manual/native checks for integration, stage, copy history, tasks, and readiness. | yes |

**User's choice:** Deep Snowflake proof.
**Notes:** Wrapper success alone is insufficient for SNOW-03.

### Wrapper Invocation

| Option | Description | Selected |
|--------|-------------|----------|
| Native pull first | Run `deploy-snowflake-stack.sh --env prod --snow-connection edgartools-prod --run-validation`, then run dbt separately. | yes |
| One wrapper pass | Run with `--run-validation --run-dbt` together. | |
| Manual Terraform sequence | Run the three Terraform roots and SnowCLI steps manually instead of the wrapper. | |

**User's choice:** Native pull first.
**Notes:** Keeps SNOW-03 and SNOW-04 evidence boundaries clean.

### Raw Validation Artifact Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Local only, summarize | Keep raw artifact local/untracked and summarize only safe fields. | |
| Commit sanitized copy | Commit a redacted/sanitized version of the JSON artifact. | yes |
| Do not use artifact | Treat JSON as transient and rely only on CLI/text evidence. | |

**User's choice:** Commit sanitized copy.
**Notes:** Raw `prod_native_pull_handshake.json` is not committed.

### Sanitized Artifact Contents

| Option | Description | Selected |
|--------|-------------|----------|
| Counts and status only | Include object categories, booleans, validation counts, and pass/block status only. | |
| Resource names too | Include Snowflake database/schema/integration/stage/task names, while omitting sensitive values. | yes |
| Hash sensitive values | Include hashes of ARNs/S3 URLs/external IDs for correlation. | |

**User's choice:** Resource names too.
**Notes:** Omit ARNs, external IDs, S3 URLs, file names, account identifiers, and raw errors.

### Validation Failure Classification

| Option | Description | Selected |
|--------|-------------|----------|
| BLOCKED with partial pass | Mark SNOW-03 blocked and record deployed categories plus failing validation check. | |
| PASS with warning | Mark SNOW-03 pass if Terraform/wrapper succeeded and track validation separately. | |
| Retry once then decide | Allow one immediate validation rerun before classifying pass/block. | yes |

**User's choice:** Retry once then decide.
**Notes:** Second failure means SNOW-03 remains BLOCKED with partial-pass evidence.

---

## dbt Gold Evidence Shape

### dbt Invocation

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone dbt | Run `uv run --with dbt-snowflake dbt deps`, `dbt run --target prod`, and `dbt test --target prod` from the dbt project. | yes |
| Wrapper dbt flag | Re-run deploy wrapper with `--run-dbt`. | |
| dbt build | Use `dbt build --target prod`. | |

**User's choice:** You choose the best option.
**Notes:** Agent selected standalone dbt because it separates SNOW-03 and SNOW-04 evidence and avoids rerunning the wrapper for dbt only.

### dbt Evidence Detail

| Option | Description | Selected |
|--------|-------------|----------|
| Summary counts only | Command, target, exit status, model/test counts, failed names if any; no raw traces. | |
| Detailed dbt output | Selected sanitized console output with model names and timings. | yes |
| Artifact summary | Summarize `target/run_results.json` and `target/manifest.json`; commit neither. | |

**User's choice:** Detailed dbt output.
**Notes:** Still excludes compiled SQL, raw adapter traces, account locators, passwords, and secrets.

### Freshness/Status Evidence

| Option | Description | Selected |
|--------|-------------|----------|
| Gold status plus dynamic tables | Query status view and summarize dynamic-table freshness/task context. | |
| Gold status only | Query and summarize only `EDGARTOOLS_GOLD_STATUS`. | |
| Broad Snowflake audit | Include status view, dynamic tables, task history, source row counts, and grant checks. | yes |

**User's choice:** Broad Snowflake audit.
**Notes:** Summaries only; no raw row dumps.

### Grant Checks

| Option | Description | Selected |
|--------|-------------|----------|
| Preflight before dbt | Check required grants before `dbt run`, stop early if missing. | yes |
| After failure only | Run dbt first; check grants only if dbt fails. | |
| After dbt success | Treat grants as audit evidence after dbt passes. | |

**User's choice:** Preflight before dbt.
**Notes:** Missing grants block before predictable dbt failure.

### dbt Test Failure

| Option | Description | Selected |
|--------|-------------|----------|
| BLOCKED | `dbt test` failure blocks SNOW-04; record passing run plus failed test names and owners. | yes |
| Partial PASS | Gold tables deployed, but tests open a follow-up issue. | |
| Retry tests once | Allow one immediate `dbt test` rerun, then classify BLOCKED if still failing. | |

**User's choice:** BLOCKED.
**Notes:** Passing `dbt run` alone is not a launch pass.

---

## Evidence Writeback Location

### Primary Evidence Location

| Option | Description | Selected |
|--------|-------------|----------|
| Both places | Create Phase 7-local evidence/artifact files, then update Phase 1 evidence and matrix with concise citations. | yes |
| Phase 1 only | Update existing launch evidence and matrix directly; no Phase 7-local evidence files. | |
| Phase 7 only | Keep detailed evidence in Phase 7 and leave Phase 1 matrix/evidence untouched until final launch decision. | |

**User's choice:** Both places.
**Notes:** Detail lives in Phase 7; launch tracker gets concise citations.

### Phase 7-Local Files

| Option | Description | Selected |
|--------|-------------|----------|
| Two evidence files | `evidence/native-pull.md`, `evidence/dbt-gold.md`, plus sanitized JSON. | yes |
| One combined file | `evidence/snowflake.md` plus sanitized JSON. | |
| No evidence dir | Only summaries and Phase 1 evidence/matrix. | |

**User's choice:** Two evidence files.
**Notes:** Sanitized JSON path locked in CONTEXT.md as `evidence/native-pull-validation-sanitized.json`.

### Matrix Update Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Only after each plan passes | Plan 07-01 updates SNOW-03 rows after native-pull passes; Plan 07-02 updates SNOW-04 rows after dbt/audit passes. | yes |
| At end of Phase 7 | Leave matrix unchanged until both plans complete. | |
| Immediately as pending | Add Phase 7 placeholders before execution starts. | |

**User's choice:** Only after each plan passes.
**Notes:** Matrix updates are proof-driven, not placeholders.

### Partial Phase Outcome

| Option | Description | Selected |
|--------|-------------|----------|
| Mixed status | Passed rows flip to PASS, blocked rows stay BLOCKED with evidence and remediation. | yes |
| Keep all BLOCKED | Any Phase 7 blocker keeps all Snowflake rows BLOCKED until the whole phase passes. | |
| Do not update matrix | Record only Phase 7-local evidence until both plans pass. | |

**User's choice:** Mixed status.
**Notes:** Allows accurate launch gate state after each plan.

### Blocked Evidence Commits

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, commit safe blocked evidence | Commit sanitized partial evidence so the blocker is reproducible and actionable. | yes |
| Only on full pass | Do not commit evidence artifacts unless the plan passes. | |
| Ask operator per blocker | Decide case by case before committing blocked evidence. | |

**User's choice:** Yes, commit safe blocked evidence.
**Notes:** Secret-safety still overrides completeness.

---

## the agent's Discretion

- The user asked the agent to choose the best dbt invocation option. The agent chose standalone dbt.

## Deferred Ideas

- MDM secret value population remains Phase 8.
- Hosted graph E2E remains Phase 9.
- Dashboard UAT/upload remains outside Phase 7 unless later scoped.
