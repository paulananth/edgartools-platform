# Implement Authoritative Form ADV Private-Fund Ingestion

Type: task
Status: resolved
Blocked by: 13, 16
Blocks: 20, 06

## Task

Implement the approved adviser-fund source contract: capture official IAPD Part 1 bulk artifacts, reconstruct the effective filing set, ingest Schedule D Sections 7.B.(1) and 7.B.(2), model CRD/PFID identity and lineage, and derive temporal `MANAGES_FUND` relationships without caps or name-only identity.

## Done when

- The official bulk snapshot and current-compilation control are acquired immutably with schema, digest, watermark, and latest-filing reconciliation evidence.
- The native relational importer covers all required linked tables, removes the 100-fund cap, and records filing ID, CRD, PFID, section, action/cross-reference, source hash, and parser version.
- Latest-effective filing reconstruction is deterministic and amendments, deletions, withdrawals, master-feeder rows, and multiple advisers per PFID obey the approved contract.
- Every candidate has one terminal ledger outcome; unresolved, quarantined, exhausted-retry, missing, and silently skipped counts are zero.
- Adviser and fund entities resolve by CRD and PFID, temporal relationship versions replay idempotently, and exact expected-to-MDM-to-hosted-graph key/property parity passes.
- Focused parser, schema, derivation, retry, idempotency, and parity tests pass and their evidence is bound to the release candidate.

## Contract

[`docs/release-readiness/adviser-fund-source-contract.md`](../../../docs/release-readiness/adviser-fund-source-contract.md)

## Resolution

Implemented by commits `ddc24d3`, `846d648`, and `4f4e1a9`: the deployed manifest importer
validates immutable official IAPD bulk archives, imports IA/ERA base plus Schedule D
7.B.(1)/(2) without a fund cap, preserves FilingID/CRD/PFID/action/cross-reference
lineage, reconstructs the latest effective filing per CRD, resolves funds by PFID,
and derives evidence-bound temporal `MANAGES_FUND` relationships. Production
watermark acquisition, zero-unresolved reconciliation, and hosted-graph parity are
the execution evidence owned by ticket 20.
