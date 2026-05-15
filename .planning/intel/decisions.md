# Architectural Decisions
# Source: synthesized from 11 DOC-type classified documents
# Note: All decisions below originate from DOC-type sources (no ADR files in this ingest set).
# Several carry explicit project-policy weight ("must", "do not", key invariant) from
# the source docs. These are recorded as "policy-locked" decisions — not LOCKED-ADR status —
# so the roadmapper is aware of their weight without over-classifying them.

---

## DEC-001: AWS is the only active deployment path

status: policy-locked (project policy, not a formal ADR)
source: AGENTS.md, CLAUDE.md

Decision: The active runtime deployment path is AWS-only (ECS Fargate, ECR, S3, Step Functions,
Secrets Manager). No non-AWS deployment paths, registry targets, storage targets, workflow
engines, or secret-management steps may be added or revived without explicit user request and
explicit architecture change decision.

Scope: runtime deployment, container registry, secret management

---

## DEC-002: bootstrap-batch must NOT be in GOLD_AFFECTING_COMMANDS

status: policy-locked (key invariant enforced in warehouse_orchestrator.py:79)
source: CLAUDE.md, AGENTS.md

Decision: The `bootstrap-batch` command must not be listed in GOLD_AFFECTING_COMMANDS. This
prevents every parallel batch task from rebuilding gold tables and uploading silver.duckdb,
which would multiply I/O by batch count. The sole gold builder in the phased pipeline is
`gold-refresh`.

Scope: pipeline orchestration, batch loading

---

## DEC-003: gold-refresh must be in GOLD_AFFECTING_COMMANDS

status: policy-locked (key invariant)
source: CLAUDE.md

Decision: The `gold-refresh` command must be in GOLD_AFFECTING_COMMANDS. It is the sole gold
builder in the phased pipeline. Removing it breaks the bootstrap_phased Step Function's
gold-refresh stage.

Scope: pipeline orchestration, gold build

---

## DEC-004: silver_mdm_gold map MUST pass --artifact-policy skip to bootstrap-batch

status: policy-locked (key invariant)
source: CLAUDE.md

Decision: When the silver_mdm_gold pipeline runs bootstrap-batch, it must pass
`--artifact-policy skip`. Without this flag the pipeline makes thousands of SEC API calls to
re-fetch ownership XMLs, defeating the purpose of reprocessing already-loaded bronze.

5-why root cause: The artifact pipeline is a separate SEC fetch pass; "no SEC calls" must be
encoded as a flag, not assumed from the pipeline name.

Scope: pipeline configuration, SEC API calls

---

## DEC-005: SNOWFLAKE_RUN_MANIFEST_TASK must be STARTED in EDGARTOOLS_GOLD

status: policy-locked (key invariant)
source: CLAUDE.md

Decision: The SNOWFLAKE_RUN_MANIFEST_TASK Snowflake task must remain in STARTED state in
EDGARTOOLS_GOLD. Verify with:
  snow sql --connection edgartools-dev -q "SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK'"

Scope: Snowflake task management, gold refresh automation

---

## DEC-006: Use uv for all Python dependency management

status: policy-locked (project policy)
source: CLAUDE.md, AGENTS.md

Decision: Always use `uv` for Python dependency management and CLI execution. Never invoke bare
`pip` or bare `dbt` from repo workflows. Commands:
  - `uv sync` for project deps (uses uv.lock)
  - `uv pip install` for deliberate one-off installs
  - `uv run --with <package>` for transient tools (e.g., dbt-snowflake)

Scope: tooling, developer workflow

---

## DEC-007: Use Colima on macOS for local Docker

status: policy-locked (project policy)
source: CLAUDE.md, AGENTS.md

Decision: On macOS, use Colima as the local Docker daemon. On Windows, use Docker Desktop. On
Linux/CI, docker buildx with registry cache is the default path. Do not introduce another
container build/runtime stack. Docker 29+ in Colima defaults to the containerd image-store
snapshotter (incompatible with legacy docker build) — run infra/scripts/setup-colima.sh once
per workstation to disable the snapshotter.

Scope: local development, Docker runtime

---

## DEC-008: Use AWS ECR only for deployable images

status: policy-locked (project policy)
source: CLAUDE.md, AGENTS.md

Decision: Use AWS ECR exclusively for deployable container images. Do not add Azure Container
Registry (ACR), Azure SDK, ODBC, or Azure deployment steps back into this repo unless the
platform architecture changes explicitly.

Scope: container registry, image management

---

## DEC-009: SEC filing artifacts are additive and immutable after capture

status: policy-locked (project policy)
source: CLAUDE.md, AGENTS.md

Decision: SEC filing artifacts are treated as additive and immutable after they have been
captured. Warehouse loaders must skip already-loaded SEC files by default. Re-fetch is only
permitted when an operator passes an explicit `--force` repair flag. This applies to all loader
commands.

