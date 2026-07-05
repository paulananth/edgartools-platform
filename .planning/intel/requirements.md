# Requirements
# Source: synthesized from 11 DOC-type classified documents
# All entries carry source: attribution for downstream traceability.

---

## Functional Requirements

### REQ-edgartools-version
description: The edgartools PyPI package >= 5.29.0 must be installed as a runtime dependency.
  It is not a local path dependency — install from PyPI only. It is not vendored in this
  repository.
acceptance:
  - edgartools>=5.29.0 present in the Python environment
  - Installed via `uv sync` or `pip install "edgartools>=5.29.0"` from PyPI
  - When edgartools version is bumped, batch scripts in scripts/batch/ must be rerun to
    confirm that library surfaces still behave as expected
source: CLAUDE.md, AGENTS.md, README.md

### REQ-edgar-identity
description: EDGAR_IDENTITY must be set to a valid SEC User-Agent string in the format
  "Name email@example.com". The runtime rejects any command where this variable is absent
  or lacks an email address. This is required by SEC rate-limiting policy.
acceptance:
  - EDGAR_IDENTITY env var is present before any warehouse CLI command
  - Value contains a name and a valid email address
  - Runtime validates this at startup and rejects without it
source: AGENTS.md, docs/runbook.md, edgar/ai/skills/platform/pipeline-setup.md

### REQ-warehouse-runtime-mode
description: WAREHOUSE_RUNTIME_MODE must be set to either bronze_capture or
  infrastructure_validation. No other values are accepted.
acceptance:
  - WAREHOUSE_RUNTIME_MODE is set to bronze_capture or infrastructure_validation
  - Runtime rejects unrecognized values
source: AGENTS.md

### REQ-serving-export-root
description: Gold-affecting commands require SERVING_EXPORT_ROOT to be set. The variable
  must include a trailing slash on snowflake_exports/. SNOWFLAKE_EXPORT_ROOT is accepted
  as a compatibility fallback during migration.
acceptance:
  - SERVING_EXPORT_ROOT is set before running gold-affecting commands (gold-refresh and any
    command in GOLD_AFFECTING_COMMANDS)
  - Value ends with trailing slash on snowflake_exports/
source: AGENTS.md, docs/runbook.md

### REQ-idempotent-loaders
description: Warehouse loaders must skip already-loaded SEC files by default. Re-fetching is
  only permitted when an operator passes an explicit --force flag. This applies to all loader
  commands.
acceptance:
  - Default behavior: loader detects previously captured bronze artifact and skips
  - --force flag triggers re-fetch of already-captured files
  - No SEC API calls made for ownership XMLs already in S3 bronze unless forced
source: CLAUDE.md, AGENTS.md

### REQ-tracked-universe-seed
description: The tracked company universe must be seeded before running edgar-warehouse
  bootstrap. The MDM system owns the canonical list of CIKs that the warehouse processes.
acceptance:
  - edgar-warehouse mdm seed-universe completes successfully before first bootstrap run
  - MDM_DATABASE_URL is configured and pointing to the PostgreSQL MDM store
source: edgar/ai/skills/platform/pipeline-setup.md

### REQ-phased-pipeline-for-scale
description: For all bootstraps of 10 or more companies, the bootstrap_phased Step Function
  must be used rather than running bootstrap-next sequentially. bootstrap-next is reserved for
  single-company ad-hoc loads with explicit --cik-list.
acceptance:
  - Batch loads >= 10 companies use bootstrap_phased Step Function
  - bootstrap-next is not run locally for large batches
  - bootstrap_phased completes all four stages: bronze, MDM resolution, gold refresh
source: CLAUDE.md

### REQ-gold-tables
description: The dbt gold project must publish nine business-facing tables plus one status
  view in the EDGARTOOLS_GOLD schema.
acceptance:
  - COMPANY table present in EDGARTOOLS_GOLD
  - FILING_ACTIVITY table present
  - OWNERSHIP_ACTIVITY table present
  - OWNERSHIP_HOLDINGS table present
  - ADVISER_OFFICES table present
  - ADVISER_DISCLOSURES table present
  - PRIVATE_FUNDS table present
  - FILING_DETAIL table present
  - TICKER_REFERENCE table present
  - EDGARTOOLS_GOLD_STATUS view present
  - On Snowflake: business tables are dbt-managed dynamic tables with TARGET_LAG = DOWNSTREAM
source: infra/snowflake/dbt/edgartools_gold/README.md, CLAUDE.md

### REQ-snowflake-enterprise
description: Snowflake Enterprise edition or higher is required. Standard edition does not
  support CREATE DYNAMIC TABLE, which the dbt gold project depends on.
acceptance:
  - Snowflake account is Enterprise or Business Critical edition
  - Dynamic table creation succeeds during dbt run
source: AGENTS.md, docs/runbook.md, edgar/ai/skills/platform/pipeline-setup.md

### REQ-mdm-env-vars
description: MDM commands require MDM_DATABASE_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
  and MDM_API_KEYS environment variables to be set.
