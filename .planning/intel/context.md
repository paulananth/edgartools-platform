# Project Context
# Source: synthesized from 11 DOC-type classified documents
# Each topic carries source: attribution.

---

## Topic: Domain

The EdgarTools Platform is a data platform for SEC EDGAR built on the edgartools PyPI package.
It extracts SEC EDGAR filings data for a universe of public companies and investment advisers
across all major SEC form types (10-K, 10-Q, Forms 3/4/5 ownership, ADV investment adviser).
The goal is to deliver structured, business-ready financial data to analytics dashboards and
downstream consumers.

source: CLAUDE.md, README.md

---

## Topic: Data Layer Architecture

Four layers, each with distinct ownership:

Bronze: Raw Parquet files written by edgar-warehouse to S3. One file per filing/entity,
partitioned by form type and date. Never mutated. Source of truth.
  Location: s3://edgartools-<env>-bronze/
  Owner: edgar-warehouse runtime (runtime.py, artifacts.py)

Source: Snowflake EDGARTOOLS_SOURCE schema. External stage plus tables auto-refreshed from S3
via Snowflake native S3 pull. Read-only raw layer.
  Location: Snowflake EDGARTOOLS_DEV.EDGARTOOLS_SOURCE
  Owner: Terraform (storage integration, manifest pipe, refresh task)

Silver: Cleaned, typed, deduplicated records. Applied inside the warehouse container using
DuckDB as an intermediate processing engine. Not persisted to an external store between stages.
  Location: DuckDB intermediate (in-container)
  Owner: edgar_warehouse/silver.py

Gold: Business-ready tables in Snowflake EDGARTOOLS_GOLD. Managed by dbt as dynamic tables
with TARGET_LAG = DOWNSTREAM. 9 business tables + 1 status view.
  Location: Snowflake EDGARTOOLS_DEV.EDGARTOOLS_GOLD
  Owner: dbt project (infra/snowflake/dbt/edgartools_gold/)

source: CLAUDE.md, README.md, infra/snowflake/dbt/edgartools_gold/README.md

---

## Topic: Gold Layer Tables

The nine published business-facing gold tables:
1. COMPANY — company master with CIKs, tickers, SIC, state of incorporation
2. FILING_ACTIVITY — monthly filing volume and form type distribution
3. OWNERSHIP_ACTIVITY — insider transaction records (Forms 3/4/5)
4. OWNERSHIP_HOLDINGS — insider position holdings
5. ADVISER_OFFICES — investment adviser office locations (geography not yet plottable)
6. ADVISER_DISCLOSURES — ADV form disclosures for investment advisers
7. PRIVATE_FUNDS — private fund AUM and adviser relationships
8. FILING_DETAIL — individual filing metadata
9. TICKER_REFERENCE — ticker-to-CIK mapping

Plus: EDGARTOOLS_GOLD_STATUS — provider-neutral view of refresh status (reads SERVING_REFRESH_STATUS)

source: infra/snowflake/dbt/edgartools_gold/README.md, CLAUDE.md

---

## Topic: ETL Runtime

The edgar-warehouse Python CLI (entry point: edgar_warehouse/cli.py) is the ETL runtime.
It runs in AWS ECS Fargate containers and performs:
1. SEC EDGAR API fetch — internal loader code (_download_sec_bytes) handles raw SEC downloads
   and bronze persistence. edgartools is NOT used for raw downloads.
2. Bronze write — Parquet files written to S3 by runtime.py and artifacts.py
3. Silver transform — silver.py cleans and types records; DuckDB used as intermediate engine
4. Ownership parsing — edgartools enters here: Ownership.from_xml() for Forms 3/4/5
5. ADV parsing — local parser in edgar_warehouse/parsers/adv.py
6. Gold export — gold.py reads complete silver DuckDB, builds gold tables, writes manifests
7. Snowflake refresh — SNOWFLAKE_RUN_MANIFEST_TASK picks up manifests within ~1 minute

