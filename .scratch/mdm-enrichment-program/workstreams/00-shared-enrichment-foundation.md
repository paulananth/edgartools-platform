# Shared enrichment foundation

Classification: mandatory foundation
Status: specified 2026-09-19 (decision-complete for the GoF review items; open items and release gates listed in the spec; not yet verified)
Depends on: accepted program decisions
Spec: [`docs/specs/mdm-enrichment/shared-foundation.md`](../../../docs/specs/mdm-enrichment/shared-foundation.md)

## Destination

One AWS source-evidence path supports every enrichment source and consumer with
temporary Bronze staging, a low-cost immutable Source Artifact Archive,
source/run identity, independent checkpoints, temporal versions, review states,
replay, observability, security, and retention hooks.

## Required decisions and evidence

- Authoritative source archive, member-file, cadence, domain route, and recovery
  inventory from the
  [source-file pipeline catalog](../source-file-pipeline-catalog.md).
- Schema boundaries for source publications, records, candidates, accepted
  links, conflicts, deferred domains, mappings, and stewardship decisions.
- Generic legal-entity registry representation and source-classification
  history for accepted records, such as GLEIF International Organizations,
  that do not justify a dedicated domain table or consumer.
- Bookkeeping Root Run, Change Ledger transition authority, S3 path and
  storage-class journal, Snowflake native-pull boundary, and Snowflake Postgres
  bounded consumer transaction/run binding.
- Delta continuity, full reconciliation, replay, migration, rollback, threat,
  cost, and TDD contracts.

Exit only after offline fixtures reproduce identical inventories, state changes,
and evidence hashes without publishing a domain record.
