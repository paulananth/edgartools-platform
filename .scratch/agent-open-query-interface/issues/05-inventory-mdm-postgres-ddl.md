# Inventory MDM Postgres DDL as input to the Agent Query Catalog

Type: research
Status: resolved
Blocked by: none

## Question

The operator scoped this map's near-term work to the Postgres backend
first, deferring the Snowflake half (gold, graph Native App) until
[Clean MDM](../../clean-mdm/map.md)'s local-Postgres-first qualification
gate clears (see this map's own Notes — that policy is Clean MDM's,
cited here, not re-decided).

Inventory the **current** MDM Postgres schema — the 38 tables across
migrations 001-022, already applied locally per
[Clean MDM ticket 03](../../clean-mdm/issues/03-apply-current-mdm-schema-to-local-postgres.md)
— as raw input to what the Agent Query Catalog must describe for this
backend: table names, columns, types, null semantics where documented,
primary/foreign keys, and any existing relationship/graph-adjacent
tables (`mdm_relationship_instance` and neighbors).

**Important framing, not a caveat to skip past**: this schema is
actively being rebuilt by Clean MDM (shared Company/Person identities,
governed profiles, a Merge Stage — none landed yet). This is a
**current-state inventory**, expected to move under Clean MDM's own
work, not a settled catalog. Do not treat it as final. Do not propose
schema changes here — that is Clean MDM's decision surface, not this
map's.

Read-only. Do not modify any Clean MDM file, branch, or worktree. Do not
connect to or query Snowflake — the local `edgartools-prod` SnowCLI
profile currently points at an expired-trial account
(`PRJEDJU-QJB05385`), not prod's real account (`xcpclkf-kb19989` per
CLAUDE.md), so Snowflake-side verification is unavailable from this
environment regardless of scope.

Save findings at
`.scratch/agent-open-query-interface/research/05-mdm-postgres-ddl-inventory.md`.

## Comments

- 2026-09-19: run against the live local Postgres instance (read-only
  introspection, container already running — no Clean MDM file/branch/
  worktree touched). Full findings in the research file below.

## Answer

27 tables in the `mdm` database (+ 11 in `change_ledger` = 38, matching
Clean MDM ticket 03's figure; `bookkeeping`'s 10 and `silver`'s 6 tables
are separate, non-MDM concerns). Full column/PK/FK inventory, by
category (entity identity, source binding, relationship model,
governance config, operational/staging, graph generation bookkeeping),
plus current row counts, in
`.scratch/agent-open-query-interface/research/05-mdm-postgres-ddl-inventory.md`.

Two facts worth carrying forward into catalog design:

1. The relationship data (`mdm_relationship_instance`/
   `mdm_relationship_type`) already lives in the same Postgres database
   as the entity tables — "MDM" and "graph (Postgres mirror)," named
   separately in this map's Destination, are one database locally, not
   two connections.
2. `mdm_relationship_instance` carries its own versioning
   (`superseded_by_version_id`) and temporal validity
   (`valid_from_date`/`valid_to_date`) — an agent needs to know to filter
   on these for "current" relationships, echoing `CONTEXT.md`'s Current
   Neighborhood rule for the bundle-based surfaces. Whether the catalog
   states this explicitly is a catalog-design question, not resolved
   here.

Left open, not resolved by this ticket: whether `change_ledger`/
`bookkeeping` belong in the Agent Query Catalog's "MDM" scope at all
(my read: no, they're warehouse/acquisition internals, not domain data
an agent would ask about — but this wasn't decided), and whether
operational/staging/governance tables should be catalog-visible or
excluded as internal-only.
