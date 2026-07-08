# Project: EdgarTools Platform

status: active
milestone: multi-milestone (v1.2 / v1.3 / v1.4 / v2.0 fix-pipelines / model-builder-contract-gaps)
updated: 2026-07-08

---

## Core Value

Deliver structured, business-ready SEC EDGAR data — ownership transactions, filing activity,
adviser disclosures, and private fund data — through a reliable phased ETL pipeline that runs
at scale on AWS ECS and publishes to Snowflake gold tables consumed by analytics dashboards.

---

## Current Milestone: v2.0 fix-pipelines — Pipeline Data-Source Completeness & Verification

**Goal:** Close the remaining data-source and verification gaps across the MDM → Neo4j graph
pipeline so every *derivable* relationship type is populated and independently verified, missing
source artifacts are either sourced or documented as external blockers, and platform parsing is
cross-checked against — and where possible replaced by — the `edgartools` reference library.

**Target features:**
- **Neo4j graph verification** — graph sync materializes MDM_GRAPH_NODES/EDGES + per-type views
  with strict MDM↔graph parity across the full active coverage target; Native App verification
  runs the current API (compute pool + WCC) green; app-side GRAPH_INFO/BFS gaps are resolved or
  documented with evidence; readiness failures (no compute pool) are distinguished from parity
  failures.
- **MDM relationship completeness** — populate still-zero relationship types where source data
  supports it (AUDITED_BY via fundamentals entity-facts); document unsatisfiable ones (ADV,
  HAS_PARENT_COMPANY, EMPLOYED_BY, INSTITUTIONAL_HOLDS) as source-coverage exclusions; derivation
  stays idempotent.
- **Missing artifacts** — triage missing bronze source artifacts: capture genuinely-fetchable
  gaps; document unsatisfiable ones (ADV primary attachments are paper filings — see
  `.planning/workstreams/claude-mdm-source-recovery/FINDINGS.md`); fix the `parse-adv-bronze`
  silver-clobber hazard that can truncate the canonical silver.duckdb.
- **edgartools crosscheck** — validate platform-parsed output (ownership, ADV, financials) against
  `edgartools` for a sample of filings; prefer edgartools' native parsing over hand-built pipeline
  parsers where the library covers it; audit edgartools API usage against the pinned version's
  current (non-deprecated) surfaces.

**Key context:** AWS-only (DEC-001); dev account `690839588395` + `EDGARTOOLS_PRODB` only —
never touch real prod (`077127448006` / `EDGARTOOLS_PROD`). Codex is active on the
`fundamental-factors-v2` workstream; the AUDITED_BY/fundamentals work overlaps and must be
isolated per DEC-019. `fix-pipelines v1.0` (Pipeline Observability, 2026-05-16) is the prior
milestone under this name.

**Progress:** Phase 5 (Node And Populated-Relationship Graph Parity) complete 2026-07-08 —
all 6 MDM entity types have a verified per-type graph view (including the previously-missing
`GRAPH_NODE_AUDITFIRM`), the 4 populated relationship types have proven MDM↔graph parity via
named checks in `mdm verify-graph`, and derivation/sync idempotency is a committed regression
test (both halves: graph-sync full-rebuild and MDM node/relationship derivation). Full detail:
`.planning/workstreams/fix-pipelines/phases/05-node-and-populated-relationship-graph-parity/05-VERIFICATION.md`.
Next: Phase 6 (Relationship Investigation And Population).

Developer-facing success metric: `mdm verify-graph` exits 0 with strict MDM↔graph parity across
the full active coverage target, every relationship type is populated or has a documented
source-coverage exclusion, and a documented crosscheck shows platform parsing agrees with
`edgartools` (or edgartools has replaced the custom parser) for the sampled filings.

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
| DEC-008 | Use AWS ECR only for deployable images — no non-ECR registry or non-ECR registry steps | CLAUDE.md, AGENTS.md |
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
