# Inventory MDM Postgres DDL as input to the Agent Query Catalog

Type: research
Status: open
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
