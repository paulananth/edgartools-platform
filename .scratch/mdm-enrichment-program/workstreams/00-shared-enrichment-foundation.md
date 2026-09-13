# Shared enrichment foundation

Classification: mandatory foundation
Status: planned
Depends on: accepted program decisions
Future spec: `docs/specs/mdm-enrichment/shared-foundation.md`

## Destination

One AWS source-evidence path supports every enrichment source and consumer with
immutable capture, source/run identity, independent checkpoints, temporal
versions, review states, replay, observability, security, and retention hooks.

## Required decisions and evidence

- Authoritative source archive, member-file, cadence, domain route, and recovery
  inventory from the
  [source-file pipeline catalog](../source-file-pipeline-catalog.md).
- Schema boundaries for source publications, records, candidates, accepted
  links, conflicts, deferred domains, mappings, and stewardship decisions.
- Change Ledger authority, S3 path catalog, Snowflake native-pull boundary, and
  Snowflake Postgres transaction/run binding.
- Delta continuity, full reconciliation, replay, migration, rollback, threat,
  cost, and TDD contracts.

Exit only after offline fixtures reproduce identical inventories, state changes,
and evidence hashes without publishing a domain record.
