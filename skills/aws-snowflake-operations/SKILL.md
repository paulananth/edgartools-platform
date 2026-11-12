---
name: aws-snowflake-operations
description: This platform's AWS and Snowflake operations - the one live AWS account, the hosted MDM store on Snowflake Postgres, Snowflake credit usage, Terraform, ECR images and deploy recipes. Use before running any AWS, Snowflake, Terraform, image build or deploy command.
---

# AWS and Snowflake Operations

Read before any AWS, Snowflake, Terraform, image or deploy command.

## AWS account map (READ THIS before running any AWS command)

**The platform lives in AWS account `690839588395` (current/active).** All `edgartools-*`
resources, ECR images, ECS clusters, and Terraform state should target `690839588395`.

**Account `077127448006` is DECOMMISSIONED and empty.** Everything was migrated to
`690839588395` first, then the old account was torn down.
- **Final closure is a ROOT action.** The `cli-access` IAM user in `077127448006` *cannot*
  close the account: closure or suspension is done through root sign-in or the AWS
  Organizations management account. What was left in place is reaped when the account is closed.
- **State backups** (the only surviving record of the destroyed account) live at
  `~/edgartools-077-tfstate-backups-FINAL` and `infra/.aws-tfstate-backups/`.
- Do NOT reprovision anything into `077127448006`. If an old ARN/bucket/`aws-prod-application.json`
  still references `077127448006`, it is stale — the live target is `690839588395`.

## One environment

There is one environment, prod: AWS account `690839588395` and the `edgartools-prod` Snowflake connection.
No dev environment exists on AWS or on Snowflake; a command that targets dev has nothing to reach.

## Data layers

| Layer | Location | Description |
|-------|----------|-------------|
| **Bronze** | S3 (`s3://<bucket>/`) and local captures | Provider files as captured, one receipt per file. Never mutated. |
| **Merge Stage and MDM** | PostgreSQL 16 (local, or Snowflake Postgres when hosted) | Pre-merge records wait in the Merge Stage; the golden record is in MDM. |
| **RDM** | PostgreSQL 16 | Code sets and their versions. |
| **Silver** | PostgreSQL 16, written by `edgar_warehouse/silver_writer/` | Every detail of each source, typed and keyed. The platform ends here. |

## Checking Snowflake credit usage

For total account consumption over a rolling 48-hour window, query
`SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY` and group by `SERVICE_TYPE`. This
view includes non-warehouse services as well as warehouse cloud-services
usage; use `WAREHOUSE_METERING_HISTORY` only when the question is specifically
warehouse attribution.