Scope: data idempotency, SEC API usage

---

## DEC-010: Ownership parser import pattern must not change without edgartools changelog check

status: policy-locked (key invariant)
source: CLAUDE.md, AGENTS.md

Decision: The ownership parser must use:
  from edgar.ownership import Ownership
  parsed = Ownership.from_xml(content)

Do not change this import pattern without checking the edgartools changelog.
When the edgartools version is bumped, run batch scripts in scripts/batch/ to smoke-test
parsing.

Scope: parser layer, edgartools integration

---

## DEC-011: Terraform is for passive infrastructure only — not runtime data

status: policy-locked (project policy)
source: infra/terraform/README.md, AGENTS.md

Decision: AWS and Azure Terraform roots are infra-only. They may create networks, storage,
registries, databases, logs, and empty secret containers. They must not create runnable
application jobs/services, schedules, workflow engines, SQL procedures/tasks, dashboard apps,
access-control bindings, or runtime secret values. CIK lists, seed data, runtime params, image
digests, workflow rollout, and schedules belong in operator scripts or CLI, not Terraform.

Scope: infrastructure provisioning, Terraform scope

---

## DEC-012: Runtime uses service-assumed roles — no runner IAM user

status: policy-locked (project policy)
source: infra/terraform/README.md, AGENTS.md, edgar/ai/skills/platform/pipeline-setup.md

Decision: Runtime does not use a runner IAM user or long-lived runner access key. It uses
service-assumed roles:
  - sec_platform_runner_execution
  - sec_platform_runner_task
  - sec_platform_runner_step_functions

Deployment uses sec_platform_deployer (IAM Identity Center permission set or CI OIDC role).
Do not create runner access keys.

Scope: AWS IAM, security

---

## DEC-013: Prod bronze bucket has prevent_destroy protection

status: policy-locked (project policy)
source: AGENTS.md, edgar/ai/skills/platform/pipeline-setup.md

Decision: The prod bronze S3 bucket has prevent_destroy = true. Do not destroy prod bronze
storage without explicit operator request and a reviewed migration plan. Terraform destroy of
prod will fail intentionally without manual removal of this protection.

Scope: data protection, Terraform, bronze layer

---

## DEC-014: Terraform ownership boundaries for Snowflake

status: proposed (no formal ADR)
source: infra/snowflake/sql/README.md, infra/terraform/snowflake/README.md

Decision: Clear ownership boundaries apply across Terraform, dbt, and SQL:
  - Terraform owns: storage integration, S3 import path, run-manifest auto-ingest objects,
    refresh-status table, manifest stream, source-side load wrapper, public gold refresh wrapper
  - dbt project owns: curated gold models, dynamic tables, EDGARTOOLS_GOLD_STATUS view
  - SQL files under bootstrap/ are no longer the deployment mechanism — retained as reference

Scope: Snowflake infrastructure, deployment

---

## DEC-015: bootstrap_phased Step Function is the canonical batch load path

status: proposed (no formal ADR)
source: CLAUDE.md

Decision: For all bootstraps of 10+ companies, use the bootstrap_phased Step Function. It
runs in four sequential stages optimized for their workload:
  Stage 1: Bronze + Silver (parallel, N×10 concurrent ECS tasks via bootstrap-batch)
  Stage 2: MDM entity resolution (sequential: mdm-run → mdm-backfill-relationships →
            mdm-sync-graph → mdm-verify-graph)
  Stage 3: Gold refresh (single ECS task: gold-refresh)
Do NOT run bootstrap-next locally for large batches — it is sequential and cannot reach
MDM Postgres (private VPC).

Scope: pipeline orchestration, scale loading

---

## DEC-016: NEO4J_USERNAME (Aura) must be mapped to NEO4J_USER

status: proposed (operational note)
source: docs/neo4j.md

Decision: Neo4j Aura displays NEO4J_USERNAME and NEO4J_DATABASE. Map NEO4J_USERNAME to
NEO4J_USER before running the repo. NEO4J_DATABASE is not used at runtime — the MDM graph
client uses the driver's default database.

Scope: MDM, Neo4j connectivity

---

## DEC-017: S3 backend state locking uses use_lockfile = true — no DynamoDB required

status: proposed (operational note)
source: AGENTS.md, infra/terraform/README.md

Decision: Terraform S3 backend state locking uses use_lockfile = true. No DynamoDB lock table
is required or should be created.

Scope: Terraform state management

---

## DEC-018: ECR tags must be MUTABLE for :dev to be overwritten

status: proposed (operational note)
source: CLAUDE.md

Decision: ECR repositories must have MUTABLE tag setting for the :dev tag to be overwritten
on each push. If a push fails with "tag is immutable", run:
  aws ecr put-image-tag-mutability --region us-east-1 \
    --repository-name edgartools-dev-warehouse --image-tag-mutability MUTABLE

Scope: container registry, image tagging
