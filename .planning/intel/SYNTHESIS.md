# Intel Synthesis — EdgarTools Platform
# Entry point for gsd-roadmapper and downstream consumers.
# Generated from 11 DOC-type classified documents (new mode bootstrap).

---

## Document Counts by Type

DOC: 11
ADR: 0
SPEC: 0
PRD: 0
UNKNOWN: 0

Source documents:
  - CLAUDE.md (primary architecture and developer reference)
  - README.md (project overview)
  - AGENTS.md (AI agent operational guide)
  - docs/runbook.md (end-to-end setup runbook)
  - docs/neo4j.md (Neo4j/MDM graph integration)
  - edgar/ai/skills/platform/pipeline-setup.md (pipeline setup skill)
  - examples/dashboard/README.md (Streamlit dashboard)
  - infra/snowflake/dbt/edgartools_gold/README.md (dbt gold layer)
  - infra/snowflake/sql/README.md (Snowflake native-pull)
  - infra/terraform/README.md (Terraform AWS layout)
  - infra/terraform/snowflake/README.md (Snowflake Terraform)

---

## Decisions Locked (Policy-Locked, Not Formal ADRs)

Note: No ADR-type documents exist in this ingest set. The classifications identified
several items in source docs with explicit "must", "key invariant", or "do not" language
that carries project-policy weight. These are recorded as "policy-locked" decisions in
decisions.md — they are binding project policy but are not LOCKED-ADR decisions per the
conflict engine's technical definition. The roadmapper should treat them as high-authority
constraints when generating plans.

Policy-locked decisions (8):
  DEC-001: AWS is the only active deployment path
    source: AGENTS.md, CLAUDE.md
  DEC-002: bootstrap-batch must NOT be in GOLD_AFFECTING_COMMANDS
    source: CLAUDE.md, AGENTS.md (enforced in warehouse_orchestrator.py:79)
  DEC-003: gold-refresh must be in GOLD_AFFECTING_COMMANDS
    source: CLAUDE.md
  DEC-004: silver_mdm_gold map MUST pass --artifact-policy skip to bootstrap-batch
    source: CLAUDE.md
  DEC-005: SNOWFLAKE_RUN_MANIFEST_TASK must be STARTED in EDGARTOOLS_GOLD
    source: CLAUDE.md
  DEC-006: Use uv for all Python dependency management
    source: CLAUDE.md, AGENTS.md
  DEC-007: Use Colima on macOS for local Docker
    source: CLAUDE.md, AGENTS.md
  DEC-008: Use AWS ECR only for deployable images
    source: CLAUDE.md, AGENTS.md

Additional proposed decisions (10):
  DEC-009 through DEC-018 — see decisions.md for full list

---

## Requirements Extracted

Total: 21 (15 functional, 6 non-functional)

Functional requirements:
  REQ-edgartools-version — edgartools >= 5.29.0 from PyPI
  REQ-edgar-identity — EDGAR_IDENTITY env var with email
  REQ-warehouse-runtime-mode — bronze_capture or infrastructure_validation
  REQ-serving-export-root — trailing slash required
  REQ-idempotent-loaders — skip existing files by default; --force for repair
  REQ-tracked-universe-seed — MDM universe seeded before first bootstrap
  REQ-phased-pipeline-for-scale — bootstrap_phased for >= 10 companies
  REQ-gold-tables — 9 business tables + 1 status view in EDGARTOOLS_GOLD
  REQ-snowflake-enterprise — Enterprise+ edition required for dynamic tables
  REQ-mdm-env-vars — MDM_DATABASE_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, MDM_API_KEYS
  REQ-snowflake-account-format — ORGNAME-ACCOUNTNAME format required
  REQ-two-pass-snowflake-bootstrap — two AWS Terraform passes for native-pull trust
  REQ-ecr-must-exist — ECR repos must exist before push
  REQ-snoccli-connection — SnowCLI connection must exist before deploy
  REQ-dashboard-prerequisites — Python 3.11+, role grants, config.toml

Non-functional requirements:
  REQ-nfr-idempotency — all pipeline ops must be idempotent
  REQ-nfr-scale-performance — 100 companies in ~15 min via phased pipeline
  REQ-nfr-no-secrets-in-terraform — no secret values in Terraform state
  REQ-nfr-bronze-immutability — bronze Parquet files never mutated; S3 protections kept
  REQ-nfr-non-AWS-managed-identity — non-AWS object storage via workload identity only
  REQ-nfr-gold-cache-ttl — dashboard queries cached 1 hour

