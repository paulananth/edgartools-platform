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

A driver's own error can print the whole address, password included (`psycopg2` does when it rejects a URL, such as the
`+psycopg2` driver suffix a SQLAlchemy URL carries). A one-off check that connects directly catches the exception and
prints only its type, or runs through the engine's own command, and filters the output of any command that may fail on a
connection (`sed -E 's#postgres[a-z0-9+]*://[^ "]*#<url>#g'`).

The shared `.env` keeps one standard URL variable per store and one per
catalog service. Use the variable names below directly; keep role-specific
owner, migration and governance connections in their original private role
files. Load the appropriate role file only for that duty. Preserve complete
URLs and keep owner credentials separate from runtime credentials.

## Local catalog endpoint inventory

Keep every database and service URL in the private local connection catalog,
mode `0600`. `OPENMETADATA_URL` selects the catalog root;
`AUTO_ONTOLOGY_API_URL` selects the AutoOntology public web gateway. Runtime
`.env` files remain private. Skills contain variable names and file locations,
not live hosted addresses or credentials. Inventory assignment names only when
the operator asks to list variables without values. Load shell-compatible
assignments with shell sourcing; preserve escaped characters in complete URLs.

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

Six stores live in three databases, each store in its own schema: the **data database** holds `mdm`, `rdm` and `silver` (what
consumers read and one mirror carries), the **control database** holds `bookkeeping` and `change_journal` (what runs the
platform: runs, leases, receipts), and the **config database** holds `rules` (what says how data is processed). A duty is one
login and one file in the stores folder, and every file holds one URL a database and no more: `DATA_URL`, `CONTROL_URL` and
`CONFIG_URL`, each naming its database (operator: "mdm, rdm, silver is data_url, others are control_db, control_url do not have
too many urls"; "control should only have control no configuration"). Each store takes the URL of its group in one place
(`edgar_warehouse.database_connections.store_url`); a missing URL or one that names no database is refused by name, never
guessed. A script that needs the instance and no store (monitoring, role guards, the reset, the audit) uses `DATA_URL`. Nothing
in the product is called a migration: a store has one `init`, which makes its schema or brings it to current.

**The data database holds data, the control database holds run evidence, and the config database holds what says how data is
processed.** The registered rules (the merge rules and the Dataset Contracts under their digests, and their pins) live in the
config database's `rules` schema, beside `rules_used`, and the merge reads them there by digest (a policy by its digest, a
contract by its reading number, which is hashed into every record id, so the registry is kept whole); run evidence and build
records live in `bookkeeping`. The data database keeps its golden records, reference codes and silver rows, the merge's working
tables, and the merge's progress per file (`mastering_file`, `mastering_delivery`), since a file is marked merged in the same
transaction that writes its masters. One init stamp records the data database's schema; it keeps no migration history. A table
nothing reads or writes is deleted from init with its code, never kept empty.

Why three: a managed mirror reads one database, and the instance allows two CDC publications, so the stores consumers read share
one database and one mirror; the control stores stay apart, so their churn and their grants never reach a consumer; and the
configuration stays apart from both, so a reset of the data or the control database (`reset-hosted-databases.py`,
`reset-hosted-tables.py`) never reaches it. Neither the control nor the config database is mirrored.

| Duty | File | Login | Used by |
|---|---|---|---|
| Owner | `owner.env` | the instance's administrator | each store's `init`, silver `register`, `bookkeeping grant-profile`, resetting databases, role guards |
| Loader | `worker.env` | `edgar_loader`, a member of every store's runtime role | `load` and the workers; it can create nothing |
| Governance | `governance.env` | `governance`, a member of the MDM and Rules governance roles | registering and activating rules |
| Reader | `reader.env` | `ops_reader` (`pg_monitor`, no store) | monitoring, profiling, the access audit |

The selected stores folder is authoritative (a hosted store's is `~/.config/edgartools/hosted/`, the only copy of its files).
Every load uses the one loader login, which `provision_hosted_store.py --loader` makes and checks; only a store's owner
login changes a schema. No agent, reviewer or subagent opens the stores folder or prints a connection URL: a reviewer that
needs to know what a login can do asks for the login's name and reads the database's own grants, since a review that
reads the folder puts every password in its transcript.
Source the duty's file in a command-scoped subshell with `set -a` and disable tracing; a command that needs a second duty reads
that file from `--stores` by path, never from the environment. `infra/scripts/local-test-stores.py` makes the local files and
`provision_hosted_store.py` the hosted ones. Never leave the owner file sourced for work: an owner connection is never a runtime
default. Configure each duty only for its requested work.
For load profiling, `quality` reads MDM, `progress`, `failures` and `steps`
read Bookkeeping, and `sample` uses the profiling login's `pg_stat_activity`
access.

Rules commands use the restricted `rules_agent` login, which also reads the registry (`rules.policy`,
`rules.dataset_reading`); registering rules (`rules register`) uses the governance login, a member of
`rules_governance`, which `rules init --registrar-role rules_governance` lets add to the registry. Silver landing
uses its runtime connection and the MDM runtime connection to resolve master
IDs. Each profile grants its worker duty to `bookkeeping_runtime`. After `provision_hosted_store.py --loader --retire`, every load logs in as
`edgar_loader`, and the runtime roles named here are NOLOGIN groups it holds by membership.
For a hosted store, it is a member of `bookkeeping_control`, the group
role passed to Bookkeeping initialization/migration.
The application guard uses runtime role `mdm_runtime`.

When provisioning these files, use `umask 077`, retain TLS settings
(`sslmode=require` for the hosted PostgreSQL target), and keep owners
separate from restricted runtime logins. No login may change or delete a registry row: the agent role holds
SELECT on the registry, the registrar SELECT and INSERT. Apply the committed provisioning and grant procedures rather
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

Hosted OpenMetadata uses `OPENMETADATA_URL` and `OPENMETADATA_TOKEN`, an
authorized bot token from private configuration. The separate local Edgartools
instance is `http://127.0.0.1:8587`; its endpoint, administrator login and PAT
come from the repository-root `.env` documented in the
[OpenMetadata skill](../openmetadata/LOCAL-SERVER.md). Retain all credentials
privately; login/token creation and catalog operations belong to that skill.
The server root has no `/api/v1` suffix when passed to `catalog.connect`,
which appends it.
