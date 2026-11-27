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
| **Silver** | PostgreSQL 16, written by `edgar_warehouse/silver_writer/` | Every detail of each source, typed and keyed. |
| **Mirror** | Snowflake mirror database (named in `rules/snowflake.yaml`) | One managed Postgres mirror database with Snowflake-managed Iceberg tables for approved final MDM, RDM and Silver outputs. Consumers read it; the mirror owns writes. |
| **Gold** | Snowflake writable destination (database and schema named in `rules/snowflake.yaml`) | Use dbt when consumption requirements need transformations of approved mirror inputs. Direct mirror reads do not need dbt. Gold writes outside the managed mirror database. |

Gold is published through the mirror: one managed mirror of the data database
(schemas `MDM`, `RDM`, `SILVER`) carries the tables `sources/managed-mirror.yaml`
lists, and Gold is dbt views over it (`edgar_warehouse/gold/views.py` writes the
project from `destination/gold/gold.yaml`). The mirror exists only while it
replicates: a store reset removes it, and it is made again after the next load
and its finish ([HOSTED-MIRRORING](../data-platform/HOSTED-MIRRORING.md#after-the-first-load-mirror-only-what-gold-reads)).
Until then Gold's views read nothing. `verified` in `sources/managed-mirror.yaml`
says whether the current mirror passed its read-back. A dropped target's name
cannot be reused, so a mirror made again takes a new `mirror.database` in
`rules/snowflake.yaml`. Follow
[`SINGLE-DATABASE-ICEBERG.md`](../data-platform/SINGLE-DATABASE-ICEBERG.md)
for the selection, hosted proof and Gold acceptance gates.

## Retiring a Snowflake database

For an architecture change that removes a Snowflake database, resolve the exact
database name first; a database is not a schema. Use the production connection
and an administrative role to inventory it before deletion:

```sql
SHOW DATABASES LIKE '<database_name>';
SHOW SCHEMAS IN DATABASE <database_name>;
SHOW OBJECTS IN DATABASE <database_name>;
SHOW GRANTS ON DATABASE <database_name>;
```

Inspect grants and all objects in each user schema as well. `SHOW OBJECTS IN
DATABASE` includes built-in `INFORMATION_SCHEMA` views; separate those from
user-owned objects when assessing impact. Check dependencies and retention,
and record both with the proposed drop.

Check managed mirror ownership before a database drop. For a mirror target,
follow the Snowflake Postgres mirror skill's `DROP_MIRROR` workflow and its
approval checkpoint; do not drop the target database directly. If mirror
inventory is denied because the `snowflake` application lacks `USAGE` on the
source Postgres instance, use `SHOW TASKS IN ACCOUNT` to check for
`APPLY_MIRROR_<mirror_name>` tasks. An empty task list does not establish
historical mirror ownership. If target ownership remains uncertain, stop before
dropping the database and report the missing evidence. Do not add the
application grant just to complete preflight without authorization, because it
changes access and may affect active mirrors.

Check for network-rule policy associations before dropping the database. A
network rule inside the database can be referenced by a network policy attached
to a live Postgres instance, which blocks `DROP DATABASE ... CASCADE`. Use
`SHOW NETWORK RULES IN SCHEMA <database>.<schema>`, `SHOW NETWORK POLICIES`,
`DESC NETWORK POLICY <policy_name>`, and `DESCRIBE POSTGRES INSTANCE
<instance_name>`; inspect only rule names and policy associations. Never print
IP lists or `access_roles`. If a contained rule is referenced by an active
policy, stop: relocating the rule while preserving access or removing the
association is a separate network-security change. Obtain authorization for
that exact change and verify the new policy reference before retrying the
database drop.

After the owner explicitly authorizes deletion of the named database and its
inventoried contents, run `DROP DATABASE <database_name> CASCADE` and verify it
is absent with `SHOW DATABASES LIKE '<database_name>'`. Do not remove other
account objects, database grants, Postgres instances, network policies, or
integrations as part of this operation unless they are separately requested
and inventoried.

For the selected single managed Iceberg mirror architecture, consult
[`SINGLE-DATABASE-ICEBERG.md`](../data-platform/SINGLE-DATABASE-ICEBERG.md).
The writable Gold destination requires approval of its exact database and
schema names; an existing operational object does not establish that approval.
Retiring an existing database does not complete source consolidation or the hosted mirror
qualification described there.

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

- **A login holds `CONNECT`, never `TEMPORARY`.** Run-time code creates no table, temporary ones included: the silver
  writer applies each batch straight into its table and the financials builds run as one statement
  (`tests/architecture/test_no_temporary_tables_at_run_time.py` refuses one). `provision_hosted_store.py` revokes PUBLIC
  from each database and grants its logins `CONNECT` only. A live store provisioned earlier keeps `TEMPORARY` until the
  next provisioning or reset.
- **One instance holds all six stores.** The hosted instance carries three databases, `data` (`mdm`, `rdm`, `silver`),
  `control` (`bookkeeping`, `change_journal`) and `config` (`rules`), each store a schema, not MDM alone. Before any drop, list its databases and name every
  store it holds to the operator: `DROP POSTGRES INSTANCE` deletes them all, with no undrop and no backup unless one
  was taken first.
- **A fresh instance** is created with the snowflake-postgres skill's `pg_connect.py --create` (it saves the
  administrator's login privately, never shown). Its hostname can take several minutes to resolve after `READY`, and a
  machine that looked it up too early keeps "not found" cached: compare with a public resolver before waiting longer
  (data-operations runbook, "Initialize a hosted store", step 1). Then give it its logins and databases with the data-platform skill's
  `scripts/provision_hosted_store.py`, and follow the data-operations runbook, "Initialize a hosted store".
- **Reachability through a network policy** is decided by the policy's network rules of mode `POSTGRES_INGRESS`;
  `ALLOWED_IP_LIST` does not apply to an instance. A checker that reads only the IP list reports every rule-based
  policy as denied: resolve the rules before concluding an address is blocked, and change no policy on that report.
- Its connection files live in `~/.config/edgartools/hosted/` (`owner.env` the owner login, `worker.env`,
  `governance.env`; folder and files owner-only), beside the other private env files, never in a repo `.env` (each
  worktree is a checkout of a public repository) nor among the disposable local stores, whose folders are deleted when
  unused. This is the one folder: `load --stores` takes it, and a second copy elsewhere goes stale. Source `worker.env`
  before a hosted load; never print its values. Its manifests are the run artifacts (large); the manifest root in
  `worker.env` names where they go.
- `mdm init` does not run automatically on deploy. Treat any prod deploy carrying new migration files
  as incomplete until it has been re-run explicitly — "the image is current" and "the migration was
  applied" are separate facts.
- Snowflake-hosted Postgres re-grants `snowflake_write`'s baseline DML as a platform side effect of
  `ALTER POSTGRES INSTANCE ... RESET ACCESS FOR '<role>'` for *either* role, so run `mdm init` as the last
  database-mutating step after any reset. A reset also replaces that role's password, so it needs the operator's word.

### Creating the hosted store in an empty account

Check the account first: `snow sql --connection <name> -q "SHOW DATABASES"` and `"SHOW POSTGRES INSTANCES"`.
A rebuilt account holds neither the `EDGARTOOLS_<ENV>` database nor an instance, and the account named in older
notes is not the live one. The order:

1. Use [`scripts/mdm_create_network_policy.sql`](scripts/mdm_create_network_policy.sql) with an explicitly approved writable control database/schema for the network rule and policy. This is operational connectivity setup, independent of Gold; it does not create a Gold schema or approve a model destination. Preserve existing policy references until an approved relocation is verified.
2. Use `pg_connect.py --create` from the Snowflake Postgres manage skill for a new instance, with the created network policy. Review compute family and storage before execution.
3. `bootstrap-prod-mdm.sh`, which rotates both credentials and runs `mdm init` last. It rotates on every run
   with no way to skip it, and a rotation needs the operator's word; without it, build the connection file from the
   instance's saved credentials and run `mdm init` directly.

- The network-policy SQL helper needs `snow sql --filename ... -D name=value --enable-templating JINJA`. Without
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
- **The account holds no state machine of the old pipeline.** A load's one state machine is
  `infra/load-pipeline/state-machine.asl.json`, run by the data-operations skill's pipeline. Before a state
  machine is deleted, its definition and tags are saved outside the repository (`describe-state-machine`,
  `list-tags-for-resource`), and the check is that nothing runs it: no running execution, no schedule, no
  event-rule target. The two event rules Step Functions keeps for its own `.sync` tasks are its own; leave them.
- Provisioning that isn't Terraform or a committed script does not survive an account rebuild, however
  carefully a runbook describes it. And when one stage turns out to have been an uncommitted manual step,
  assume every later stage in the same family is too.
- A check that can silently run against stale, superseded infrastructure makes a false positive and a
  false negative look identical to success. Confirm the *code* under test is what is actually running
  before treating a clean result as evidence — a SQL contract "applied successfully" says nothing about
  the image that writes to it.

## Access identities (read-only first)

- Every tool, monitor and audit uses a named, least-privilege identity. The person's own administrator account (password,
  `ACCOUNTADMIN`) is never used by an agent, never changed and never planned against; it must stay as it is.
- A read-only identity is a key-pair service user (type `SERVICE`, no password; connection `authenticator = "SNOWFLAKE_JWT"`)
  on a role that holds only what it reads. Reading the Postgres server log: Snowflake's `EVENTS_VIEWER` application role gives
  `SELECT` on `SNOWFLAKE.TELEMETRY.EVENTS_VIEW`, not on the events table; the instance's id is the first label of its host name
  and filters `resource_attributes['instance.id']`. Auditing: the security, usage and governance viewer database roles plus
  `MONITOR USAGE ON ACCOUNT`.
- `ACCOUNT_USAGE` lags by minutes to hours (a new user or grant is missing at first), and a view the role may not read fails:
  treat both as "not tested", never as "empty, so clean".
- These identities, the resource monitor, the statement timeout and the key-pair-only authentication policy are code
  (`infra/terraform/access/snowflake`), applied by a dedicated access-admin service identity ([Fixing an access
  finding](#fixing-an-access-finding)), not by hand. The [access-audit](../access-audit/SKILL.md) skill grades them.
- The server log quotes the data a failed statement held: read it only through the monitoring script, which drops those lines.
- The Gold writer is the one identity that writes: a key-pair service user whose role reads the approved mirror databases and
  creates views (never tables) in the Gold schema only. dbt reads its settings from the private file
  `~/.config/edgartools/gold-writer/gold-writer.env` (account, user, role, warehouse and the private key's path; the key stays in that
  folder, mode 0600). Prove a new writer by connecting with the key and checking that a view in its schema is created and dropped, and
  that a table, a view in another schema and an account-usage read are refused.
- The mirror operator makes, reads back and changes the managed Postgres mirrors, and nothing else: a key-pair service user
  (`~/.config/edgartools/mirror-operator/mirror-operator.env`, key in that folder, mode 0600) whose role holds the
  `SNOWFLAKE.POSTGRES_MIRROR_ADMIN` application role and owns the Postgres instance, since `CREATE_MIRROR` refuses any role
  that does not own it. The ownership was moved with `COPY CURRENT GRANTS`, and the administrator holds the operator role, so it
  keeps control of the instance. Prove it by connecting with the key: the mirror procedures are listed, and creating a database
  and reading account usage are refused.
- An access change made by an account owner's SQL, before the access-admin identity exists, is the same objects as the Terraform
  and is written there too; import them (`terraform import`) before the first apply, or the plan tries to create them again.

## Fixing an access finding

A finding from the [access-audit](../access-audit/SKILL.md) skill is fixed here, as code, with no hand steps
([access_remediate.py](../access-audit/scripts/access_remediate.py); the Terraform root is `infra/terraform/access/snowflake/accounts/prod`).
The auditor never fixes; this procedure never grades.

1. `bootstrap` creates a key pair for a dedicated **access-admin** service identity (a role that creates roles, users and
   policies and grants them; never `ACCOUNTADMIN`) and prints the one-time SQL that creates it, holding the public key only. An
   account owner runs that SQL once; nothing else is ever run by hand.
2. `plan` runs Terraform as that identity and summarises creates, updates and destroys. It refuses a plan that touches the
   operator's own administrator account, and any destroy unless `--allow-destroy`.
3. `apply --words "<the operator's exact words>"` records the words with the ET time and the plan counts
   (`.scratch/access-audit/approvals.jsonl`), then applies the saved plan.
4. Hand back to the access audit: re-run `access_audit.py` on the platform; the finding is closed only by the re-run's PASS.

**No database is created to hold a control.** A password or authentication policy is a schema-level object (Snowflake documents no account-level form), so it lives in a schema of a database the platform already has (the Gold database's `POLICIES`); its values and home are `rules/snowflake_policy.yaml`, Terraform reads that file, and the audit's POL control fails any difference. A new database needs the operator's approval first; use the platform's native feature before adding an object.

Objects made before the root existed are imported once, so a plan shows no change for them. A permission error from the
access-admin identity is reported as the missing privilege to grant it; it is never worked around with an administrator.
A finding about a person's own account (their MFA, their password) has no code fix: it is reported, and closes by the
operator's signed acceptance (owner, reason, expiry) or by moving the work to a service identity.

## Database ownership

Every database the platform creates is owned by the platform's one owner role (`owner` in `rules/snowflake.yaml`), never by ACCOUNTADMIN, which holds that
role and so keeps control. A database made by an administrator's
SQL has its ownership moved at once with `GRANT OWNERSHIP ON DATABASE <name> TO ROLE <owner> COPY CURRENT GRANTS` (never
`REVOKE CURRENT GRANTS`, above); `scripts/database_owner_sql.py` writes the statements from the names file and the databases named, and the
role and the grants belong in the access Terraform root. The exception is a managed
mirror's target database, proved on a probe mirror: while the mirror replicates (active or suspended) the Snowflake application owns the target
and `GRANT OWNERSHIP` is refused ("cannot be transferred while the mirror is active"); `CREATE_MIRROR` refuses a database that already exists, even one the
mirror operator owns, so the owner role cannot own a target in advance. `DROP_MIRROR(<mirror>, TRUE)` removes the target. A target left by
`DROP_MIRROR(<mirror>, FALSE)` is moved with the administrator's `GRANT OWNERSHIP ON DATABASE <name> TO ROLE <owner>` (no `COPY CURRENT GRANTS`: refused for
an application-owned object, and the mirror operator's own attempt gives "Insufficient privileges"), then dropped by that owner. A live target is administered through its database role `<DATABASE>_ADMIN`, which the mirror operator role holds (the owner role does not).

## Credentials on the command line

- Never pipe `snow sql ... RESET ACCESS` or `aws secretsmanager get-secret-value` output to
  `head`/`tail`/`cat`/a bare variable capture, for any reason including debugging a downstream parsing
  error — pipe straight into the credential-consuming script and put debug output (`type(pw)`, length,
  key presence) *inside* that script. This leaked a live plaintext password into a transcript twice in one
  session.

Hosted MDM connection setup belongs to
[Data Platform](../data-platform/SKILL.md#connection-urls-and-environment).

- Never inspect a credential file by redacting a pattern (`sed` or `grep` on `password =`): a missed pattern prints the secret.
  List key names only (`cut -d= -f1`, or a parser that returns keys). A plain-text password found in a client file is an
  audit finding: move that connection to a key pair.

## Development Commands

Read [COMMANDS.md](COMMANDS.md) for the exact command before a setup, Terraform or deploy step.

Before designing anything that runs inside Snowflake (a compute pool, a job service, a stage volume, Postgres reached
from a service), read [CONTAINER-SERVICES.md](CONTAINER-SERVICES.md): what a trial account refuses, the no-always-on
rule and the probe method.

## Image management

Read [IMAGES.md](IMAGES.md) before building, tagging, publishing or pruning a container image, or changing an ECR repository.

## Sizing a worker runtime

Judge a cheaper profile on validated output (correctness, completeness,
idempotency across reruns, a matched control on the same input), never on
memory use or an exit code.
