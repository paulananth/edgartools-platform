# Defer the existing SEC Bronze migration

Type: deferred follow-up
Status: deferred
Blocked by: production proof of the enrichment Source Artifact Archive

## Decision

Release 1 applies Temporary Bronze Stage and Source Artifact Archive behavior
only to new enrichment pipelines. Existing SEC pipelines keep ADR 0006's
durable Bronze contract.

A separate future Wayfinder map may plan the SEC migration after the enrichment
archive path has production evidence. That map must inventory every SEC source
family and prove artifact parity, deterministic replay, parser-upgrade recovery,
retention, storage and retrieval cost, rollback, and a no-loss cutover before it
may supersede ADR 0006.

Accepted by the user during the 2026-09-13 Wayfinder session.
