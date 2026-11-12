# Connection URLs and environment

Part of the [Data Platform skill](SKILL.md). This is the sole skill reference
for service URLs and connection setup. Other skills link here; they retain
their operational procedures, not copies of the connection instructions.

## Discover existing configuration first

Check variable presence without displaying values in the process environment,
the active worktree's root `.env`, and the shared
`~/.local/share/edgartools/.env` before asking for a connection. A worktree
does not automatically inherit another worktree's ignored `.env`. Confirm the
requested environment and duty before using any saved address; a discovered
URL does not authorize a different target.

Keep private files mode `0600`, outside Git or covered by its ignore rules.
Load only the selected variables into the process that needs them, without
shell tracing or printing the file. Source only trusted, operator-controlled
shell env files; parse dotenv files as data when they are not shell-compatible.
Keep existing explicit process values unless deliberately selecting a new
environment. Missing configuration means ask the operator to set it in their
own terminal, never paste it into chat. Examples contain placeholders only.

The shared `.env` is a private URL catalog across agent worktrees. Standard
database variable names hold hosted worker connections. Saved alternatives
use `HOSTED_PROD_VERIFIER_`, `HOSTED_PROD_GOVERNANCE_`,
`HOSTED_PROD_CONNECTION_` and `WORKTREE_` prefixes. These are catalog aliases,
not variables applications automatically select. Preserve the original role
files and refresh saved values from them when connections change; do not
combine credentials or silently substitute an owner for a runtime login.

## Database connections and duties

Each store uses its own database and URL; never derive another store's URL
by changing an MDM address. Preserve the complete authorized dialect, host,
port, database, role, credential and SSL options.

Bare PostgreSQL and MySQL URLs select the shipped drivers. An independent
Bookkeeping installation needs its `mysql` extra for MySQL; an independent
Change Journal installation needs its selected `mysql` or `sqlserver` extra.
Provision separate owners and restricted runtime roles, retaining the
environment's ownership checks; do not adopt another workstream's databases.
Missing store configuration never falls back to a legacy store, another
store's URL, or a guessed database name.

| Store | Runtime variable | Migration/owner variable |
|---|---|---|
| MDM | `MDM_DATABASE_URL` | `MDM_MIGRATION_DATABASE_URL` |
| RDM | `RDM_DATABASE_URL` | `RDM_MIGRATION_DATABASE_URL` |
| Rules | `RULES_DATABASE_URL` | `RULES_MIGRATION_DATABASE_URL` |
| Bookkeeping | `BOOKKEEPING_DATABASE_URL` | `BOOKKEEPING_MIGRATION_DATABASE_URL` |
| Change Journal | `CHANGE_JOURNAL_DATABASE_URL` | `CHANGE_JOURNAL_MIGRATION_DATABASE_URL` |
| Silver | `SILVER_DATABASE_URL` | `SILVER_MIGRATION_DATABASE_URL` |

The selected stores folder is authoritative: use its `worker.env` for work,
`verifier.env` for independent verification, `connection.env` for owner or
migration duties, and `governance.env` for activation. Source the appropriate
trusted file in a command-scoped subshell with `set -a` and disable tracing.
`load --stores` takes this folder and selects duties itself, not a single
`.env` file. `infra/scripts/local-test-stores.py` creates local role files.

MDM and Bookkeeping migration commands consume their ordinary
`*_DATABASE_URL` variable as the owner for that command only; other stores'
migrations consume `*_MIGRATION_DATABASE_URL`. Never leave owner connections
as runtime defaults. Activation additionally needs
`RULES_MDM_ACTIVATION_DATABASE_URL` from the governance file; destination
guard setup uses `DESTINATION_MIGRATION_DATABASE_URL` as its owner.
`PROFILE_DATABASE_URL` is a separately authorized profiling login with access
to database activity. Configure these only for their requested duty.
For load profiling, `quality` reads MDM, `progress`, `failures` and `steps`
read Bookkeeping, and `sample` uses the profiling login's `pg_stat_activity`
access.

Rules commands use the restricted `rules_agent` login; activation uses the
Rules governance login plus the MDM governance connection. Silver landing
uses its runtime connection and the MDM runtime connection to resolve master
IDs. Bookkeeping work and verification must use different authenticated
logins; each profile grants worker duty to `bookkeeping_runtime` and
verifier duty to `bookkeeping_verifier`, never both duties to one login.
For a hosted store, both are members of `bookkeeping_control`, the group
role passed to Bookkeeping initialization/migration. MDM verification uses
`mdm_verifier` with schema usage and read access to prepared/mastering tables.
The application guard uses runtime role `mdm_runtime`.

When provisioning these files, use `umask 077`, retain TLS settings
(`sslmode=require` for the hosted PostgreSQL target), and keep owners
separate from restricted runtime logins. `mdm_governance` needs database
`CONNECT`, schema `USAGE`, read access to prepared/mastering tables, and
`INSERT` on `mdm.policy`, `mdm.dataset` and `mdm.dataset_mapping`, plus the
registration grant. `rules_governance` needs Rules agent and approver
membership. Apply the committed provisioning and grant procedures rather
than granting administrative rights to runtimes.

`MDM_APPLICATION_ROLE` names the application role.
`BOOKKEEPING_MANIFEST_ROOT` is the manifest folder written as a `file://`
URI (a plain path is refused), or the authorized S3 prefix on AWS. The role
files carry these non-URL settings too; a URL-only catalog does not replace
them. Check configuration with `edgar-warehouse doctor`, then the requested
read-only connectivity command; report presence and outcomes, not addresses.

## Snowflake and catalog services

Snowflake SQL uses the explicit named connection `edgartools-prod`; inspect
connection names in `~/.snowflake/connections.toml` and defaults in
`~/.snowflake/config.toml` without displaying credentials. Do not derive a
connection name from the environment slug.

Snowflake-hosted MDM is PostgreSQL protocol on port `5432`, not the Snowflake
SQL connection. Its complete authorized DSN belongs in private `.env` storage.
Do not infer it from the SQL account, rotate access to discover it, or run a
bootstrap/reset command as a URL lookup.

OpenMetadata uses `OPENMETADATA_URL` and `OPENMETADATA_TOKEN`, an authorized
bot token from private configuration. The local server endpoint is
`http://127.0.0.1:8585`; confirm the configured instance rather than replacing
it with that default. Retain the token privately; login/token creation and
catalog operations belong to the OpenMetadata skill.
The server root has no `/api/v1` suffix when passed to `catalog.connect`,
which appends it. Local initialization may instead use
`OPENMETADATA_LOGIN_EMAIL` with `OPENMETADATA_LOGIN_PASSWORD` (or the
supported `OPENMETADATA_PASSWORD` alias) for native login.
