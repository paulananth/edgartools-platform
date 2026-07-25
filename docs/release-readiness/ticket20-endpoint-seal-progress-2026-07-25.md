# Ticket 20 progress — EMPLOYED_BY endpoint seal (2026-07-25)

## Root cause (confirmed from failed candidate)

Failed execution:
`ticket20-strict-q1y-resume-eef3f5b-20260725T0156Z` at `StrictMdmVerifyCandidate`.

Observed:

| Check | Result |
| --- | --- |
| Node identity/property match | OK |
| Relationship identity/property match | OK |
| `person` MDM active / graph nodes | **0 / 0** |
| `EMPLOYED_BY` MDM / graph edges | **13403 / 13403** |
| `missing_graph_edge_endpoints` | samples with `missing_source_node=true` |

Cause: `_ensure_proxy_person` (and other stub creators) inserted Postgres
entities **without** `mdm_change_log` rows. Relationships export via
`graph_synced_at` independently, so EMPLOYED_BY edges landed in the Snowflake
MDM mirror while person nodes never did. Verification correctly fail-closed.

## Code fix (PR #258, `850ea34`)

1. Stub creators write `mdm_change_log` on create.
2. `export_pending_relationships` seals source/target endpoints before
   stamping `graph_synced_at`.
3. `mdm export` always runs `export_active_relationship_endpoints` so already-
   synced edges still pull missing person/company nodes into the mirror.

## Production deploy for this fix

| Item | Value |
| --- | --- |
| Commit | `850ea3473c249afbb35432d391bdda9b27c4b2aa` |
| Warehouse image | `…/edgartools-prod-warehouse@sha256:94f3766cbf620ab048d6ba0ec03424b4e3b0472b1cd3fbd937103f71403e5339` |
| MDM image | `…/edgartools-prod-mdm@sha256:c1b0f72a2a98dd81590ed4b1a7872c36898c72bbe59f89f47b3b3729f4cc00f1` |
| Task defs | small `65` medium `70` large `65` mdm-small `58` mdm-medium `58` |
| Roles | `sec_platform_prod_runner_*` |
| Remaining batches | **0** (all 108 batch_done markers present) |
| Remaining key | `…/candidate_batches_remaining-ticket20-endpoint-seal.jsonl` (empty) |

## New execution (never redrive failed name)

- Name: `ticket20-strict-endpoint-seal-850ea34-20260725T130457Z`
- ARN: `arn:aws:states:us-east-1:690839588395:execution:edgartools-prod-bronze-seed-silver-gold:ticket20-strict-endpoint-seal-850ea34-20260725T130457Z`
- Freeze fingerprint: `61be5eaeebc99c7eb9bf1e5a5e2c67076619bcc28b19ece715a7c2ebb175d852`
- Watermark: `2026-07-02`
- Empty map: `StrictBatchSilver` succeeded in <1s (0 remaining batches)

## Still required before Ticket 20 PASS / GO

1. Candidate verify + activate + active Native App verify + gold refresh succeed.
2. Unchanged-watermark no-change validation.
3. Assemble secret-free completion evidence; do not self-declare production GO.
