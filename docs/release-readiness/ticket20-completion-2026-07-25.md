# Ticket 20 completion — 2026-07-25

## Disposition

| Field | Value |
| --- | --- |
| Strict production chain | **SUCCEEDED** |
| Bulk-load evidence | **PASS** |
| Graph candidate verify + activate + active verify | **PASS** |
| Gold refresh | **PASS** |
| In-chain no-change checks | **PASS** |
| **Production GO** | **Not self-declared** — operator / Release Owner decision |

## Execution

- **Name:** `ticket20-strict-endpoint-seal-850ea34-20260725T130457Z`
- **ARN:** `arn:aws:states:us-east-1:690839588395:execution:edgartools-prod-bronze-seed-silver-gold:ticket20-strict-endpoint-seal-850ea34-20260725T130457Z`
- **Window:** 2026-07-25 09:05–14:21 EDT (~5.3 h)
- **Commit / images:** `850ea34` · warehouse `sha256:94f3766c…` · MDM `sha256:c1b0f72a…`

## Freeze (unchanged watermark)

| Field | Value |
| --- | --- |
| Watermark | `2026-07-02` |
| Fingerprint | `61be5eaeebc99c7eb9bf1e5a5e2c67076619bcc28b19ece715a7c2ebb175d852` |
| Candidates | 20,833 / 10,792 CIKs / 108 batches |
| 13F | `[2026-04-02, 2026-07-02]` |
| Proxy | `[2025-07-02, 2026-07-02]` latest-in-band |
| Item 5.02 8-K | `[2024-07-02, 2026-07-02]` |

## Bulk-load ledger

| Status | Count |
| --- | ---: |
| applicable_loaded | 14,280 |
| not_applicable | 5,925 |
| unresolved_accepted (Item 5.02) | 628 (9.03% of 6,952 Item 5.02 candidates) |
| failure / quarantine / force | **0** |

Evidence:

- `s3://edgartools-prod-warehouse-690839588395/warehouse/release-evidence/ticket20-strict-endpoint-seal-850ea34-20260725T130457Z/required_relationship_bulk_load_evidence.json`
- Local: `docs/release-readiness/ticket20-required-relationship-bulk-load-evidence.json`
- Machine package: `docs/release-readiness/ticket20-completion-evidence-2026-07-25.json`

## Graph (endpoint fix)

| Metric | Prior failed candidate | This generation |
| --- | ---: | ---: |
| Person nodes | **0** | **5,892** |
| EMPLOYED_BY edges | 13,403 (broken endpoints) | **19,147** (parity OK) |
| missing_graph_edge_endpoints | samples present | **[]** |
| Total nodes / edges | — | 193,063 / 157,732 |
| Active Native App GRAPH_INFO / BFS / WCC | — | **ok** |

Active generation: `ticket20-strict-endpoint-seal-850ea34-20260725T130457Z` (activated).

## No-change validation (in-chain)

| Check | Result |
| --- | --- |
| Remaining batches | **0** → StrictBatchSilver empty map, **zero SEC tasks** |
| StrictMdmBackfill then StrictMdmIdempotency | both `backfilled: 0` |
| Sync then SyncIdempotency | identical 193,063 nodes / 157,732 edges |
| Silver checksum | `e409b8e71fd85d1ea227da36d467cef7` |

## Approved PASS phrase (bound)

```text
Required relationship sources for EMPLOYED_BY and INSTITUTIONAL_HOLDS are
bulk-load complete for agent windows at watermark 2026-07-02
(fingerprint 61be5eaeebc99c7eb9bf1e5a5e2c67076619bcc28b19ece715a7c2ebb175d852):
  13F [2026-04-02, 2026-07-02];
  proxy [2025-07-02, 2026-07-02] (latest-in-band baseline only);
  Item 5.02 / ambiguous 8-K [2024-07-02, 2026-07-02] complete EXCEPT for
  628 enumerated unresolved candidates (9.03% of the Item 5.02 8-K candidate
  inventory), accepted by the Release Owner as a known, bounded gap —
  not claimed complete.
```

## Residual gaps (not Ticket 20 hard-fail for this package)

1. **Insider coverage** not bound into SM reconcile (`--insider-coverage`) — Ticket 21.
2. **INSTITUTIONAL_HOLDS / IS_INSIDER / security nodes** empty on this generation — reported; non-blocking per Release Owner 2026-07-19 for Ticket 20 launch decision.
3. Item 5.02 **628** unresolved accepted — enumerated; bounded exception.

## Operator next step for GO

Review this package + S3 evidence + active graph generation, then record Release Owner GO/NO_GO. Do not treat this agent note as GO authorization.