Full text: .planning/intel/requirements.md

---

## Constraints Extracted

Total: 20

Type breakdown:
  api-contract: 3 (edgartools version/import, SNOWFLAKE_ACCOUNT format, SERVING_EXPORT_ROOT trailing slash)
  tooling: 3 (uv required, Colima required, Terraform CLI/provider version pins)
  security: 5 (no runner IAM user, no secrets in VCS, no S3 protections removed, Neo4j Fleet tokens, cloud workload identity only)
  operational: 3 (ECR only, prod bronze prevent_destroy, large files read in chunks)
  protocol: 1 (Terraform passive infra only)
  schema: 2 (Snowflake separate state keys, dbt ownership boundaries)
  nfr: 3 (Snowflake Enterprise+ for dynamic tables, dashboard geography limitations, Python version scoping)

Full text: .planning/intel/constraints.md

---

## Context Topics

Total: 13 topics covering the full platform scope:
  - Domain (SEC EDGAR, universe of companies and advisers)
  - Data Layer Architecture (Bronze / Source / Silver / Gold ownership)
  - Gold Layer Tables (9 business tables + 1 status view, named and described)
  - ETL Runtime (edgar-warehouse CLI, ECS Fargate, edgartools entry point)
  - edgartools Package Usage (where it enters, what surfaces are used)
  - MDM (Master Data Management) (PostgreSQL + Neo4j AuraDB, entity resolution)
  - AWS Infrastructure (ECS, ECR, S3, Step Functions, IAM model)
  - Snowflake Infrastructure (Terraform, dbt, access roots, native-pull)
  - Dashboards (Streamlit-in-Snowflake and standalone Streamlit variants)
  - Phased Pipeline Variants (5 Step Function state machines)
  - Terraform Layout (directory structure, apply order)
  - Current Platform State (AWS active, non-AWS parallel-run migration)
  - Image Management (4 Docker images, rebuild triggers, CI)

Full text: .planning/intel/context.md

---

## Conflicts Summary

Total: 5 (0 blockers, 0 warnings, 5 info)

No workflow gates. No user resolution required before routing.

INFO-level findings (all auto-resolved, recorded for transparency):
  1. Terraform CLI version pin is scope-specific (1.14.7 AWS vs 1.14.8 Snowflake vs "1.14.x" runbook)
     — use 1.14.8 for both root types
  2. Gold table count stale in CLAUDE.md Quick Navigation ("8 dynamic tables") vs authoritative
     count of 9 business tables + 1 status view in dbt README
     — dbt README wins as authoritative source for dbt project scope; CLAUDE.md Quick Nav
     should be updated as documentation debt
  3. Python minimum differs between dashboard (3.11+) and platform runtime (3.12)
     — scoped correctly: 3.11+ for dashboard, 3.12 for warehouse container
  4. README.md uses bare pip in install example, contradicting uv policy
     — CLAUDE.md/AGENTS.md win as authoritative developer policy; README install is
     documentation debt (shorthand for new users)
  5. retired non-AWS path paths in runbook/README vs AWS-only policy in AGENTS.md/CLAUDE.md
     — consistent in context: non-AWS is a documented parallel-run migration path, not
     a revival; AWS-only policy governs new work

Full report: .planning/INGEST-CONFLICTS.md

---

## Per-Type Intel Files

decisions.md — 18 decisions (8 policy-locked, 10 proposed)
requirements.md — 21 requirements (15 functional, 6 non-functional)
constraints.md — 20 constraints across 7 types
context.md — 13 context topics

---

## Roadmapper Guidance

All 11 source documents are DOC type. No ADR, SPEC, or PRD documents were ingested.
The platform currently has no formal Architecture Decision Records on file. The roadmapper
should consider whether any of the policy-locked decisions (DEC-001 through DEC-008)
should be promoted to formal ADRs, particularly:
  - DEC-002/DEC-003/DEC-004/DEC-005 (pipeline invariants) — strong candidates for ADR
  - DEC-001 (AWS-only active path) — strong candidate for ADR given its governance weight

The requirements list has no IDs from a formal product requirements process. When the
roadmapper generates REQUIREMENTS.md, it should preserve the REQ-* identifiers from
requirements.md as stable references.

Documentation debt items surfaced in conflict detection:
  - CLAUDE.md Quick Navigation "8 dynamic tables" should be updated to "9 dynamic tables + 1 status view"
  - README.md install example should be updated from bare pip to uv commands
  - Pipeline steps suggest a Terraform CLI version pin clarification document would be useful
