---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: fix-pipelines — Pipeline Data-Source Completeness & Verification
current_phase: 5
current_phase_name: node-and-populated-relationship-graph-parity
status: planning
stopped_at: Requirements (26, across NODE/EDGE/GVER/ARTF/EDGX) and ROADMAP.md (phases 5-9)
  written and committed. Ready for /gsd-discuss-phase 5 or /gsd-plan-phase 5.
last_updated: "2026-07-08T00:00:00.000Z"
last_activity: 2026-07-08 -- Milestone v2.0 defined via /gsd-new-milestone. v1.0 (Pipeline
  Observability) is archived below and in milestones/v1.0-*.
---

# Project State — fix-pipelines

## Current Position

Phase: 5 (Node And Populated-Relationship Graph Parity) — not started
Plan: none yet
Status: Roadmap approved; ready to plan Phase 5
Last activity: 2026-07-08 -- v2.0 requirements + roadmap committed

[                              ] 0% (0/5 phases complete)

## Milestone Context

**v2.0 fix-pipelines — Pipeline Data-Source Completeness & Verification**

Goal: Every MDM node type and relationship type is either verified-populated or has a written,
evidenced source-coverage exclusion traced to its actual source artifact (or explicit absence
of one); Neo4j Native App verification cleanly separates readiness from parity failures;
platform parsing is cross-checked against edgartools.

Requirements: NODE-01..06, EDGE-01..11, GVER-01..03, ARTF-01..02, EDGX-01..03 (26 total, see
REQUIREMENTS.md)

## Phase Summary

| Phase | Goal | Requirements | Status |
|-------|------|--------------|--------|
| 5 — Node And Populated-Relationship Graph Parity | All 6 node types + 4 populated relationship types verified, idempotency established | NODE-01..06, EDGE-01..04, GVER-03 | Not started |
| 6 — Relationship Investigation And Population | Root-cause + populate the 5 ambiguous zero relationship types against their actual artifacts | EDGE-05, 06, 09, 10, 11 | Not started |
| 7 — Source-Coverage Exclusions And Artifact Hygiene | Document the 2 artifact-confirmed exclusions; fix silver-clobber + fetch-idempotency | EDGE-07, 08, ARTF-01, 02 | Not started |
| 8 — Neo4j Native App Verification Gaps | verify-graph separates readiness vs parity; GRAPH_INFO/BFS/LIST_GRAPHS resolved or documented | GVER-01, 02 | Not started |
| 9 — edgartools Crosscheck | Validate platform parsing vs edgartools; replace parsers where it's a clear win; audit API usage | EDGX-01..03 | Not started |

## Progress

**Phases Complete:** 0/5
**Current Plan:** none yet — next step is `/gsd-discuss-phase 5` or `/gsd-plan-phase 5`

## Session Continuity

**Stopped At:** Milestone v2.0 initialized 2026-07-08 (requirements + roadmap committed on
`claude/fix-pipelines-v2`). Not yet planned or executed.
**Resume File:** None

## Accumulated Context

### Active Decisions

- Artifact triage is embedded per-relationship (EDGE-05..11) rather than as a separate generic
  audit, so each zero relationship type's source artifact (or explicit absence of one) is
  traceable — user-directed adjustment during milestone setup (2026-07-08).
- AUDITED_BY (EDGE-10) and any fundamentals-pipeline work must coordinate with the active
  `fundamental-factors-v2` workstream (Codex) — do not run fundamentals in dev without checking
  for overlap first.
- MANAGES_FUND (EDGE-07) is a confirmed dead end from EDGAR: all 30 ADV filings in the active
  universe are paper filings with no electronic document. See
  `.planning/workstreams/claude-mdm-source-recovery/FINDINGS.md`.
- This workstream continues phase numbering from v1.0 (ended at Phase 4) — v2.0 starts at
  Phase 5, per default (non-reset) numbering behavior.

### Blockers

- Phase 6 EDGE-10 (AUDITED_BY) is blocked on a fundamentals entity-facts run landing in the
  unified `silver/sec/silver.duckdb` — external dependency on `fundamental-factors-v2` timing.

### Roadmap Evolution

None yet — roadmap just created.

### Pending Todos

None yet.

---

## Archived: v1.0 Pipeline Observability (complete 2026-05-16)

Full archive: `milestones/v1.0-ROADMAP.md`, `milestones/v1.0-REQUIREMENTS.md`,
`milestones/v1.0-phases/`.

All 4 phases shipped: Failure Surfacing, Status Completeness, Failure Notifications, SEC Rate
Limiting. Pipeline failures surface as hard Step Functions FAILED states, `status.sh` covers all
5 state machines, operators receive SNS email within 60 seconds of failure, SEC EDGAR calls are
rate-limited to 9 req/sec per ECS task. One known low-severity residual gap: the live-behavior
test script for OBS-01 (`scripts/ops/test-failure-surfacing.sh`) has its own injection-mechanism
race condition — definition-level verification is complete, runtime re-test tooling was never
redesigned.
