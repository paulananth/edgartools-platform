---
gsd_state_version: 1.0
milestone: multi-milestone
milestone_name: Multiple active workstreams
status: executing
last_updated: "2026-06-03"
last_activity: 2026-06-03 -- neo4j-pipe Phase 8 plan executed; verification pending
---

# Project State

## Project Reference

See: .planning/PROJECT.md

**Core value:** Structured, business-ready SEC EDGAR data through a reliable phased ETL pipeline
publishing to Snowflake gold tables.

---

## Active Milestones

| Milestone | Workstream | Progress | Status | Resumption Point |
|-----------|-----------|----------|--------|-----------------|
| v1.4 ADV Bronze-To-Silver Backfill | neo4j-pipe | 33% | Phase 8 verification pending | Phase 8: ADV Bronze Discovery Contract verification |
| v1.2 MDM Neo4j Review Dashboard | mdm-neo4j-dashboard | 60% | Phase 10 ready to execute | Phase 10 UI-SPEC approved |
| v1.3 Neo4j Snowflake Native App | neo4j-snowflake | 50% | Phase 3 ready to plan | Phase 3: Hosted Graph Verification + E2E |
| Model Builder Contract Gaps | model-builder-contract-gaps | 0% | Phase 1 ready to start | Phase 1: Contract Governance |

---

## Completed Workstreams

### fix-pipelines v1.0 (2026-05-16)
4 phases · 6 plans — Pipeline Observability
- Phase 1: Failure Surfacing ✓
- Phase 2: Status Completeness ✓
- Phase 3: Failure Notifications ✓
- Phase 4: SEC Rate Limiting ✓
Archive: .planning/workstreams/fix-pipelines/milestones/v1.0-ROADMAP.md

### Fundamentals + Stage1Parallel — PRs 1–3 (merged to main, 2026-05-29 – 2026-05-31)

**PR-2 (#31) — Branch B silver + 3 MDM relationships + 6 dbt gold models**
- Branch B silver pipeline (separate `silver/fundamentals/` DuckDB namespace — AD-05)
  - `per-filing` mode: 8-K earnings releases + DEF 14A proxy filings
  - `entity-facts` mode: SEC `/api/xbrl/companyfacts/` JSON (CIK-level XBRL facts)
  - `thirteenf` mode: 13F-HR INFORMATION TABLE XML attachments
- 6 new silver tables: `sec_earnings_release`, `sec_executive_record`, `sec_financial_fact`,
  `sec_accounting_flag`, `sec_financial_derived`, `sec_thirteenf_holding`
- 3 new MDM relationship types derived from silver
- 6 new dbt gold models: `accounting_flags`, `earnings_releases`, `executive_records`,
  `financial_derived`, `financial_facts`, `institutional_holdings`
- Forensic scoring: Beneish M / Altman Z / Piotroski F via `accounting_flags.py`
- Snowflake DDL: `06_fundamentals_load_wrapper.sql`

**PR-1 (#33) — Snowflake DDL + verify-pr1 harness**
- `01_source_stage.sql` DDL for Snowflake source stage
- verify-pr1: 39/39 local schema checks + 32/32 builder smoke checks ✓

**PR-3 (#39) — Stage1Parallel Branch B orchestration + verify-pr3**
- `load_history` Step Function: Stage1Parallel (Type=Parallel, ResultPath=null, Next=MdmRun)
  Branch A: bootstrap-next (ownership/ADV) — MaxConcurrency=1
  Branch B: bootstrap-fundamentals per-filing → entity-facts (sequential, States.ALL Catch)
- `--cik-offset` / `--cik-limit` on `bootstrap-fundamentals`; mirrors Branch A MDM windowing
- `silver_store.py`: added `SilverDatabase.fetch()` for API parity with ShardedSilverReader
- verify-pr3: 29/29 ASL structural checks + 9/9 CLI/windowing smoke checks ✓

### Neo4j Snowflake Native App — Phases 1–2 (Codex, PRs #29 #30 #35)
Phase 1 (feasibility + architecture decision) and Phase 2 (graph sync contract + CLI wiring)
complete. Phase 3 (hosted graph verification + E2E cutover) ready to plan.

---

## Current Gold Layer State

**15 dbt gold dynamic tables + 1 status view** in `EDGARTOOLS_GOLD`:

| Table | Source | Added |
|-------|--------|-------|
| `company` | MDM | original |
| `ticker_reference` | MDM | original |
| `filing_activity` | ownership/ADV bronze | original |
| `filing_detail` | ownership bronze | original |
| `ownership_activity` | ownership silver | original |
| `ownership_holdings` | ownership silver | original |
| `adviser_disclosures` | ADV silver | original |
| `adviser_offices` | ADV silver | original |
| `private_funds` | ADV silver | original |
| `earnings_releases` | fundamentals silver | PR-2 |
| `executive_records` | fundamentals silver | PR-2 |
| `financial_facts` | fundamentals silver | PR-2 |
| `financial_derived` | fundamentals silver | PR-2 |
| `accounting_flags` | fundamentals silver | PR-2 |
| `institutional_holdings` | fundamentals silver | PR-2 |
| `edgartools_gold_status` (view) | all | original |

---

## Pipeline Architecture (current, post-PR-3)

```
Stage 1: Stage1Parallel (Parallel state, MaxConcurrency=1 per branch)
  Branch A: bootstrap-next (ownership/ADV)         → silver/ownership/
  Branch B: bootstrap-fundamentals per-filing       → silver/fundamentals/
             → bootstrap-fundamentals entity-facts  (sequential within branch)

Stage 2: MDM (sequential)
  mdm-run → mdm-backfill-relationships → mdm-sync-graph → mdm-verify-graph

Stage 3: Gold refresh (single ECS task)
  gold-refresh → dbt dynamic tables (15 + status view)
```

---

## Active Worktrees

| Branch | Path | Runtime | Workstream | Status |
|--------|------|---------|-----------|--------|
| main | /Users/aneenaananth/projects/edgartools-platform | Claude | — | active |
| workspace/mdm-neo4j-dashboard | /Users/aneenaananth/gsd-workspaces/mdm-neo4j-dashboard/edgartools-platform | paused | mdm-neo4j-dashboard | stopped at Phase 10 |

> REGISTRY.md (to be created) is the live ownership table for concurrent worktrees.

---

## Repository Policy

- **`edgartools` is read-only** — never commit to it. All work goes in `edgartools-platform`.
- See `.planning/COORDINATION.md` for multi-agent isolation rules (Claude + Codex).
- See `.planning/REGISTRY.md` for live worktree ownership (to be created).

## Accumulated Context

### Locked Decisions (key)

- DEC-004: silver_mdm_gold map MUST pass `--artifact-policy skip` to bootstrap-batch
- DEC-009: SEC artifacts are additive/immutable — loaders skip by default
- DEC-002/DEC-003: bootstrap-batch NOT in GOLD_AFFECTING_COMMANDS; gold-refresh IS
- DEC-019: Claude and Codex must use isolated git worktrees + GSD workstream dirs
- (NEW) edgartools is read-only — never commit to it

### Documentation Debt

- CLAUDE.md Quick Navigation still says "8 dynamic tables" — now 15 + status view
- README.md install example uses bare pip — should be updated to uv commands
- Terraform CLI version pin differs between AWS roots (1.14.7) and Snowflake roots (1.14.8)
