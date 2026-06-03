# Project: EdgarTools Platform

status: active
milestone: multi-milestone (v1.2 / v1.3 / v1.4 / model-builder-contract-gaps)
updated: 2026-06-03

---

## Core Value

Deliver structured, business-ready SEC EDGAR data — ownership transactions, filing activity,
adviser disclosures, and private fund data — through a reliable phased ETL pipeline that runs
at scale on AWS ECS and publishes to Snowflake gold tables consumed by analytics dashboards.

---

## Current Milestone: v1.4 ADV Bronze-To-Silver Backfill

**Goal:** Add a safe operator path that parses already-downloaded ADV bronze artifacts into
silver ADV tables without SEC re-fetch, unblocking the MDM adviser/fund load path.

**Current progress:** Phase 8 complete. ADV bronze discovery/read contracts are in place; Phase 9 is ready to plan the `parse-adv-bronze` command and silver merge path.

**Target features:**
- Discover and select ADV filings already present in bronze or the artifact registry.
- Parse ADV bronze through the existing ADV parser into `sec_adv_filing`, `sec_adv_office`,
  `sec_adv_disclosure_event`, and `sec_adv_private_fund`.
- Provide a bounded idempotent operator command with `--accession-list` and `--limit`.
- Report missing artifacts clearly and prove the command performs no SEC API re-fetch.
- Document live validation steps so the paused `neo4j-pipe` Phase 5 checkpoint can resume.

Developer-facing success metric: Given existing ADV bronze artifacts in S3,
`edgar-warehouse parse-adv-bronze` can populate nonzero ADV silver rows and make
`edgar-warehouse mdm run --entity-type adviser` / `fund` eligible to run without touching SEC
network fetches, gold-layer pipeline work, or generated deployment JSON.

---

## Architecture

```
SEC EDGAR API
      |
      v
edgar-warehouse CLI  (edgar_warehouse/runtime.py)
      |
      v
S3 Parquet (bronze)
      |
      v
Snowflake EDGARTOOLS_SOURCE  <-- native S3 pull via Snowflake storage integration
      |
      v
dbt (infra/snowflake/dbt/edgartools_gold/)
      |
      v
EDGARTOOLS_GOLD  (15 dynamic tables + 1 status view)
      |
      v
Streamlit dashboard  (infra/snowflake/streamlit/  OR  examples/dashboard/)
```

MDM runs as Stage 2 in the phased pipeline (between silver batches and gold refresh):
```
Stage 1: Stage1Parallel (Type=Parallel Step Function state)
  Branch A: bootstrap-next   (ownership + ADV, MaxConcurrency=1) → silver/ownership/
  Branch B: bootstrap-fundamentals per-filing → entity-facts      → silver/fundamentals/
            (sequential within branch, States.ALL Catch → BranchBComplete)

Stage 2: MDM entity resolution (sequential)
  mdm-run → mdm-backfill-relationships → mdm-sync-graph → mdm-verify-graph

Stage 3: gold refresh (single ECS task)
  gold-refresh → dbt (15 dynamic tables + status view)
```

---

## Target Runtime

- AWS ECS Fargate (warehouse + MDM containers)
- Snowflake Enterprise+ (gold layer via dbt dynamic tables)
- Neo4j AuraDB (graph layer for entity relationships)
- PostgreSQL (MDM relational store)

---

## Locked Decisions

The following 10 decisions are explicitly locked per project policy (CLAUDE.md/AGENTS.md).
Do not change without explicit user instruction.

| ID | Decision | Enforcement |
|----|----------|-------------|
| DEC-001 | AWS is the only active deployment path — no non-AWS registries, workflows, or secret-management steps may be added | AGENTS.md, CLAUDE.md |
| DEC-002 | `bootstrap-batch` must NOT be in `GOLD_AFFECTING_COMMANDS` | warehouse_orchestrator.py:79 |
| DEC-003 | `gold-refresh` must be in `GOLD_AFFECTING_COMMANDS` — it is the sole gold builder | CLAUDE.md |
| DEC-004 | `silver_mdm_gold` map MUST pass `--artifact-policy skip` to `bootstrap-batch` | CLAUDE.md |
| DEC-005 | `SNOWFLAKE_RUN_MANIFEST_TASK` must remain in STARTED state in EDGARTOOLS_GOLD | CLAUDE.md |
| DEC-006 | Use `uv` for all Python dependency management — never bare `pip` or bare `dbt` | CLAUDE.md, AGENTS.md |
| DEC-007 | Use Colima on macOS for local Docker — no other container runtime stacks permitted | CLAUDE.md, AGENTS.md |
| DEC-008 | Use AWS ECR only for deployable images — no Azure Container Registry or ACR steps | CLAUDE.md, AGENTS.md |
| DEC-009 | SEC filing artifacts are additive and immutable after capture — loaders skip by default; `--force` required to re-fetch | CLAUDE.md, AGENTS.md |
| DEC-010 | Ownership parser import must use `from edgar.ownership import Ownership` / `Ownership.from_xml(content)` — do not change without checking edgartools changelog | CLAUDE.md |

---

## Additional Decisions
| DEC-011 | Terraform is passive infra only — no runnable jobs, schedules, SQL tasks, or secret values | |
| DEC-012 | Runtime uses service-assumed roles only — no runner IAM user or long-lived access keys | |
| DEC-013 | Prod bronze S3 bucket has `prevent_destroy = true` — must not be destroyed without explicit operator request | |
| DEC-014 | Snowflake Terraform ownership: Terraform owns platform objects; dbt owns gold models and dynamic tables | |
| DEC-015 | `bootstrap_phased` Step Function is the canonical path for batch loads of 10+ companies | |
| DEC-016 | NEO4J_USERNAME (Aura display name) must be mapped to NEO4J_USER before running MDM commands | |
| DEC-017 | Terraform S3 backend state locking uses `use_lockfile = true` — no DynamoDB lock table | |
| DEC-018 | ECR tags must be MUTABLE for `:dev` to be overwritten on each image push | |
| DEC-019 | Claude and Codex may work independently only through isolated git/workstream ownership; neither runtime may overwrite the other's in-progress work | AGENTS.md, .planning/COORDINATION.md |

---

## Key Decisions Log

| Date | Phase | Decision | Rationale |
|------|-------|----------|-----------|
| 2026-05-15 | init | 10 decisions LOCKED (DEC-001 through DEC-010) | Derived from CLAUDE.md/AGENTS.md; DEC-005 and DEC-010 promoted to LOCKED on user confirmation |
| 2026-05-16 | coordination | Claude/Codex work must be isolated by worktree/branch and GSD workstream ownership | User requested independent Claude and Codex work without conflicts |

---

## Documentation Debt

Items surfaced during intel ingest — to address at an appropriate point:

- CLAUDE.md Quick Navigation says "8 dynamic tables" — should be "9 dynamic tables + 1 status view"
- README.md install example uses bare pip — should be updated to uv commands
- Terraform CLI version pin differs between AWS roots (1.14.7) and Snowflake roots (1.14.8) — use 1.14.8 for both
- No formal ADRs exist — DEC-001 through DEC-005 are strong ADR candidates (pipeline invariants, AWS-only policy)
