# Claude Instructions: Data Architecture Inconsistency Fixes

## Context

Codex reviewed `docs/data-architecture.md` against the current AWS-focused implementation after syncing `codex/data-architecture` onto `origin/main`. The review found several mismatches between the documented data architecture, the deployed Step Functions shape, and the runtime command boundaries.

Work in a separate Claude branch/worktree. Do not edit `.planning/workstreams/fundamental-factors-v2/` unless the user explicitly assigns that active workstream to Claude. Keep the AWS path only; do not add non-AWS deployment, registry, storage, workflow, or secret-management paths.

## Primary Goal

Make the implementation and architecture contract agree for:

- Branch B fundamentals source reads and writes.
- MDM tracked-universe seeding and window computation.
- MDM export and Snowflake graph sync ordering.
- 13F automation status.
- SEC identity/client usage for direct SEC calls.

Update `docs/data-architecture.md` only after the runtime contract is fixed or explicitly documented.

## Issues To Fix

### 1. Branch B fundamentals has an unresolved silver read/write boundary

Observed files:

- `docs/data-architecture.md`
- `edgar_warehouse/application/commands/bootstrap_fundamentals.py`
- `edgar_warehouse/application/workflows/fundamentals_ingest.py`
- `infra/scripts/deploy-aws-application.sh`

The doc says Branch B reads cached filing artifacts and writes to `silver/fundamentals`. The command opens only the fundamentals shard, then `run_bootstrap_fundamentals_per_filing()` and `run_bootstrap_thirteenf()` query `sec_company_filing`, `sec_filing_attachment`, and `sec_raw_object` through that same DB handle.

This is inconsistent because those source tables are produced by the ownership/SEC silver path, not the fundamentals writer shard. In `load_history`, Branch A and Branch B currently run in parallel, so Branch B also races the source artifact production for first-time loads.

Recommended fix:

- Introduce an explicit Branch B source reader for SEC/ownership silver tables while keeping writes isolated to `silver/fundamentals`.
- Decide whether Branch B per-filing/13F should use only previously cached artifacts or run after Branch A completes for the same CIK windows.
- If same-run artifacts are required, change `load_history` so Branch B per-filing/13F happens after Branch A artifact capture, or add an explicit artifact hydration stage before Branch B.
- Add regression coverage proving Branch B can read filing/attachment/raw-object rows from the source silver namespace while writing only fundamentals outputs.

Acceptance criteria:

- A fresh first-time load does not silently scan zero Branch B filings because the fundamentals shard lacks source tables.
- Branch B writer concurrency remains safe.
- The architecture doc states the source-reader/writer boundary clearly.

### 2. MDM seeding semantics are mixed up

Observed files:

- `docs/data-architecture.md`
- `infra/scripts/deploy-aws-application.sh`
- `edgar_warehouse/application/warehouse_orchestrator.py`
- `edgar_warehouse/mdm/cli.py`

The deployed `load_history` comments say `SeedUniverse` enrolls CIKs into MDM, but the state invokes warehouse `seed-universe`, not `edgar-warehouse mdm seed-universe`. Warehouse `seed-universe` writes SEC reference data and CIK window artifacts; MDM `seed-universe` is the command that calls edgartools ticker data and upserts `mdm_entity` / `mdm_company`.

Recommended fix:

- Separate the two concepts in code comments, state-machine names, and docs:
  - warehouse reference/window seed
  - MDM tracked-universe seed
- Make `load_history` either run `mdm seed-universe` before window computation or document it as a hard prerequisite.
- Verify the tracking-status contract end to end. In particular, make sure the seed status used by `mdm seed-universe` matches the filters used by `compute-windows`, `bootstrap-next`, and `bootstrap-fundamentals` (`active` vs `bootstrap_pending`).

Acceptance criteria:

- A new environment has a deterministic path from empty MDM tables to runnable `load_history`.
- Step Functions comments and command arrays describe the same command.
- Runtime error messages guide the operator to the correct seed command.