source: CLAUDE.md, README.md, AGENTS.md

---

## Topic: edgartools Package Usage

edgartools enters the warehouse runtime at the ownership parsing step only — after the primary
filing artifact has already been downloaded and stored in bronze. It is not used for raw SEC
downloads or bronze writes.

Current runtime usage:
  - edgar.ownership.Ownership — parses Forms 3, 4, 5 via Ownership.from_xml(content)
  - edgar.filing — filing metadata and document fetching in runtime.py
  - edgar.entity — company/entity resolution
  - edgar.xbrl — financial statement parsing in batch scripts (scripts/batch/)

The standalone dashboard (examples/dashboard/) does not import edgartools; it reads already-
modeled Snowflake gold tables directly.

source: README.md, CLAUDE.md, AGENTS.md

---

## Topic: MDM (Master Data Management)

MDM owns the canonical company/adviser/person/fund registry and the tracked company universe
(the list of CIKs the warehouse processes).

Components:
  - PostgreSQL (prod) or external SQL (non-AWS path) — relational MDM store
  - Neo4j AuraDB — graph layer for entity relationships (IS_INSIDER, MANAGES_FUND, etc.)
  - MDM CLI — edgar-warehouse mdm subcommands for migrate, seed-universe, run, sync-graph,
    verify-graph, backfill-relationships, check-connectivity

MDM runs as its own Docker image (edgartools-dev-mdm, built from Dockerfile.mdm-neo4j).
In the phased pipeline, MDM runs in Stage 2 (sequential) after all bronze + silver batch tasks
complete, so entity resolution sees the full silver dataset.

source: edgar/ai/skills/platform/pipeline-setup.md, docs/neo4j.md, CLAUDE.md

---

## Topic: AWS Infrastructure

Primary runtime infrastructure:

ECS Fargate — runs edgar-warehouse CLI tasks for bronze, silver, gold stages
ECR — four repositories:
  - edgartools-dev-warehouse-deps (base with locked deps)
  - edgartools-dev-warehouse (warehouse ECS tasks)
  - edgartools-dev-mdm-deps (MDM base with locked deps)
  - edgartools-dev-mdm (MDM ECS tasks and API)
S3 — two separate buckets: bronze bucket and warehouse/export bucket
Step Functions — state machines for phased pipeline, targeted resync, gold refresh, daily incremental
Secrets Manager — secret containers for EDGAR identity, Neo4j credentials, MDM config
SNS — topic container for manifest notifications

IAM model: Three principal classes
  1. Admin profile — applies Terraform roots
  2. sec_platform_deployer — deploys images, task definitions, state machines, starts executions
  3. Service-assumed runner roles (sec_platform_runner_execution/task/step_functions)

source: infra/terraform/README.md, AGENTS.md, edgar/ai/skills/platform/pipeline-setup.md

---

## Topic: Snowflake Infrastructure

Snowflake is the analytics target. Provisioning is split across Terraform, dbt, and access roots.

Terraform (infra/terraform/snowflake/) provisions:
  - EDGARTOOLS_DEV database and schemas (EDGARTOOLS_SOURCE, EDGARTOOLS_GOLD)
  - Refresh and reader warehouses
  - Storage integration, export stage, file formats, source mirror tables, manifest pipe,
    manifest stream, source-side load wrapper, public gold refresh wrapper, task

dbt (infra/snowflake/dbt/edgartools_gold/) manages:
  - Nine business-facing gold dynamic tables and EDGARTOOLS_GOLD_STATUS view

access/snowflake/ (separate Terraform root) manages:
  - Roles and grants

The deploy-snowflake-stack.sh script coordinates the full E2E deploy:
AWS Terraform → AWS access → Snowflake provisioning → trust narrowing → Snowflake access → dbt → Streamlit

source: infra/terraform/snowflake/README.md, infra/snowflake/sql/README.md,
        infra/snowflake/dbt/edgartools_gold/README.md

