# Phase 4: Operator Dashboard And Data Issue Triage - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 04-operator-dashboard-and-data-issue-triage
**Areas discussed:** NEO4J_* cleanup ownership, Triage guide scope, Dashboard UAT environment

---

## NEO4J_* Cleanup Ownership

**Background:** `neo4j-snowflake` workstream Phase 4 Plan 03 (`04-03-PLAN.md`) is written but unexecuted. It removes `NEO4J_*` external graph setup instructions from `examples/mdm_graph_dashboard/README.md` and creates a verification checklist. Launch gate matrix row 27 classifies this as launch-blocking.

### Q1: How should Phase 4 handle 04-03-PLAN.md?

| Option | Description | Selected |
|--------|-------------|----------|
| Execute it inside Phase 4 | Phase 4 go-live includes a plan that runs 04-03's two tasks (README rewrite + verification checklist) as part of go-live scope. Crosses workstream boundary but clears the BLOCKED row cleanly. | ✓ |
| Prerequisite — run it first | User executes 04-03 separately in the neo4j-snowflake workstream before Phase 4 begins. Phase 4 starts with a clean README and just records the recheck evidence. | |
| Document BLOCKED, proceed in parallel | Phase 4 proceeds with existing README state. Row 27 stays BLOCKED. Phase 5 checks whether row 27 has cleared. | |

**User's choice:** Execute it inside Phase 4
**Notes:** This is the "unless a later phase explicitly scopes source-code or runbook edits" exception to go-live workstream isolation.

### Q2: Which branch do the commits land on?

| Option | Description | Selected |
|--------|-------------|----------|
| workspace/go-live | All go-live Phase 4 commits land on workspace/go-live. neo4j-snowflake workstream stays untouched. | ✓ |
| workspace/neo4j-snowflake | README rewrite commits to the neo4j-snowflake branch. Requires branch switching mid-phase. | |

**User's choice:** workspace/go-live

### Q3: Run architecture tests as gate?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — tests must pass | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` is the automated gate after README rewrite. | ✓ |
| No — docs only | Treat as documentation work only. Arch tests stay as-is. | |

**User's choice:** Yes — tests must pass

### Q4: Standalone plan or bundled with UAT?

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone plan, Wave 1 | 04-01 = README rewrite + arch tests. Must complete before UAT plans can start. | ✓ |
| Bundle with UAT plan | One plan covers README rewrite + UAT in sequence. | |

**User's choice:** Standalone plan, Wave 1

---

## Triage Guide Scope

**Background:** DASH-02 requires a "one-stop data issue workflow" classifying 8 layers. Launch gate matrix rows 90-100 have an existing triage table but it's at a high level. No new runbook document currently exists for this.

### Q1: What form should the DASH-02 triage guide take?

| Option | Description | Selected |
|--------|-------------|----------|
| New runbook/data-issue-triage.md | New file in go-live Phase 4 runbook directory. Operator-facing with symptoms, CLI commands, owner, escalation. | ✓ |
| Extend existing matrix table | Add symptom triggers and dashboard links to existing matrix rows 90-100. | |
| You decide | Claude picks. | |

**User's choice:** New runbook/data-issue-triage.md

### Q2: Include CLI commands per layer?

| Option | Description | Selected |
|--------|-------------|----------|
| Include CLI commands | Each layer entry includes 1-2 diagnostic CLI commands. Operator can follow guide start-to-finish. | ✓ |
| Symptom and owner only | Triage guide lists symptoms/owner/escalation only; points to other docs for commands. | |

**User's choice:** Include CLI commands

### Q3: Where does the triage guide live?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 4 runbook dir | `.planning/workstreams/go-live/phases/04-.../runbook/data-issue-triage.md` — same pattern as Phase 3's runbook/mdm-secrets.md. | ✓ |
| docs/ in repo root | `docs/runbooks/data-issue-triage.md` — permanent doc outside planning tree. | |
| You decide | Claude picks. | |

**User's choice:** Phase 4 runbook dir

### Q4: Cover all 8 DASH-02 layers or launch-critical subset?

| Option | Description | Selected |
|--------|-------------|----------|
| All 8 layers | Complete coverage: ingestion, bronze/silver, MDM, hosted graph, dbt/gold, Native App, dashboard, permissions. | ✓ |
| Launch-critical subset only | Focus on MDM, hosted graph, dbt/gold, Native App. Defer others. | |

**User's choice:** All 8 layers

---

## Dashboard UAT Environment

**Background:** DASH-01 requires "production or production-like read-only config." Dashboard has two data sources: MDM Postgres (via Secrets Manager) and Snowflake hosted graph (via MDM_SNOWFLAKE_* or SNOWFLAKE_CONNECTION). Phase 3 already re-verified dev MDM Postgres connectivity.

### Q1: Which environment config for Phase 4 dashboard UAT?

| Option | Description | Selected |
|--------|-------------|----------|
| Dev secrets, dev Snowflake | MDM_DATABASE_URL from dev Secrets Manager + dev Snowflake connection. Record as "dev precedent only — prod proof required separately." | ✓ |
| Prod Snowflake required | UAT must use prod Snowflake. Blocked by prod secrets not yet populated. | |
| Either — document which was used | Accept dev or prod; template records which was tested. | |

**User's choice:** Dev secrets, dev Snowflake

### Q2: Fill existing Phase 1 template or create new UAT file?

| Option | Description | Selected |
|--------|-------------|----------|
| Fill existing Phase 1 template | Populate 5 pending rows in evidence/dashboard-security.md. Same pattern as Phase 3 using evidence/mdm-hosted-graph.md. | ✓ |
| New Phase 4 UAT file | Separate evidence file in Phase 4 directory. | |

**User's choice:** Fill existing Phase 1 template

### Q3: Live launch or documentation-only?

| Option | Description | Selected |
|--------|-------------|----------|
| Live launch + text UAT notes | Operator runs streamlit locally with dev credentials, inspects each view, records pass/fail text notes. | ✓ |
| Documentation-only | UAT rows filled based on known behavior. No live dashboard launch. | |

**User's choice:** Live launch + text UAT notes

---

## Claude's Discretion

None — user made explicit choices for all gray areas.

## Deferred Ideas

- Prod Snowflake dashboard UAT — deferred to Phase 5 or post-launch.
- Managed dashboard deployment (Snowflake-in-Streamlit) — out of scope per REQUIREMENTS.md.
- Historical trend views — future requirement.
- External Neo4j deprecation (beyond README cleanup) — future requirement.