### 3. MDM graph sync can run without refreshing the Snowflake MDM mirror

Observed files:

- `docs/data-architecture.md`
- `infra/scripts/deploy-aws-application.sh`
- `edgar_warehouse/mdm/cli.py`
- `edgar_warehouse/mdm/snowflake_graph.py`

The doc groups `mdm export`, `mdm sync-graph`, and `mdm verify-graph`, but deployed MDM chains call `mdm run`, `mdm backfill-relationships`, `mdm sync-graph`, and `mdm verify-graph` without `mdm export`.

`sync-graph` materializes graph tables from Snowflake `MDM_*` mirror tables. If the mirror is stale or missing, graph sync can produce stale output or fail independently of the freshly updated runtime MDM database.

Recommended fix:

- Add `mdm export` before `mdm sync-graph` in workflows that expect Snowflake graph tables to reflect the just-completed MDM run.
- Alternatively, change `sync-graph` to refresh/export the required MDM mirror as part of the command, but keep the behavior explicit.
- Add a test or generated-state-machine assertion proving `mdm export` precedes `mdm sync-graph` where required.

Acceptance criteria:

- After an MDM run/backfill, Snowflake graph sync reads current MDM rows.
- `verify-graph` compares against the same MDM snapshot that was exported.

### 4. 13F is documented as Branch B but is not automated in `load_history`

Observed files:

- `docs/data-architecture.md`
- `infra/scripts/deploy-aws-application.sh`
- `edgar_warehouse/application/commands/bootstrap_fundamentals.py`
- `edgar_warehouse/application/workflows/fundamentals_ingest.py`

`bootstrap-fundamentals --mode thirteenf` exists, but the `load_history` Branch B definition only runs per-filing and entity-facts maps.

Recommended fix:

- Either add a `thirteenf` map to the appropriate workflow or mark 13F as manual/backfill-only in the architecture doc.
- If automated, apply the same source-reader fix from issue 1 because 13F also reads filing and attachment metadata.

Acceptance criteria:

- The doc does not imply automated 13F coverage unless a deployed workflow actually runs it.
- If automated, generated Step Functions include the 13F mode and tests cover the state shape.

### 5. Entity facts uses a separate SEC identity and raw HTTP path

Observed files:

- `edgar_warehouse/application/commands/bootstrap_fundamentals.py`
- `edgar_warehouse/application/workflows/fundamentals_ingest.py`
- `edgar_warehouse/infrastructure/sec_client.py`

`bootstrap-fundamentals` reads `SEC_EDGAR_IDENTITY` with a default, while the rest of the warehouse runtime centers on `EDGAR_IDENTITY`. Entity facts also fetches companyfacts with `urllib` directly rather than the shared SEC client path.

Recommended fix:

- Prefer the shared SEC client and `EDGAR_IDENTITY` validation path.
- If `SEC_EDGAR_IDENTITY` must remain as compatibility fallback, document it and make the precedence explicit.
- Consider persisting companyfacts responses as bronze raw/audit objects if entity facts is a governed warehouse input.

Acceptance criteria:

- Direct SEC traffic follows the same identity/rate-limit/client contract as the rest of the runtime.
- Runtime docs and errors mention one primary identity variable.

## Suggested Verification

Run the narrowest useful tests first, then broaden:

```bash
uv run pytest tests/unit tests/architecture
```

Add or update targeted tests for:

- Branch B reading source SEC silver while writing fundamentals silver.
- `load_history` state-machine command order for MDM seeding, MDM export, graph sync, and optional 13F.
- SEC identity precedence for `bootstrap-fundamentals`.

For any generated AWS state-machine changes, inspect the generated JSON before deployment. Do not apply Terraform or deploy AWS components unless the user explicitly asks.

## Documentation Update

After implementation, update `docs/data-architecture.md` so each pipeline is marked as one of:

- automated in deployed AWS workflows
- required prerequisite
- manual/backfill-only
- optional validation/export

Keep direct SEC vs edgartools-mediated source attribution precise.
