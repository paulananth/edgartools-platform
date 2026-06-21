# MDM Prod Secrets and Connectivity Evidence - Phase 8

Date: 2026-06-20 UTC (Task 1 initial BLOCKED attempt). Updated 2026-06-21 UTC (Task 1 re-run,
instance now provisioned). Updated again 2026-06-21 UTC (credential rotation completed).

Environment: production. This evidence records Task 1's precondition outcome, not Task 2/3
secret-population proof (Task 2 remains separately blocked — see below).

This artifact captures non-secret evidence only. It omits credential values, tokens, DSNs,
hosts, full connector output, and raw error text per the v1.5 runbook Security Note.

## Architecture correction (2026-06-21)

A prior pass of this evidence (and a decision recorded in `.planning/HANDOFF.json`) assumed
Snowflake prod and dev are separate accounts. Direct verification disproved this:
`SELECT CURRENT_ACCOUNT(), CURRENT_ACCOUNT_NAME(), CURRENT_ORGANIZATION_NAME()` returned
identical values via both the `edgartools-prod` and `snowconn` (dev) SnowCLI connections.
`EDGARTOOLS_DEV` and `EDGARTOOLS_PROD` are two databases inside **one** shared Snowflake
account — consistent with the already-documented AWS pattern (same-account,
prefix-distinguished, not separate). The corrected decision is recorded in `HANDOFF.json`.
Practical consequence: Postgres instances and network policies are account-scoped, not
database-scoped, so the dev and prod MDM Postgres instances/network policies share one
account-level blast radius.

## Task 1 — Precondition: Confirm prod Snowflake-hosted Postgres MDM instance exists

### Outcome: CONFIRMED — instance exists and is ready

A SnowCLI connection named `edgartools-prod` is now configured and reachable (previously
absent, which caused the original BLOCKED outcome below). A production-named Postgres
instance, `EDGARTOOLS_PROD_MDM`, was provisioned in this Snowflake account and confirmed via
`SHOW POSTGRES INSTANCES`:

- name: `EDGARTOOLS_PROD_MDM`
- state: `READY`
- type: `PRIMARY`
- owner role: `ACCOUNTADMIN`
- comment: references the MDM Snowflake Postgres runtime database (prod)

No host string, DSN, or credential is recorded above or anywhere in this file.

### Credential rotation (2026-06-21) — COMPLETE

This instance's original `snowflake_admin`/`application` credentials were inadvertently
exposed in a chat transcript during creation and were treated as compromised. A first rotation
attempt (`ALTER POSTGRES INSTANCE ... RESET ACCESS FOR`) also leaked its output before a
redaction-filter gap in `go-live.sh` was identified and fixed (the command returns a generic
`password` field that the existing filter did not match). A third rotation attempt, run after
the fix, completed cleanly with no credential values printed anywhere in the transcript or
written to any file. The instance now has fresh `snowflake_admin`/`application` credentials
that have never been exposed. The original (pre-rotation) credentials are permanently invalid
and must never be used in any secret value or DSN.

Per the architecture correction above, this instance shares its Snowflake account with the dev
instance (`EDGARTOOLS_DEV_MDM`, also `READY` in the same account) — they are distinguished by
name/comment only, not by account isolation.

### Original BLOCKED finding (2026-06-20, superseded above)

The initial Task 1 attempt found no `edgartools-prod` SnowCLI connection configured, and found
`aws-admin-prod` resolving to the dev AWS account (`077127448006`). The Snowflake half of that
gap is now resolved (connection configured, instance provisioned and `READY`). The AWS half is
**not** resolved — see Task 2 status below.

## AWS architecture correction (2026-06-21)

A prior pass of this evidence (and `08-01-SUMMARY.md`, `STATE.md` Blocker 2, and
`.planning/HANDOFF.json`) treated `aws-admin-prod` resolving to account `077127448006` as a
blocker — framing it as "the dev account" and requiring "genuine production AWS credentials" in
a *different* account. This was a documentation error, not a real gap, and repeats (in the
opposite direction) the same kind of mistake already corrected for Snowflake above.

The settled architecture decision is **D-05**
(`.planning/workstreams/go-live/milestones/v1.5-phases/02-aws-and-snowflake-production-deployment-dry-run/02-CONTEXT.md`),
made in v1.5 Phase 2: `aws-admin-dev` and `aws-admin-prod` are **intentionally** the same AWS
account. "Prod" is a same-account, prefix-distinguished resource set (separate Terraform root,
`:prod`-tagged ECR images, `edgartools-prod-*` named resources) — not a separate account. D-05
explicitly states: "Downstream agents must not assume a separate prod account/ECR exists."

Live verification via the `aws-admin-prod` profile (same underlying credentials as `default`,
by design — see `docs/aws-authentication.md`) confirms prod resources already exist in this
account:
- S3: `edgartools-prod-bronze`, `edgartools-prod-warehouse`, `edgartools-prod-snowflake-export`,
  `edgartools-prod-tfstate`.
- Secrets Manager: `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake` both
  exist (created by the prod Terraform apply, 2026-06-19), with `VersionIdsToStages: null` —
  i.e. created but never populated. This is exactly the precondition Task 2 expects.

**Practical consequence: there is no AWS-side blocker.** Task 2 can run now using the
`aws-admin-prod` profile as already configured.

### Implication for Task 2 and Task 3

- **Task 2 (populate both required prod secrets): ready to execute.** Both target secrets exist,
  unpopulated. The only remaining precondition (rotated, never-exposed Postgres credentials) was
  satisfied earlier in this session. No further blocker exists — population was not run in this
  update pending explicit operator go-ahead before writing to a real production secret.
- **Task 3 (HANDOFF.json neo4j/api_keys scope clarification):** independent of the above;
  pre-satisfied by a prior session per `08-01-SUMMARY.md`.

### Required Operator Action Before Task 2 Retry

None. The previously-listed AWS-credentials blocker did not exist — `aws-admin-prod` was
already correctly configured per D-05. Task 2 is unblocked and ready to run.
