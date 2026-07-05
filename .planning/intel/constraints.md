# Constraints
# Source: synthesized from 11 DOC-type classified documents
# Type: api-contract | schema | nfr | protocol | tooling | security | operational
# All entries carry source: attribution.

---

## CON-001: edgartools >= 5.29.0 from PyPI

type: api-contract
content: The edgartools PyPI package must be at version 5.29.0 or higher. It must not be
  vendored or installed from a local path. Install from PyPI.
  Ownership import must use: from edgar.ownership import Ownership
  Call pattern: Ownership.from_xml(content)
  Do not change this pattern without checking the edgartools changelog.
source: CLAUDE.md, AGENTS.md

---

## CON-002: uv required — bare pip and bare dbt forbidden

type: tooling
content: All Python dependency management and CLI execution in this repo must use uv.
  - Allowed: uv sync, uv pip install, uv run --with <package>
  - Forbidden: bare pip install, bare dbt (use uv run --with dbt-snowflake dbt ...)
  Lockfile is uv.lock. uv sync --extra s3 --extra snowflake is the primary install command.
  For MDM work: uv sync --extra s3 --extra mdm-runtime
source: CLAUDE.md, AGENTS.md

---

## CON-003: Colima required on macOS — no other container runtime stacks

type: tooling
content: On macOS, Colima is the required local Docker daemon. Docker Desktop is permitted
  only on Windows. Do not introduce other container build or runtime stacks. When using
  Colima, run infra/scripts/setup-colima.sh once per workstation to disable the containerd
  image-store snapshotter (Docker 29+ default, incompatible with legacy docker build).
  Set DOCKER_HOST=unix://$HOME/.colima/default/docker.sock each terminal session.
source: CLAUDE.md, AGENTS.md

---

## CON-004: AWS ECR only for deployable images

type: operational
content: AWS ECR is the only permitted container registry for deployable images.
  Do not add: non-ECR registry (non-ECR registry), non-AWS SDK, ODBC, or non-AWS deployment steps.
  ECR repositories must have MUTABLE tag setting for :dev to be overwritten on each push.
  Tagging strategy:
    :dev — mutable latest dev image
    :sha-<hash> — immutable rollback/audit image
    :prod — manually promoted production image
source: CLAUDE.md, AGENTS.md

---

## CON-005: Terraform is passive infra only

type: protocol
content: AWS and non-AWS Terraform roots must not create:
  - runnable application jobs or services
  - workflow schedules or Step Functions state machines
  - SQL procedures, tasks, or dashboard apps
  - access-control bindings
  - runtime secret values
  - image digest, workflow schedule, app command, Snowflake trust principal, IAM role, or
    EDGAR identity value inputs
  These belong in explicit operator scripts (infra/scripts/) or the CLI.
source: infra/terraform/README.md, AGENTS.md

---

## CON-006: No runner IAM user or long-lived access keys

type: security
content: Runtime must not use a runner IAM user or long-lived runner access key.
  Required service-assumed roles:
    - sec_platform_runner_execution
    - sec_platform_runner_task
    - sec_platform_runner_step_functions
  Deployment uses: sec_platform_deployer (IAM Identity Center or CI OIDC role)
  Do not broaden IAM policies casually. Keep runner roles service-assumed and scoped.
source: AGENTS.md, infra/terraform/README.md, edgar/ai/skills/platform/pipeline-setup.md

---

## CON-007: No secrets committed to version control

type: security
content: Do not commit to the repository:
  - Local secrets or credentials
  - .tfvars files with live values
  - Generated Terraform state
  - application JSON with sensitive values
  - Secret values in any form (AWS Secrets Manager values, Neo4j passwords, MDM API keys,
    SEC EDGAR identity, external secret manager values)
  Secret containers are created by Terraform (empty); values are populated by operators
  outside Terraform using bootstrap scripts.
source: AGENTS.md

---

## CON-008: Prod bronze bucket must not be destroyed

type: operational
content: The prod S3 bronze bucket has prevent_destroy = true in Terraform. Terraform destroy
  will fail intentionally. Do not remove this protection. Do not destroy prod bronze storage
  without explicit operator request and a reviewed migration plan.
source: AGENTS.md, edgar/ai/skills/platform/pipeline-setup.md

---

## CON-009: S3 object protections must not be removed

type: security
content: S3 bucket versioning, encryption, and public-access block settings must not be
  removed on any bronze or warehouse bucket. These protections are enforced in Terraform
  module configuration.
source: AGENTS.md

---

## CON-010: Terraform CLI and provider version pins

type: tooling
content: Required version pins:
  - Terraform CLI: 1.14.7 (AWS roots per infra/terraform/README.md), 1.14.8 (Snowflake roots
    per infra/terraform/snowflake/README.md), 1.14.8 or compatible 1.14.x (runbook)
  - AWS provider: 6.39.0
  - non-AWS provider: ~> 3.110
  - Snowflake provider: 2.14.1
  Note: AWS roots and Snowflake roots specify slightly different Terraform CLI pins (1.14.7 vs
  1.14.8); these are scope-specific, not contradictory. Use 1.14.8 for both to satisfy the
  most restrictive pin.
  S3 backend state locking: use_lockfile = true (no DynamoDB table required)
