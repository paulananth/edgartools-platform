---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: ADV Bronze-To-Silver Backfill
status: planned
last_updated: "2026-06-03T00:00:00-04:00"
last_activity: 2026-06-03 -- Phase 8 planned
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 1
  completed_plans: 0
  percent: 0
---

# Project State — neo4j-pipe

## Current Position

Phase: 8 (ADV Bronze Discovery Contract) - PLANNED
Plan: 1 of 1
Status: Ready to execute Phase 8
Last activity: 2026-06-03 -- Phase 8 planned
Resume file: None

## Milestone Context

**v1.4 ADV Bronze-To-Silver Backfill**

Goal: Add a safe operator path that parses already-downloaded ADV bronze artifacts into silver
ADV tables without SEC re-fetch, unblocking the MDM adviser/fund load path.

## Phase Summary

| Phase | Goal | Requirements | Status |
|-------|------|--------------|--------|
| 8 — ADV Bronze Discovery Contract | Existing ADV bronze artifacts can be discovered and selected without SEC calls | ADV-01, ADV-02, ADV-03, ISO-01, ISO-02, ISO-03 | Ready to execute |
| 9 — Parse ADV Bronze Command | A bounded idempotent command parses ADV bronze into silver ADV tables | ADV-04, ADV-05, ADV-06, ADV-07 | Not started |
| 10 — Live ADV Backfill Validation | Dev S3 validation proves ADV silver rows and MDM adviser/fund readiness | MDM-ADV-01, MDM-ADV-02, MDM-ADV-03 | Not started |

## Accumulated Context

### Decisions

- Use the isolated git worktree at `/Users/aneenaananth/gsd-workspaces/neo4j-pipe/edgartools-platform`.
- Preserve v1.1 `neo4j-pipe` phase directories and reports as historical context; v1.4 continues phase numbering at Phase 8.
- Keep the backfill AWS/local only: existing S3/local bronze artifacts in, silver ADV tables out.
- Do not fetch missing ADV artifacts from SEC during this milestone.
- Prefer registry-backed reads (`sec_filing_attachment` + `sec_raw_object`) when available, but include an explicit bounded fallback for existing bronze object paths because the live blocker is "bronze exists, no silver path."
- Reuse `edgar_warehouse.parsers.adv` and `SilverDatabase.merge_adv_*` rather than adding a new ADV parser.
- Keep the workstream isolated from loader-fix artifacts, generated deployment JSON, gold/dbt, Snowflake graph sync, and generic Step Functions work.
- Phase 8 plans discovery/read helper code only; `parse-adv-bronze` CLI registration and ADV silver merges are Phase 9.

### Blockers

- v1.1 Phase 5 live checkpoint remains paused until ADV bronze can be backfilled into `sec_adv_filing` and `sec_adv_private_fund`.

### Pending Todos

None.
