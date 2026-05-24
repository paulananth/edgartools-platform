---
phase: 10
slug: operator-review-experience
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-23
---

# Phase 10 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` |
| **Full suite command** | `uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q`
- **After every plan wave:** Run `uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 10-01 | 1 | GRAPH-01, UX-01 | T-10-01 | Entity-domain Neo4j counts use registry labels, not display-label guessing | architecture regression | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` | yes | pending |
| 10-01-02 | 10-01 | 1 | UX-01 | T-10-02 | Primary navigation exposes review-first views and removes stale placeholder labels | architecture regression | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` | yes | pending |
| 10-02-01 | 10-02 | 1 | UX-02 | T-10-03 | Row limit is bounded to 25/50/100/250 with default 50 | architecture regression | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` | yes | pending |
| 10-02-02 | 10-02 | 1 | UX-02 | T-10-04 | Page filters are single-select with All default and no free-form operator input | architecture regression | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` | yes | pending |
| 10-03-01 | 10-03 | 2 | UX-03 | T-10-05 | Missing MDM is blocking; Neo4j unavailable is non-blocking and secret-safe | architecture regression | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` | yes | pending |
| 10-03-02 | 10-03 | 2 | UX-03 | T-10-06 | Empty filtered tables use neutral copy and do not imply success or failure | architecture regression | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` | yes | pending |
| 10-04-01 | 10-04 | 2 | UX-01, UX-02, UX-03 | T-10-07 | Runbook documents workflow, env vars, read-only guarantee, filters, existing check commands, and focused tests | documentation regression | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q` | yes | pending |

*Status: pending, green, red, flaky*

---

## Wave 0 Requirements

- [ ] Convert `DashboardFoundationBoundaryTests.test_entity_comparison_uses_registry_labels_for_neo4j_node_counts` from expected failure to passing regression.
- [ ] Add architecture assertions for final navigation labels: `Overview`, `MDM Overview`, `Neo4j Overview`, `Mismatch Diagnostics`.
- [ ] Add architecture assertions for bounded row-limit choices `25`, `50`, `100`, `250` and default `50`.
- [ ] Add architecture assertions for page-specific single-select filters with `All` default where statically checkable.
- [ ] Add architecture assertions for neutral filtered-empty copy: `No rows match the current filters.`
- [ ] Add README assertions for guided workflow, read-only guarantee, existing check-command references, and focused test command.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Local browser visual density and Streamlit rendering polish | UX-01, UX-02, UX-03 | Streamlit visual layout is not covered by current browser automation | Optional operator review after implementation: launch with `uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py` and inspect the four primary views. |

---

## Validation Sign-Off

- [ ] All tasks have automated verify commands or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all missing references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30 seconds
- [ ] `nyquist_compliant: true` set in frontmatter after validation passes

**Approval:** pending
