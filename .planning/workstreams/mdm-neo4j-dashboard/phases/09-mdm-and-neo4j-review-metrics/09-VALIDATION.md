---
phase: 09
slug: mdm-and-neo4j-review-metrics
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-20
---

# Phase 09 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest via uv |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q` |
| **Full suite command** | `uv run pytest tests/mdm tests/architecture -q` |
| **Estimated runtime** | ~60 seconds focused, ~90 seconds full excluding live-Neo4j credential failures |

---

## Sampling Rate

- **After every task commit:** Run the focused test file touched by that task.
- **After every plan wave:** Run `uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q`.
- **Before `$gsd-verify-work`:** Full focused Phase 9 suite must be green.
- **Max feedback latency:** 90 seconds for focused feedback.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | MDM-01 | T-09-01 | MDM entity count helpers perform SELECT-only reads and return all five domains | unit | `uv run pytest tests/mdm/test_dashboard_readonly.py -q` | existing | pending |
| 09-01-02 | 01 | 1 | MDM-02 | T-09-02 | Relationship count helpers include all active registry types and pending sync counts without committing | unit | `uv run pytest tests/mdm/test_dashboard_readonly.py -q` | existing | pending |
| 09-01-03 | 01 | 1 | MDM-03 | T-09-03 | Readiness warnings classify missing registry data, sparse counts, pending sync, and unavailable sources without secrets | unit | `uv run pytest tests/mdm/test_dashboard_readonly.py -q` | existing | pending |
| 09-02-01 | 02 | 1 | GRAPH-01 | T-09-04 | Neo4j count helpers use registry-validated labels/types and read-only Cypher only | unit | `uv run pytest tests/mdm/test_graph_readonly.py -q` | existing | pending |
| 09-02-02 | 02 | 1 | GRAPH-03 | T-09-05 | Graph diagnostic helpers calculate missing/extra counts and keep sample Cypher bounded/read-only | unit + static | `uv run pytest tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q` | existing | pending |
| 09-03-01 | 03 | 2 | GRAPH-02 | T-09-06 | Pending sync samples are per-type bounded, globally capped, and ordered by registry/type and age | unit | `uv run pytest tests/mdm/test_dashboard_readonly.py -q` | existing | pending |
| 09-03-02 | 03 | 2 | MDM-01, MDM-02, GRAPH-01, GRAPH-03 | T-09-07 | Streamlit renders metrics and warnings from structured helper outputs without SQL/Cypher or mutation controls | static/import | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` | existing | pending |

*Status: pending -> green/red during execution.*

---

## Wave 0 Requirements

- [ ] `tests/mdm/test_dashboard_readonly.py` includes Phase 9 tests for entity counts, relationship counts, zero registered relationship rows, readiness warnings, bounded pending samples, no commits, and secret-safe failures.
- [ ] `tests/mdm/test_graph_readonly.py` includes Phase 9 tests for node counts by label, edge counts by type, label/type validation, unavailable Neo4j partial state, bounded sample query calls, and no write tokens.
- [ ] `tests/architecture/test_dashboard_foundation_boundaries.py` scans all Phase 9 helper and dashboard targets for mutation imports, write Cypher, forbidden controls, generated deployment JSON, Terraform, Step Functions, Snowflake/dbt, and rollout path references.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live dashboard metric render with a real MDM database | MDM-01, MDM-02, MDM-03 | Requires operator-provided `MDM_DATABASE_URL` and browser inspection | Run `uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py`, open the dashboard, refresh metrics, and confirm MDM counts/warnings render without secrets. |
| Optional live Neo4j metric state | GRAPH-01, GRAPH-03 | Requires operator-provided Neo4j credentials/network | Launch with valid Neo4j env vars and confirm node/edge counts and graph coverage render; launch without or invalid Neo4j and confirm MDM metrics remain usable with safe Neo4j unavailable copy. |

---

## Validation Sign-Off

- [ ] All tasks have automated verify commands or Wave 0 test dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify.
- [ ] Wave 0 covers all Phase 9 missing test references.
- [ ] No watch-mode flags.
- [ ] Feedback latency < 90s for focused commands.
- [ ] `nyquist_compliant: true` set in frontmatter after green execution evidence.

**Approval:** pending
