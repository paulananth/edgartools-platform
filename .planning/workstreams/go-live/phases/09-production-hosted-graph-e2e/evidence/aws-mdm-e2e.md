# AWS MDM Hosted Graph E2E Evidence - Phase 9 Plan 09-02

Date: 2026-06-25T04:20:32.130Z

Environment: production. This artifact records secret-safe evidence for the
production AWS bronze-from-existing-bronze, silver, MDM hosted graph, and gold
refresh path. It omits secret values, DSNs, raw Step Functions cause JSON, and
generated deployment JSON bodies.

## Final PASS - `bronze_seed_silver_gold`

The production `edgartools-prod-bronze-seed-silver-gold` state machine
completed successfully.

| Field | Result |
| --- | --- |
| Execution name | `bronze-seed-silver-gold-1782351277` |
| Input | `{"batch_size": 100}` |
| Started | 2026-06-25T01:34:39.738Z |
| Succeeded | 2026-06-25T04:20:32.130Z |
| Parent status | `SUCCEEDED` |
| BatchSilver map run | 81 succeeded, 0 failed, 0 aborted |

Validated task/runtime state:

- Warehouse task definition: `edgartools-prod-medium:19`
- Warehouse image digest: `sha256:036b7487...`
- MDM task definition: `edgartools-prod-mdm-medium:19`
- MDM image digest: `sha256:50af1f66...`
- BatchSilver command included both `--artifact-policy skip` and
  `--parser-policy skip`.
- Live BatchSilver `MaxConcurrency=2` is the setting proven by this evidence.
  A later source edit to `MaxConcurrency=5` was not part of the successful
  production run.

## Stage Evidence

| Stage | Evidence | Status |
| --- | --- | --- |
| `SeedFromBronze` | `seed_bronze_batches_started` and `seed_bronze_batches_completed` logged `cik_count=8006`, `batch_count=81`, and the production bronze CIK universe path for this run. | PASS |
| `BatchSilver` | 81 child executions completed. Example child ran on `edgartools-prod-medium:19` using the PR #95-capable warehouse image and skip policies. | PASS |
| No SEC refetch | CloudWatch search in `/aws/ecs/edgartools-prod-warehouse` from execution start returned 0 `sec_pull_started` events. | PASS |
| No parser fanout | CloudWatch search from execution start returned 0 `filing_artifact_pipeline_started` events. | PASS |
| Bronze/silver reuse | Batch logs include `parser_policy=skip`, `shard_manifest_missing_monolith_fallback`, and `silver_database_hydrated` from the existing production warehouse silver database. | PASS |
| Batch timing | 81 `bronze_capture_completed` events: min 1.240s, median 12.514s, max 30.742s, average 14.544s. | PASS |
| `MdmRun` | `mdm_command_completed` for `run`, exit code 0, duration 4,195,363 ms. Summary: `companies_processed=8006`, optional parser-derived entity counts 0. | PASS |
| `MdmBackfill` | `mdm_command_completed` for `backfill-relationships`, exit code 0, duration 18,789 ms; `backfilled=0`, `issuers_repaired=0`, `synced=0`. | PASS |
| `MdmSync` | `mdm_command_completed` for `sync-graph`, exit code 0, duration 12,715 ms; 10 graph nodes materialized and synced, 0 graph edges. | PASS |
| `MdmVerify` | `mdm_command_completed` for `verify-graph`, exit code 0, duration 35,140 ms. Native App installation, roles, compute pool, graph sample, graph info, BFS, WCC, node parity, and relationship parity all `ok`. | PASS |
| `GoldRefresh` | `gold_refresh` completed exit 0. Logs show `gold_build_completed`, `gold_storage_write_completed`, `gold_snowflake_export_completed`, and `gold_publish_completed`. | PASS |

Optional ADV and ownership rows were 0 by design for this run because
BatchSilver intentionally skipped parser fanout. The acceptance gate for
Blocker 4 was production chain correctness without a live SEC refetch, not
parser backfill.

## Gold Output Evidence

Gold refresh produced production-scale company and filing outputs:

| Output | Rows |
| --- | ---: |
| `dim_company` | 8006 |
| `dim_filing` | 4017296 |
| `fact_filing_activity` | 4017296 |
| `dim_date` | 11859 |
| `dim_form` | 481 |
| `dim_geography` | 121 |

Snowflake export evidence:

- Export counts included `company=8006`, `filing_activity=4017296`, and
  `filing_detail=4017296`.
- Manifest path:
  `s3://edgartools-prod-snowflake-export/warehouse/artifacts/snowflake_exports/manifests/workflow_name=gold_refresh/business_date=2026-06-25/run_id=bronze-seed-silver-gold-1782351277/run_manifest.json`

## Timeline

| Stage | Entered | Succeeded |
| --- | --- | --- |
| `SeedFromBronze` | 2026-06-25T01:34:39.764Z | 2026-06-25T01:36:14.224Z |
| `BatchSilver` map run | 2026-06-25T01:36:14.381Z | 2026-06-25T03:03:57.678Z |
| `MdmRun` | 2026-06-25T03:03:57.766Z | 2026-06-25T04:14:52.852Z |
| `MdmBackfill` | 2026-06-25T04:14:52.877Z | 2026-06-25T04:16:08.327Z |
| `MdmSync` | 2026-06-25T04:16:08.343Z | 2026-06-25T04:17:15.035Z |
| `MdmVerify` | 2026-06-25T04:17:15.049Z | 2026-06-25T04:18:42.867Z |
| `GoldRefresh` | 2026-06-25T04:18:42.882Z | 2026-06-25T04:20:32.082Z |

## Superseded Failure Evidence

Earlier Phase 9 attempts found real blockers and were intentionally left as
diagnostic history in `STATE.md` and `TODOS.md`. They are superseded by the
final pass above:

- Legacy Neo4j/API-key secret injection in MDM ECS task definitions.
- Prod bucket-name mismatch and empty prod warehouse path.
- Lack of a production bootstrap path from an existing bronze snapshot.
- BatchSilver attempting live SEC/parser work instead of reusing bronze.
- MDM task runtime using the wrong image/default runtime.
- MDM preflight requiring nonempty optional parser-derived tables despite
  intentionally skipped parser fanout.

The final pass did not populate or require `edgartools-prod/mdm/neo4j` or
`edgartools-prod/mdm/api_keys`.