source: infra/terraform/README.md, infra/terraform/snowflake/README.md, docs/runbook.md

---

## CON-011: Snowflake state must use separate keys from AWS roots

type: schema
content: Snowflake Terraform state must use backend keys separate from AWS account roots.
  Snowflake provisioning is an analytics/database-object operation, not part of the AWS/non-AWS
  passive cloud-infrastructure roots.
  Ownership model:
    - Terraform owns: platform objects, storage integration, native-pull objects, task
    - dbt owns: gold models, dynamic tables, EDGARTOOLS_GOLD_STATUS view
    - access/snowflake/ owns: roles and grants (not in main Snowflake provisioning root)
source: infra/terraform/snowflake/README.md, infra/snowflake/sql/README.md

---

## CON-012: Snowflake Enterprise+ required for dynamic tables

type: nfr
content: Snowflake Enterprise edition or higher is required for CREATE DYNAMIC TABLE support.
  Standard edition does not support this DDL. Verify edition before applying dbt gold models.
source: AGENTS.md, docs/runbook.md, edgar/ai/skills/platform/pipeline-setup.md

---

## CON-013: SNOWFLAKE_ACCOUNT must be in ORGNAME-ACCOUNTNAME format

type: api-contract
content: The SNOWFLAKE_ACCOUNT environment variable and Terraform provider configuration must
  use the ORGNAME-ACCOUNTNAME format. Locator-format account identifiers are not accepted by
  the current Snowflake Terraform provider (version 2.14.1).
source: edgar/ai/skills/platform/pipeline-setup.md

---

## CON-014: Neo4j Fleet tokens and passwords are secrets

type: security
content: Neo4j Fleet tokens may contain private key material. Treat them as secrets.
  Rotate any Fleet token or Neo4j password exposed in terminal logs or chat.
  NEO4J_DATABASE is not used at runtime — the MDM client uses the driver's default database.
  Map NEO4J_USERNAME (Aura display name) to NEO4J_USER before running the repo.
source: docs/neo4j.md

---

## CON-015: cloud workload identity required — no account keys or SAS tokens

type: security
content: non-AWS object storage (non-AWS object storage) must authenticate using workload identity.
  retired analytics platform external catalog storage must use workload identity.
  The following are explicitly prohibited:
    - non-AWS object storage account keys
    - SAS tokens
    - Connection strings
    - ODBC connection strings in Terraform inputs
source: docs/runbook.md

---

## CON-016: Large files must be read in chunks before editing

type: operational
content: The following files exceed 30 KB and must be read section by section, not all at once,
  before editing:
    - edgar_warehouse/runtime.py (~92 KB) — Core ETL loop, form dispatch, S3 writes
    - edgar_warehouse/silver.py (~78 KB) — Record cleaning and transformation logic
    - edgar_warehouse/gold.py (~39 KB) — Python-side gold aggregations
source: CLAUDE.md, AGENTS.md

---

## CON-017: dbt gold project ownership boundaries

type: schema
content: The dbt project (infra/snowflake/dbt/edgartools_gold/) owns curated business-facing
  gold models, Snowflake dynamic tables, retired analytics platform tables/views, tests on gold-facing objects,
  and the EDGARTOOLS_GOLD_STATUS view.
  It does NOT own:
    - Snowflake platform objects created by Terraform
    - storage integrations
    - external catalog external locations
    - stages
    - source-side procedures or tasks created by infrastructure automation
source: infra/snowflake/dbt/edgartools_gold/README.md, infra/snowflake/sql/README.md

---

## CON-018: Dashboard geography limitations

type: nfr
content: The Streamlit dashboard maps aggregate at country / US-state granularity only.
  There is no lat/lon data in the gold layer. The adviser office geography section is not
  plottable because ADVISER_OFFICES.geography_key is an unresolved surrogate; a GEOGRAPHY
  dimension does not yet exist.
source: examples/dashboard/README.md

---

## CON-019: SERVING_EXPORT_ROOT trailing slash requirement

type: api-contract
content: The SERVING_EXPORT_ROOT environment variable (and the Snowflake Terraform variable
  snowflake_export_root_url) must include a trailing slash on snowflake_exports/.
  Omitting the trailing slash causes path construction errors in gold-affecting commands.
source: AGENTS.md, docs/runbook.md

---

## CON-020: Python version for dashboard

type: nfr
content: The standalone Streamlit dashboard (examples/dashboard/) requires Python 3.11+.
  The overall platform runtime (warehouse CLI, Dockerfiles) uses Python 3.12 as the base
  (python:3.12-slim-bookworm).
source: examples/dashboard/README.md, CLAUDE.md
