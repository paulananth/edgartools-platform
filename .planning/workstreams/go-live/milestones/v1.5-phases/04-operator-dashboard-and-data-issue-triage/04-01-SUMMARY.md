---
phase: 04-operator-dashboard-and-data-issue-triage
plan: "01"
subsystem: dashboard-runbook
tags: [readme, architecture-test, snowflake-hosted-graph, mdm]
dependency_graph:
  requires: []
  provides: [DASH-03-readme-contract, DASH-01-runbook-updated]
  affects: [tests/architecture/test_dashboard_foundation_boundaries.py]
tech_stack:
  added: []
  patterns: [assert-absent-pattern mirrored from streamlit test]
key_files:
  created: []
  modified:
    - examples/mdm_graph_dashboard/README.md
    - tests/architecture/test_dashboard_foundation_boundaries.py
decisions:
  - "Remove NEO4J_* from README and assertIn loop; add assert-absent block mirroring streamlit test pattern (lines 425-447)"
  - "allowed_commands updated to exactly {counts, verify-graph} per new Existing checks section"
  - "Atomic single commit — README and test changed together to avoid broken intermediate state"
metrics:
  duration: "~10 minutes"
  completed: "2026-06-17T00:03:02Z"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 2
---

# Phase 04 Plan 01: Dashboard README Snowflake-hosted graph rewrite Summary

**One-liner:** Rewrote MDM Graph Dashboard README to remove active external NEO4J_* / Bolt / Aura / check-connectivity setup, replacing with Snowflake-hosted Neo4j Graph Analytics prerequisites, and flipped the architecture test contract to enforce the post-rewrite README.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewrite dashboard README and flip arch test contract | e5865ba | examples/mdm_graph_dashboard/README.md, tests/architecture/test_dashboard_foundation_boundaries.py |

## Acceptance Criteria Results

| Criterion | Result |
|-----------|--------|
| `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` exits 0 | PASS (24 passed) |
| grep for NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_SECRET_JSON, bolt://, neo4j://, Aura, check-connectivity --neo4j in README returns 0 | PASS (0 matches) |
| README contains `Neo4j Overview` | PASS |
| README contains `verify-graph` | PASS |
| README `Existing checks` yields exactly `{edgar-warehouse mdm counts, edgar-warehouse mdm verify-graph}` | PASS |
| All 9 headings preserved in order | PASS (Purpose, Read-only guarantee, Prerequisites, Launch, Review workflow, Filters, Failure states, Existing checks, Validation) |
| streamlit_app.py, graph_readonly.py, dashboard_readonly.py unmodified | PASS (git diff shows only README.md + test file) |

## Deviations from Plan

None — plan executed exactly as written. One minor issue auto-resolved during execution: initial README draft included the word "Aura" (in "Bolt or Aura connection") which triggered the grep gate. Fixed by replacing with "external graph database connection" before running tests.

## Decisions Made

1. **Atomic commit:** README and test edited in a single commit (`e5865ba`) to prevent any broken intermediate state where the old test requires NEO4J_* tokens that the new README no longer contains.

2. **Assert-absent pattern:** The new assert-absent block in `test_d13_d14_d15_d16_readme_contract_matches_operator_runbook` mirrors the existing streamlit copy test at lines 425-447 — first strips the allowed `Neo4j Overview` route label and `Snowflake-hosted Neo4j Graph Analytics` copy, then asserts forbidden tokens absent.

3. **MDM_DATABASE_URL env-var loop:** Reduced to a single-element tuple `("MDM_DATABASE_URL",)` — the five NEO4J_* vars removed from the assertIn loop and added to the assert-absent block instead.

4. **Documentation-text references:** `verify-graph`, `neo4j_graph_analytics_app_grants.sql`, and `run-aws-mdm-e2e.sh` referenced as inline/backtick text only — never as standalone `edgar-warehouse mdm` code-block lines, which would have been captured by the mdm_commands regex and broken the `assertEqual`.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Changes are documentation (README.md) and test assertions only. Threat model mitigations T-04-01-01 and T-04-01-02 verified:
- T-04-01-01 (Information Disclosure): Secret-safe MDM_DATABASE_URL load block preserved with `--query SecretString --output text`; no DSNs or passwords in README.
- T-04-01-02 (Tampering): README documents only read-only acceptance-gate commands; `test_dashboard_text_contains_no_mutation_controls` stays green.
- T-04-01-03 (Repudiation): README and test changed atomically; passing test run is proof the post-rewrite contract holds.

## Self-Check: PASSED

- [x] `examples/mdm_graph_dashboard/README.md` exists and was modified
- [x] `tests/architecture/test_dashboard_foundation_boundaries.py` exists and was modified
- [x] Commit `e5865ba` exists: `git log --oneline | head -1` confirms `e5865ba docs(04-01): rewrite dashboard README for Snowflake-hosted graph; flip arch test contract`
- [x] `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` → 24 passed
- [x] Grep gate → 0 forbidden matches in README
- [x] `git diff --name-only HEAD~1 HEAD` shows exactly 2 source files changed (README.md + test file)
- [x] No accidental file deletions in commit