acceptance:
  - All five env vars are set before running any edgar-warehouse mdm command
  - MDM_DATABASE_URL points to a reachable PostgreSQL instance
  - NEO4J_URI uses the neo4j+s:// scheme for Aura
  - NEO4J_USERNAME from Aura is mapped to NEO4J_USER (not NEO4J_USERNAME)
source: edgar/ai/skills/platform/pipeline-setup.md, docs/neo4j.md

### REQ-snowflake-account-format
description: SNOWFLAKE_ACCOUNT must be set in the ORGNAME-ACCOUNTNAME format for the
  Snowflake provider and SnowCLI to work correctly.
acceptance:
  - SNOWFLAKE_ACCOUNT value matches ORGNAME-ACCOUNTNAME format
  - Terraform and SnowCLI both accept the value without error
source: edgar/ai/skills/platform/pipeline-setup.md

### REQ-two-pass-snowflake-bootstrap
description: The Snowflake native-pull bootstrap requires two AWS Terraform passes. The first
  applies to capture the external stage Snowflake principal ID. The second (via access root
  re-apply) narrows the AWS IAM trust to that exact principal.
acceptance:
  - deploy-snowflake-stack.sh automates this two-pass sequence for dev
  - For prod: AWS provisioning → AWS access (temp trust) → Snowflake provisioning →
    AWS access reconcile (narrow trust) → Snowflake access → dbt → Streamlit upload
source: edgar/ai/skills/platform/pipeline-setup.md, infra/terraform/snowflake/README.md

### REQ-ecr-must-exist
description: ECR repositories must exist before a Docker image push. They are not created
  dynamically during image publish.
acceptance:
  - ECR repositories present in target AWS account before publish-warehouse-image.sh runs
  - Repositories have MUTABLE tag setting for :dev to be overwritten
source: docs/runbook.md, CLAUDE.md

### REQ-snoccli-connection
description: A SnowCLI connection named per environment must exist in ~/.snowflake/config.toml
  before running deploy-snowflake-stack.sh or any snow sql commands.
acceptance:
  - ~/.snowflake/config.toml contains a connection block for the target environment
  - snow sql --connection edgartools-dev succeeds
source: AGENTS.md, infra/snowflake/sql/README.md

### REQ-dashboard-prerequisites
description: The standalone Streamlit dashboard requires Python 3.11+, a Snowflake role with
  SELECT on EDGARTOOLS_DEV.EDGARTOOLS_GOLD.* and USAGE on a compute warehouse, and a valid
  ~/.snowflake/config.toml connection block.
acceptance:
  - Python 3.11+ in the dashboard virtual environment
  - Snowflake role grants verified before dashboard startup
  - config.toml connection block present with database=EDGARTOOLS_DEV, schema=EDGARTOOLS_GOLD
source: examples/dashboard/README.md

---

## Non-Functional Requirements

### REQ-nfr-idempotency
description: All pipeline operations must be idempotent. Re-running any step must not produce
  duplicate data or fail on already-present artifacts.
acceptance:
  - Loader skips existing bronze files by default
  - Snowflake source tables auto-refresh without re-ingesting unchanged Parquet files
  - dbt dynamic tables refresh from current state without manual deduplication
source: CLAUDE.md, AGENTS.md

### REQ-nfr-scale-performance
description: Loading 100 companies must complete in approximately 15 minutes via the phased
  pipeline (vs 30-90 minutes sequential). The phased pipeline achieves this via MaxConcurrency=10
  ECS tasks for bronze + silver, then sequential MDM, then a single gold-refresh task.
acceptance:
  - bootstrap_phased Step Function completes 100 companies in approximately 15 minutes
  - No gold builds during parallel bronze phase
source: CLAUDE.md

### REQ-nfr-no-secrets-in-terraform
description: Runtime secret values must never be stored in Terraform state. Secret containers
  are created by Terraform (empty), but values are populated by operators outside Terraform.
acceptance:
  - Terraform plan output contains no plaintext secret values
  - Secret values are set via aws secretsmanager put-secret-value or bootstrap scripts
source: infra/terraform/README.md, AGENTS.md

### REQ-nfr-bronze-immutability
description: Bronze layer Parquet files in S3 are never mutated after being written. They are
  additive only. The S3 bucket has versioning and encryption enabled; public access is blocked.
acceptance:
  - No in-place overwrites of bronze Parquet files
  - S3 bucket versioning, encryption, and public-access block remain enabled
  - Prod bucket has prevent_destroy = true
source: AGENTS.md, infra/terraform/README.md

### REQ-nfr-non-AWS-managed-identity
description: non-AWS object storage must use workload identity authentication. No account keys, SAS
  tokens, or connection strings are permitted.
acceptance:
  - non-AWS non-AWS app runtime and runtime jobs authenticate to non-AWS object storage via workload identity
  - No account keys or SAS tokens in any config, script, or Terraform state
source: docs/runbook.md

### REQ-nfr-gold-cache-ttl
description: Streamlit dashboard queries are cached for 1 hour by default. This is a known
  operational characteristic; users must restart or clear the Streamlit cache to see gold
  table updates applied within the cache TTL.
acceptance:
  - All Streamlit gold queries use @st.cache_data with ttl=3600
  - Clear cache button or restart is the documented path for immediate refresh
source: examples/dashboard/README.md