Select the connection through
[Data Platform connection setup](../data-platform/SKILL.md#connection-urls-and-environment).

```sql
SELECT
    CONVERT_TIMEZONE('America/New_York', CURRENT_TIMESTAMP()) AS AS_OF_ET,
    CONVERT_TIMEZONE(
        'America/New_York', DATEADD(HOUR, -48, CURRENT_TIMESTAMP())
    ) AS WINDOW_START_ET,
    SERVICE_TYPE,
    ROUND(SUM(CREDITS_USED), 6) AS TOTAL_CREDITS,
    ROUND(SUM(CREDITS_USED_COMPUTE), 6) AS COMPUTE_CREDITS,
    ROUND(SUM(CREDITS_USED_CLOUD_SERVICES), 6) AS CLOUD_SERVICES_CREDITS,
    CONVERT_TIMEZONE('America/New_York', MIN(START_TIME)) AS FIRST_METERED_START_ET,
    CONVERT_TIMEZONE('America/New_York', MAX(START_TIME)) AS LAST_METERED_START_ET
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
WHERE START_TIME >= DATEADD(HOUR, -48, CURRENT_TIMESTAMP())
  AND START_TIME < CURRENT_TIMESTAMP()
GROUP BY SERVICE_TYPE
ORDER BY TOTAL_CREDITS DESC;
```

Sum `TOTAL_CREDITS` across service rows for the account total. Report the
observation time and rolling-window start in `America/New_York`; account-usage
data can lag, and the newest hourly interval may be incomplete. Treat recent
usage as provisional and recheck after it catches up before billing
reconciliation. If a selected column fails compilation, inspect the live view
with `DESC VIEW SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY` rather than assuming
an adjustment column exists. Avoid ordering by `SUM(CREDITS_USED)` when the
selected alias is also named `CREDITS_USED`; Snowflake can resolve the alias
inside the aggregate and report a nested-aggregate error. Use an unambiguous
alias and order by that alias. Ordinal ordering (`ORDER BY 2 DESC`) only works
while the credit column is the second selected column: adding a column in
front of it silently orders by the wrong one, so order by the alias instead.

## The hosted MDM store

- `mdm migrate` does not run automatically on deploy. Treat any prod deploy carrying new migration files
  as incomplete until it has been re-run explicitly — "the image is current" and "the migration was
  applied" are separate facts.
- Snowflake-hosted Postgres re-grants `snowflake_write`'s baseline DML as a platform side effect of
  `ALTER POSTGRES INSTANCE ... RESET ACCESS FOR '<role>'` for *either* role, so run `mdm migrate` as the last
  database-mutating step after any reset. A reset also replaces that role's password, so it needs the operator's word.

### Creating the hosted store in an empty account

Check the account first: `snow sql --connection <name> -q "SHOW DATABASES"` and `"SHOW POSTGRES INSTANCES"`.
A rebuilt account holds neither the `EDGARTOOLS_<ENV>` database nor an instance, and the account named in older
notes is not the live one. The order:

1. The database and its `MDM` schema (the network rule and policy live in that schema).
2. `infra/snowflake/postgres/mdm_create_network_policy.sql`, then `mdm_create_instance.sql`.
3. `bootstrap-prod-mdm.sh`, which rotates both credentials and runs `mdm migrate` last. It rotates on every run
   with no way to skip it, and a rotation needs the operator's word; without it, build the connection file from the
   instance's saved credentials and run `mdm migrate` directly.

- Every `snow sql --filename ... -D name=value` run of those two files needs `--enable-templating JINJA`. Without
  it the CLI leaves `{{ name }}` unreplaced and fails with `syntax error ... unexpected '{'`.
- `CREATE POSTGRES INSTANCE` returns the generated admin and application credentials once, inside the `access_roles`
  value. Send its output to a private file (`umask 077`, a folder outside the repository) and never to the terminal.
  The instance stays `CREATING` for a short while; wait for `state` to read `READY` before connecting.
- A Snowflake CLI result with a credential in it is redacted by key *and by value*: print only the named keys
  you know are public (`state`, `host`, `compute_family`), never a slice of a value, since a slice of a password is a
  leak.

## Pipeline and runtime rules

- Bounded work and idempotent output are the `bookkeeping` skill's (DESIGN: a bounded, validated
  child-work manifest; immutable output by conditional creation, `IfNoneMatch: *`), the one source for them.
- Any "same calendar day" check needs an explicit timezone, and the right one is the business
  process's — `America/New_York` via `pytz` (`zoneinfo` needs a tz database these images don't install).
- A one-time backfill CLI's `--dry-run` needs a `--limit` from the start: proving the logic on real data
  needs tens of rows; only estimating full-run cost needs the whole table.
- Before running a multi-step workflow step by step by hand, look for the one already built (a
  Bookkeeping run, a committed script).
- Provisioning that isn't Terraform or a committed script does not survive an account rebuild, however
  carefully a runbook describes it. And when one stage turns out to have been an uncommitted manual step,
  assume every later stage in the same family is too.
- A check that can silently run against stale, superseded infrastructure makes a false positive and a
  false negative look identical to success. Confirm the *code* under test is what is actually running
  before treating a clean result as evidence — a SQL contract "applied successfully" says nothing about
  the image that writes to it.

## Credentials on the command line

- Never pipe `snow sql ... RESET ACCESS` or `aws secretsmanager get-secret-value` output to
  `head`/`tail`/`cat`/a bare variable capture, for any reason including debugging a downstream parsing
  error — pipe straight into the credential-consuming script and put debug output (`type(pw)`, length,
  key presence) *inside* that script. This leaked a live plaintext password into a transcript twice in one
  session.

Hosted MDM connection setup belongs to
[Data Platform](../data-platform/SKILL.md#connection-urls-and-environment).

## Development Commands

Read [COMMANDS.md](COMMANDS.md) for the exact command before a setup, Terraform or deploy step.

## Image management

Read [IMAGES.md](IMAGES.md) before building, tagging, publishing or pruning a container image, or changing an ECR repository.

## Sizing a worker runtime

Judge a cheaper profile on validated output (correctness, completeness,
idempotency across reruns, a matched control on the same input), never on
memory use or an exit code.
