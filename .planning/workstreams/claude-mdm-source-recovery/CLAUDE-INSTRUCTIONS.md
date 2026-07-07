# Claude Instructions: MDM Relationship Source Recovery

## Current Repository State

- Start from `origin/main` at or after `8cff30c` (`Merge pull request #122 from paulananth/claude/neo4j-app-v2-api`).
- PR #119 (`codex/data-architecture-fixes`) is merged, not open. It merged on 2026-07-06 at 17:09 UTC.
- The current Codex checkout that wrote this handoff was detached at `5403b02`; do not continue from that detached state.
- `.planning/active-workstream` currently names `fundamental-factors-v2`. Do not edit that workstream unless the user explicitly assigns it to Claude.
- Generated/local deployment artifacts may be dirty in the shared checkout:
  - `infra/aws-prodb-application.json`
  - `infra/aws-prod-application.json`
  - `infra/snowflake/sql/prod_native_pull_handshake.json`
  These are operator/generated artifacts. Inspect if needed, but do not commit them.

Recommended setup:

```bash
git fetch --all --prune
git worktree add -b claude/mdm-source-recovery ../edgartools-platform-claude-mdm-source-recovery origin/main
cd ../edgartools-platform-claude-mdm-source-recovery
git status --short
cat .planning/active-workstream
```

## What Is Already Fixed

Do not spend time re-solving these unless new evidence contradicts current `main`:

- Branch B fundamentals now writes the canonical SEC silver database at `silver/sec/silver.duckdb`.
- `bootstrap-fundamentals` hydrates and publishes the unified silver DuckDB through `WAREHOUSE_STORAGE_ROOT`.
- `bootstrap-fundamentals` resolves SEC identity through the shared `EDGAR_IDENTITY` path.
- `load_history` sequences Branch B modes after Branch A because they share the same DuckDB artifact.
- The AWS deploy script defaults `MDM_SILVER_DUCKDB` to `s3://<warehouse-bucket>/warehouse/silver/sec/silver.duckdb`.
- Snowflake hosted graph sync and verify code includes the PR #122 Neo4j Graph Analytics app API update.

## Confirmed Live Findings To Carry Forward

- MDM graph materialization was not the source of the remaining zero counts:
  - graph nodes materialized: 15,285
  - graph edges materialized: 1,117
  - MDM-to-graph SQL parity: OK
- Strict Native App verification still failed because Snowflake returned no available compute pools.
- Populated relationship types: `COMPANY_HOLDS`, `HOLDS`, `IS_INSIDER`, `ISSUED_BY`.
- Still zero from available sources: `AUDITED_BY`, `EMPLOYED_BY`, `HAS_PARENT_COMPANY`, `INSTITUTIONAL_HOLDS`, `IS_ENTITY_OF`, `IS_PERSON_OF`, `MANAGES_FUND`.
- `parse-adv-bronze --limit 20` found 0 parseable ADV artifacts and logged `missing_primary_attachment`.
- `sec_adv_filing` and `sec_adv_private_fund` remain empty, so adviser/fund relationships cannot load from current data.
- An ECS `bootstrap-fundamentals --mode entity-facts` run succeeded for 15 CIKs but used a stale deployed image. It wrote `silver/fundamentals/shard-0.duckdb`, which MDM does not read.
- A local unified `entity-facts` load was interrupted before publish/upload at the user's request. Do not assume it changed S3.

## Primary Work Items

### 1. Redeploy current unified fundamentals code

The fastest path to unblock `AUDITED_BY` is deploying a current warehouse image and rerunning a bounded entity-facts load that publishes to `warehouse/silver/sec/silver.duckdb`.

Use the AWS-only deploy path:

```bash
bash infra/scripts/deploy-aws-application.sh \
  --env prod \
  --aws-profile sec_platform_deployer \
  --aws-region us-east-1 \
  --build-image \
  --publish-mode linux \
  --enable-mdm \
  --mdm-database-source snowflake-postgres \
  --output-file infra/aws-prod-application.json
```

Keep `infra/aws-prod-application.json` uncommitted. After deploy, run a bounded production entity-facts execution and verify `sec_financial_fact` rows appear in `silver/sec/silver.duckdb`, not `silver/fundamentals/shard-0.duckdb`.

Acceptance:

- Deployed task definition image digest corresponds to current `main`.
- Entity facts publish logs include `silver_database_uploaded` with `silver/sec/silver.duckdb`.
- `mdm derive-relationships --relationship-type AUDITED_BY` inserts nonzero rows when auditor source facts are present.

### 2. Resolve missing ADV source artifacts

The remaining adviser/fund relationship paths are blocked upstream. The registry rows exist, but their primary attachments are missing from bronze, so parsing cannot produce `sec_adv_filing` or `sec_adv_private_fund`.

Start by reproducing the current failure:

```bash
uv run edgar-warehouse parse-adv-bronze --limit 20
```

Then trace where ADV registry rows point for primary attachment storage. Relevant files:

- `edgar_warehouse/application/commands/parse_adv_bronze.py`
- `edgar_warehouse/application/warehouse_orchestrator.py`
- `edgar_warehouse/parsers/adv.py`
- `edgar_warehouse/infrastructure/dataset_path_catalog.py`
- `edgar_warehouse/config/warehouse_paths.properties`

Acceptance:

- `parse-adv-bronze` finds parseable primary attachments.
- `sec_adv_filing` and `sec_adv_private_fund` become nonzero.
- Adviser/fund relationships derived from ADV sources become nonzero if source data supports them.

### 3. Treat Snowflake Native App compute pool absence as an environment blocker

Graph sync and SQL parity already worked. If strict verify still reports no available compute pools after PR #122, do not rewrite sync logic without new evidence.

Check:

```bash
export SNOW_CONNECTION=snowconn
uv run --extra snowflake edgar-warehouse mdm verify-graph --native-app-compute-pool CPU_X64_XS
```

If Snowflake still returns no pool selectors, capture the failure as a Snowflake Native App/environment readiness issue. Do not mark it as an MDM-to-graph parity failure.

Acceptance:

- SQL parity remains OK.
- Native App app-role/grant checks use the current PR #122 API path.
- Compute pool failure is either fixed by Snowflake environment setup or documented as an external blocker with exact command/date evidence.

## Verification Commands

Use `uv`, not bare `pip` or bare `dbt`.

```bash
uv run pytest tests/mdm/test_cli_snowflake_graph.py tests/mdm/test_snowflake_graph_migration.py
uv run pytest tests/unit tests/architecture
uv run edgar-warehouse --help
python -c "from edgar_warehouse.cli import main; print('OK')"
```

For Snowflake dev/local DDL or graph verification, use:

```bash
export SNOW_CONNECTION=snowconn
```

Do not use `YG91578` or `edgartools-dev` for dev Snowflake verification.

## Safety Notes

- Keep work AWS-focused.
- Do not add non-AWS storage, workflow, registry, deployment, or secret-management paths.
- Do not commit `.tfvars`, generated Terraform state, generated application JSON, image digests from operator runs, or secrets.
- Preserve loader idempotency. Default loaders should skip existing SEC files; repair paths require explicit `--force`.
- Do not change the ownership parser import path:

```python
from edgar.ownership import Ownership
```
