# Execute Required Relationship Production Bulk Load

Type: task
Status: open
Blocked by: none
Blocks: 06

## Task

Run the strict production bulk load at the frozen Release Data Watermark, repair every unresolved candidate, derive all required relationship types without caps, publish the graph generation, and commit the passing evidence artifact.

## Done when

- Candidate inventory and Bulk-Load Completion Ledger reconcile exactly.
- Failure, unresolved, quarantine, circuit-breaker-leftover, and unapproved-force counts are zero.
- A no-change rerun makes no SEC requests and produces identical silver/MDM semantic digests with zero new relationship identities.
- `EMPLOYED_BY` and `INSTITUTIONAL_HOLDS` pass exact MDM-to-hosted-graph parity and current-at-watermark checks.
- Named Warehouse, MDM, Graph, Release Data Operator, and Release Owner attestations are bound to the evidence artifact.

## Current disposition

`NO_GO` for **production bulk-load PASS** (as of 2026-07-18). See
`docs/release-readiness/required-relationship-bulk-load-preflight.json` and
`docs/release-readiness/ticket20-production-remediation-evidence.json`.

### Implementation path status (code / unit)

| Prerequisite | Status |
| --- | --- |
| Item 5.02 employment events (ticket 18) | **Landed** — parse + temporal `EMPLOYED_BY` application |
| Active-voice + spaCy extraction | **Landed** — PRs #154, #155 |
| Residual possessive / modifier gaps | **Landed** — PR #157 |
| Strict bulk-load + completion ledger code | **Landed** (tickets 16–17) |
| ADV / subsidiary / auditor ingestion | **Landed** (tickets 21–23) |

Parser note: Item 5.02 still has residual unresolved rate on real filings (~40%
on the pre-#157 survey). Further NLP gains are diminishing-returns; production
GO may need a **gate-policy decision** (accept bounded unresolved with repair
manifests) rather than waiting for 0% unresolved from rule-based NLP alone.

### Production execution blockers (this ticket — operator-owned)

These still block marking this ticket **resolved / GO**:

1. **Frozen production candidate manifest + reconciled completion ledger** for
   the release watermark window (2013-05-20 through watermark).
2. **Historical quarterly-index coverage** on production bronze (preflight found
   only 2026 index coverage — full fingerprint set cannot reconcile).
3. **Bound warehouse + MDM image digests** for the candidate commit on the
   strict bulk-load path (not ordinary `artifact_policy=skip` full-chain).
4. **Live execution + parity evidence** (`EMPLOYED_BY`, `INSTITUTIONAL_HOLDS`
   exact MDM↔graph; zero unresolved/quarantine/circuit leftovers).
5. **Named attestations** (Warehouse, MDM, Graph, Release Data Operator,
   Release Owner) on the evidence artifact.

### Operator path to close this ticket

1. Build/publish warehouse image from a fixed RC commit that includes #157+;
   bind digests into the evidence record.
2. Ensure bronze holds complete quarterly indexes for the coverage window.
3. Run `build_relationship_release_manifest` against production silver to freeze
   the candidate ledger.
4. Execute **strict** relationship bulk-load (not ordinary skip-policy chain);
   repair unresolved candidates with explicit `--force` repair manifests.
5. Derive/publish without caps; prove graph parity; commit
   `required_relationship_bulk_load_evidence.json` with attestations.
6. No-change rerun: zero SEC network, identical semantic digests.

Until steps 1–6 produce PASS evidence, leave status **open** / disposition
**NO_GO**. Do **not** start ordinary full-chain as substitute for Ticket 20
proof.
