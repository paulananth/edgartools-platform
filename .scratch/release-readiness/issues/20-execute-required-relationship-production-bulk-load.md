# Execute Required Relationship Production Bulk Load

Type: task
Status: open
Blocked by: none
Blocks: 06

## Task

Run the strict production bulk load at the frozen Release Data Watermark, repair every unresolved candidate, derive all required relationship types without caps, publish the graph generation, and commit the passing evidence artifact.

**Coverage policy (document-type specific):** do not freeze a single global
2013 start for every form. Per-type windows are defined in
`docs/release-readiness/relationship-source-coverage-by-document-type.md`
(e.g. Item 5.02 **8-K = 1 year** before watermark; 13F keeps XML floor
`2013-05-20`; proxy baseline + 5y history). Rebuild the candidate freeze under
those windows before GO.

## Done when

- Candidate inventory and Bulk-Load Completion Ledger reconcile exactly.
- Failure, unresolved, quarantine, circuit-breaker-leftover, and unapproved-force counts are zero.
- A no-change rerun makes no SEC requests and produces identical silver/MDM semantic digests with zero new relationship identities.
- `EMPLOYED_BY` and `INSTITUTIONAL_HOLDS` pass exact MDM-to-hosted-graph parity and current-at-watermark checks.
- Named Warehouse, MDM, Graph, Release Data Operator, and Release Owner attestations are bound to the evidence artifact.

## Current disposition

`IN_PROGRESS` / **NO_GO until terminal PASS** (as of 2026-07-18). Strict
production bulk-load is **running**. See
`docs/release-readiness/ticket20-production-remediation-evidence.json`.

### Live execution (started 2026-07-18)

| Field | Value |
| --- | --- |
| Execution | `ticket20-strict-20260718T013201Z` |
| ARN | `arn:aws:states:us-east-1:690839588395:execution:edgartools-prod-bronze-seed-silver-gold:ticket20-strict-20260718T013201Z` |
| Path | `release_mode=true` → StrictManifestCheck → **StrictBatchSilver** |
| Watermark | `2026-07-02` (coverage start `2013-05-20`) |
| Candidates | **528,829** across **15,941** CIKs (160 batches of 100) |
| Fingerprint | `ded1b9a2c3e14c3b1c30fd01e30924acac158014c4e9a114e18b76f47fbbf746` |
| Warehouse image | `sha256:1b654302ef7fbec4fcad90aa711c9ac6b211f8051252ef1d01c18c2db0b3a1d1` (`sha-8db4abf9868b`) |
| MDM image | `sha256:f97963824fbfa54a41151f37c548788c84add07e31c62e252b25d59457cbe118` |
| Data plane | `edgartools-prodb-bronze` / `edgartools-prodb-warehouse` (prodb runner roles) |
| Early signal | bronze catalog network fetches **0**; artifact pipeline started with `all_attachments` + `branch_b_deferred` |

### Implementation path status (code / unit)

| Prerequisite | Status |
| --- | --- |
| Item 5.02 employment events (ticket 18) | **Landed** — parse + temporal `EMPLOYED_BY` application |
| Active-voice + spaCy extraction | **Landed** — PRs #154, #155 |
| Residual possessive / modifier gaps | **Landed** — PR #157 |
| Strict bulk-load + completion ledger code | **Landed** (tickets 16–17) |
| ADV / subsidiary / auditor ingestion | **Landed** (tickets 21–23) |
| Warehouse image promote + prod deploy | **Done** (crane copy + deploy rev 23) |
| Frozen candidate manifest | **Done** (uploaded to prodb bronze) |
| Strict SF execution started | **Done** (in progress) |

### Still required for GO (do not mark resolved until all pass)

1. All 160 StrictBatchSilver batches succeed fail-closed.
2. ReconcileRelationshipRelease ledger reconciles with zero nonterminal outcomes.
3. MDM run/backfill/export/sync/verify without caps; exact `EMPLOYED_BY` +
   `INSTITUTIONAL_HOLDS` MDM↔graph parity.
4. No-change rerun: zero SEC network, identical semantic digests.
5. Commit `required_relationship_bulk_load_evidence.json` with terminal PASS
   counts and bound attestations.

Until those produce PASS evidence, leave status **open** / disposition
**NO_GO**. Do **not** treat ordinary skip-policy full-chain as Ticket 20 proof.

### Operator notes from this session

- Empty `edgartools-prod-*-690839588395` buckets are **not** the live store;
  deploy must target **prodb** buckets + `sec_platform_prodb_runner_*` roles.
- Docker layer push to prod ECR failed on corrupted `uv` binary; **crane copy**
  from dev→prod ECR succeeded for digest `1b654302…`.
