---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Neo4j bronze-to-graph pipe
status: executing
last_updated: "2026-05-17T10:18:38Z"
last_activity: 2026-05-17
---

# Project State — neo4j-pipe

## Current Position

Phase: 5 of 7 (Source To MDM Load Path)
Plan: 3 of 4 complete in current phase
Status: Ready to execute
Last activity: 2026-05-17
Resume file: None

## Milestone Context

**v1.1 Neo4j bronze-to-graph pipe**

Goal: Fix the path from already-captured bronze/silver data through MDM relationship derivation
into Neo4j so graph sync is complete, idempotent, and independently verifiable.

## Phase Summary

| Phase | Goal | Requirements | Status |
|-------|------|--------------|--------|
| 5 — Source To MDM Load Path | Existing silver data can populate MDM entities without loader overlap | PIPE-01, PIPE-02, PIPE-03, ISO-01, ISO-02 | Not started |
| 6 — Relationship Derivation Coverage | Graph relationships are fully derived into MDM rows | REL-01, REL-02, REL-03, REL-04 | Not started |
| 7 — Neo4j Sync And Verification | Neo4j sync and verification are idempotent and diagnostic | GRAPH-01, GRAPH-02, GRAPH-03, GRAPH-04 | Not started |

## Accumulated Context

### Decisions

- Use the isolated git worktree at `/Users/aneenaananth/gsd-workspaces/neo4j-pipe/edgartools-platform`.
- Do not edit loader-fix workstream artifacts or generated deployment JSON from this worktree.
- Keep scope to bronze/silver → MDM → Neo4j. Gold refresh, generic Step Functions observability, and unrelated loader refactors are out of scope.
- Phase 5 context confirms that missing ownership relationships should be repaired independently by parsing already-captured bronze Form 3/4/5 XML into silver ownership tables before MDM/Neo4j derivation.
- Plan 05-01: RED tests anchor to known current defects — form_type/period_of_report schema mismatch, _session() called before _silver_reader(), sec_tracked_universe stale reference.
- Plan 05-01: parse_ownership patched at edgar_warehouse.parsers.ownership (function-local import pattern); FakeSilverDB records raw SQL for schema assertion without DuckDB execution.
- Plan 05-01: 3 of 15 MDM tests intentionally pass current code (ftp/http rejection, s3 read_bytes delegation) — these verify existing correct behaviors.
- Plan 05-03: _require_silver_reader() runs before _session() in all three mutation handlers; _validate_silver_tables() uses fixed allowlist constants only (T-05-14/T-05-15 mitigated).
- Plan 05-03: sec_tracked_universe stale reference fixed to sec_company_sync_state in pipeline.py run_companies() (D-12).
- Plan 05-03: TestEntityLoadIdempotentForDomainCounts deferred to 05-04 (SQLite Date/FundResolver compatibility issue).

### Blockers

None known.

### Pending Todos

None.
