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

## Annotation (2026-07-27, `.scratch/adv-pipeline` map, ticket 01/02)

A 2026-07-24 session recorded `docs/release-readiness/adv-bulk-ingest-format-change-2026-07-24.md`,
which reported this ticket's parser as blocked by an SEC format change ("parser rewrite
needed"). **That finding was wrong and has been corrected** — see
`.scratch/adv-pipeline/issues/01-confirm-scope-of-iapd-format-change.md` (resolved
2026-07-24). The relational per-fund format this ticket implemented against was never
discontinued; the debugging session that reported "zero rows" had staged the wrong SEC
product (`sec.gov`'s aggregate-only Firm Roster CSV) instead of the correct one
(`adviserinfo.sec.gov`'s monthly `advFilingData` feed). `adv_bulk_ingest.py`'s regexes,
as implemented by this ticket's commits, were tested directly against a real
`advFilingData` archive and match every target file. **This ticket's implementation was
never broken in production** — do not read the 2026-07-24 blocker doc as evidence
otherwise. Full corrected picture, including the rolling-window and Firm Roster
cross-check decisions this finding fed into: `.scratch/adv-pipeline/map.md`.
