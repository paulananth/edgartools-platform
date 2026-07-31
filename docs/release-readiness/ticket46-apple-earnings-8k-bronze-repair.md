# Ticket 46: Apple earnings-8-K bronze repair

## Decision

Do not add a normalization exception to the shared immutability guard.
Ticket 44's one-byte conclusion was insufficient for the current production
image: a live comparison of accession `0000320193-19-000073` found its current
gateway output is 109 bytes shorter than the migrated object and first differs
at byte 1. A scoped one-byte normalization is therefore not a valid repair.

## Execution evidence

- 2026-07-31: dry-run read all 45 objects. Every object had exactly one
  terminal `LF`; total size was 2,011,374 bytes and the proposed replacement
  total was 2,011,329 bytes.
- 2026-07-31: the previously proposed one-byte normalization was applied to
  the 45 keys only after a complete dry run and current-version ETag checks.
  A re-registration run then showed 18 immutable conflicts remained.
- The original version IDs and SHA-256 values were restored immediately with
  a current replacement-version precondition. Independent current-object reads
  verified **45/45** restored SHA-256 values.

The immutable guard remains unchanged. No parser run follows this failed
repair attempt. A new read-only investigation must establish the actual
current-image byte contract and a safe equivalence rule, if one exists.
