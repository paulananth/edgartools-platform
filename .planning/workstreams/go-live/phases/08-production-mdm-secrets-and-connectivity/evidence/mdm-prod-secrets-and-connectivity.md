# MDM Prod Secrets and Connectivity Evidence - Phase 8

Date: 2026-06-20 UTC (Task 1 initial BLOCKED attempt). Updated 2026-06-21 UTC (Task 1 re-run,
instance now provisioned).

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

No host string, DSN, or credential is recorded above or anywhere in this file. (Note: this
instance's `snowflake_admin`/`application` credentials were inadvertently exposed in a chat
transcript during creation and must be treated as compromised and rotated — tracked
separately, not part of this evidence file.)

Per the architecture correction above, this instance shares its Snowflake account with the dev
instance (`EDGARTOOLS_DEV_MDM`, also `READY` in the same account) — they are distinguished by
name/comment only, not by account isolation.

### Original BLOCKED finding (2026-06-20, superseded above)

The initial Task 1 attempt found no `edgartools-prod` SnowCLI connection configured, and found
`aws-admin-prod` resolving to the dev AWS account (`077127448006`). The Snowflake half of that
gap is now resolved (connection configured, instance provisioned and `READY`). The AWS half is
**not** resolved — see Task 2 status below.

### Implication for Task 2 and Task 3

- **Task 2 (populate both required prod secrets): still NOT executed.** `aws-admin-prod`
  continues to resolve to IAM user `cli-access` in account `077127448006` (the dev account),
  confirmed via `aws sts get-caller-identity --profile aws-admin-prod` immediately before this
  update. Writing `postgres_dsn`/`snowflake` secrets without genuine production AWS access
  would write to the wrong account or require fabricating values — both prohibited. Task 2
  remains blocked on operator provisioning of real `aws-admin-prod` credentials.
- **Task 3 (HANDOFF.json neo4j/api_keys scope clarification):** independent of the above
  blocker; not yet executed in this update, can proceed on request.

### Required Operator Action Before Task 2 Retry

1. Configure genuine production AWS admin credentials under the `aws-admin-prod` profile such
   that `aws sts get-caller-identity --profile aws-admin-prod` resolves to a real production AWS
   account distinct from `077127448006`.
2. Rotate the `EDGARTOOLS_PROD_MDM` Postgres instance's `snowflake_admin`/`application`
   credentials (compromised via chat exposure during creation) before using them in any
   `postgres_dsn` secret value.
3. Once both are done, proceed to Task 2 secret population using the documented helper script
   and raw `put-secret-value` pattern in `runbook/mdm-secrets.md`.
