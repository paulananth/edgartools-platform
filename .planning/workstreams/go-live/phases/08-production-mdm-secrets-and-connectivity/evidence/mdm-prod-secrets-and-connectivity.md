# MDM Prod Secrets and Connectivity Evidence - Phase 8

Date: 2026-06-20 UTC
Environment: production required; this evidence records a BLOCKED precondition check, not
production proof.

This artifact captures non-secret evidence only. It omits credential values, tokens, DSNs,
hosts, full connector output, and raw error text per the v1.5 runbook Security Note.

## Task 1 — Precondition: Confirm prod Snowflake-hosted Postgres MDM instance exists

### Outcome: BLOCKED

The production Snowflake-hosted Postgres MDM instance's existence/readiness could not be
verified from this execution environment, and no genuine production AWS access was available
either. Both gaps independently block this plan from proceeding to Task 2.

### What was checked

1. **AWS prod access.** The plan calls for `--aws-profile aws-admin-prod`. This profile is
   configured locally, but its `credential_process` resolves to the same underlying identity
   as the `default` AWS CLI profile. `aws sts get-caller-identity` against this profile
   resolved to IAM user `cli-access` in account `077127448006`. Per `CLAUDE.md` Quick
   Navigation / bucket and state-machine naming (`edgartools-dev-bronze-077127448006`,
   `edgartools-dev-*` state machines), account `077127448006` is the **dev** account, not a
   distinct production account. There is no evidence that `aws-admin-prod` in this environment
   reaches a separate production AWS account at all — it appears to be dev credentials under a
   prod-labeled profile name. This independently blocks Task 2 (secret population requires
   genuine prod Secrets Manager write access) regardless of the Postgres-instance outcome
   below.

2. **Snowflake prod connection.** `infra/scripts/go-live.sh` documents the canonical prod
   SnowCLI connection name as `edgartools-prod` (`default_snow_connection_for_env`). Listing
   locally configured SnowCLI connections (`snow connection list`) shows only two entries:
   one personal/OAuth connection and one named `snowconn` (the dev connection, matching the
   account used by `infra/snowflake/postgres/mdm_create_instance.sql`'s documented dev
   invocation). No connection named `edgartools-prod` (or any other prod-labeled connection) is
   configured in this environment. Attempting `snow sql --connection edgartools-prod` fails
   with "Connection edgartools-prod is not configured."

3. **Read-only check against the one reachable account (strengthener, non-secret).** As a
   cheap sanity check that does not require prod access, `SHOW POSTGRES INSTANCES` was run
   against the only fully-configured, reachable connection (`snowconn`, the dev connection).
   Result: exactly one Postgres instance exists in that account — `EDGARTOOLS_DEV_MDM`
   (type `PRIMARY`, owner role `ACCOUNTADMIN`, comment references the MDM Snowflake Postgres
   runtime database). No production-named instance exists in this reachable account. This
   confirms the dev instance is present and accounted for, and rules out a same-account prod
   instance, but says nothing about whether a separate production Snowflake account/instance
   exists — that account is not reachable from this environment.

No host string, DSN, credential, or raw connector error is recorded above or anywhere in this
file.

### Conclusion

The production Snowflake-hosted Postgres MDM instance's existence/readiness is **unverifiable
from this execution environment** — not confirmed-absent, not confirmed-present. Combined with
the absence of genuine production AWS access, Task 2 (secret population) cannot proceed without
fabricating values. Per this plan's explicit instruction and the Phase 7 precedent (07-01/07-02
correctly stopped at BLOCKED evidence rather than fabricating prod Snowflake credentials),
execution STOPS here. Task 2 is NOT executed. No DSN or credential was written to
`edgartools-prod/mdm/postgres_dsn` or `edgartools-prod/mdm/snowflake`.

### 5-Whys Root Cause

1. **Symptom:** Task 1's precondition check cannot confirm the prod Postgres MDM instance
   exists or is ready.
2. **Why?** No SnowCLI connection named `edgartools-prod` (or equivalent) is configured in this
   execution environment, so no prod-targeted `DESCRIBE POSTGRES INSTANCE` or
   `SHOW POSTGRES INSTANCES` call can be issued.
3. **Why?** Separately, the `aws-admin-prod` AWS CLI profile configured in this environment
   resolves to the same identity/account as the dev profile (`077127448006`), so even AWS-side
   prod evidence (e.g., a prod Secrets Manager describe-secret) is not obtainable here either.
4. **Why?** No operator has yet provisioned distinct production Snowflake and AWS credentials
   for this execution environment. This mirrors the Phase 7 finding verbatim: "production
   Snowflake Terraform backend/tfvars files... have never been provisioned by a human
   operator — this is the first phase to touch the Snowflake side of prod" (STATE.md, Phase 07
   decision log) — Phase 8 is the analogous first phase to require a genuinely separate
   *production* AWS identity and a *production* Snowflake connection for MDM secrets, and
   neither has been provisioned yet either.
5. **Root cause:** Production AWS admin credentials and a production Snowflake connection have
   never been provisioned for an operator in this execution environment. This is an external
   operator-provisioning gap, not a code or configuration defect in this repository.

### Implication for Task 2 and Task 3

- **Task 2 (populate both required prod secrets):** NOT executed. Cannot proceed without
  genuine production AWS write access and a confirmed-ready target Postgres instance; doing so
  would require either fabricating a DSN/credential value (explicitly prohibited) or writing to
  an account that may not be the real production account.
- **Task 3 (HANDOFF.json neo4j/api_keys scope clarification):** independent of the above
  blocker — proceeds normally.

### Required Operator Action Before Retry

1. Provision/confirm a production Snowflake-hosted Postgres MDM instance and configure a
   `edgartools-prod` (or equivalently prod-scoped) SnowCLI connection pointing at the genuine
   production Snowflake account, entering any credentials directly via `snow connection add` or
   the Snowflake config file — never pasted into chat or committed.
2. Configure genuine production AWS admin credentials under the `aws-admin-prod` profile (or
   an equivalent profile) such that `aws sts get-caller-identity --profile aws-admin-prod`
   resolves to the real production AWS account, not the dev account `077127448006`.
3. Once both are confirmed, re-run this plan's Task 1 precondition check, then proceed to
   Task 2 secret population using the documented helper script and raw `put-secret-value`
   pattern in `runbook/mdm-secrets.md`.