---

## Topic: Dashboards

Two dashboard variants:

1. Streamlit-in-Snowflake (infra/snowflake/streamlit/streamlit_app.py)
   — Minimal 2-tab app (Summary / Company Details)
   — Lives inside Snowflake, uses get_active_session()
   — Deployed via Snowflake Streamlit artifact upload (not Terraform)

2. Standalone Streamlit dashboard (examples/dashboard/edgar_universe_dashboard.py)
   — Six sections: Overview, World & US Map, Industry & Entity, Filing Activity,
     Ownership & Funds, Company Lookup
   — Reads EDGARTOOLS_GOLD via Snowflake connector
   — Requires Python 3.11+, ~/.snowflake/config.toml, role with SELECT on EDGARTOOLS_GOLD.*
   — All queries cached for 1 hour

Caveats: No lat/lon in gold layer; maps are country/state granularity only.
ADVISER_OFFICES.geography_key is an unresolved surrogate; adviser office map section not yet
plottable.

source: examples/dashboard/README.md, CLAUDE.md

---

## Topic: Phased Pipeline Variants

Step Function state machines for different load scenarios:

bootstrap_phased — canonical path for >= 10 companies (three stages, ~15 min for 100 companies)
targeted_resync — single company debug or resync
gold_refresh — rebuild gold from existing silver only
bootstrap_recent_10 — recent filings only (fast, for incremental checks)
daily_incremental — ongoing daily incremental load

source: CLAUDE.md

---

## Topic: Terraform Layout

The Terraform directory structure separates concerns into:

bootstrap-state/ — creates the S3 backend for Terraform state
accounts/{dev,prod}/ — passive AWS infra (networks, storage, ECR, ECS cluster, SNS)
access/aws/accounts/{dev,prod}/ — IAM roles, SNS trust policies, ECS task roles
access/non-aws/accounts/{dev,prod}/ — workload identities, RBAC, external secret manager policies
access/snowflake/accounts/{dev,prod}/ — Snowflake roles and grants
non-aws/accounts/{dev,prod}/ — non-AWS passive infra (non-AWS app runtime shell, retired analytics platform, storage)
snowflake/accounts/{dev,prod}/ — Snowflake database objects and native-pull runtime

Apply order matters: bootstrap-state first, then accounts, then access roots.
For Snowflake: use deploy-snowflake-stack.sh for the two-pass bootstrap.

source: infra/terraform/README.md, infra/terraform/snowflake/README.md

---

## Topic: Current Platform State (as of document set)

The platform is in active development. The AWS/Snowflake path is the active production path.
An retired non-AWS path parallel-run path is documented in the runbook as a migration target.
Key guidance from AGENTS.md: "Keep agent work AWS-focused. Do not add or revive non-AWS
deployment paths unless the user explicitly asks for that architecture change."

The dbt project supports both Snowflake (dynamic tables) and retired analytics platform (tables by default,
views with DBT_RETIRED_ANALYTICS_GOLD_MATERIALIZED=view for dev).

source: AGENTS.md, README.md, docs/runbook.md, infra/snowflake/dbt/edgartools_gold/README.md

---

## Topic: Image Management

Four Docker images, two for warehouse and two for MDM:

edgartools-dev-warehouse-deps (Dockerfile.warehouse-deps) — locked .[s3] deps via uv
edgartools-dev-warehouse (Dockerfile) — source copy on warehouse-deps base
edgartools-dev-mdm-deps (Dockerfile.mdm-deps) — locked .[s3,mdm-runtime] deps via uv
edgartools-dev-mdm (Dockerfile.mdm-neo4j) — source copy on mdm-deps base

Rebuild triggers:
  - edgar_warehouse/** (not mdm/) → warehouse only
  - edgar_warehouse/mdm/** → MDM only
  - uv.lock changed → deps images for both (run without --skip-build)

CI (GitHub Actions build-images.yml) runs on every push to main.

source: CLAUDE.md
