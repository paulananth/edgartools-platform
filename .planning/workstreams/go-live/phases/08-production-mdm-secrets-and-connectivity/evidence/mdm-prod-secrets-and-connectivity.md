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

## Task 2 — Secret population (2026-06-21) — COMPLETE

### 4th Postgres credential rotation + `edgartools-prod/mdm/postgres_dsn`

Recovered the exact rotation statement from Snowflake `QUERY_HISTORY` (query *text* only,
no result set, no secret) instead of reconstructing it from memory:

```
ALTER POSTGRES INSTANCE EDGARTOOLS_PROD_MDM RESET ACCESS FOR 'application';
```

Ran as a single atomic shell pipeline: rotation command → JSON parse (extracts only the
`password` field, in-process, never printed) → directly into
`infra/scripts/bootstrap-aws-mdm-secrets.sh --host <host> --username application --database mdm
--password-stdin --env prod --aws-profile aws-admin-prod --aws-region us-east-1`, which
constructs, validates, and writes the DSN itself. The raw credential never appeared in any
individual tool result or intermediate variable echo. Host (non-secret, from `DESCRIBE POSTGRES
INSTANCE`) and username (`application`, literal from the rotation statement) were the only
inputs supplied outside the pipe.

### `edgartools-prod/mdm/snowflake`

Populated by copying `EDGARTOOLS_PROD_DEPLOYER`'s existing credentials from
`edgartools-prod/dbt/snowflake` (Phase 07), remapped `DBT_SNOWFLAKE_*` → `MDM_SNOWFLAKE_*`,
with `MDM_SNOWFLAKE_SCHEMA` hardcoded to `EDGARTOOLS_GOLD`. Single piped command
(`get-secret-value | jq | put-secret-value --secret-string file:///dev/stdin > /dev/null`); no
human typed or saw a password. Post-write verification checked only key *names* and value
*types* (`jq 'with_entries(.value = (.value | type))'`), never the values themselves — confirmed
all 7 expected keys present as non-empty strings.

### `describe-secret` metadata (non-secret)

| Secret | ARN suffix | LastChangedDate | AWSCURRENT |
|---|---|---|---|
| `edgartools-prod/mdm/postgres_dsn` | `...postgres_dsn-s71voe` | 2026-06-21T17:32:22-04:00 | present |
| `edgartools-prod/mdm/snowflake` | `...snowflake-CNgES5` | 2026-06-21T17:32:35-04:00 | present |

Both secrets show a current AWSCURRENT version. No DSN, host, password, username value, or
connector error is recorded in this file.

## Task 3 — HANDOFF.json scope check (2026-06-21)

Confirmed: `.planning/HANDOFF.json`'s `human_actions_pending`/`remaining_tasks` entries for this
phase reference only `postgres_dsn` and `snowflake` secrets. No reference to `neo4j` or
`api_keys` secrets exists anywhere in the file — pre-satisfied, no edit needed.

## Plan 08-02 Task 1 — Connectivity verification (2026-06-21) — COMPLETE

### Root-cause: `mdm` database did not exist on the instance

The first `check-connectivity` attempt against the rotated `application` credential failed with
`FATAL: database "mdm" does not exist` — auth succeeded (proving the rotation/secret were
correct), but the database itself had never been created on this fresh instance. Per the 5-whys
discipline: (1) symptom — connection refused at the database-selection step; (2) why — only
`postgres`/`snowflake_monitoring` databases existed (checked non-secretly via `pg_database`);
(3) why — `docs/aws-mdm-snowflake-postgres-cutover.md` documents `CREATE DATABASE mdm` as a
required one-time step using `snowflake_admin`, never run for this prod instance; (4) why — this
is a brand-new MDM install (no RDS restore), so the existing runbook's restore-oriented grant
script (`mdm_post_restore.sql`) was never triggered; (5) root cause — database provisioning was
not yet performed as part of this rotation cycle. Fixed by rotating `snowflake_admin` access
(5th rotation overall, ALTER POSTGRES INSTANCE EDGARTOOLS_PROD_MDM RESET ACCESS FOR
'snowflake_admin') and running `CREATE DATABASE mdm` via a transient, never-persisted admin
connection (password held only in-process, never printed, discarded immediately after use).

A connection-retry loop (up to ~40s) was required immediately after each rotation — the new
Snowflake-hosted Postgres credential is not instantly active; this matches the workstream's
known propagation-delay characteristic for this feature.

### Schema migration required snowflake_admin (6th rotation)

`edgar-warehouse mdm migrate` initially failed under the `application` role with
`InsufficientPrivilege: permission denied to create extension "pgcrypto"` — Postgres 15+
revokes `CREATE` on the `public` schema from non-owner roles by default, so the runtime
application role cannot create extensions/tables on a freshly created database. Re-ran the
migration with a 6th, freshly rotated `snowflake_admin` credential passed only as an in-process
env var to a child `edgar-warehouse mdm migrate` invocation (never written to any secret, file,
or the chat transcript), then applied the same grant set as
`infra/snowflake/postgres/mdm_post_restore.sql` (CONNECT, schema USAGE, table/sequence DML,
default privileges) so the long-lived `application` role in the secret has correct runtime
access going forward. Admin password discarded (`pw = None`) immediately after the grants
committed; it is not stored anywhere and the admin role is not used by the application secret.

### Final verification (sanitized — `application` role only)

```
check-connectivity: {"sql": {"connected": true, "dialect": "postgresql", "missing_tables": []}}
migrate (re-run, idempotent no-op confirmed): exit_code 0
counts: all 19 MDM tables queried successfully, all counts 0 (expected — fresh database, no data loaded yet)
```

`MDM_DATABASE_URL` was exported only for the duration of each command and `unset` immediately
after in every invocation. No DSN, host-with-credentials, password, or raw connector error
appears in this file or in any tool output during this session.

## Disposition

Plan 08-01 (Task 2, Task 3) and Plan 08-02 (Task 1) are complete. Plan 08-02 Task 2 (human
checkpoint — confirm this evidence file is secret-safe before flipping launch gate matrix rows)
is the only remaining gate for Phase 8.
